"""Pure pricing logic. Mirrors ``webapp/src/domain/pricing.ts``; parity is enforced by the
shared contract vectors in ``shared/pricing-cases.json``.

All amounts are integer kopecks — floats never touch money.
"""

from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from .enums import DeliveryMethod
from .errors import ValidationFailed

PromoKind = Literal["percent", "free_delivery"]


@dataclass(frozen=True, slots=True)
class Promo:
    code: str
    kind: PromoKind
    value: int = 0
    max_discount: int | None = None


@dataclass(frozen=True, slots=True)
class PricingRules:
    courier_fee: int
    free_delivery_threshold: int
    max_quantity_per_line: int
    max_lines: int
    kopecks_per_star: int
    promo_codes: Mapping[str, Promo] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, raw: Mapping[str, Any]) -> PricingRules:
        promos = {
            code.upper(): Promo(
                code=code.upper(),
                kind=spec["kind"],
                value=int(spec.get("value", 0)),
                max_discount=spec.get("maxDiscount"),
            )
            for code, spec in raw.get("promoCodes", {}).items()
        }
        return cls(
            courier_fee=int(raw["courierFee"]),
            free_delivery_threshold=int(raw["freeDeliveryThreshold"]),
            max_quantity_per_line=int(raw["maxQuantityPerLine"]),
            max_lines=int(raw["maxLines"]),
            kopecks_per_star=int(raw["kopecksPerStar"]),
            promo_codes=promos,
        )

    @classmethod
    def from_file(cls, path: Path) -> PricingRules:
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))


@dataclass(frozen=True, slots=True)
class PricedLine:
    unit_price: int
    quantity: int

    @property
    def total(self) -> int:
        return self.unit_price * self.quantity


@dataclass(frozen=True, slots=True)
class Quote:
    subtotal: int
    discount: int
    delivery_fee: int
    total: int
    stars: int
    promo_code: str | None
    promo_error: Literal["unknown"] | None


def normalize_promo(raw: str | None) -> str:
    return (raw or "").strip().upper()


def to_stars(amount: int, rules: PricingRules) -> int:
    """Convert kopecks to Telegram Stars, always rounding in the shop's favour."""
    return -(-amount // rules.kopecks_per_star)  # ceil division without floats


def validate_lines(lines: Sequence[PricedLine], rules: PricingRules) -> None:
    if not lines:
        raise ValidationFailed("Cart is empty", code="cart_empty")
    if len(lines) > rules.max_lines:
        raise ValidationFailed(f"Too many items (max {rules.max_lines})", code="cart_too_large")
    for line in lines:
        if not 1 <= line.quantity <= rules.max_quantity_per_line:
            raise ValidationFailed(
                f"Quantity must be between 1 and {rules.max_quantity_per_line}",
                code="bad_quantity",
            )
        if line.unit_price < 0:
            raise ValidationFailed("Negative price", code="bad_price")


def calculate_quote(
    lines: Sequence[PricedLine],
    delivery: DeliveryMethod,
    promo_code: str | None,
    rules: PricingRules,
) -> Quote:
    validate_lines(lines, rules)
    subtotal = sum(line.total for line in lines)

    code = normalize_promo(promo_code)
    promo = rules.promo_codes.get(code) if code else None

    discount = 0
    if promo is not None and promo.kind == "percent":
        # Percent discounts are rounded down to whole roubles.
        discount = subtotal * promo.value // 100 // 100 * 100
        if promo.max_discount is not None:
            discount = min(discount, promo.max_discount)

    after_discount = subtotal - discount
    delivery_fee = 0
    if (
        delivery is DeliveryMethod.COURIER
        and not (promo is not None and promo.kind == "free_delivery")
        and after_discount < rules.free_delivery_threshold
    ):
        delivery_fee = rules.courier_fee

    total = after_discount + delivery_fee
    return Quote(
        subtotal=subtotal,
        discount=discount,
        delivery_fee=delivery_fee,
        total=total,
        stars=to_stars(total, rules),
        promo_code=promo.code if promo is not None else None,
        promo_error="unknown" if code and promo is None else None,
    )
