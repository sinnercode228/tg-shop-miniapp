from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any

import pytest
from aiogram import Bot
from aiogram.methods import RefundStarPayment
from aiogram.methods.base import TelegramMethod, TelegramType
from aiogram_stars import PaymentStatus, RefundPolicy, RefundStatus
from aiogram_stars.sqlalchemy import SqlAlchemyStorage
from pydantic import ValidationError
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

import tgshop.container
from tgshop.bot.factory import create_dispatcher
from tgshop.bot.handlers.payments import create_stars
from tgshop.config import Settings
from tgshop.container import build_container, refund_policy
from tgshop.db.session import SessionFactory, init_models
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderStatus
from tgshop.domain.errors import InvalidTransition
from tgshop.domain.pricing import PricingRules
from tgshop.domain.schemas import OrderCreate, OrderOut
from tgshop.services.orders import Customer, OrderService
from tgshop.services.refunds import RefundOut

from .conftest import (
    ADMIN_ID,
    BOT_TOKEN,
    STARS_SECRET,
    USER_ID,
    WEBAPP_URL,
    Clock,
    FakeNotifier,
    FakePayments,
    RecordingSession,
    Telegram,
    add_refund_fails_once,
    make_stars,
    order_payload,
    run_after_next_read,
)

CUSTOMER = Customer(user_id=USER_ID, language="ru")
ALREADY_CANCELLED = "Заказ уже оплачен или отменён"


async def stars_order(service: OrderService) -> OrderOut:
    data = OrderCreate.model_validate(order_payload(paymentMethod="stars"))
    return (await service.place_order(CUSTOMER, data)).order


async def pay(service: OrderService, order: OrderOut, charge_id: str) -> OrderOut:
    return await service.mark_paid(
        order_id=order.id,
        total_amount=order.stars_amount or 0,
        payer_id=USER_ID,
        charge_id=charge_id,
    )


async def cancelled_order(service: OrderService) -> OrderOut:
    return await service.change_status((await stars_order(service)).id, OrderStatus.CANCELLED)


async def test_refund_that_fails_twice_goes_through_on_the_third_attempt(
    service: OrderService,
    telegram: Telegram,
    session: RecordingSession,
    clock: Clock,
    notifier: FakeNotifier,
) -> None:
    order = await cancelled_order(service)
    payment = await telegram.pay(order, "late-charge")
    assert (payment.status, payment.order_id, payment.amount) == (
        PaymentStatus.REJECTED,
        str(order.id),
        order.stars_amount,
    )
    assert telegram.refunds == [], "the update handler leaves the Bot API call to the outbox"
    session.fail_next(RefundStarPayment, TimeoutError("no answer"), RuntimeError("Bad Gateway"))

    [first] = await telegram.send_refunds()
    assert (first.status, first.attempts) == (RefundStatus.PENDING, 1)
    assert first.last_error == "TimeoutError: no answer"
    assert first.next_attempt_at == clock.now + timedelta(seconds=30)
    clock.advance(seconds=29)
    assert await telegram.send_refunds() == [], "the first retry waits 30 s"

    clock.advance(seconds=1)
    [second] = await telegram.send_refunds()
    assert (second.status, second.attempts) == (RefundStatus.PENDING, 2)
    assert second.next_attempt_at == clock.now + timedelta(seconds=60), "each wait doubles"
    assert notifier.returned == [], "the customer hears nothing until the Stars are back"

    clock.advance(seconds=60)
    [third] = await telegram.send_refunds()

    assert (third.status, third.attempts) == (RefundStatus.DONE, 3)
    assert (third.charge_id, third.reason) == ("late-charge", ALREADY_CANCELLED)
    assert telegram.refunds == [(USER_ID, "late-charge")]
    assert notifier.returned == [(USER_ID, ALREADY_CANCELLED)]
    assert notifier.failed_refunds == []
    clock.advance(days=1)
    assert await telegram.send_refunds() == [], "a refund that went through is not sent again"


