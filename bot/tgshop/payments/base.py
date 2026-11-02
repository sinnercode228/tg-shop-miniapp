from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol


@dataclass(frozen=True, slots=True)
class Invoice:
    order_id: int
    title: str
    description: str
    label: str
    amount: int


class PaymentGateway(Protocol):
    async def create_invoice_link(self, invoice: Invoice) -> str:
        """Return a link the Mini App opens with ``Telegram.WebApp.openInvoice``."""
        ...

    async def send_invoice(self, chat_id: int, invoice: Invoice) -> None:
        """Send an invoice message to a chat (used by the ``web_app_data`` flow)."""
        ...


class RefundQueue(Protocol):
    async def refund(
        self, charge_id: str, *, user_id: int | None = None, reason: str | None = None
    ) -> object:
        """Store a refund of the charge to ``user_id``; it is sent in the background."""
        ...
