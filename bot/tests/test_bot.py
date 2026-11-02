"""Bot tests run real updates through the real Dispatcher (routing, filters, DI), with a
recording session instead of the network."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest
from aiogram import Bot, Dispatcher
from aiogram.methods import (
    AnswerCallbackQuery,
    AnswerPreCheckoutQuery,
    CreateInvoiceLink,
    RefundStarPayment,
    SendInvoice,
    SendMessage,
)
from aiogram.types import Update
from aiogram_stars import (
    PayloadSigner,
    PaymentStatus,
    RefundPolicy,
    RefundStatus,
    StarsPayments,
)
from aiogram_stars.sqlalchemy import SqlAlchemyStorage
from sqlalchemy.ext.asyncio import AsyncEngine

from tgshop.bot.keyboards import OrderAction, admin_order
from tgshop.bot.notifier import TelegramNotifier
from tgshop.bot.texts import CHECKOUT_ERROR, money, status_update
from tgshop.config import Settings
from tgshop.container import build_container
from tgshop.db.session import SessionFactory, init_models
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderSource, OrderStatus
from tgshop.domain.pricing import PricingRules
from tgshop.domain.schemas import OrderCreate, OrderOut
from tgshop.payments import TelegramStarsGateway, build_invoice
from tgshop.services.expiry import UnpaidOrderExpiry
from tgshop.services.notifier import NullNotifier
from tgshop.services.orders import Customer, OrderService

from .conftest import (
    ADMIN_ID,
    BOT_TOKEN,
    STARS_SECRET,
    USER_ID,
    WEBAPP_URL,
    Clock,
    FakeNotifier,
    FakePayments,
    RecordingSession,
    Telegram,
    _user,
    add_refund_fails_once,
    make_stars,
    message_update,
    order_payload,
    payment_update,
)


@pytest.fixture
def telegram_outbox(
    bot: Bot, engine: AsyncEngine, session_factory: SessionFactory, catalog: Catalog, clock: Clock
) -> StarsPayments:
    """Sends the refunds in the shop's database, and their messages, through ``bot``."""
    return make_stars(
        engine,
        session_factory,
        TelegramNotifier(bot, catalog, [ADMIN_ID]),
        clock,
        RefundPolicy(max_attempts=2, first_delay=timedelta(seconds=30)),
    )


async def stars_order(service: OrderService) -> OrderOut:
    data = OrderCreate.model_validate(order_payload(paymentMethod="stars"))
    return (await service.place_order(Customer(user_id=USER_ID), data)).order


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


async def test_invoice_payload_is_signed_for_the_order_and_its_amount(
    bot: Bot, session: RecordingSession, service: OrderService, stars: StarsPayments
) -> None:
    order = await stars_order(service)
    gateway = TelegramStarsGateway(bot, stars)

    await gateway.create_invoice_link(build_invoice(order))
    await gateway.send_invoice(USER_ID, build_invoice(order))

    [link] = session.sent(CreateInvoiceLink)
    [message] = session.sent(SendInvoice)
    for invoice in (link, message):
        assert invoice.currency == "XTR"
        assert [price.amount for price in invoice.prices] == [order.stars_amount]
        signed_for = PayloadSigner(STARS_SECRET).verify(invoice.payload, order.stars_amount or 0)
        assert signed_for == str(order.id)
    assert message.chat_id == USER_ID


async def test_pre_checkout_declines_a_payload_the_bot_did_not_sign(
    dp: Dispatcher, bot: Bot, session: RecordingSession, service: OrderService
) -> None:
    order = await stars_order(service)
    # Any invoice made with the bot token could carry this payload, at any price.
    query = {
        "id": "q1",
        "from": _user(USER_ID),
        "currency": "XTR",
        "total_amount": order.stars_amount,
        "invoice_payload": f"order:{order.id}",
    }

    await dp.feed_update(bot, Update.model_validate({"update_id": 2, "pre_checkout_query": query}))

    [answer] = session.sent(AnswerPreCheckoutQuery)
    assert (answer.ok, answer.error_message) == (False, CHECKOUT_ERROR)


async def test_redelivered_successful_payment_pays_the_order_once(
    dp: Dispatcher,
    bot: Bot,
    session: RecordingSession,
    service: OrderService,
    stars: StarsPayments,
    notifier: FakeNotifier,
) -> None:
    order = await stars_order(service)
    update = payment_update(stars, order, "tg-charge-42")

    await dp.feed_update(bot, update)
    await dp.feed_update(bot, update)  # Telegram sent it again

    [thanks] = session.sent(SendMessage)
    assert thanks.text == f"Оплата получена, заказ №{order.id} передан в работу 💫"
    assert len(notifier.placed) == 1, "admins hear about the payment once"
    payment = await stars.get_payment("tg-charge-42")
    assert payment is not None
    assert (payment.status, payment.order_id) == (PaymentStatus.ACCEPTED, str(order.id))


