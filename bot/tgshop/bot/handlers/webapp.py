"""Orders sent by the Mini App via ``Telegram.WebApp.sendData`` (keyboard-button launch).

``web_app_data`` arrives as a regular message from the user, so Telegram already guarantees
who sent it — no initData check is needed here, unlike the REST API.
"""

from __future__ import annotations

import logging

from aiogram import F, Router
from aiogram.types import Message
from pydantic import ValidationError

from tgshop.bot import texts
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderSource, OrderStatus
from tgshop.domain.errors import DomainError
from tgshop.domain.schemas import OrderCreate
from tgshop.services.orders import Customer, OrderService

log = logging.getLogger(__name__)


async def order_from_web_app(
    message: Message, order_service: OrderService, catalog: Catalog
) -> None:
    if message.web_app_data is None or message.from_user is None:
        return
    user = message.from_user
    try:
        data = OrderCreate.model_validate_json(message.web_app_data.data)
        order = await order_service.create_order(
            Customer(user_id=user.id, username=user.username, language=user.language_code),
            data,
            source=OrderSource.WEB_APP_DATA,
        )
    except ValidationError:
        log.info("rejected malformed web_app_data from %s", user.id)
        await message.answer("Не получилось прочитать заказ. Попробуйте оформить его ещё раз.")
        return
    except DomainError as exc:
        await message.answer(f"Заказ не оформлен: {exc.message}")
        return

    await message.answer("Спасибо! Заказ принят 🙌\n\n" + texts.order_summary(order, catalog))
    if order.status is OrderStatus.AWAITING_PAYMENT:
        await order_service.send_invoice(message.chat.id, order)


def create_router() -> Router:
    router = Router(name="webapp")
    router.message.register(order_from_web_app, F.web_app_data)
    return router
