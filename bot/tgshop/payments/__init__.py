"""Payments are isolated behind :class:`PaymentGateway` and :class:`RefundQueue`.

The rest of the application never talks to Telegram's payment API directly — swapping Telegram
Stars for a card provider (YooKassa, Stripe, …) means adding one more gateway implementation.
"""

from .base import Invoice, PaymentGateway, RefundQueue
from .stars import TelegramStarsGateway, build_invoice, check_payment

__all__ = [
    "Invoice",
    "PaymentGateway",
    "RefundQueue",
    "TelegramStarsGateway",
    "build_invoice",
    "check_payment",
]
