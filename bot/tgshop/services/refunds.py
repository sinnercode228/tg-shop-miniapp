"""Sends the Stars refunds recorded in the ``refunds`` table.

``OrderService`` writes a refund row in the same transaction as the order change that calls for
it. ``refundStarPayment`` is called here, after that commit and outside any transaction, so a
failed commit leaves neither the refund nor the status change, and a Bot API error is retried.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta

from tgshop.db.models import Refund, utcnow
from tgshop.db.repository import OrderRepository, RefundRepository
from tgshop.db.session import SessionFactory
from tgshop.domain.enums import RefundStatus
from tgshop.domain.schemas import OrderOut
from tgshop.payments import PaymentGateway

from .notifier import Notifier

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class RefundOut:
    id: int
    order_id: int | None
    user_id: int
    amount: int
    charge_id: str
    reason: str | None
    status: RefundStatus
    attempts: int
    next_attempt_at: datetime
    last_error: str | None

    @classmethod
    def of(cls, refund: Refund) -> RefundOut:
        return cls(
            id=refund.id,
            order_id=refund.order_id,
            user_id=refund.user_id,
            amount=refund.amount,
            charge_id=refund.telegram_payment_charge_id,
            reason=refund.reason,
            status=refund.status,
            attempts=refund.attempts,
            next_attempt_at=refund.next_attempt_at,
            last_error=refund.last_error,
        )


class RefundOutbox:
    """Every ``interval`` seconds, and right after ``wake``, sends the refunds that are due.

    A failed attempt is retried ``retry_delay`` later, and each next wait is twice as long. After
    ``max_attempts`` failures the refund is marked failed and the admins are told. ``clock``
    returns the current time; tests pass their own.
    """

    def __init__(
        self,
        session_factory: SessionFactory,
        payments: PaymentGateway,
        notifier: Notifier,
        *,
        max_attempts: int = 8,
        retry_delay: timedelta = timedelta(seconds=30),
        interval: float = 10,
        clock: Callable[[], datetime] = utcnow,
    ) -> None:
        self.max_attempts = max_attempts
        self.retry_delay = retry_delay
        self._sessions = session_factory
        self._payments = payments
        self._notifier = notifier
        self._interval = interval
        self._clock = clock
        self._wakeup = asyncio.Event()
        self._task: asyncio.Task[None] | None = None

    def wake(self) -> None:
        """A refund was recorded: send it now rather than at the next interval."""
        self._wakeup.set()

    async def run_once(self) -> list[RefundOut]:
        """Make one attempt at every due refund and return them as they are after it."""
        async with self._sessions() as session:
            due = [RefundOut.of(r) for r in await RefundRepository(session).due(self._clock())]
        return [await self._attempt(refund) for refund in due]

    async def _attempt(self, refund: RefundOut) -> RefundOut:
        error: str | None = None
        try:
            await self._payments.refund(refund.user_id, refund.charge_id)
        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"
            log.warning("refund %s of charge %s failed: %s", refund.id, refund.charge_id, error)

        order: OrderOut | None = None
        async with self._sessions() as session, session.begin():
            row = await RefundRepository(session).get(refund.id)
            row.attempts += 1
            if error is None:
                row.status = RefundStatus.DONE
            else:
                row.last_error = error
                if row.attempts >= self.max_attempts:
                    row.status = RefundStatus.FAILED
                else:
                    row.next_attempt_at = self._clock() + self.retry_delay * 2 ** (row.attempts - 1)
            await session.flush()
            refund = RefundOut.of(row)
            if refund.status is RefundStatus.DONE and refund.reason is None and refund.order_id:
                found = await OrderRepository(session).get(refund.order_id)
                order = OrderOut.model_validate(found, from_attributes=True) if found else None

        if refund.status is RefundStatus.FAILED:
            log.error("refund %s of charge %s failed for good", refund.id, refund.charge_id)
            await self._notifier.refund_failed(refund)
        elif refund.status is RefundStatus.DONE:
            if refund.reason is not None:
                await self._notifier.payment_returned(refund.user_id, refund.reason)
            elif order is not None:
                await self._notifier.order_refunded(order)
        return refund

    async def run(self) -> None:
        while True:
            # Cleared before the sweep, so a wake during it starts the next one at once.
            self._wakeup.clear()
            try:
                await self.run_once()
            except Exception:
                # A locked or unreachable database must not stop the next sweeps.
                log.exception("failed to send refunds")
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._wakeup.wait(), self._interval)

    @property
    def running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def start(self) -> None:
        if self._task is None:
            self._task = asyncio.create_task(self.run(), name="send-star-refunds")

    async def stop(self) -> None:
        if self._task is None:
            return
        self._task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await self._task
        self._task = None
