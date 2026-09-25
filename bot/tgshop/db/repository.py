"""Data access for orders. Keeps SQL out of the service layer."""

from __future__ import annotations

from collections.abc import Sequence

from sqlalchemy import select
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
