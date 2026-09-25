"""Bot tests run real updates through the real Dispatcher (routing, filters, DI), with a
recording session instead of the network."""

from __future__ import annotations

import json
from collections.abc import AsyncGenerator
from datetime import UTC, datetime
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.methods import AnswerCallbackQuery, AnswerPreCheckoutQuery, SendMessage
from aiogram.methods.base import TelegramMethod, TelegramType
from aiogram.types import Update

from tgshop.bot.factory import create_dispatcher
from tgshop.bot.keyboards import OrderAction, admin_order
from tgshop.bot.texts import money
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderSource, OrderStatus
from tgshop.domain.schemas import OrderCreate
from tgshop.payments import make_payload
from tgshop.services.orders import Customer, OrderService

from .conftest import BOT_TOKEN, USER_ID, FakePayments, order_payload

ADMIN_ID = 900_000_001
WEBAPP_URL = "https://sinnercode228.github.io/tg-shop-miniapp/"


class RecordingSession(BaseSession):
    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109 - aiogram signature
    ) -> TelegramType:
        self.calls.append(method)
        return True  # type: ignore[return-value]  # handlers ignore API results

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    async def close(self) -> None:
        return None

    def sent(self, kind: type[TelegramMethod[Any]]) -> list[Any]:
        return [c for c in self.calls if isinstance(c, kind)]


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(session: RecordingSession) -> Bot:
    return Bot(BOT_TOKEN, session=session)


@pytest.fixture
def dp(service: OrderService, catalog: Catalog) -> Dispatcher:
    return create_dispatcher(
        order_service=service, catalog=catalog, admin_ids=[ADMIN_ID], webapp_url=WEBAPP_URL
    )


def _user(user_id: int) -> dict[str, Any]:
    return {"id": user_id, "is_bot": False, "first_name": "Анна", "language_code": "ru"}


def message_update(user_id: int, **fields: Any) -> Update:
    now = int(datetime.now(UTC).timestamp())
    message = {
        "message_id": 1,
        "date": now,
        "chat": {"id": user_id, "type": "private"},
        "from": _user(user_id),
        **fields,
    }
    return Update.model_validate({"update_id": 1, "message": message})


def command(user_id: int, text: str) -> Update:
    entity = {"type": "bot_command", "offset": 0, "length": len(text.split(maxsplit=1)[0])}
    return message_update(user_id, text=text, entities=[entity])


async def test_start_offers_the_mini_app(
    dp: Dispatcher, bot: Bot, session: RecordingSession
) -> None:
    await dp.feed_update(bot, command(USER_ID, "/start"))
    messages = session.sent(SendMessage)
    assert len(messages) == 2
    inline = messages[0].reply_markup.inline_keyboard[0][0]
    assert inline.web_app.url == WEBAPP_URL
    reply = messages[1].reply_markup.keyboard[0][0]
    assert reply.web_app.url == WEBAPP_URL


async def test_web_app_data_creates_order(
    dp: Dispatcher, bot: Bot, session: RecordingSession, service: OrderService
) -> None:
    data = json.dumps(order_payload(), ensure_ascii=False)
    update = message_update(USER_ID, web_app_data={"data": data, "button_text": "Магазин"})
    await dp.feed_update(bot, update)

    [order] = await service.list_for_user(USER_ID)
    assert order.source is OrderSource.WEB_APP_DATA
    assert order.status is OrderStatus.NEW
    # confirmation to the customer + notification to the admin come from different layers
    [reply] = session.sent(SendMessage)
    assert "Заказ принят" in reply.text


async def test_web_app_data_stars_order_sends_invoice(
    dp: Dispatcher, bot: Bot, payments: FakePayments
) -> None:
    data = json.dumps(order_payload(paymentMethod="stars"))
    await dp.feed_update(
        bot, message_update(USER_ID, web_app_data={"data": data, "button_text": "x"})
    )
    [(chat_id, invoice)] = payments.sent
    assert chat_id == USER_ID
    assert invoice.amount > 0


async def test_malformed_web_app_data_is_reported(
    dp: Dispatcher, bot: Bot, session: RecordingSession
) -> None:
    update = message_update(USER_ID, web_app_data={"data": "{broken", "button_text": "x"})
    await dp.feed_update(bot, update)
    [reply] = session.sent(SendMessage)
    assert "Не получилось" in reply.text


