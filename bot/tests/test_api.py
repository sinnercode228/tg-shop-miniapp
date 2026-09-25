from __future__ import annotations

import time

import httpx
import pytest

from .conftest import OTHER_USER_ID, auth_header, make_init_data, order_payload


async def test_health(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


async def test_catalog_is_public_and_camel_cased(client: httpx.AsyncClient) -> None:
    response = await client.get("/api/catalog")
    assert response.status_code == 200
    body = response.json()
    assert {c["id"] for c in body["categories"]} == {"coffee", "drip", "tea", "gear"}
    product = body["products"][0]
    assert {"categoryId", "variants", "art", "grindable"} <= product.keys()
    assert "pickupPoints" in body
    assert "max-age" in response.headers["cache-control"]


async def test_quote(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/quote",
        json={
            "items": [{"productId": "paper-filters", "variantId": "std", "quantity": 1}],
            "deliveryMethod": "courier",
            "promoCode": "whatever",
        },
    )
    assert response.status_code == 200
    assert response.json() == {
        "subtotal": 39000,
        "discount": 0,
        "deliveryFee": 35000,
        "total": 74000,
        "stars": 494,
        "promoCode": None,
        "promoError": "unknown",
    }


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "Bearer abc"},
        {"Authorization": "tma "},
        {"Authorization": "tma user=1&hash=deadbeef"},
        {"Authorization": f"tma {make_init_data(token='1:wrong')}"},
        {"Authorization": f"tma {make_init_data(auth_date=int(time.time()) - 3 * 86400)}"},
    ],
)
async def test_orders_require_valid_init_data(
    client: httpx.AsyncClient, headers: dict[str, str]
) -> None:
    response = await client.post("/api/orders", json=order_payload(), headers=headers)
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthorized"


async def test_create_and_read_order(client: httpx.AsyncClient) -> None:
    response = await client.post("/api/orders", json=order_payload(), headers=auth_header())
    assert response.status_code == 201, response.text
    created = response.json()
    order = created["order"]
    assert created["invoiceUrl"] is None
    assert order["status"] == "new"
    assert order["total"] == 272000
    assert order["items"][0]["productId"] == "ethiopia-yirgacheffe"

    listing = await client.get("/api/orders", headers=auth_header())
    assert [o["id"] for o in listing.json()] == [order["id"]]

    single = await client.get(f"/api/orders/{order['id']}", headers=auth_header())
    assert single.status_code == 200
    assert single.json()["events"][0]["status"] == "new"


async def test_client_supplied_prices_are_ignored(client: httpx.AsyncClient) -> None:
    payload = order_payload(
        items=[{"productId": "gaiwan", "variantId": "std", "quantity": 1, "price": 1}],
        total=1,
    )
    response = await client.post("/api/orders", json=payload, headers=auth_header())
    assert response.status_code == 201
    assert response.json()["order"]["subtotal"] == 129000


async def test_foreign_order_is_not_found(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/orders", json=order_payload(), headers=auth_header())
    order_id = created.json()["order"]["id"]
    response = await client.get(f"/api/orders/{order_id}", headers=auth_header(OTHER_USER_ID))
    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_stars_order_returns_invoice_link(client: httpx.AsyncClient) -> None:
    response = await client.post(
        "/api/orders", json=order_payload(paymentMethod="stars"), headers=auth_header()
    )
    body = response.json()
    assert body["order"]["status"] == "awaiting_payment"
    assert body["invoiceUrl"].startswith("https://t.me/$")

    again = await client.post(f"/api/orders/{body['order']['id']}/invoice", headers=auth_header())
    assert again.status_code == 200
    assert again.json()["invoiceUrl"].startswith("https://t.me/$")


async def test_invoice_for_cash_order_is_conflict(client: httpx.AsyncClient) -> None:
    created = await client.post("/api/orders", json=order_payload(), headers=auth_header())
    response = await client.post(
        f"/api/orders/{created.json()['order']['id']}/invoice", headers=auth_header()
    )
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "not_payable"


@pytest.mark.parametrize(
    ("overrides", "fragment"),
    [
        ({"items": []}, "items"),
        ({"address": None}, "address"),
        ({"deliveryMethod": "pickup", "pickupPointId": None}, "pickupPointId"),
        ({"customer": {"name": "A", "phone": "12"}}, "phone"),
        ({"customer": {"name": "  ", "phone": "+79000000000"}}, "name"),
        ({"paymentMethod": "crypto"}, "paymentMethod"),
    ],
)
async def test_payload_validation(
    client: httpx.AsyncClient, overrides: dict[str, object], fragment: str
) -> None:
    response = await client.post(
        "/api/orders", json=order_payload(**overrides), headers=auth_header()
    )
    assert response.status_code == 422
    body = response.json()
    assert body["error"]["code"] == "invalid_request"
    assert fragment in response.text


async def test_domain_errors_are_mapped(client: httpx.AsyncClient) -> None:
    payload = order_payload(items=[{"productId": "ghost", "variantId": "x", "quantity": 1}])
    response = await client.post("/api/orders", json=payload, headers=auth_header())
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unknown_product"


async def test_cors_preflight(client: httpx.AsyncClient) -> None:
    response = await client.options(
        "/api/orders",
        headers={
            "Origin": "https://sinnercode228.github.io",
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "authorization,content-type",
        },
    )
    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "https://sinnercode228.github.io"
