"""Telegram Stars (XTR) payments, handled by aiogram-stars.

Flow:
1. The order is created with status ``awaiting_payment`` and a fixed ``stars_amount``.
2. We issue an invoice (link for the Mini App, or a chat message). aiogram-stars signs its
   payload for the order id and the amount, so the bot takes only invoices it made itself.
3. Telegram sends ``pre_checkout_query`` → aiogram-stars checks the signature and answers within
   10 s; :func:`check_payment` decides.
4. Telegram sends ``successful_payment`` → aiogram-stars records the charge once and the order
   becomes ``paid``; the charge id is stored so the payment can later be refunded with
   ``refundStarPayment``.

Digital goods must be sold for Stars; physical goods may use Stars or a regular provider.
Stars invoices need no provider token.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram_stars import StarsPayments

from tgshop.domain.enums import OrderStatus
from tgshop.domain.schemas import OrderOut

from .base import Invoice


def build_invoice(order: OrderOut, *, shop_name: str = "Zernolist") -> Invoice:
    if order.stars_amount is None:
        raise ValueError("order has no Stars amount")
    positions = sum(item.quantity for item in order.items)
    return Invoice(
        order_id=order.id,
        title=f"{shop_name} — заказ №{order.id}",
        description=f"Позиций: {positions}. Кофе и чай с доставкой (демо-магазин).",
        label=f"Заказ №{order.id}",
        amount=order.stars_amount,
    )


def check_payment(order: OrderOut | None, *, total_amount: int, payer_id: int) -> str | None:
    """Validate a pre-checkout query / successful payment. Returns an error text or ``None``."""
    if order is None:
        return "Заказ не найден"
    if order.user_id != payer_id:
        return "Этот заказ оформлен другим пользователем"
    if order.status is not OrderStatus.AWAITING_PAYMENT:
        return "Заказ уже оплачен или отменён"
    if order.stars_amount != total_amount:
        return "Сумма счёта устарела — оформите заказ заново"
    return None


class TelegramStarsGateway:
    """:class:`~tgshop.payments.base.PaymentGateway` backed by the Bot API."""

    def __init__(self, bot: Bot, stars: StarsPayments) -> None:
        self._bot = bot
        self._stars = stars

    async def create_invoice_link(self, invoice: Invoice) -> str:
        return await self._stars.create_invoice_link(
            self._bot,
            order_id=invoice.order_id,
            amount=invoice.amount,
            title=invoice.title,
            description=invoice.description,
            label=invoice.label,
        )

    async def send_invoice(self, chat_id: int, invoice: Invoice) -> None:
        await self._stars.send_invoice(
            self._bot,
            chat_id,
            order_id=invoice.order_id,
            amount=invoice.amount,
            title=invoice.title,
            description=invoice.description,
            label=invoice.label,
        )
