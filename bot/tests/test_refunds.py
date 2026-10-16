from __future__ import annotations

import asyncio
import logging
import sqlite3
from datetime import datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from tgshop.config import Settings
from tgshop.container import build_container
from tgshop.db.models import Refund
from tgshop.db.repository import RefundRepository
from tgshop.db.session import SessionFactory, init_models
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderStatus, RefundStatus
from tgshop.domain.errors import InvalidTransition, PaymentError
from tgshop.domain.pricing import PricingRules
from tgshop.domain.schemas import OrderCreate, OrderOut
from tgshop.payments import make_payload
from tgshop.services.orders import Customer, OrderService
from tgshop.services.refunds import RefundOut, RefundOutbox

from .conftest import (
    BOT_TOKEN,
    USER_ID,
    Clock,
    FakeNotifier,
    FakePayments,
    order_payload,
    pay_concurrently,
    run_after_next_read,
)

CUSTOMER = Customer(user_id=USER_ID, language="ru")
ALREADY_CANCELLED = "Заказ уже оплачен или отменён"


async def stars_order(service: OrderService) -> OrderOut:
    data = OrderCreate.model_validate(order_payload(paymentMethod="stars"))
    return (await service.place_order(CUSTOMER, data)).order


async def pay(service: OrderService, order: OrderOut, charge_id: str) -> OrderOut:
    return await service.mark_paid(
        payload=make_payload(order.id),
        currency="XTR",
        total_amount=order.stars_amount or 0,
        payer_id=USER_ID,
        charge_id=charge_id,
    )


async def cancelled_order(service: OrderService) -> OrderOut:
    return await service.change_status((await stars_order(service)).id, OrderStatus.CANCELLED)


async def recorded(sessions: SessionFactory) -> list[RefundOut]:
    async with sessions() as session:
        rows = (await session.execute(select(Refund).order_by(Refund.id))).scalars()
        return [RefundOut.of(row) for row in rows]


async def test_refund_that_fails_twice_goes_through_on_the_third_attempt(
    service: OrderService,
    outbox: RefundOutbox,
    clock: Clock,
    payments: FakePayments,
    notifier: FakeNotifier,
) -> None:
    order = await cancelled_order(service)
    with pytest.raises(PaymentError):
        await pay(service, order, "late-charge")
    assert payments.refunds == [], "the update handler leaves the Bot API call to the outbox"
    payments.refund_errors = [TimeoutError("no answer"), RuntimeError("Bad Gateway")]

    [first] = await outbox.run_once()
    assert (first.status, first.attempts) == (RefundStatus.PENDING, 1)
    assert first.last_error == "TimeoutError: no answer"
    assert first.next_attempt_at == clock.now + timedelta(seconds=30)
    clock.advance(seconds=29)
    assert await outbox.run_once() == [], "the first retry waits 30 s"

    clock.advance(seconds=1)
    [second] = await outbox.run_once()
    assert (second.status, second.attempts) == (RefundStatus.PENDING, 2)
    assert second.next_attempt_at == clock.now + timedelta(seconds=60), "each wait doubles"
    assert notifier.returned == [], "the customer hears nothing until the Stars are back"

    clock.advance(seconds=60)
    [third] = await outbox.run_once()

    assert (third.status, third.attempts) == (RefundStatus.DONE, 3)
    assert (third.order_id, third.charge_id, third.amount) == (
        order.id,
        "late-charge",
        order.stars_amount,
    )
    assert payments.refunds == [(USER_ID, "late-charge")]
    assert notifier.returned == [(USER_ID, ALREADY_CANCELLED)]
    assert notifier.failed_refunds == []
    clock.advance(days=1)
    assert await outbox.run_once() == [], "a refund that went through is not sent again"


async def test_refund_that_keeps_failing_ends_failed_and_tells_the_admins(
    service: OrderService,
    outbox: RefundOutbox,
    clock: Clock,
    payments: FakePayments,
    notifier: FakeNotifier,
) -> None:
    order = await pay(service, await stars_order(service), "charge-1")
    refunded = await service.change_status(order.id, OrderStatus.REFUNDED)
    assert refunded.status is OrderStatus.REFUNDED
    payments.refund_errors = [RuntimeError("Telegram is down") for _ in range(3)]

    for wait in (0, 30, 60):
        clock.advance(seconds=wait)
        [refund] = await outbox.run_once()

    assert refund.status is RefundStatus.FAILED
    assert refund.attempts == 3
    assert refund.last_error == "RuntimeError: Telegram is down"
    assert notifier.failed_refunds == [refund], "the admins are told"
    assert notifier.refunded == [], "the customer is not told the Stars are back"
    clock.advance(days=1)
    assert await outbox.run_once() == [], "a failed refund is left to the admins"
    assert payments.refunds == []


