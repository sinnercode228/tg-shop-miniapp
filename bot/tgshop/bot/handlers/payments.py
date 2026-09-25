"""Telegram Stars payment updates. Business rules live in ``tgshop.payments``."""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message, PreCheckoutQuery

from tgshop.domain.errors import PaymentError
from tgshop.services.orders import OrderService

log = logging.getLogger(__name__)


async def pre_checkout(query: PreCheckoutQuery, order_service: OrderService) -> None:
    # Telegram waits at most 10 seconds for this answer.
    error = await order_service.pre_checkout_error(
        payload=query.invoice_payload,
        currency=query.currency,
        total_amount=query.total_amount,
        payer_id=query.from_user.id,
    )
    await query.answer(ok=error is None, error_message=error)


async def successful_payment(message: Message, order_service: OrderService) -> None:
    payment = message.successful_payment
    if payment is None or message.from_user is None:
        return
    try:
        order = await order_service.mark_paid(
            payload=payment.invoice_payload,
            currency=payment.currency,
            total_amount=payment.total_amount,
            payer_id=message.from_user.id,
            charge_id=payment.telegram_payment_charge_id,
        )
    except PaymentError as exc:
        log.warning("payment rejected and refunded: %s", exc.message)
        await message.answer(f"Платёж не принят ({exc.message}). Звёзды возвращены.")
        return
    await message.answer(f"Оплата получена, заказ №{order.id} передан в работу 💫")


def create_router() -> Router:
    router = Router(name="payments")
    router.pre_checkout_query.register(pre_checkout)
    router.message.register(successful_payment, F.successful_payment)
    return router
