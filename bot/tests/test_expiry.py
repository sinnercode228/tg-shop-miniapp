from __future__ import annotations

import asyncio
import logging
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from pydantic import ValidationError

from tgshop.config import Settings
from tgshop.container import build_container
from tgshop.db.session import init_models
from tgshop.domain.enums import OrderSource, OrderStatus
from tgshop.domain.errors import PaymentError
from tgshop.domain.schemas import OrderCreate, OrderOut
from tgshop.payments import make_payload
from tgshop.services.expiry import UnpaidOrderExpiry
from tgshop.services.orders import Customer, OrderService

from .conftest import (
    BOT_TOKEN,
    USER_ID,
    FakeNotifier,
    FakePayments,
    order_payload,
    pay_concurrently,
    run_after_next_read,
)

TTL = timedelta(minutes=30)
CUSTOMER = Customer(user_id=USER_ID, language="ru")


def expiry_at(service: Any, now: datetime, *, interval: float = 60) -> UnpaidOrderExpiry:
    return UnpaidOrderExpiry(service, ttl=TTL, interval=interval, clock=lambda: now)


async def place_stars_order(service: OrderService) -> OrderOut:
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


async def stored_statuses(service: OrderService, order: OrderOut) -> list[OrderStatus]:
    stored = await service.get_for_user(USER_ID, order.id)
    return [e.status for e in stored.events]


async def test_unpaid_order_is_kept_until_the_ttl_has_passed(
    service: OrderService, notifier: FakeNotifier
) -> None:
    order = await place_stars_order(service)

    assert await expiry_at(service, order.created_at + TTL).run_once() == []

    assert await stored_statuses(service, order) == [OrderStatus.AWAITING_PAYMENT]
    assert notifier.changes == []
    assert notifier.expired == []


async def test_unpaid_order_is_cancelled_after_the_ttl(
    service: OrderService, notifier: FakeNotifier, payments: FakePayments
) -> None:
    order = await place_stars_order(service)
    paid = await pay(service, await place_stars_order(service), "charge-1")
    cash = await service.create_order(
        CUSTOMER, OrderCreate.model_validate(order_payload()), source=OrderSource.API
    )
    notifier.changes.clear()
    later = order.created_at + TTL + timedelta(seconds=1)

    [expired] = await expiry_at(service, later).run_once()

    assert expired.id == order.id
    assert expired.status is OrderStatus.CANCELLED
    assert await stored_statuses(service, order) == [
        OrderStatus.AWAITING_PAYMENT,
        OrderStatus.CANCELLED,
    ]
    assert (await service.get_for_user(USER_ID, paid.id)).status is OrderStatus.PAID
    assert (await service.get_for_user(USER_ID, cash.id)).status is OrderStatus.NEW
    assert notifier.changes == [(expired, OrderStatus.AWAITING_PAYMENT)], (
        "the customer gets the same status message as after a manual cancel"
    )
    assert notifier.expired == [expired], "admins hear about it"
    assert payments.refunds == []
    assert await expiry_at(service, later + TTL).run_once() == [], "an order expires once"


async def test_payment_for_an_expired_order_is_refunded(
    service: OrderService, notifier: FakeNotifier, payments: FakePayments
) -> None:
    order = await place_stars_order(service)
    await expiry_at(service, order.created_at + 2 * TTL).run_once()

    assert (
        await service.pre_checkout_error(
            payload=make_payload(order.id),
            currency="XTR",
            total_amount=order.stars_amount or 0,
            payer_id=USER_ID,
        )
        == "Заказ уже оплачен или отменён"
    )
    with pytest.raises(PaymentError):
        await pay(service, order, "late-charge")

    assert payments.refunds == [(USER_ID, "late-charge")]
    assert await stored_statuses(service, order) == [
        OrderStatus.AWAITING_PAYMENT,
        OrderStatus.CANCELLED,
    ]
    assert notifier.placed == [], "admins never get a new-order message for it"