async def test_refund_is_recorded_with_the_status_change_or_not_at_all(
    service: OrderService,
    engine: AsyncEngine,
    outbox: RefundOutbox,
    payments: FakePayments,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = await pay(service, await stars_order(service), "charge-1")

    def refuse_commit(dbapi_connection: Any) -> None:
        raise sqlite3.OperationalError("disk I/O error")

    monkeypatch.setattr(engine.sync_engine.dialect, "do_commit", refuse_commit)
    with pytest.raises(OperationalError):
        await service.refund(order.id)
    monkeypatch.undo()

    assert payments.refunds == [], "Telegram is not called inside the transaction"
    assert (await service.get_for_user(USER_ID, order.id)).status is OrderStatus.PAID
    assert await outbox.run_once() == [], "no refund is left without the status change"

    refunded = await service.refund(order.id)
    [refund] = await outbox.run_once()

    assert refunded.status is OrderStatus.REFUNDED
    assert (refund.order_id, refund.status) == (order.id, RefundStatus.DONE)
    assert payments.refunds == [(USER_ID, "charge-1")]


async def test_redelivered_payment_update_records_one_refund(
    service: OrderService,
    session_factory: SessionFactory,
    outbox: RefundOutbox,
    payments: FakePayments,
    notifier: FakeNotifier,
) -> None:
    order = await cancelled_order(service)

    for _ in range(2):
        with pytest.raises(PaymentError):
            await pay(service, order, "late-charge")
    await outbox.run_once()
    with pytest.raises(PaymentError):
        await pay(service, order, "late-charge")
    await outbox.run_once()

    [refund] = await recorded(session_factory)
    assert (refund.charge_id, refund.status) == ("late-charge", RefundStatus.DONE)
    assert payments.refunds == [(USER_ID, "late-charge")]
    assert notifier.returned == [(USER_ID, ALREADY_CANCELLED)]


async def test_concurrent_copies_of_a_payment_update_record_one_refund(
    file_service: OrderService,
    file_sessions: SessionFactory,
    file_outbox: RefundOutbox,
    payments: FakePayments,
) -> None:
    order = await cancelled_order(file_service)

    results = await pay_concurrently(file_service, order, "late-charge", "late-charge")

    assert all(isinstance(r, PaymentError) for r in results)
    assert len(await recorded(file_sessions)) == 1
    await file_outbox.run_once()
    assert payments.refunds == [(USER_ID, "late-charge")]


async def test_refund_between_another_refunds_read_and_write_is_refused(
    file_service: OrderService,
    file_sessions: SessionFactory,
    file_outbox: RefundOutbox,
    payments: FakePayments,
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
    assert len(await recorded(file_sessions)) == 1
    await file_outbox.run_once()
    assert payments.refunds == [(USER_ID, "charge-1")]


class SignallingPayments(FakePayments):
    """Puts the charge id of every refund that went through on ``sent``."""

    def __init__(self) -> None:
        super().__init__()
        self.sent: asyncio.Queue[str] = asyncio.Queue()

    async def refund(self, user_id: int, charge_id: str) -> None:
        await super().refund(user_id, charge_id)
        self.sent.put_nowait(charge_id)


async def test_recorded_refund_wakes_the_background_task(
    session_factory: SessionFactory, catalog: Catalog, rules: PricingRules, notifier: FakeNotifier
) -> None:
    payments = SignallingPayments()
    # Without the wake the second refund would wait an hour for the next sweep.
    outbox = RefundOutbox(session_factory, payments, notifier, interval=3600)
    service = OrderService(
        session_factory=session_factory,
        catalog=catalog,
        rules=rules,
        notifier=notifier,
        payments=payments,
        refund_recorded=outbox.wake,
    )
    order = await cancelled_order(service)

    await outbox.start()
    try:
        for charge_id in ("charge-a", "charge-b"):
            with pytest.raises(PaymentError):
                await pay(service, order, charge_id)
            async with asyncio.timeout(5):
                assert await payments.sent.get() == charge_id
    finally:
        await outbox.stop()

    assert payments.refunds == [(USER_ID, "charge-a"), (USER_ID, "charge-b")]


async def test_background_task_sweeps_again_after_a_failure_until_stopped(
    session_factory: SessionFactory,
    payments: FakePayments,
    notifier: FakeNotifier,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    due = RefundRepository.due
    sweeps: list[datetime] = []
    swept_twice = asyncio.Event()

    async def locked_once(self: RefundRepository, moment: datetime) -> Any:
        sweeps.append(moment)
        if len(sweeps) == 1:
            raise RuntimeError("database is locked")
        swept_twice.set()
        return await due(self, moment)

    monkeypatch.setattr(RefundRepository, "due", locked_once)
    outbox = RefundOutbox(session_factory, payments, notifier, interval=0.01)

    with caplog.at_level(logging.ERROR, logger="tgshop.services.refunds"):
        await outbox.start()
        assert outbox.running
        try:
            async with asyncio.timeout(5):
                await swept_twice.wait()
        finally:
            await outbox.stop()

    assert not outbox.running
    assert "database is locked" in caplog.text


def settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        bot_token=BOT_TOKEN,
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
    session_factory: SessionFactory, payments: FakePayments, notifier: FakeNotifier, clock: Clock
) -> None:
    # A first wait of a week would carry the last retry past year 9999: every sweep would then
    # send the refund again, and it would never end failed.
    longest = settings(refund_max_attempts=20, refund_retry_seconds=24 * 60 * 60)
    outbox = RefundOutbox(
        session_factory,
        payments,
        notifier,
        max_attempts=longest.refund_max_attempts,
        retry_delay=timedelta(seconds=longest.refund_retry_seconds),
        clock=clock,
    )
    async with session_factory() as session, session.begin():
        await RefundRepository(session).add(
            charge_id="charge-1", user_id=USER_ID, amount=100, order_id=None, reason="test"
        )
    payments.refund_errors = [RuntimeError("Telegram is down") for _ in range(20)]

    for _ in range(20):
        [refund] = await outbox.run_once()
        clock.now = refund.next_attempt_at

    assert (refund.status, refund.attempts) == (RefundStatus.FAILED, 20)
    assert notifier.failed_refunds == [refund]


async def test_bot_sends_refunds_while_it_polls() -> None:
    container = build_container(settings(refund_max_attempts=4, refund_retry_seconds=5))
    await init_models(container.engine)
    try:
        outbox = container.refund_outbox
        assert outbox.max_attempts == 4
        assert outbox.retry_delay == timedelta(seconds=5)

        dp = container.dispatcher()
        await dp.emit_startup()
        assert outbox.running
        await dp.emit_shutdown()
        assert not outbox.running
    finally:
        await container.aclose()
