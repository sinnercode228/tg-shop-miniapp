from __future__ import annotations

from collections.abc import Iterable

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand, BotCommandScopeChat, MenuButtonWebApp, WebAppInfo

from tgshop.domain.catalog import Catalog
from tgshop.services.orders import OrderService

from .handlers import admin, common, payments, webapp


def create_bot(token: str) -> Bot:
    return Bot(token=token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))


def create_dispatcher(
    *,
    order_service: OrderService,
    catalog: Catalog,
    admin_ids: Iterable[int],
    webapp_url: str,
) -> Dispatcher:
    # Keyword arguments become "workflow data" and are injected into handlers/filters by name.
    dp = Dispatcher(
        order_service=order_service,
        catalog=catalog,
        admin_ids=frozenset(admin_ids),
        webapp_url=webapp_url,
    )
    # Payments first: pre-checkout queries must be answered fast and never be shadowed.
    dp.include_routers(
        payments.create_router(),
        admin.create_router(),
        webapp.create_router(),
        common.create_router(),
    )
    return dp


USER_COMMANDS = [
    BotCommand(command="start", description="Открыть магазин"),
    BotCommand(command="myorders", description="Мои заказы"),
    BotCommand(command="paysupport", description="Помощь с оплатой"),
    BotCommand(command="help", description="Справка"),
]
ADMIN_COMMANDS = [
    *USER_COMMANDS,
    BotCommand(command="orders", description="Активные заказы"),
    BotCommand(command="status", description="Сменить статус: /status <id> <статус>"),
    BotCommand(command="refund", description="Вернуть Stars: /refund <id>"),
    BotCommand(command="admin", description="Справка администратора"),
]


async def setup_bot_ui(bot: Bot, *, webapp_url: str, admin_ids: Iterable[int]) -> None:
    """Commands menu + the persistent «Магазин» button next to the input field."""
    await bot.set_my_commands(USER_COMMANDS)
    for admin_id in admin_ids:
        await bot.set_my_commands(ADMIN_COMMANDS, scope=BotCommandScopeChat(chat_id=admin_id))
    await bot.set_chat_menu_button(
        menu_button=MenuButtonWebApp(text="Магазин", web_app=WebAppInfo(url=webapp_url))
    )
