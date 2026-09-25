from __future__ import annotations

from typing import Any

import pytest

from tgshop.domain.enums import OrderSource, OrderStatus, PaymentMethod
from tgshop.domain.errors import InvalidTransition, NotFound, PaymentError, ValidationFailed
from tgshop.domain.schemas import OrderCreate
from tgshop.payments import make_payload
from tgshop.services.orders import Customer, OrderService

from .conftest import OTHER_USER_ID, USER_ID, FakeNotifier, FakePayments, order_payload

CUSTOMER = Customer(user_id=USER_ID, username="anna_demo", language="ru")


def build(**overrides: Any) -> OrderCreate:
    return OrderCreate.model_validate(order_payload(**overrides))


async def test_cash_order_is_created_with_server_side_prices(
    service: OrderService, notifier: FakeNotifier
) -> None:
    order = await service.create_order(CUSTOMER, build(), source=OrderSource.API)

    assert order.status is OrderStatus.NEW
    # 2 × 890 ₽ + 1 × 590 ₽ = 2 370 ₽ (< 3 000 ₽ → paid delivery 350 ₽)
    assert order.subtotal == 237_000
    assert order.delivery_fee == 35_000
    assert order.total == 272_000
    assert order.stars_amount is None
    assert order.phone == "+79000000000", "phone is normalised"
    assert [i.title for i in order.items] == ["Эфиопия Иргачефф", "Сенча Фукамуси"]
    assert order.items[0].grind == "filter"
    assert [e.status for e in order.events] == [OrderStatus.NEW]
    assert notifier.placed == [order], "admins are notified about new cash orders"


async def test_item_titles_follow_customer_language(service: OrderService) -> None:
    en = Customer(user_id=USER_ID, language="en")
    order = await service.create_order(en, build(), source=OrderSource.API)
    assert order.items[0].title == "Ethiopia Yirgacheffe"
    assert order.items[0].variant_label == "250 g"


async def test_duplicate_lines_are_merged(service: OrderService) -> None:
    item = {"productId": "gaiwan", "variantId": "std", "quantity": 2}
    order = await service.create_order(
        CUSTOMER, build(items=[item, {**item, "quantity": 3}]), source=OrderSource.API
    )
    assert len(order.items) == 1
    assert order.items[0].quantity == 5


async def test_grindable_product_defaults_to_whole_bean(service: OrderService) -> None:
    item = {"productId": "kenya-aa", "variantId": "1kg", "quantity": 1}
    order = await service.create_order(CUSTOMER, build(items=[item]), source=OrderSource.API)
    assert order.items[0].grind == "beans"
    assert order.delivery_fee == 0, "3 590 ₽ order ships for free"


@pytest.mark.parametrize(
    ("items", "code"),
    [
        ([{"productId": "nope", "variantId": "250g", "quantity": 1}], "unknown_product"),
        ([{"productId": "kenya-aa", "variantId": "5kg", "quantity": 1}], "unknown_variant"),
        (
            [{"productId": "kenya-aa", "variantId": "250g", "grind": "dust", "quantity": 1}],
            "unknown_grind",
        ),
        (
            [{"productId": "gaiwan", "variantId": "std", "grind": "espresso", "quantity": 1}],
            "unknown_grind",
        ),
        ([{"productId": "gaiwan", "variantId": "std", "quantity": 21}], "bad_quantity"),
    ],
)
async def test_invalid_items_are_rejected(
    service: OrderService, items: list[dict[str, Any]], code: str
) -> None:
    with pytest.raises(ValidationFailed) as exc_info:
        await service.create_order(CUSTOMER, build(items=items), source=OrderSource.API)
    assert exc_info.value.code == code


async def test_unknown_promo_blocks_the_order(service: OrderService) -> None:
    with pytest.raises(ValidationFailed) as exc_info:
        await service.create_order(CUSTOMER, build(promoCode="FREECOFFEE"), source=OrderSource.API)
    assert exc_info.value.code == "unknown_promo"


async def test_promo_is_applied(service: OrderService) -> None:
    order = await service.create_order(CUSTOMER, build(promoCode="zerno10"), source=OrderSource.API)
    assert order.promo_code == "ZERNO10"
    assert order.discount == 23_700


async def test_pickup_order_drops_address_and_validates_point(service: OrderService) -> None:
    order = await service.create_order(
        CUSTOMER,
        build(deliveryMethod="pickup", pickupPointId="chayny-5"),
        source=OrderSource.API,
    )
    assert order.address is None
    assert order.pickup_point_id == "chayny-5"
    assert order.delivery_fee == 0

    with pytest.raises(ValidationFailed):
        await service.create_order(
            CUSTOMER, build(deliveryMethod="pickup", pickupPointId="moon"), source=OrderSource.API
        )


async def test_stars_order_awaits_payment_and_gets_invoice(
    service: OrderService, notifier: FakeNotifier, payments: FakePayments
) -> None:
    created = await service.place_order(CUSTOMER, build(paymentMethod="stars"))

    order = created.order
    assert order.status is OrderStatus.AWAITING_PAYMENT
    assert order.stars_amount == 1814  # ceil(2 720 ₽ / 1.5 ₽)
    assert created.invoice_url == f"https://t.me/$demo-invoice-{order.id}"
    assert payments.links[0].amount == 1814
    assert payments.links[0].payload == make_payload(order.id)
    assert notifier.placed == [], "admins hear about Stars orders only after payment"


