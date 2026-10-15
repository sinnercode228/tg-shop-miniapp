from __future__ import annotations

import asyncio
import json
import time
from collections.abc import AsyncIterator, Coroutine
from pathlib import Path
from typing import Any

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncEngine

from tgshop.api.app import create_app
from tgshop.api.context import ApiContext
from tgshop.db.models import Order
from tgshop.db.repository import OrderRepository
from tgshop.db.session import SessionFactory, create_engine, create_session_factory, init_models
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import OrderStatus
from tgshop.domain.pricing import PricingRules
from tgshop.domain.schemas import OrderOut
from tgshop.payments import Invoice, make_payload
from tgshop.security.init_data import sign_init_data
from tgshop.services.orders import OrderService

BOT_TOKEN = "7000000001:AAtest-token-used-only-in-unit-tests"
SHARED = Path(__file__).resolve().parents[2] / "shared"
USER_ID = 111_222_333
OTHER_USER_ID = 444_555_666


class FakeNotifier:
    def __init__(self) -> None:
        self.placed: list[OrderOut] = []
        self.changes: list[tuple[OrderOut, OrderStatus]] = []

    async def order_placed(self, order: OrderOut) -> None:
        self.placed.append(order)

    async def status_changed(self, order: OrderOut, previous: OrderStatus) -> None:
        self.changes.append((order, previous))


class FakePayments:
    def __init__(self) -> None:
        self.links: list[Invoice] = []
        self.sent: list[tuple[int, Invoice]] = []
        self.refunds: list[tuple[int, str]] = []

    async def create_invoice_link(self, invoice: Invoice) -> str:
        self.links.append(invoice)
        return f"https://t.me/$demo-invoice-{invoice.order_id}"

    async def send_invoice(self, chat_id: int, invoice: Invoice) -> None:
        self.sent.append((chat_id, invoice))

    async def refund(self, user_id: int, charge_id: str) -> None:
        self.refunds.append((user_id, charge_id))


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
def service(
    session_factory: SessionFactory,
    catalog: Catalog,
    rules: PricingRules,
    notifier: FakeNotifier,
    payments: FakePayments,
) -> OrderService:
    return OrderService(
        session_factory=session_factory,
        catalog=catalog,
        rules=rules,
        notifier=notifier,
        payments=payments,
    )


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
async def file_service(
    tmp_path: Path,
    catalog: Catalog,
    rules: PricingRules,
    notifier: FakeNotifier,
    payments: FakePayments,
) -> AsyncIterator[OrderService]:
    """Like ``service``, but every session gets its own connection to a database file,
    as in production. The in-memory fixture shares one connection between sessions."""
    engine = create_engine(f"sqlite+aiosqlite:///{tmp_path / 'shop.db'}")
    await init_models(engine)
    yield OrderService(
        session_factory=create_session_factory(engine),
        catalog=catalog,
        rules=rules,
        notifier=notifier,
        payments=payments,
    )
    await engine.dispose()


async def pay_concurrently(
    service: OrderService, order: OrderOut, *charge_ids: str
) -> list[OrderOut | BaseException]:
    # aiogram runs every update as its own task, so two successful_payment updates for one
    # order can be handled at the same time.
    return await asyncio.gather(
        *(
            service.mark_paid(
                payload=make_payload(order.id),
                currency="XTR",
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
