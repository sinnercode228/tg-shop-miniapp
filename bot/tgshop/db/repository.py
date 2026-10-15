"""Data access for orders. Keeps SQL out of the service layer."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
from typing import Any, cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from tgshop.domain.enums import OrderStatus

from .models import Order


class OrderRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def add(self, order: Order) -> Order:
        self._session.add(order)
        await self._session.flush()
        return order

    async def get(self, order_id: int, *, for_update: bool = False) -> Order | None:
        stmt = select(Order).where(Order.id == order_id)
        if for_update:
            stmt = stmt.with_for_update()
        return (await self._session.execute(stmt)).scalar_one_or_none()

    async def move_status(
        self, order_id: int, current: OrderStatus, target: OrderStatus, **values: Any
    ) -> bool:
        """Set ``target`` (and ``values``) only if the order is still in ``current``.

        One conditional UPDATE, so of two concurrent calls at most one matches the row.
        It does not rely on ``with_for_update()``, which SQLite compiles to a plain SELECT.
        """
        stmt = (
            update(Order)
            .where(Order.id == order_id, Order.status == current)
            .values(status=target, **values)
        )
        result = cast(CursorResult[Any], await self._session.execute(stmt))
        return result.rowcount == 1

    async def claim_payment(self, order_id: int, charge_id: str) -> bool:
        """Set ``paid`` and the charge id only if the order still awaits payment."""
        return await self.move_status(
            order_id,
            OrderStatus.AWAITING_PAYMENT,
            OrderStatus.PAID,
            telegram_payment_charge_id=charge_id,
        )

    async def unpaid_placed_before(self, moment: datetime) -> Sequence[int]:
        """Ids of the orders still awaiting payment that were placed before ``moment``."""
        stmt = (
            select(Order.id)
            .where(Order.status == OrderStatus.AWAITING_PAYMENT, Order.created_at < moment)
            .order_by(Order.id)
        )
        return (await self._session.execute(stmt)).scalars().all()

    async def list_for_user(self, user_id: int, *, limit: int = 50) -> Sequence[Order]:
        stmt = select(Order).where(Order.user_id == user_id).order_by(Order.id.desc()).limit(limit)
        return (await self._session.execute(stmt)).scalars().all()

    async def list_recent(
        self, *, statuses: Sequence[OrderStatus] | None = None, limit: int = 20
    ) -> Sequence[Order]:
        stmt = select(Order).order_by(Order.id.desc()).limit(limit)
        if statuses:
            stmt = stmt.where(Order.status.in_(statuses))
        return (await self._session.execute(stmt)).scalars().all()
