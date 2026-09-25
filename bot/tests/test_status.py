from __future__ import annotations

from itertools import pairwise

import pytest

from tgshop.domain.enums import DeliveryMethod as D
from tgshop.domain.enums import OrderStatus as S
from tgshop.domain.enums import PaymentMethod as P
from tgshop.domain.errors import InvalidTransition
from tgshop.domain.status import allowed_transitions, ensure_transition


def test_cash_courier_happy_path() -> None:
    path = [S.NEW, S.CONFIRMED, S.IN_DELIVERY, S.COMPLETED]
    for current, target in pairwise(path):
        ensure_transition(current, target, delivery=D.COURIER, payment=P.ON_RECEIPT)


def test_stars_pickup_happy_path() -> None:
    assert S.PAID not in allowed_transitions(
        S.AWAITING_PAYMENT, delivery=D.PICKUP, payment=P.STARS
    ), "paid is set by the payment flow only"
    path = [S.PAID, S.CONFIRMED, S.READY_FOR_PICKUP, S.COMPLETED]
    for current, target in pairwise(path):
        ensure_transition(current, target, delivery=D.PICKUP, payment=P.STARS)


@pytest.mark.parametrize(
    ("current", "target", "delivery", "payment"),
    [
        (S.CONFIRMED, S.READY_FOR_PICKUP, D.COURIER, P.ON_RECEIPT),
        (S.CONFIRMED, S.IN_DELIVERY, D.PICKUP, P.ON_RECEIPT),
        (S.PAID, S.CANCELLED, D.COURIER, P.STARS),
        (S.CONFIRMED, S.CANCELLED, D.COURIER, P.STARS),
        (S.CONFIRMED, S.REFUNDED, D.COURIER, P.ON_RECEIPT),
        (S.NEW, S.COMPLETED, D.COURIER, P.ON_RECEIPT),
        (S.COMPLETED, S.CANCELLED, D.PICKUP, P.ON_RECEIPT),
        (S.CANCELLED, S.NEW, D.PICKUP, P.ON_RECEIPT),
        (S.AWAITING_PAYMENT, S.PAID, D.PICKUP, P.STARS),
    ],
)
def test_forbidden_transitions(current: S, target: S, delivery: D, payment: P) -> None:
    with pytest.raises(InvalidTransition):
        ensure_transition(current, target, delivery=delivery, payment=payment)


@pytest.mark.parametrize("status", [S.COMPLETED, S.CANCELLED, S.REFUNDED])
def test_final_statuses_have_no_exits(status: S) -> None:
    assert status.is_final
    for delivery in D:
        for payment in P:
            assert not allowed_transitions(status, delivery=delivery, payment=payment)


def test_unpaid_stars_order_can_be_cancelled() -> None:
    ensure_transition(S.AWAITING_PAYMENT, S.CANCELLED, delivery=D.COURIER, payment=P.STARS)