async def test_pre_checkout_is_validated(
    dp: Dispatcher, bot: Bot, session: RecordingSession, service: OrderService
) -> None:
    created = await service.place_order(
        Customer(user_id=USER_ID), OrderCreate.model_validate(order_payload(paymentMethod="stars"))
    )
    order = created.order
    for amount in (order.stars_amount, 1):
        update = Update.model_validate(
            {
                "update_id": 2,
                "pre_checkout_query": {
                    "id": f"q{amount}",
                    "from": _user(USER_ID),
                    "currency": "XTR",
                    "total_amount": amount,
                    "invoice_payload": make_payload(order.id),
                },
            }
        )
        await dp.feed_update(bot, update)

    ok, rejected = session.sent(AnswerPreCheckoutQuery)
    assert ok.ok is True
    assert rejected.ok is False
    assert rejected.error_message


async def test_successful_payment_marks_order_paid(
    dp: Dispatcher, bot: Bot, service: OrderService
) -> None:
    created = await service.place_order(
        Customer(user_id=USER_ID), OrderCreate.model_validate(order_payload(paymentMethod="stars"))
    )
    payment = {
        "currency": "XTR",
        "total_amount": created.order.stars_amount,
        "invoice_payload": make_payload(created.order.id),
        "telegram_payment_charge_id": "tg-charge-42",
        "provider_payment_charge_id": "",
    }
    await dp.feed_update(bot, message_update(USER_ID, successful_payment=payment))
    order = await service.get(created.order.id)
    assert order is not None
    assert order.status is OrderStatus.PAID


async def test_admin_commands_are_admin_only(
    dp: Dispatcher, bot: Bot, session: RecordingSession, service: OrderService
) -> None:
    order = await service.create_order(
        Customer(user_id=USER_ID),
        OrderCreate.model_validate(order_payload()),
        source=OrderSource.API,
    )

    await dp.feed_update(bot, command(USER_ID, f"/status {order.id} confirmed"))
    assert session.sent(SendMessage) == [], "non-admins are ignored"
    assert (await service.get(order.id)).status is OrderStatus.NEW  # type: ignore[union-attr]

    await dp.feed_update(bot, command(ADMIN_ID, f"/status {order.id} confirmed"))
    assert (await service.get(order.id)).status is OrderStatus.CONFIRMED  # type: ignore[union-attr]
    texts = [m.text for m in session.sent(SendMessage)]
    assert any("Подтверждён" in t for t in texts)

    await dp.feed_update(bot, command(ADMIN_ID, "/status 1 flying"))
    assert "Использование" in session.sent(SendMessage)[-1].text


async def test_admin_orders_listing(
    dp: Dispatcher, bot: Bot, session: RecordingSession, service: OrderService
) -> None:
    await service.create_order(
        Customer(user_id=USER_ID),
        OrderCreate.model_validate(order_payload()),
        source=OrderSource.API,
    )
    await dp.feed_update(bot, command(ADMIN_ID, "/orders"))
    [card] = session.sent(SendMessage)
    assert "Заказ №1" in card.text
    assert "+79000000000" in card.text, "admins see contact details"


async def test_admin_inline_buttons_change_status(
    dp: Dispatcher, bot: Bot, session: RecordingSession, service: OrderService
) -> None:
    order = await service.create_order(
        Customer(user_id=USER_ID),
        OrderCreate.model_validate(order_payload()),
        source=OrderSource.API,
    )
    data = OrderAction(order_id=order.id, status=OrderStatus.CONFIRMED).pack()
    update = Update.model_validate(
        {
            "update_id": 3,
            "callback_query": {
                "id": "cb1",
                "from": _user(ADMIN_ID),
                "chat_instance": "ci",
                "data": data,
            },
        }
    )
    await dp.feed_update(bot, update)
    assert (await service.get(order.id)).status is OrderStatus.CONFIRMED  # type: ignore[union-attr]
    assert session.sent(AnswerCallbackQuery)


async def test_admin_keyboard_offers_only_valid_transitions(service: OrderService) -> None:
    order = await service.create_order(
        Customer(user_id=USER_ID),
        OrderCreate.model_validate(order_payload()),
        source=OrderSource.API,
    )
    keyboard = admin_order(order)
    assert keyboard is not None
    statuses = {
        OrderAction.unpack(button.callback_data).status  # type: ignore[arg-type]
        for row in keyboard.inline_keyboard
        for button in row
    }
    assert statuses == {OrderStatus.CONFIRMED, OrderStatus.CANCELLED}


@pytest.mark.parametrize(
    ("kopecks", "text"),
    [(0, "0 ₽"), (35000, "350 ₽"), (272000, "2 720 ₽"), (12345, "123,45 ₽")],
)
def test_money_format(kopecks: int, text: str) -> None:
    assert money(kopecks) == text
