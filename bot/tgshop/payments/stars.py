"""Telegram Stars (XTR) payments.

Flow:
1. The order is created with status ``awaiting_payment`` and a fixed ``stars_amount``.
2. We issue an invoice (link for the Mini App, or a chat message) with payload ``order:<id>``.
3. Telegram sends ``pre_checkout_query`` → :func:`check_payment` must approve it within 10 s.
4. Telegram sends ``successful_payment`` → the order becomes ``paid``; the charge id is stored
   so the payment can later be refunded with ``refundStarPayment``.

Digital goods must be sold for Stars; physical goods may use Stars or a regular provider.
Stars invoices need no provider token.
"""

from __future__ import annotations

from aiogram import Bot
from aiogram.types import LabeledPrice

from tgshop.domain.enums import OrderStatus
from tgshop.domain.schemas import OrderOut

from .base import Invoice

STARS_CURRENCY = "XTR"
_PAYLOAD_PREFIX = "order:"


def make_payload(order_id: int) -> str:
    return f"{_PAYLOAD_PREFIX}{order_id}"


def parse_payload(payload: str) -> int | None:
    if not payload.startswith(_PAYLOAD_PREFIX):
        return None
    tail = payload.removeprefix(_PAYLOAD_PREFIX)
    return int(tail) if tail.isdecimal() else None


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
        payload=make_payload(order.id),
    )


def check_payment(
    order: OrderOut | None,
    *,
    currency: str,
    total_amount: int,
    payer_id: int,
) -> str | None:
    """Validate a pre-checkout query / successful payment. Returns an error text or ``None``."""
    if order is None:
        return "Заказ не найден"
    if currency != STARS_CURRENCY:
        return "Неподдерживаемая валюта"
    if order.user_id != payer_id:
        return "Этот заказ оформлен другим пользователем"
    if order.status is not OrderStatus.AWAITING_PAYMENT:
        return "Заказ уже оплачен или отменён"
    if order.stars_amount != total_amount:
        return "Сумма счёта устарела — оформите заказ заново"
    return None


class TelegramStarsGateway:
    """:class:`~tgshop.payments.base.PaymentGateway` backed by the Bot API."""

    def __init__(self, bot: Bot) -> None:
        self._bot = bot

    @staticmethod
    def _prices(invoice: Invoice) -> list[LabeledPrice]:
        return [LabeledPrice(label=invoice.label, amount=invoice.amount)]

    async def create_invoice_link(self, invoice: Invoice) -> str:
        return await self._bot.create_invoice_link(
            title=invoice.title,
            description=invoice.description,
            payload=invoice.payload,
            currency=STARS_CURRENCY,
            prices=self._prices(invoice),
        )

    async def send_invoice(self, chat_id: int, invoice: Invoice) -> None:
        await self._bot.send_invoice(
            chat_id=chat_id,
            title=invoice.title,
            description=invoice.description,
            payload=invoice.payload,
            currency=STARS_CURRENCY,
            prices=self._prices(invoice),
        )

    async def refund(self, user_id: int, charge_id: str) -> None:
        await self._bot.refund_star_payment(user_id=user_id, telegram_payment_charge_id=charge_id)
