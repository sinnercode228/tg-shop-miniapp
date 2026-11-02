from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncGenerator, AsyncIterator, Coroutine
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import httpx
import pytest
from aiogram import Bot, Dispatcher
from aiogram.client.session.base import BaseSession
from aiogram.exceptions import TelegramBadRequest
from aiogram.methods import RefundStarPayment
from aiogram.methods.base import TelegramMethod, TelegramType
from aiogram.types import Update
from aiogram_stars import Payment, Refund, RefundPolicy, StarsPayments
from aiogram_stars.sqlalchemy import SqlAlchemyStorage
from sqlalchemy.exc import OperationalError
from sqlalchemy.ext.asyncio import AsyncEngine

from tgshop.api.app import create_app
from tgshop.api.context import ApiContext
from tgshop.bot.factory import create_dispatcher
from tgshop.bot.handlers.payments import create_stars
from tgshop.db.models import Order, utcnow
from tgshop.db.repository import OrderRepository
from tgshop.db.session import SessionFactory, create_engine, create_session_factory, init_models
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderStatus
from tgshop.domain.pricing import PricingRules
from tgshop.domain.schemas import OrderOut
from tgshop.payments import Invoice
from tgshop.security.init_data import sign_init_data
from tgshop.services.notifier import Notifier
from tgshop.services.orders import OrderService
from tgshop.services.refunds import RefundNotices, RefundOut

BOT_TOKEN = "7000000001:AAtest-token-used-only-in-unit-tests"
STARS_SECRET = "stars-secret-used-only-in-unit-tests"
SHARED = Path(__file__).resolve().parents[2] / "shared"
USER_ID = 111_222_333
OTHER_USER_ID = 444_555_666
ADMIN_ID = 900_000_001
WEBAPP_URL = "https://sinnercode228.github.io/tg-shop-miniapp/"


class FakeNotifier:
    def __init__(self) -> None:
        self.placed: list[OrderOut] = []
        self.changes: list[tuple[OrderOut, OrderStatus]] = []
        self.expired: list[OrderOut] = []
        self.refunded: list[OrderOut] = []
        self.returned: list[tuple[int, str]] = []
        self.failed_refunds: list[RefundOut] = []

    async def order_placed(self, order: OrderOut) -> None:
        self.placed.append(order)

    async def status_changed(self, order: OrderOut, previous: OrderStatus) -> None:
        self.changes.append((order, previous))

    async def order_expired(self, order: OrderOut) -> None:
        self.expired.append(order)

    async def order_refunded(self, order: OrderOut) -> None:
        self.refunded.append(order)

    async def payment_returned(self, user_id: int, reason: str) -> None:
        self.returned.append((user_id, reason))

    async def refund_failed(self, refund: RefundOut) -> None:
        self.failed_refunds.append(refund)


class FakePayments:
    def __init__(self) -> None:
        self.links: list[Invoice] = []
        self.sent: list[tuple[int, Invoice]] = []

    async def create_invoice_link(self, invoice: Invoice) -> str:
        self.links.append(invoice)
        return f"https://t.me/$demo-invoice-{invoice.order_id}"

    async def send_invoice(self, chat_id: int, invoice: Invoice) -> None:
        self.sent.append((chat_id, invoice))


class RecordingSession(BaseSession):
    """Records every Bot API call instead of making it, and answers it with ``True``."""

    def __init__(self) -> None:
        super().__init__()
        self.calls: list[TelegramMethod[Any]] = []
        self.answered: list[TelegramMethod[Any]] = []
        self.refusals: dict[type[TelegramMethod[Any]], str] = {}
        self.errors: dict[type[TelegramMethod[Any]], list[Exception]] = {}

    def refuse(self, kind: type[TelegramMethod[Any]], description: str) -> None:
        """Answer every later ``kind`` call with a Bot API 400 error."""
        self.refusals[kind] = description

    def fail_next(self, kind: type[TelegramMethod[Any]], *errors: Exception) -> None:
        """Raise ``errors`` from the next ``kind`` calls, one per call."""
        self.errors.setdefault(kind, []).extend(errors)

    async def make_request(
        self,
        bot: Bot,
        method: TelegramMethod[TelegramType],
        timeout: int | None = None,  # noqa: ASYNC109 - aiogram signature
    ) -> TelegramType:
        self.calls.append(method)
        if errors := self.errors.get(type(method)):
            raise errors.pop(0)
        if type(method) in self.refusals:
            raise TelegramBadRequest(method=method, message=self.refusals[type(method)])
        self.answered.append(method)
        return True  # type: ignore[return-value]  # handlers ignore API results

    async def stream_content(self, *args: Any, **kwargs: Any) -> AsyncGenerator[bytes, None]:
        yield b""

    async def close(self) -> None:
        return None

    def sent(self, kind: type[TelegramMethod[Any]]) -> list[Any]:
        return [c for c in self.calls if isinstance(c, kind)]

    @property
    def refunds(self) -> list[tuple[int, str]]:
        """``(user_id, charge_id)`` of every refund Telegram accepted."""
        return [
            (call.user_id, call.telegram_payment_charge_id)
            for call in self.answered
            if isinstance(call, RefundStarPayment)
        ]


