"""Payments are isolated behind :class:`PaymentGateway`.

The rest of the application never talks to Telegram's payment API directly — swapping Telegram
Stars for a card provider (YooKassa, Stripe, …) means adding one more gateway implementation.
"""

from .base import Invoice, PaymentGateway
from .stars import (
    STARS_CURRENCY,
    TelegramStarsGateway,
    build_invoice,
    check_payment,
    make_payload,
    parse_payload,
)

__all__ = [
    "STARS_CURRENCY",
    "Invoice",
    "PaymentGateway",
    "TelegramStarsGateway",
    "build_invoice",
    "check_payment",
    "make_payload",
    "parse_payload",
]
