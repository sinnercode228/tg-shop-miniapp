"""Outbound notifications (admins / customers) behind a small protocol."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol

from tgshop.domain.enums import OrderStatus
from tgshop.domain.schemas import OrderOut

if TYPE_CHECKING:
    from .refunds import RefundOut


class Notifier(Protocol):
    async def order_placed(self, order: OrderOut) -> None:
        """A new order is ready to be processed (cash order placed or Stars order paid)."""
        ...

    async def status_changed(self, order: OrderOut, previous: OrderStatus) -> None:
        """Tell the customer their order moved to another status."""
        ...

    async def order_expired(self, order: OrderOut) -> None:
        """Tell the admins a Stars order was cancelled because it was not paid in time."""
        ...

    async def order_refunded(self, order: OrderOut) -> None:
        """Tell the customer the Stars for their refunded order are back."""
        ...

    async def payment_returned(self, user_id: int, reason: str) -> None:
        """Tell the payer that a payment the order could not take (``reason``) went back."""
        ...

    async def refund_failed(self, refund: RefundOut) -> None:
        """Tell the admins a refund ran out of attempts and needs a person."""
        ...


class NullNotifier:
    async def order_placed(self, order: OrderOut) -> None:
        return None

    async def status_changed(self, order: OrderOut, previous: OrderStatus) -> None:
        return None

    async def order_expired(self, order: OrderOut) -> None:
        return None

    async def order_refunded(self, order: OrderOut) -> None:
        return None

    async def payment_returned(self, user_id: int, reason: str) -> None:
        return None

    async def refund_failed(self, refund: RefundOut) -> None:
        return None