class Clock:
    """A clock that moves only when a test moves it."""

    def __init__(self, now: datetime) -> None:
        self.now = now

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta: float) -> None:
        self.now += timedelta(**delta)


def make_init_data(
    user_id: int = USER_ID,
    *,
    token: str = BOT_TOKEN,
    auth_date: int | None = None,
    **extra: str,
) -> str:
    user = {"id": user_id, "first_name": "Анна", "username": "anna_demo", "language_code": "ru"}
    fields = {
        "query_id": "AAHdF6IQAAAAAN0XohDhrOrc",
        "user": json.dumps(user, ensure_ascii=False, separators=(",", ":")),
        "auth_date": str(auth_date if auth_date is not None else int(time.time())),
        **extra,
    }
    return sign_init_data(fields, token)


def auth_header(user_id: int = USER_ID) -> dict[str, str]:
    return {"Authorization": f"tma {make_init_data(user_id)}"}


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


def payment_update(
    stars: StarsPayments, order: OrderOut, charge_id: str, *, payer_id: int = USER_ID
) -> Update:
    """The ``successful_payment`` Telegram sends once the invoice for ``order`` is paid."""
    amount = order.stars_amount or 0
    payment = {
        "currency": "XTR",
        "total_amount": amount,
        "invoice_payload": stars.make_payload(order.id, amount),
        "telegram_payment_charge_id": charge_id,
        "provider_payment_charge_id": "",
    }
    return message_update(payer_id, successful_payment=payment)


def order_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "items": [
            {
                "productId": "ethiopia-yirgacheffe",
                "variantId": "250g",
                "grind": "filter",
                "quantity": 2,
            },
            {"productId": "sencha-fukamushi", "variantId": "50g", "quantity": 1},
        ],
        "deliveryMethod": "courier",
        "customer": {"name": "Анна", "phone": "+7 (900) 000-00-00"},
        "address": "ул. Примерная, 1, кв. 2",
        "deliverySlot": "evening",
        "paymentMethod": "on_receipt",
    }
    payload.update(overrides)
    return payload


@pytest.fixture(scope="session")
def catalog() -> Catalog:
    return Catalog.from_file(SHARED / "catalog.json")


@pytest.fixture(scope="session")
def rules() -> PricingRules:
    return PricingRules.from_file(SHARED / "pricing.json")


@pytest.fixture
async def engine() -> AsyncIterator[AsyncEngine]:
    engine = create_engine("sqlite+aiosqlite:///:memory:")
    await init_models(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
def session_factory(engine: AsyncEngine) -> SessionFactory:
    return create_session_factory(engine)


@pytest.fixture
def notifier() -> FakeNotifier:
    return FakeNotifier()


@pytest.fixture
def payments() -> FakePayments:
    return FakePayments()


@pytest.fixture
def clock() -> Clock:
    # A minute ahead, so the refunds a test records are already due at its first sweep.
    return Clock(utcnow() + timedelta(minutes=1))


def make_stars(
    engine: AsyncEngine,
    sessions: SessionFactory,
    notifier: Notifier,
    clock: Clock,
    refunds: RefundPolicy | None = None,
) -> StarsPayments:
    """The bot's aiogram-stars, keeping its records in ``engine`` next to the orders."""
    storage = SqlAlchemyStorage(engine)
    return create_stars(
        storage,
        secret=STARS_SECRET,
        notices=RefundNotices(sessions, storage, notifier),
        refunds=refunds or RefundPolicy(max_attempts=3, first_delay=timedelta(seconds=30)),
        clock=clock,
    )


@pytest.fixture
def stars(
    engine: AsyncEngine, session_factory: SessionFactory, notifier: FakeNotifier, clock: Clock
) -> StarsPayments:
    return make_stars(engine, session_factory, notifier, clock)


@pytest.fixture
def service(
    session_factory: SessionFactory,
    catalog: Catalog,
    rules: PricingRules,
    notifier: FakeNotifier,
    payments: FakePayments,
    stars: StarsPayments,
) -> OrderService:
    return OrderService(
        session_factory=session_factory,
        catalog=catalog,
        rules=rules,
        notifier=notifier,
        payments=payments,
        refunds=stars,
    )


@pytest.fixture
def session() -> RecordingSession:
    return RecordingSession()


@pytest.fixture
def bot(session: RecordingSession) -> Bot:
    return Bot(BOT_TOKEN, session=session)


@pytest.fixture
def dp(service: OrderService, stars: StarsPayments, catalog: Catalog) -> Dispatcher:
    return create_dispatcher(
        order_service=service,
        stars=stars,
        catalog=catalog,
        admin_ids=[ADMIN_ID],
        webapp_url=WEBAPP_URL,
    )


@dataclass(frozen=True, slots=True)
class Telegram:
    """Sends the bot the payment updates Telegram would, and lets it send the due refunds."""

    dp: Dispatcher
    bot: Bot
    session: RecordingSession
    stars: StarsPayments

    @property
    def refunds(self) -> list[tuple[int, str]]:
        return self.session.refunds

    async def pay(self, order: OrderOut, charge_id: str, *, payer_id: int = USER_ID) -> Payment:
        await self.dp.feed_update(
            self.bot, payment_update(self.stars, order, charge_id, payer_id=payer_id)
        )
        payment = await self.stars.get_payment(charge_id)
        assert payment is not None
        return payment

    async def pay_concurrently(self, order: OrderOut, *charge_ids: str) -> list[Payment]:
        # aiogram runs every update as its own task, so two successful_payment updates for one
        # order can be handled at the same time.
        await asyncio.gather(
            *(
                self.dp.feed_update(self.bot, payment_update(self.stars, order, charge_id))
                for charge_id in charge_ids
            )
        )
        found = [await self.stars.get_payment(charge_id) for charge_id in dict.fromkeys(charge_ids)]
        return [payment for payment in found if payment is not None]

    async def send_refunds(self) -> list[Refund]:
        """One attempt at every refund that is due, as the background outbox makes."""
        return await self.stars.send_due_refunds(self.bot)


@pytest.fixture
def telegram(dp: Dispatcher, bot: Bot, session: RecordingSession, stars: StarsPayments) -> Telegram:
    return Telegram(dp, bot, session, stars)


@pytest.fixture
async def client(service: OrderService, catalog: Catalog) -> AsyncIterator[httpx.AsyncClient]:
    app = create_app(
        ApiContext(
            order_service=service,
            catalog=catalog,
            bot_token=BOT_TOKEN,
            cors_origins=["https://sinnercode228.github.io"],
        )
    )
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http


@pytest.fixture
async def file_engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    """Every session gets its own connection to a database file, as in production.
    The in-memory ``engine`` shares one connection between sessions."""
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'shop.db'}")
    await init_models(engine)
    yield engine
    await engine.dispose()


