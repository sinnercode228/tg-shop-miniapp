"""Order status state machine.

The graph is intentionally explicit: every allowed edge is listed, everything else is rejected.

    awaiting_payment ──► paid ──► confirmed ──► in_delivery ──────► completed
          │                │          │    └──► ready_for_pickup ─► completed
          ▼                ▼          ▼
      cancelled        refunded   cancelled / refunded
    new ──► confirmed …          (cash orders skip the payment step)
"""

from __future__ import annotations

from collections.abc import Mapping

from .enums import DeliveryMethod, OrderStatus, PaymentMethod
from .errors import InvalidTransition

S = OrderStatus

_GRAPH: Mapping[OrderStatus, frozenset[OrderStatus]] = {
    S.AWAITING_PAYMENT: frozenset({S.PAID, S.CANCELLED}),
    S.NEW: frozenset({S.CONFIRMED, S.CANCELLED}),
    S.PAID: frozenset({S.CONFIRMED, S.REFUNDED}),
    S.CONFIRMED: frozenset({S.IN_DELIVERY, S.READY_FOR_PICKUP, S.CANCELLED, S.REFUNDED}),
    S.IN_DELIVERY: frozenset({S.COMPLETED}),
    S.READY_FOR_PICKUP: frozenset({S.COMPLETED}),
    S.COMPLETED: frozenset(),
    S.CANCELLED: frozenset(),
    S.REFUNDED: frozenset(),
}


def allowed_transitions(
    current: OrderStatus, *, delivery: DeliveryMethod, payment: PaymentMethod
) -> frozenset[OrderStatus]:
    """Statuses reachable from ``current`` for an order with the given delivery/payment."""
    targets = set(_GRAPH[current])
    # Courier orders are delivered, pickup orders wait at the counter.
    targets.discard(S.READY_FOR_PICKUP if delivery is DeliveryMethod.COURIER else S.IN_DELIVERY)
    # A Stars-paid order can't simply be cancelled: the money must go back (refund), and
    # an unpaid one has nothing to refund.
    if payment is PaymentMethod.STARS and current is not S.AWAITING_PAYMENT:
        targets.discard(S.CANCELLED)
    if payment is PaymentMethod.ON_RECEIPT:
        targets.discard(S.REFUNDED)
    # Payments only arrive through the payment flow, never as a manual status change.
    targets.discard(S.PAID)
    return frozenset(targets)


def ensure_transition(
    current: OrderStatus,
    target: OrderStatus,
    *,
    delivery: DeliveryMethod,
    payment: PaymentMethod,
) -> None:
    if target not in allowed_transitions(current, delivery=delivery, payment=payment):
        raise InvalidTransition(f"Cannot move order from '{current}' to '{target}'")
