"""Outbound notifications (admins / customers) behind a small protocol."""

from __future__ import annotations

from typing import Protocol

from tgshop.domain.enums import OrderStatus
from tgshop.domain.schemas import OrderOut


class Notifier(Protocol):
    async def order_placed(self, order: OrderOut) -> None:
        """A new order is ready to be processed (cash order placed or Stars order paid)."""
        ...

    async def status_changed(self, order: OrderOut, previous: OrderStatus) -> None:
        """Tell the customer their order moved to another status."""
        ...


class NullNotifier:
    async def order_placed(self, order: OrderOut) -> None:
        return None

    async def status_changed(self, order: OrderOut, previous: OrderStatus) -> None:
        return None