@pytest.fixture
def file_sessions(file_engine: AsyncEngine) -> SessionFactory:
    return create_session_factory(file_engine)


@pytest.fixture
def file_stars(
    file_engine: AsyncEngine, file_sessions: SessionFactory, notifier: FakeNotifier, clock: Clock
) -> StarsPayments:
    return make_stars(file_engine, file_sessions, notifier, clock)


@pytest.fixture
def file_service(
    file_sessions: SessionFactory,
    catalog: Catalog,
    rules: PricingRules,
    notifier: FakeNotifier,
    payments: FakePayments,
    file_stars: StarsPayments,
) -> OrderService:
    """Like ``service``, but on ``file_sessions``."""
    return OrderService(
        session_factory=file_sessions,
        catalog=catalog,
        rules=rules,
        notifier=notifier,
        payments=payments,
        refunds=file_stars,
    )


@pytest.fixture
def file_telegram(
    file_service: OrderService,
    file_stars: StarsPayments,
    catalog: Catalog,
    bot: Bot,
    session: RecordingSession,
) -> Telegram:
    """Like ``telegram``, but on ``file_service``."""
    dp = create_dispatcher(
        order_service=file_service,
        stars=file_stars,
        catalog=catalog,
        admin_ids=[ADMIN_ID],
        webapp_url=WEBAPP_URL,
    )
    return Telegram(dp, bot, session, file_stars)


async def pay_concurrently(
    service: OrderService, order: OrderOut, *charge_ids: str
) -> list[OrderOut | BaseException]:
    """Call ``mark_paid`` for every charge at once, as aiogram-stars does for two charges."""
    return await asyncio.gather(
        *(
            service.mark_paid(
                order_id=order.id,
                total_amount=order.stars_amount or 0,
                payer_id=USER_ID,
                charge_id=charge_id,
            )
            for charge_id in charge_ids
        ),
        return_exceptions=True,
    )


def run_after_next_read(
    monkeypatch: pytest.MonkeyPatch, other: Coroutine[Any, Any, object]
) -> list[object]:
    """Run ``other`` to the end right after the next order read, before that caller writes.

    On SQLite that read takes no lock, so this is an order of events production can hit.
    """
    read = OrderRepository.get
    results: list[object] = []

    async def read_then_run(
        self: OrderRepository, order_id: int, *, for_update: bool = False
    ) -> Order | None:
        found = await read(self, order_id, for_update=for_update)
        monkeypatch.setattr(OrderRepository, "get", read)
        results.extend(await asyncio.gather(other, return_exceptions=True))
        return found

    monkeypatch.setattr(OrderRepository, "get", read_then_run)
    return results


def add_refund_fails_once(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make the next refund aiogram-stars queues fail, as a locked SQLite database does."""
    add_refund = SqlAlchemyStorage.add_refund
    calls = 0

    async def locked_once(self: SqlAlchemyStorage, refund: Refund) -> Refund:
        nonlocal calls
        calls += 1
        if calls == 1:
            raise OperationalError("INSERT INTO stars_refunds", {}, Exception("database is locked"))
        return await add_refund(self, refund)

    monkeypatch.setattr(SqlAlchemyStorage, "add_refund", locked_once)
