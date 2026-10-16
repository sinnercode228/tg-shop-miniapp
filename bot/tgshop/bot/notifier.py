from __future__ import annotations

import logging
from collections.abc import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderStatus
from tgshop.domain.schemas import OrderOut
from tgshop.services.refunds import RefundOut

from .keyboards import admin_order
from .texts import order_summary, payment_returned, refund_failed, status_update

log = logging.getLogger(__name__)


class TelegramNotifier:
    """Delivers order notifications through the bot. Failures are logged, never raised:
    a blocked bot or a flaky network must not break order placement."""

    def __init__(self, bot: Bot, catalog: Catalog, admin_ids: Iterable[int]) -> None:
        self._bot = bot
        self._catalog = catalog
        self._admins = tuple(admin_ids)

    async def order_placed(self, order: OrderOut) -> None:
        await self._tell_admins(order, "🛎 <b>Новый заказ</b>")

    async def order_expired(self, order: OrderOut) -> None:
        await self._tell_admins(order, "⌛ <b>Заказ не оплачен вовремя</b>")

    async def refund_failed(self, refund: RefundOut) -> None:
        for admin_id in self._admins:
            try:
                await self._bot.send_message(admin_id, refund_failed(refund))
            except TelegramAPIError:
                log.exception("failed to notify admin %s about refund %s", admin_id, refund.id)

    async def _tell_admins(self, order: OrderOut, title: str) -> None:
        text = f"{title}\n\n" + order_summary(order, self._catalog, for_admin=True)
        for admin_id in self._admins:
            try:
                await self._bot.send_message(admin_id, text, reply_markup=admin_order(order))
            except TelegramAPIError:
                log.exception("failed to notify admin %s about order %s", admin_id, order.id)

    async def status_changed(self, order: OrderOut, previous: OrderStatus) -> None:
        await self._tell_customer(order.user_id, status_update(order))

    async def order_refunded(self, order: OrderOut) -> None:
        await self._tell_customer(order.user_id, status_update(order))

    async def payment_returned(self, user_id: int, reason: str) -> None:
        await self._tell_customer(user_id, payment_returned(reason))

    async def _tell_customer(self, user_id: int, text: str) -> None:
        try:
            await self._bot.send_message(user_id, text)
        except TelegramAPIError:
            log.exception("failed to notify user %s", user_id)