async def test_stars_disabled(
    session_factory: Any, catalog: Any, rules: Any, notifier: FakeNotifier
) -> None:
    service = OrderService(
        session_factory=session_factory,
        catalog=catalog,
        rules=rules,
        notifier=notifier,
        payments=None,
    )
    with pytest.raises(ValidationFailed) as exc_info:
        await service.create_order(CUSTOMER, build(paymentMethod="stars"), source=OrderSource.API)
    assert exc_info.value.code == "payment_unavailable"


async def test_full_stars_payment_flow(
    service: OrderService, notifier: FakeNotifier, payments: FakePayments
) -> None:
    order = (await service.place_order(CUSTOMER, build(paymentMethod="stars"))).order
    payload = make_payload(order.id)
    assert order.stars_amount is not None

    # pre_checkout_query
    assert (
        await service.pre_checkout_error(
            payload=payload, currency="XTR", total_amount=order.stars_amount, payer_id=USER_ID
        )
        is None
    )
    assert (
        await service.pre_checkout_error(
            payload=payload, currency="XTR", total_amount=1, payer_id=USER_ID
        )
        is not None
    )
    assert (
        await service.pre_checkout_error(
            payload=payload, currency="XTR", total_amount=order.stars_amount, payer_id=OTHER_USER_ID
        )
        is not None
    )
    assert (
        await service.pre_checkout_error(
            payload="garbage", currency="XTR", total_amount=order.stars_amount, payer_id=USER_ID
        )
        is not None
    )

    # successful_payment
    paid = await service.mark_paid(
        payload=payload,
        currency="XTR",
        total_amount=order.stars_amount,
        payer_id=USER_ID,
        charge_id="charge-1",
    )
    assert paid.status is OrderStatus.PAID
    assert notifier.placed == [paid]
    assert notifier.changes == [(paid, OrderStatus.AWAITING_PAYMENT)]

    # Telegram may redeliver the update — must be idempotent.
    again = await service.mark_paid(
        payload=payload,
        currency="XTR",
        total_amount=order.stars_amount,
        payer_id=USER_ID,
        charge_id="charge-1",
    )
    assert again.status is OrderStatus.PAID
    assert len(notifier.placed) == 1

    # Refund
    refunded = await service.change_status(order.id, OrderStatus.REFUNDED)
    assert refunded.status is OrderStatus.REFUNDED
    assert payments.refunds == [(USER_ID, "charge-1")]


async def test_payment_for_cancelled_order_is_refunded_automatically(
    service: OrderService, payments: FakePayments
) -> None:
    order = (await service.place_order(CUSTOMER, build(paymentMethod="stars"))).order
    await service.change_status(order.id, OrderStatus.CANCELLED)

    with pytest.raises(PaymentError):
        await service.mark_paid(
            payload=make_payload(order.id),
            currency="XTR",
            total_amount=order.stars_amount or 0,
            payer_id=USER_ID,
            charge_id="late-charge",
        )
    assert payments.refunds == [(USER_ID, "late-charge")]


async def test_status_changes_notify_customer(
    service: OrderService, notifier: FakeNotifier
) -> None:
    order = await service.create_order(CUSTOMER, build(), source=OrderSource.API)
    confirmed = await service.change_status(order.id, OrderStatus.CONFIRMED)
    delivering = await service.change_status(order.id, OrderStatus.IN_DELIVERY)

    assert [c[1] for c in notifier.changes] == [OrderStatus.NEW, OrderStatus.CONFIRMED]
    assert [e.status for e in delivering.events] == [
        OrderStatus.NEW,
        OrderStatus.CONFIRMED,
        OrderStatus.IN_DELIVERY,
    ]
    assert confirmed.status is OrderStatus.CONFIRMED

    with pytest.raises(InvalidTransition):
        await service.change_status(order.id, OrderStatus.READY_FOR_PICKUP)


async def test_cash_order_cannot_be_refunded(service: OrderService) -> None:
    order = await service.create_order(CUSTOMER, build(), source=OrderSource.API)
    with pytest.raises(InvalidTransition):
        await service.refund(order.id)


async def test_customers_see_only_their_orders(service: OrderService) -> None:
    mine = await service.create_order(CUSTOMER, build(), source=OrderSource.API)
    other = Customer(user_id=OTHER_USER_ID)
    await service.create_order(other, build(), source=OrderSource.WEB_APP_DATA)

    assert [o.id for o in await service.list_for_user(USER_ID)] == [mine.id]
    with pytest.raises(NotFound):
        await service.get_for_user(OTHER_USER_ID, mine.id)
    with pytest.raises(NotFound):
        await service.change_status(999, OrderStatus.CONFIRMED)


async def test_admin_listing_filters_by_status(service: OrderService) -> None:
    cash = await service.create_order(CUSTOMER, build(), source=OrderSource.API)
    await service.create_order(CUSTOMER, build(paymentMethod="stars"), source=OrderSource.API)

    new_only = await service.list_recent(statuses=[OrderStatus.NEW])
    assert [o.id for o in new_only] == [cash.id]
    assert len(await service.list_recent()) == 2
    assert all(o.payment_method in PaymentMethod for o in new_only)


async def test_quote_uses_catalog_prices(service: OrderService) -> None:
    from tgshop.domain.schemas import QuoteRequest

    quote = await service.quote(
        QuoteRequest.model_validate(
            {
                "items": [{"productId": "gooseneck-kettle", "variantId": "std", "quantity": 1}],
                "deliveryMethod": "courier",
                "promoCode": "FREEDELIVERY",
            }
        )
    )
    assert quote.subtotal == 299_000
    assert quote.delivery_fee == 0
    assert quote.promo_code == "FREEDELIVERY"