async def test_payment_between_expiry_read_and_write_keeps_the_order_paid(
    file_service: OrderService,
    notifier: FakeNotifier,
    payments: FakePayments,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = await place_stars_order(file_service)
    paid = run_after_next_read(monkeypatch, pay_concurrently(file_service, order, "charge-1"))

    assert await expiry_at(file_service, order.created_at + 2 * TTL).run_once() == []

    assert len(paid) == 1, "the payment went through while the expiry was running"
    assert await stored_statuses(file_service, order) == [
        OrderStatus.AWAITING_PAYMENT,
        OrderStatus.PAID,
    ]
    assert payments.refunds == []
    assert notifier.expired == []
    assert [previous for _, previous in notifier.changes] == [OrderStatus.AWAITING_PAYMENT]
    assert len(notifier.placed) == 1


async def test_expiry_between_payment_read_and_write_refunds_the_payment(
    file_service: OrderService,
    notifier: FakeNotifier,
    payments: FakePayments,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = await place_stars_order(file_service)
    run_after_next_read(monkeypatch, expiry_at(file_service, order.created_at + 2 * TTL).run_once())

    with pytest.raises(PaymentError):
        await pay(file_service, order, "charge-1")

    assert await stored_statuses(file_service, order) == [
        OrderStatus.AWAITING_PAYMENT,
        OrderStatus.CANCELLED,
    ]
    assert payments.refunds == [(USER_ID, "charge-1")]
    assert [o.id for o in notifier.expired] == [order.id]
    assert notifier.placed == []


class FlakyOrders:
    """Stands in for ``OrderService``: the first sweep fails, as on a locked database."""

    def __init__(self) -> None:
        self.cutoffs: list[datetime] = []
        self.swept_twice = asyncio.Event()

    async def expire_unpaid(self, *, placed_before: datetime) -> list[OrderOut]:
        self.cutoffs.append(placed_before)
        if len(self.cutoffs) == 1:
            raise RuntimeError("database is locked")
        self.swept_twice.set()
        return []


async def test_background_task_sweeps_again_after_a_failure_until_stopped(
    caplog: pytest.LogCaptureFixture,
) -> None:
    orders = FlakyOrders()
    now = datetime(2026, 10, 15, 12, 0, tzinfo=UTC)
    expiry = expiry_at(orders, now, interval=0.01)

    with caplog.at_level(logging.ERROR, logger="tgshop.services.expiry"):
        await expiry.start()
        assert expiry.running
        try:
            async with asyncio.timeout(5):
                await orders.swept_twice.wait()
        finally:
            await expiry.stop()

    assert not expiry.running
    assert orders.cutoffs[:2] == [now - TTL, now - TTL]
    assert "database is locked" in caplog.text


def settings(**overrides: Any) -> Settings:
    return Settings(
        _env_file=None,
        bot_token=BOT_TOKEN,
        database_url="sqlite+aiosqlite:///:memory:",
        **overrides,
    )


def test_payment_ttl_is_read_from_the_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("ORDER_PAYMENT_TTL_MINUTES", raising=False)
    assert settings().order_payment_ttl_minutes == 30

    monkeypatch.setenv("ORDER_PAYMENT_TTL_MINUTES", "0")
    assert settings().order_payment_ttl_minutes == 0

    monkeypatch.setenv("ORDER_PAYMENT_TTL_MINUTES", "-1")
    with pytest.raises(ValidationError):
        settings()


async def test_zero_ttl_turns_the_expiry_off() -> None:
    container = build_container(settings(order_payment_ttl_minutes=0))
    try:
        assert container.unpaid_order_expiry is None
    finally:
        await container.aclose()


async def test_bot_runs_the_expiry_while_it_polls() -> None:
    container = build_container(settings(order_payment_ttl_minutes=45))
    await init_models(container.engine)
    try:
        expiry = container.unpaid_order_expiry
        assert expiry is not None
        assert expiry.ttl == timedelta(minutes=45)

        dp = container.dispatcher()
        await dp.emit_startup()
        assert expiry.running
        await dp.emit_shutdown()
        assert not expiry.running
    finally:
        await container.aclose()
