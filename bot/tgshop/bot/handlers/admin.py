from __future__ import annotations

from aiogram import Router
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InaccessibleMessage, Message

from tgshop.bot import texts
from tgshop.bot.filters import IsAdmin
from tgshop.bot.keyboards import OrderAction, admin_order
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderStatus
from tgshop.domain.errors import DomainError
from tgshop.services.orders import OrderService

ACTIVE = (
    OrderStatus.NEW,
    OrderStatus.PAID,
    OrderStatus.CONFIRMED,
    OrderStatus.IN_DELIVERY,
    OrderStatus.READY_FOR_PICKUP,
)


def parse_status_args(args: str | None) -> tuple[int, OrderStatus]:
    """``"42 confirmed"`` → ``(42, OrderStatus.CONFIRMED)``; raises ``ValueError``."""
    parts = (args or "").split()
    if len(parts) != 2 or not parts[0].lstrip("#").isdecimal():
        raise ValueError("usage: /status <id> <status>")
    return int(parts[0].lstrip("#")), OrderStatus(parts[1].lower())


async def admin_help(message: Message) -> None:
    await message.answer(texts.ADMIN_HELP)


async def list_orders(
    message: Message, command: CommandObject, order_service: OrderService, catalog: Catalog
) -> None:
    arg = (command.args or "").strip().lower()
    if arg == "all":
        statuses: tuple[OrderStatus, ...] | None = None
    elif arg:
        try:
            statuses = (OrderStatus(arg),)
        except ValueError:
            await message.answer(f"Неизвестный статус «{arg}».\n\n{texts.ADMIN_HELP}")
            return
    else:
        statuses = ACTIVE
    orders = await order_service.list_recent(statuses=statuses, limit=10)
    if not orders:
        await message.answer("Заказов с таким статусом нет.")
        return
    for order in orders:
        await message.answer(
            texts.order_summary(order, catalog, for_admin=True), reply_markup=admin_order(order)
        )


async def show_order(
    message: Message, command: CommandObject, order_service: OrderService, catalog: Catalog
) -> None:
    arg = (command.args or "").strip().lstrip("#")
    order = await order_service.get(int(arg)) if arg.isdecimal() else None
    if order is None:
        await message.answer("Заказ не найден. Использование: /order <id>")
        return
    await message.answer(
        texts.order_summary(order, catalog, for_admin=True), reply_markup=admin_order(order)
    )


async def set_status(message: Message, command: CommandObject, order_service: OrderService) -> None:
    try:
        order_id, status = parse_status_args(command.args)
    except ValueError:
        await message.answer("Использование: /status <id> <статус>\n\n" + texts.ADMIN_HELP)
        return
    try:
        order = await order_service.change_status(order_id, status)
    except DomainError as exc:
        await message.answer(f"Не получилось: {exc.message}")
        return
    await message.answer(texts.status_update(order), reply_markup=admin_order(order))


async def refund(message: Message, command: CommandObject, order_service: OrderService) -> None:
    arg = (command.args or "").strip().lstrip("#")
    if not arg.isdecimal():
        await message.answer("Использование: /refund <id>")
        return
    try:
        order = await order_service.refund(int(arg))
    except DomainError as exc:
        await message.answer(f"Возврат не выполнен: {exc.message}")
        return
    await message.answer(f"Звёзды по заказу №{order.id} возвращены покупателю.")


async def on_order_action(
    query: CallbackQuery,
    callback_data: OrderAction,
    order_service: OrderService,
    catalog: Catalog,
) -> None:
    try:
        order = await order_service.change_status(callback_data.order_id, callback_data.status)
    except DomainError as exc:
        await query.answer(exc.message, show_alert=True)
        return
    await query.answer(texts.STATUS_LABELS[order.status])
    if query.message is not None and not isinstance(query.message, InaccessibleMessage):
        await query.message.edit_text(
            texts.order_summary(order, catalog, for_admin=True), reply_markup=admin_order(order)
        )


def create_router() -> Router:
    router = Router(name="admin")
    router.message.filter(IsAdmin())
    router.callback_query.filter(IsAdmin())
    router.message.register(admin_help, Command("admin"))
    router.message.register(list_orders, Command("orders"))
    router.message.register(show_order, Command("order"))
    router.message.register(set_status, Command("status"))
    router.message.register(refund, Command("refund"))
    router.callback_query.register(on_order_action, OrderAction.filter())
    return router
