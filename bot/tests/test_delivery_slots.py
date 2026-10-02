from __future__ import annotations

import json
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

from tgshop.bot.texts import order_summary
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import DeliverySlot, OrderSource
from tgshop.domain.schemas import OrderCreate, OrderOut
from tgshop.services.orders import Customer, OrderService

from .conftest import SHARED, USER_ID, order_payload

RAW_CATALOG: dict[str, Any] = json.loads((SHARED / "catalog.json").read_text(encoding="utf-8"))
WINDOWS: dict[str, str] = RAW_CATALOG["deliveryWindows"]


async def courier_order(service: OrderService, slot: str) -> OrderOut:
    data = OrderCreate.model_validate(order_payload(deliverySlot=slot))
    return await service.create_order(Customer(user_id=USER_ID), data, source=OrderSource.API)


def test_every_timed_slot_has_a_shared_window() -> None:
    assert set(WINDOWS) == {slot.value for slot in DeliverySlot if slot is not DeliverySlot.ASAP}


@pytest.mark.parametrize(("slot", "window"), WINDOWS.items(), ids=list(WINDOWS))
async def test_order_messages_show_the_shared_window(
    slot: str, window: str, service: OrderService, catalog: Catalog
) -> None:
    """vitest checks the Mini App labels against the same windows — the two can't drift."""
    order = await courier_order(service, slot)
    assert f"({window})" in order_summary(order, catalog)
    assert f"({window})" in order_summary(order, catalog, for_admin=True)


async def test_asap_order_has_no_window(service: OrderService, catalog: Catalog) -> None:
    order = await courier_order(service, DeliverySlot.ASAP)
    text = order_summary(order, catalog)
    assert "(как можно скорее)" in text
    assert not any(window in text for window in WINDOWS.values())


@pytest.mark.parametrize(
    "windows",
    [{"morning": WINDOWS["morning"]}, {**WINDOWS, "asap": "сейчас"}],
    ids=["missing-evening", "extra-asap"],
)
def test_catalog_rejects_windows_that_do_not_match_the_slots(windows: dict[str, str]) -> None:
    with pytest.raises(ValidationError, match="deliveryWindows must list exactly"):
        Catalog.model_validate({**RAW_CATALOG, "deliveryWindows": windows})


async def test_catalog_api_serves_the_shared_windows(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/catalog")
    assert response.json()["deliveryWindows"] == WINDOWS
