"""Request/response DTOs of the public API (also reused by the ``web_app_data`` bot flow)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import Annotated, Literal, Self

from pydantic import AfterValidator, Field, StringConstraints, model_validator

from .base import CamelModel
from .enums import DeliveryMethod, DeliverySlot, OrderSource, OrderStatus, PaymentMethod

_PHONE_NOISE = re.compile(r"[\s\-()]")
_PHONE = re.compile(r"^\+?\d{10,15}$")


def _normalize_phone(value: str) -> str:
    compact = _PHONE_NOISE.sub("", value)
    if not _PHONE.fullmatch(compact):
        raise ValueError("phone must contain 10–15 digits")
    return compact


Phone = Annotated[str, AfterValidator(_normalize_phone)]
ShortText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=64)]


class CartItemIn(CamelModel):
    product_id: Annotated[str, StringConstraints(max_length=64)]
    variant_id: Annotated[str, StringConstraints(max_length=32)]
    grind: Annotated[str, StringConstraints(max_length=32)] | None = None
    quantity: int = Field(ge=1, le=99)


class QuoteRequest(CamelModel):
    items: list[CartItemIn] = Field(min_length=1, max_length=50)
    delivery_method: DeliveryMethod = DeliveryMethod.COURIER
    promo_code: Annotated[str, StringConstraints(max_length=32)] | None = None


class QuoteOut(CamelModel):
    subtotal: int
    discount: int
    delivery_fee: int
    total: int
    stars: int
    promo_code: str | None
    promo_error: Literal["unknown"] | None


class CustomerIn(CamelModel):
    name: ShortText
    phone: Phone


class OrderCreate(QuoteRequest):
    customer: CustomerIn
    address: Annotated[str, StringConstraints(max_length=200)] | None = None
    pickup_point_id: Annotated[str, StringConstraints(max_length=64)] | None = None
    delivery_slot: DeliverySlot = DeliverySlot.ASAP
    comment: Annotated[str, StringConstraints(max_length=500)] | None = None
    payment_method: PaymentMethod = PaymentMethod.ON_RECEIPT

    @model_validator(mode="after")
    def _check_delivery_details(self) -> Self:
        if self.delivery_method is DeliveryMethod.COURIER and not self.address:
            raise ValueError("address is required for courier delivery")
        if self.delivery_method is DeliveryMethod.PICKUP and not self.pickup_point_id:
            raise ValueError("pickupPointId is required for pickup")
        return self


class OrderItemOut(CamelModel):
    product_id: str
    variant_id: str
    grind: str | None
    title: str
    variant_label: str
    unit_price: int
    quantity: int


class OrderEventOut(CamelModel):
    status: OrderStatus
    created_at: datetime


class OrderOut(CamelModel):
    id: int
    user_id: int
    status: OrderStatus
    source: OrderSource
    customer_name: str
    phone: str
    delivery_method: DeliveryMethod
    address: str | None
    pickup_point_id: str | None
    delivery_slot: DeliverySlot
    comment: str | None
    payment_method: PaymentMethod
    promo_code: str | None
    subtotal: int
    discount: int
    delivery_fee: int
    total: int
    stars_amount: int | None
    created_at: datetime
    items: list[OrderItemOut]
    events: list[OrderEventOut]


class OrderCreated(CamelModel):
    order: OrderOut
    invoice_url: str | None = None