async def test_refund_that_keeps_failing_ends_failed_and_tells_the_admins(
    service: OrderService,
    telegram: Telegram,
    session: RecordingSession,
    clock: Clock,
    notifier: FakeNotifier,
) -> None:
    order = await pay(service, await stars_order(service), "charge-1")
    refunded = await service.change_status(order.id, OrderStatus.REFUNDED)
    assert refunded.status is OrderStatus.REFUNDED
    session.fail_next(RefundStarPayment, *(RuntimeError("Telegram is down") for _ in range(3)))

    for wait in (0, 30, 60):
        clock.advance(seconds=wait)
        [refund] = await telegram.send_refunds()

    assert refund.status is RefundStatus.FAILED
    assert refund.attempts == 3
    assert refund.last_error == "RuntimeError: Telegram is down"
    assert notifier.failed_refunds == [
        RefundOut(
            order_id=order.id,
            user_id=USER_ID,
            amount=order.stars_amount or 0,
            charge_id="charge-1",
            reason=None,
            status=RefundStatus.FAILED,
            attempts=3,
            last_error="RuntimeError: Telegram is down",
        )
    ], "the admins are told"
    assert notifier.refunded == [], "the customer is not told the Stars are back"
    clock.advance(days=1)
    assert await telegram.send_refunds() == [], "a failed refund is left to the admins"
    assert telegram.refunds == []