async def test_pre_checkout_for_a_cancelled_order_says_why(
    dp: Dispatcher,
    bot: Bot,
    session: RecordingSession,
    service: OrderService,
    stars: StarsPayments,
) -> None:
    order = await service.change_status((await stars_order(service)).id, OrderStatus.CANCELLED)
    amount = order.stars_amount or 0
    query = {
        "id": "q1",
        "from": _user(USER_ID),
        "currency": "XTR",
        "total_amount": amount,
        "invoice_payload": stars.make_payload(order.id, amount),
    }

    await dp.feed_update(bot, Update.model_validate({"update_id": 2, "pre_checkout_query": query}))

    [answer] = session.sent(AnswerPreCheckoutQuery)
    assert (answer.ok, answer.error_message) == (False, "Заказ уже оплачен или отменён")


async def test_payment_stays_accepted_when_the_reply_to_the_buyer_fails(
    telegram: Telegram, session: RecordingSession, service: OrderService
) -> None:
    order = await stars_order(service)
    session.refuse(SendMessage, "Forbidden: bot was blocked by the user")

    payment = await telegram.pay(order, "tg-charge-42")

    assert payment.status is PaymentStatus.ACCEPTED, "nobody has to settle it by hand"
    paid = await service.get(order.id)
    assert paid is not None
    assert paid.status is OrderStatus.PAID


async def test_pre_checkout_is_validated(
    dp: Dispatcher,
    bot: Bot,
    session: RecordingSession,
    service: OrderService,
    stars: StarsPayments,
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
                    "invoice_payload": stars.make_payload(order.id, order.stars_amount or 0),
                },
            }
        )
        await dp.feed_update(bot, update)

    ok, rejected = session.sent(AnswerPreCheckoutQuery)
    assert ok.ok is True
    assert rejected.ok is False
    assert rejected.error_message


async def test_successful_payment_marks_order_paid(
    dp: Dispatcher, bot: Bot, service: OrderService, stars: StarsPayments
) -> None:
    created = await service.place_order(
        Customer(user_id=USER_ID), OrderCreate.model_validate(order_payload(paymentMethod="stars"))
    )
    await dp.feed_update(bot, payment_update(stars, created.order, "tg-charge-42"))
    order = await service.get(created.order.id)
    assert order is not None
    assert order.status is OrderStatus.PAID


async def expire_unpaid_orders(service: OrderService, order: OrderOut) -> list[OrderOut]:
    an_hour_later = order.created_at + timedelta(hours=1)
    expiry = UnpaidOrderExpiry(service, ttl=timedelta(minutes=30), clock=lambda: an_hour_later)
    return await expiry.run_once()


async def test_payment_for_an_expired_order_is_refunded_and_explained(
    dp: Dispatcher,
    bot: Bot,
    session: RecordingSession,
    service: OrderService,
    stars: StarsPayments,
    telegram_outbox: StarsPayments,
) -> None:
    created = await service.place_order(
        Customer(user_id=USER_ID), OrderCreate.model_validate(order_payload(paymentMethod="stars"))
    )
    await expire_unpaid_orders(service, created.order)

    await dp.feed_update(bot, payment_update(stars, created.order, "tg-charge-late"))
    assert session.sent(RefundStarPayment) == [], "the outbox calls it after the commit"
    assert session.sent(SendMessage) == [], "nothing is promised before the Stars are back"
    await telegram_outbox.send_due_refunds(bot)

    [refund] = session.sent(RefundStarPayment)
    assert (refund.user_id, refund.telegram_payment_charge_id) == (USER_ID, "tg-charge-late")
    [reply] = session.sent(SendMessage)
    assert reply.chat_id == USER_ID
    assert reply.text == "Платёж не принят (Заказ уже оплачен или отменён). Звёзды возвращены."
    order = await service.get(created.order.id)
    assert order is not None
    assert order.status is OrderStatus.CANCELLED


async def test_payment_whose_payload_did_not_verify_is_refunded_and_explained_in_russian(
    dp: Dispatcher,
    bot: Bot,
    session: RecordingSession,
    service: OrderService,
    stars: StarsPayments,
    telegram_outbox: StarsPayments,
) -> None:
    order = await stars_order(service)
    amount = order.stars_amount or 0
    # Signed with another secret, e.g. an invoice sent before STARS_SECRET was changed.
    payload = PayloadSigner("an-earlier-secret-of-this-bot").sign(order.id, amount)
    payment = {
        "currency": "XTR",
        "total_amount": amount,
        "invoice_payload": payload,
        "telegram_payment_charge_id": "tg-charge-unsigned",
        "provider_payment_charge_id": "",
    }

    await dp.feed_update(bot, message_update(USER_ID, successful_payment=payment))
    await telegram_outbox.send_due_refunds(bot)

    [refund] = session.sent(RefundStarPayment)
    assert refund.telegram_payment_charge_id == "tg-charge-unsigned"
    [reply] = session.sent(SendMessage)
    assert reply.text == "Платёж не принят (Счёт не прошёл проверку). Звёзды возвращены."


