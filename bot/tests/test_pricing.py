from __future__ import annotations

import json

import pytest

from tgshop.domain.enums import DeliveryMethod
from tgshop.domain.errors import ValidationFailed
from tgshop.domain.pricing import (
    PricedLine,
    PricingRules,
    calculate_quote,
    normalize_promo,
    to_stars,
)

from .conftest import SHARED

CASES = json.loads((SHARED / "pricing-cases.json").read_text(encoding="utf-8"))["cases"]


@pytest.mark.parametrize("case", CASES, ids=[c["name"] for c in CASES])
def test_shared_contract_vectors(case: dict, rules: PricingRules) -> None:  # type: ignore[type-arg]
    """The very same vectors run in vitest — backend and Mini App can't drift apart."""
    lines = [PricedLine(unit_price=x["unitPrice"], quantity=x["quantity"]) for x in case["lines"]]
    quote = calculate_quote(lines, DeliveryMethod(case["delivery"]), case["promo"], rules)
    expected = case["expected"]
    assert {
        "subtotal": quote.subtotal,
        "discount": quote.discount,
        "deliveryFee": quote.delivery_fee,
        "total": quote.total,
        "stars": quote.stars,
        "promoCode": quote.promo_code,
        "promoError": quote.promo_error,
    } == expected


def test_total_is_consistent(rules: PricingRules) -> None:
    quote = calculate_quote([PricedLine(12345, 3)], DeliveryMethod.COURIER, "ZERNO10", rules)
    assert quote.total == quote.subtotal - quote.discount + quote.delivery_fee


def test_threshold_is_inclusive(rules: PricingRules) -> None:
    line = PricedLine(rules.free_delivery_threshold, 1)
    assert calculate_quote([line], DeliveryMethod.COURIER, None, rules).delivery_fee == 0
    line = PricedLine(rules.free_delivery_threshold - 1, 1)
    assert (
        calculate_quote([line], DeliveryMethod.COURIER, None, rules).delivery_fee
        == rules.courier_fee
    )


@pytest.mark.parametrize(
    ("lines", "code"),
    [
        ([], "cart_empty"),
        ([PricedLine(100, 0)], "bad_quantity"),
        ([PricedLine(100, 21)], "bad_quantity"),
        ([PricedLine(-1, 1)], "bad_price"),
        ([PricedLine(100, 1)] * 31, "cart_too_large"),
    ],
)
def test_invalid_carts(lines: list[PricedLine], code: str, rules: PricingRules) -> None:
    with pytest.raises(ValidationFailed) as exc_info:
        calculate_quote(lines, DeliveryMethod.PICKUP, None, rules)
    assert exc_info.value.code == code


def test_stars_round_up(rules: PricingRules) -> None:
    assert to_stars(0, rules) == 0
    assert to_stars(1, rules) == 1
    assert to_stars(rules.kopecks_per_star, rules) == 1
    assert to_stars(rules.kopecks_per_star + 1, rules) == 2


@pytest.mark.parametrize(("raw", "expected"), [(None, ""), ("  zerno10 ", "ZERNO10"), ("", "")])
def test_normalize_promo(raw: str | None, expected: str) -> None:
    assert normalize_promo(raw) == expected
