"""Cancels Stars orders that were not paid in time."""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Protocol

from tgshop.db.models import utcnow
from tgshop.domain.schemas import OrderOut

log = logging.getLogger(__name__)


class ExpiringOrders(Protocol):
    async def expire_unpaid(self, *, placed_before: datetime) -> list[OrderOut]: ...


class UnpaidOrderExpiry:
    """Every ``interval`` seconds, cancels the orders still awaiting payment ``ttl`` after
    they were placed. ``clock`` returns the current time; tests pass their own."""

    def __init__(
        self,
        orders: ExpiringOrders,
        *,
        ttl: timedelta,
        interval: float = 60,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.ttl = ttl
        self._orders = orders
        self._interval = interval
        self._clock = clock
        self._task: asyncio.Task[None] | None = None

    async def run_once(self) -> list[OrderOut]:
        return await self._orders.expire_unpaid(placed_before=self._clock() - self.ttl)

    async def run(self) -> None:
        while True:
            try:
                await self.run_once()
            except Exception:
                # A locked or unreachable database must not stop the next sweeps.
                log.exception("failed to expire unpaid orders")
            await asyncio.sleep(self._interval)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run(), name="expire-unpaid-orders")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
