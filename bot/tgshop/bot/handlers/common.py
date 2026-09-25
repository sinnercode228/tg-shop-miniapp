from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from tgshop.bot import texts
from tgshop.bot.keyboards import shop_inline, shop_reply
from tgshop.domain.catalog import Catalog
from tgshop.services.orders import OrderService


async def start(message: Message, webapp_url: str) -> None:
    await message.answer(texts.WELCOME, reply_markup=shop_inline(webapp_url))
    await message.answer(
        "Кнопка «☕ Магазин» теперь всегда под рукой 👇", reply_markup=shop_reply(webapp_url)
    )


async def help_(message: Message) -> None:
    await message.answer(texts.HELP)


async def pay_support(message: Message) -> None:
    # Required by Telegram for bots that accept Stars.
    await message.answer(texts.PAY_SUPPORT)


async def my_orders(message: Message, order_service: OrderService, catalog: Catalog) -> None:
    if message.from_user is None:
        return
    orders = await order_service.list_for_user(message.from_user.id, limit=5)
    if not orders:
        await message.answer("Заказов пока нет — самое время выбрать кофе ☕")
        return
    await message.answer("\n\n".join(texts.order_summary(o, catalog) for o in orders))


def create_router() -> Router:
    router = Router(name="common")
    router.message.register(start, CommandStart())
    router.message.register(help_, Command("help"))
    router.message.register(pay_support, Command("paysupport"))
    router.message.register(my_orders, Command("myorders"))
    return router