async def test_failed_commit_leaves_the_order_paid_and_queues_no_refund(
    service: OrderService,
    engine: AsyncEngine,
    telegram: Telegram,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = await pay(service, await stars_order(service), "charge-1")

    def refuse_commit(dbapi_connection: Any) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(engine.sync_engine.dialect, "do_commit", refuse_commit)
    with pytest.raises(OperationalError):
        await service.refund(order.id)
    monkeypatch.undo()

    assert telegram.refunds == [], "Telegram is not called inside the transaction"
    assert (await service.get_for_user(USER_ID, order.id)).status is OrderStatus.PAID
    assert await telegram.send_refunds() == [], "no refund is left without the status change"

    refunded = await service.refund(order.id)
    [refund] = await telegram.send_refunds()

    assert refunded.status is OrderStatus.REFUNDED
    assert (refund.charge_id, refund.status) == ("charge-1", RefundStatus.DONE)
    assert telegram.refunds == [(USER_ID, "charge-1")]


async def test_refund_that_could_not_be_queued_is_queued_by_the_next_refund(
    service: OrderService, telegram: Telegram, monkeypatch: pytest.MonkeyPatch
) -> None:
    order = await pay(service, await stars_order(service), "charge-1")
    add_refund_fails_once(monkeypatch)

    with pytest.raises(OperationalError):
        await service.refund(order.id)
    assert (await service.get_for_user(USER_ID, order.id)).status is OrderStatus.REFUNDED
    assert await telegram.send_refunds() == [], "the status went in, the refund did not"

    refunded = await service.refund(order.id)
    [refund] = await telegram.send_refunds()

    assert refunded.status is OrderStatus.REFUNDED
    assert [e.status for e in refunded.events].count(OrderStatus.REFUNDED) == 1
    assert (refund.charge_id, refund.status) == ("charge-1", RefundStatus.DONE)
    assert telegram.refunds == [(USER_ID, "charge-1")]
    with pytest.raises(InvalidTransition):
        await service.refund(order.id)  # the refund is queued now


async def test_redelivered_payment_update_records_one_refund(
    service: OrderService, telegram: Telegram, notifier: FakeNotifier
) -> None:
    order = await cancelled_order(service)

    for _ in range(2):
        await telegram.pay(order, "late-charge")
    await telegram.send_refunds()
    await telegram.pay(order, "late-charge")
    await telegram.send_refunds()

    refund = await telegram.stars.get_refund("late-charge")
    assert refund is not None
    assert refund.status is RefundStatus.DONE
    assert telegram.refunds == [(USER_ID, "late-charge")]
    assert notifier.returned == [(USER_ID, ALREADY_CANCELLED)]


async def test_concurrent_copies_of_a_payment_update_record_one_refund(
    file_service: OrderService, file_telegram: Telegram
) -> None:
    order = await cancelled_order(file_service)

    [payment] = await file_telegram.pay_concurrently(order, "late-charge", "late-charge")

    assert payment.status is PaymentStatus.REJECTED
    await file_telegram.send_refunds()
    assert file_telegram.refunds == [(USER_ID, "late-charge")]


async def test_refund_between_another_refunds_read_and_write_is_refused(
    file_service: OrderService,
    file_telegram: Telegram,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = await pay(file_service, await stars_order(file_service), "charge-1")
    first = run_after_next_read(monkeypatch, file_service.refund(order.id))

    with pytest.raises(InvalidTransition):
        await file_service.refund(order.id)

    assert [type(result) for result in first] == [OrderOut], "the other admin's refund went in"
    stored = await file_service.get_for_user(USER_ID, order.id)
    assert [e.status for e in stored.events] == [
        OrderStatus.AWAITING_PAYMENT,
        OrderStatus.PAID,
        OrderStatus.REFUNDED,
    ]
    await file_telegram.send_refunds()
    assert file_telegram.refunds == [(USER_ID, "charge-1")]


class SignallingSession(RecordingSession):
    """Puts the charge id of every refund Telegram accepted on ``refunded``."""

    def __init__(self) -> None:
        super().__init__()
        self.refunded: asyncio.Queue[str] = asyncio.Queue()

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109 - aiogram signature
    ) -> TelegramType:
        result = await super().make_request(bot, method, timeout)
        if isinstance(method, RefundStarPayment):
            self.refunded.put_nowait(method.telegram_payment_charge_id)
        return result


async def test_recorded_refund_wakes_the_background_task(
    file_engine: AsyncEngine,
    file_sessions: SessionFactory,
    catalog: Catalog,
    rules: PricingRules,
    notifier: FakeNotifier,
    clock: Clock,
) -> None:
    session = SignallingSession()
    bot = Bot(BOT_TOKEN, session=session)
    # Without the wake the second refund would wait an hour for the next sweep.
    stars = make_stars(
        file_engine, file_sessions, notifier, clock, RefundPolicy(poll_interval=3600)
    )
    service = OrderService(
        session_factory=file_sessions,
        catalog=catalog,
        rules=rules,
        notifier=notifier,
        payments=FakePayments(),
        refunds=stars,
    )
    dp = create_dispatcher(
        order_service=service,
        stars=stars,
        catalog=catalog,
        admin_ids=[ADMIN_ID],
        webapp_url=WEBAPP_URL,
    )
    telegram = Telegram(dp, bot, session, stars)
    order = await cancelled_order(service)

    await stars.start(bot)
    try:
        for charge_id in ("charge-a", "charge-b"):
            await telegram.pay(order, charge_id)
            async with asyncio.timeout(5):
                assert await session.refunded.get() == charge_id
    finally:
        await stars.stop()

    assert telegram.refunds == [(USER_ID, "charge-a"), (USER_ID, "charge-b")]


async def test_background_task_sweeps_again_after_a_failure_until_stopped(
    engine: AsyncEngine,
    session_factory: SessionFactory,
    notifier: FakeNotifier,
    clock: Clock,
    bot: Bot,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    claim = SqlAlchemyStorage.claim_refund
    sweeps: list[datetime] = []
    swept_twice = asyncio.Event()

    async def locked_once(self: SqlAlchemyStorage, **kwargs: Any) -> Any:
        sweeps.append(kwargs["now"])
        if len(sweeps) == 1:
            raise RuntimeError("database is locked")
        swept_twice.set()
        return await claim(self, **kwargs)

    monkeypatch.setattr(SqlAlchemyStorage, "claim_refund", locked_once)
    stars = make_stars(engine, session_factory, notifier, clock, RefundPolicy(poll_interval=0.01))

    with caplog.at_level(logging.ERROR, logger="aiogram_stars"):
        await stars.start(bot)
        assert stars.running
        try:
            async with asyncio.timeout(5):
                await swept_twice.wait()
        finally:
            await stars.stop()

    assert not stars.running
    assert "database is locked" in caplog.text


def settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        bot_token=BOT_TOKEN,
        stars_secret=STARS_SECRET,
        database_url="sqlite+aiosqlite:///:memory:",
        **overrides,
    )


def test_refund_retries_are_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("REFUND_MAX_ATTEMPTS", raising=False)
    monkeypatch.delenv("REFUND_RETRY_SECONDS", raising=False)
    assert (settings().refund_max_attempts, settings().refund_retry_seconds) == (8, 30)

    monkeypatch.setenv("REFUND_MAX_ATTEMPTS", "3")
    monkeypatch.setenv("REFUND_RETRY_SECONDS", "5")
    assert (settings().refund_max_attempts, settings().refund_retry_seconds) == (3, 5)

    for name, value in [
        ("REFUND_MAX_ATTEMPTS", "0"),
        ("REFUND_MAX_ATTEMPTS", "21"),
        ("REFUND_RETRY_SECONDS", "0"),
        ("REFUND_RETRY_SECONDS", "86401"),
    ]:
        monkeypatch.setenv(name, value)
        with pytest.raises(ValidationError):
            settings()
        monkeypatch.setenv(name, "1")


async def test_refund_with_the_longest_retry_settings_still_ends_failed(
    engine: AsyncEngine,
    session_factory: SessionFactory,
    notifier: FakeNotifier,
    clock: Clock,
    bot: Bot,
    session: RecordingSession,
) -> None:
    # A first wait of a week would carry the last retry past year 9999: every sweep would then
    # send the refund again, and it would never end failed.
    longest = settings(refund_max_attempts=20, refund_retry_seconds=24 * 60 * 60)
    stars = make_stars(engine, session_factory, notifier, clock, refund_policy(longest))
    await stars.refund("charge-1", user_id=USER_ID, reason="test")
    session.fail_next(RefundStarPayment, *(RuntimeError("Telegram is down") for _ in range(20)))

    for attempt in range(1, 21):
        [refund] = await stars.send_due_refunds(bot)
        if refund.status is RefundStatus.PENDING:
            assert refund.next_attempt_at - clock.now == timedelta(days=2 ** (attempt - 1)), (
                "each wait is twice the one before"
            )
        clock.now = refund.next_attempt_at

    assert (refund.status, refund.attempts) == (RefundStatus.FAILED, 20)
    assert [(r.charge_id, r.attempts) for r in notifier.failed_refunds] == [("charge-1", 20)]


async def test_bot_sends_refunds_while_it_polls(monkeypatch: pytest.MonkeyPatch) -> None:
    policies: list[RefundPolicy] = []

    def create_stars_and_keep_policy(*args: Any, refunds: RefundPolicy, **kwargs: Any) -> Any:
        policies.append(refunds)
        return create_stars(*args, refunds=refunds, **kwargs)

    monkeypatch.setattr(tgshop.container, "create_stars", create_stars_and_keep_policy)
    container = build_container(settings(refund_max_attempts=4, refund_retry_seconds=5))
    await init_models(container.engine)
    try:
        assert policies == [
            RefundPolicy(
                max_attempts=4, first_delay=timedelta(seconds=5), max_delay=timedelta(seconds=40)
            )
        ], "REFUND_* reach aiogram-stars"

        dp = container.dispatcher()
        await dp.emit_startup(bot=container.bot)
        assert container.stars.running
        await dp.emit_shutdown()
        assert not container.stars.running
    finally:
        await container.aclose()
