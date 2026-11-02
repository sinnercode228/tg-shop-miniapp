"""Tells customers and admins how a Stars refund ended.

aiogram-stars keeps the refunds in ``stars_refunds`` and calls ``refundStarPayment`` from its
outbox, with retries. It calls :meth:`RefundNotices.refunded` once the Stars are back and
:meth:`RefundNotices.failed` once the last attempt failed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from aiogram_stars import Refund, RefundStatus, StarsPayments, Storage
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncEngine

from tgshop.db.models import Order
from tgshop.db.repository import OrderRepository
from tgshop.db.session import SessionFactory
from tgshop.domain.schemas import OrderOut

from .notifier import Notifier

log = logging.getLogger(__name__)

# What the customer reads about a payment whose invoice payload did not verify. aiogram-stars
# gives its own reason, in English, and leaves the payment's order id empty.
UNVERIFIED_INVOICE = "Счёт не прошёл проверку"


@dataclass(frozen=True, slots=True)
class RefundOut:
    order_id: int | None
    user_id: int
    amount: int
    charge_id: str
    reason: str | None
    status: RefundStatus
    attempts: int
    last_error: str | None


class RefundNotices:
    """The ``on_refunded`` and ``on_refund_failed`` callbacks of the bot's aiogram-stars."""

    def __init__(
        self, session_factory: SessionFactory, storage: Storage, notifier: Notifier
    ) -> None:
        self._sessions = session_factory
        self._storage = storage
        self._notifier = notifier

    async def refunded(self, refund: Refund) -> None:
        if refund.reason is not None:
            # A payment the order could not take, e.g. one for an order cancelled meanwhile.
            payment = await self._storage.get_payment(refund.charge_id)
            unverified = payment is not None and not payment.order_id
            reason = UNVERIFIED_INVOICE if unverified else refund.reason
            await self._notifier.payment_returned(refund.user_id, reason)
            return
        async with self._sessions() as session:
            order = await OrderRepository(session).get_by_charge(refund.charge_id)
            dto = OrderOut.model_validate(order, from_attributes=True) if order else None
        if dto is not None:
            await self._notifier.order_refunded(dto)

    async def failed(self, refund: Refund) -> None:
        await self._notifier.refund_failed(await self._describe(refund))

    async def _describe(self, refund: Refund) -> RefundOut:
        # The payment is recorded unless it was taken before aiogram-stars handled payments.
        payment = await self._storage.get_payment(refund.charge_id)
        async with self._sessions() as session:
            orders = OrderRepository(session)
            order: Order | None = await orders.get_by_charge(refund.charge_id)
            if order is None and payment is not None and payment.order_id.isdecimal():
                order = await orders.get(int(payment.order_id))
        if payment is not None:
            amount = payment.amount
        elif order is not None and order.stars_amount is not None:
            amount = order.stars_amount
        else:
            amount = 0
        return RefundOut(
            order_id=order.id if order is not None else None,
            user_id=refund.user_id,
            amount=amount,
            charge_id=refund.charge_id,
            reason=refund.reason,
            status=refund.status,
            attempts=refund.attempts,
            last_error=refund.last_error,
        )


async def queue_old_refunds(engine: AsyncEngine, stars: StarsPayments) -> list[Refund]:
    """Queue with aiogram-stars the refunds still ``pending`` in ``refunds``, the table of the
    outbox the shop had before. aiogram-stars keeps one refund per charge, so running this at
    every start queues each of them once."""
    async with engine.connect() as conn:
        if not await conn.run_sync(lambda sync: inspect(sync).has_table("refunds")):
            return []
        rows = await conn.execute(
            text(
                "SELECT telegram_payment_charge_id, user_id, reason FROM refunds"
                " WHERE status = 'pending' ORDER BY id"
            )
        )
        pending = rows.all()
    queued: list[Refund] = []
    for charge_id, user_id, reason in pending:
        try:
            queued.append(await stars.refund(charge_id, user_id=user_id, reason=reason))
        except Exception:
            # Left pending in the old table, so the next start tries again.
            log.exception("failed to queue refund %s from the old refunds table", charge_id)
    if queued:
        log.info("queued %d refunds from the old refunds table", len(queued))
    return queued
