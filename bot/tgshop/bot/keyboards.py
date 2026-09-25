from __future__ import annotations

from aiogram.filters.callback_data import CallbackData
from aiogram.types import (
    InlineKeyboardButton,
    InlineKeyboardMarkup,
    KeyboardButton,
    ReplyKeyboardMarkup,
    WebAppInfo,
)

from tgshop.domain.enums import OrderStatus
from tgshop.domain.schemas import OrderOut
from tgshop.domain.status import allowed_transitions

from .texts import STATUS_LABELS


class OrderAction(CallbackData, prefix="ord"):
    order_id: int
    status: OrderStatus


def shop_inline(webapp_url: str) -> InlineKeyboardMarkup:
    """Inline launch: the Mini App talks to the REST API (``openInvoice`` for Stars)."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [InlineKeyboardButton(text="☕ Открыть магазин", web_app=WebAppInfo(url=webapp_url))]
        ]
    )


def shop_reply(webapp_url: str) -> ReplyKeyboardMarkup:
    """Keyboard launch: the Mini App may return the order via ``sendData`` (web_app_data)."""
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="☕ Магазин", web_app=WebAppInfo(url=webapp_url))]],
        resize_keyboard=True,
        is_persistent=True,
    )


def admin_order(order: OrderOut) -> InlineKeyboardMarkup | None:
    targets = allowed_transitions(
        order.status, delivery=order.delivery_method, payment=order.payment_method
    )
    order_of_buttons = [
        OrderStatus.CONFIRMED,
        OrderStatus.IN_DELIVERY,
        OrderStatus.READY_FOR_PICKUP,
        OrderStatus.COMPLETED,
        OrderStatus.CANCELLED,
        OrderStatus.REFUNDED,
    ]
    buttons = [
        InlineKeyboardButton(
            text=STATUS_LABELS[status],
            callback_data=OrderAction(order_id=order.id, status=status).pack(),
        )
        for status in order_of_buttons
        if status in targets
    ]
    if not buttons:
        return None
    rows = [buttons[i : i + 2] for i in range(0, len(buttons), 2)]
    return InlineKeyboardMarkup(inline_keyboard=rows)