async def test_expired_order_is_announced_to_the_customer_and_the_admins(
    bot: Bot,
    session: RecordingSession,
    session_factory: SessionFactory,
    catalog: Catalog,
    rules: PricingRules,
    stars: StarsPayments,
) -> None:
    service = OrderService(
        session_factory=session_factory,
        catalog=catalog,
        rules=rules,
        notifier=TelegramNotifier(bot, catalog, [ADMIN_ID]),
        payments=FakePayments(),
        refunds=stars,
    )
    created = await service.place_order(
        Customer(user_id=USER_ID), OrderCreate.model_validate(order_payload(paymentMethod="stars"))
    )

    [expired] = await expire_unpaid_orders(service, created.order)

    to_customer, to_admin = session.sent(SendMessage)
    assert to_customer.chat_id == USER_ID
    assert to_customer.text == status_update(expired), "the same text as after a manual cancel"
    assert to_admin.chat_id == ADMIN_ID
    assert "Заказ не оплачен" in to_admin.text
    assert f"Заказ №{expired.id}</b> · ✖️ Отменён" in to_admin.text
    assert "+79000000000" in to_admin.text, "admins see who abandoned the order"


async def paid_order(service: OrderService) -> OrderOut:
    created = await service.place_order(
        Customer(user_id=USER_ID), OrderCreate.model_validate(order_payload(paymentMethod="stars"))
    )
    return await service.mark_paid(
        order_id=created.order.id,
        total_amount=created.order.stars_amount or 0,
        payer_id=USER_ID,
        charge_id="tg-charge-1",
    )


async def test_charge_that_telegram_already_refunded_counts_as_done(
    bot: Bot, session: RecordingSession, service: OrderService, telegram_outbox: StarsPayments
) -> None:
    refunded = await service.refund((await paid_order(service)).id)
    # An earlier attempt went through, but its answer never reached the bot.
    session.refuse(RefundStarPayment, "Bad Request: CHARGE_ALREADY_REFUNDED")

    [refund] = await telegram_outbox.send_due_refunds(bot)

    assert (refund.status, refund.attempts) == (RefundStatus.DONE, 1)
    [call] = session.sent(RefundStarPayment)
    assert (call.user_id, call.telegram_payment_charge_id) == (USER_ID, "tg-charge-1")
    [to_customer] = session.sent(SendMessage)
    assert to_customer.chat_id == USER_ID
    assert to_customer.text == status_update(refunded), "the same text as before the outbox"


async def test_refund_telegram_keeps_refusing_is_handed_to_the_admins(
    bot: Bot,
    session: RecordingSession,
    service: OrderService,
    telegram_outbox: StarsPayments,
    clock: Clock,
) -> None:
    order = await service.refund((await paid_order(service)).id)
    session.refuse(RefundStarPayment, "Bad Request: CHARGE_NOT_FOUND")

    [first] = await telegram_outbox.send_due_refunds(bot)
    assert first.status is RefundStatus.PENDING
    assert session.sent(SendMessage) == []
    clock.advance(seconds=30)
    [refund] = await telegram_outbox.send_due_refunds(bot)

    assert refund.status is RefundStatus.FAILED
    assert len(session.sent(RefundStarPayment)) == 2
    [to_admin] = session.sent(SendMessage)
    assert to_admin.chat_id == ADMIN_ID
    assert "Возврат звёзд не прошёл" in to_admin.text
    assert f"Заказ №{order.id} · {order.stars_amount} ⭐" in to_admin.text
    assert "<code>tg-charge-1</code>" in to_admin.text, "admins can find the charge"
    assert "CHARGE_NOT_FOUND" in to_admin.text
    assert f"tg://user?id={USER_ID}" in to_admin.text


