from __future__ import annotations

import logging
from collections.abc import Iterable

from aiogram import Bot
from aiogram.exceptions import TelegramAPIError

from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderStatus
from tgshop.domain.schemas import OrderOut

from .keyboards import admin_order
from .texts import order_summary, status_update

log = logging.getLogger(__name__)


class TelegramNotifier:
    """Delivers order notifications through the bot. Failures are logged, never raised:
    a blocked bot or a flaky network must not break order placement."""

    def __init__(self, bot: Bot, catalog: Catalog, admin_ids: Iterable[int]) -> None:
        self._bot = bot
        self._catalog = catalog
        self._admins = tuple(admin_ids)

    async def order_placed(self, order: OrderOut) -> None:
        text = "🛎 <b>Новый заказ</b>\n\n" + order_summary(order, self._catalog, for_admin=True)
        for admin_id in self._admins:
            try:
                await self._bot.send_message(admin_id, text, reply_markup=admin_order(order))
            except TelegramAPIError:
                log.exception("failed to notify admin %s about order %s", admin_id, order.id)

    async def status_changed(self, order: OrderOut, previous: OrderStatus) -> None:
        try:
            await self._bot.send_message(order.user_id, status_update(order))
        except TelegramAPIError:
            log.exception("failed to notify user %s about order %s", order.user_id, order.id)
