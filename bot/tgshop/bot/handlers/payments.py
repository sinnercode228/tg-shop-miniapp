"""Telegram Stars payment updates, handled by aiogram-stars. Business rules live in
``tgshop.payments`` and ``OrderService``."""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import datetime

from aiogram.exceptions import TelegramAPIError
from aiogram.types import Message
from aiogram_stars import Checkout, Payment, RefundPolicy, RejectPayment, StarsPayments, Storage

from tgshop.bot import texts
from tgshop.db.models import utcnow
from tgshop.domain.errors import PaymentError
from tgshop.services.orders import OrderService
from tgshop.services.refunds import RefundNotices

log = logging.getLogger(__name__)


async def check(checkout: Checkout, order_service: OrderService) -> None:
    # The payload is verified already; aiogram-stars answers Telegram within its 10 seconds.
    error = await order_service.pre_checkout_error(
        order_id=int(checkout.order_id),
        total_amount=checkout.amount,
        payer_id=checkout.user_id,
    )
    if error is not None:
        raise RejectPayment(error)


async def on_paid(payment: Payment, message: Message, order_service: OrderService) -> None:
    try:
        order = await order_service.mark_paid(
            order_id=int(payment.order_id),
            total_amount=payment.amount,
            payer_id=payment.user_id,
            charge_id=payment.charge_id,
        )
    except PaymentError as exc:
        # aiogram-stars marks the payment rejected and queues its refund; the customer hears
        # about it from RefundNotices once the Stars are back.
        raise RejectPayment(exc.message) from exc
    try:
        await message.answer(f"Оплата получена, заказ №{order.id} передан в работу 💫")
    except TelegramAPIError:
        # The order is paid: a lost reply must not mark the payment as an error.
        log.exception("failed to confirm payment %s to user %s", payment.charge_id, payment.user_id)


def create_stars(
    storage: Storage,
    *,
    secret: str,
    notices: RefundNotices,
    refunds: RefundPolicy,
    clock: Callable[[], datetime] = utcnow,
) -> StarsPayments:
    return StarsPayments(
        storage,
        secret=secret,
        check=check,
        on_paid=on_paid,
        on_refunded=notices.refunded,
        on_refund_failed=notices.failed,
        checkout_error=texts.CHECKOUT_ERROR,
        refunds=refunds,
        clock=clock,
    )