async def test_admin_refund_command_records_the_refund(
    dp: Dispatcher,
    bot: Bot,
    session: RecordingSession,
    service: OrderService,
    telegram_outbox: StarsPayments,
) -> None:
    order = await paid_order(service)

    await dp.feed_update(bot, command(ADMIN_ID, "/refund"))
    await dp.feed_update(bot, command(ADMIN_ID, "/refund 999"))
    await dp.feed_update(bot, command(ADMIN_ID, f"/refund {order.id}"))
    usage, missing, accepted = (m.text for m in session.sent(SendMessage))
    assert usage == "Использование: /refund <id>"
    assert missing.startswith("Возврат не выполнен")
    assert accepted.startswith(f"Возврат по заказу №{order.id} оформлен")
    assert session.sent(RefundStarPayment) == []
    refunded = await service.get(order.id)
    assert refunded is not None
    assert refunded.status is OrderStatus.REFUNDED

    session.calls.clear()
    await telegram_outbox.send_due_refunds(bot)

    [call] = session.sent(RefundStarPayment)
    assert call.telegram_payment_charge_id == "tg-charge-1"
    [to_customer] = session.sent(SendMessage)
    assert (to_customer.chat_id, to_customer.text) == (USER_ID, status_update(refunded))


async def test_admin_is_told_when_a_refund_could_not_be_queued(
    dp: Dispatcher,
    bot: Bot,
    session: RecordingSession,
    service: OrderService,
    telegram_outbox: StarsPayments,
    monkeypatch: pytest.MonkeyPatch,
    caplog: pytest.LogCaptureFixture,
) -> None:
    order = await paid_order(service)
    add_refund_fails_once(monkeypatch)

    with caplog.at_level(logging.ERROR, logger="tgshop"):
        await dp.feed_update(bot, command(ADMIN_ID, f"/refund {order.id}"))
    [failed] = session.sent(SendMessage)
    assert failed.text == (
        f"Возврат по заказу №{order.id} не поставлен в очередь из-за ошибки. "
        f"Повторите /refund {order.id}."
    )
    assert "database is locked" in caplog.text

    await dp.feed_update(bot, command(ADMIN_ID, f"/refund {order.id}"))
    accepted = session.sent(SendMessage)[-1]
    assert accepted.text.startswith(f"Возврат по заказу №{order.id} оформлен")
    await telegram_outbox.send_due_refunds(bot)
    [call] = session.sent(RefundStarPayment)
    assert call.telegram_payment_charge_id == "tg-charge-1"


async def test_admin_button_says_so_when_a_refund_could_not_be_queued(
    dp: Dispatcher,
    bot: Bot,
    session: RecordingSession,
    service: OrderService,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    order = await paid_order(service)
    add_refund_fails_once(monkeypatch)
    data = OrderAction(order_id=order.id, status=OrderStatus.REFUNDED).pack()
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

    [answer] = session.sent(AnswerCallbackQuery)
    assert answer.show_alert is True
    assert (
        answer.text == f"Возврат не поставлен в очередь из-за ошибки. Повторите /refund {order.id}."
    )


async def test_bot_sends_an_admin_refund_right_after_it_is_recorded(
    session: RecordingSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    # STARS_ENABLED=false stops new Stars payments; charges taken before still go back.
    settings = Settings(
        _env_file=None,
        bot_token=BOT_TOKEN,
        stars_secret=STARS_SECRET,
        database_url=f"sqlite+aiosqlite:///{tmp_path / 'shop.db'}",
        stars_enabled=False,
        order_payment_ttl_minutes=0,
    )
    container = build_container(settings)
    container.bot.session = session
    await init_models(container.engine)
    paid_before = OrderService(
        session_factory=container.session_factory,
        catalog=container.catalog,
        rules=container.rules,
        notifier=NullNotifier(),
        payments=FakePayments(),
        refunds=container.stars,
    )
    order = await paid_order(paid_before)

    claim = SqlAlchemyStorage.claim_refund
    order_refunded = TelegramNotifier.order_refunded
    swept, told = asyncio.Event(), asyncio.Event()

    async def claim_then_signal(self: SqlAlchemyStorage, **kwargs: Any) -> Any:
        found = await claim(self, **kwargs)
        if found is None:
            swept.set()
        return found

    async def order_refunded_then_signal(self: TelegramNotifier, order: OrderOut) -> None:
        await order_refunded(self, order)
        told.set()

    monkeypatch.setattr(SqlAlchemyStorage, "claim_refund", claim_then_signal)
    monkeypatch.setattr(TelegramNotifier, "order_refunded", order_refunded_then_signal)
    dp = container.dispatcher()
    await dp.emit_startup(bot=container.bot)
    try:
        async with asyncio.timeout(5):
            await swept.wait()  # the sweep at startup, before there is anything to send
            refunded = await container.order_service.refund(order.id)
            # The next sweep is 10 s away: only the wake gets the refund out in time.
            await told.wait()
    finally:
        await dp.emit_shutdown()
        await container.aclose()

    [call] = session.sent(RefundStarPayment)
    assert (call.user_id, call.telegram_payment_charge_id) == (USER_ID, "tg-charge-1")
    [to_customer] = session.sent(SendMessage)
    assert (to_customer.chat_id, to_customer.text) == (USER_ID, status_update(refunded))


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
