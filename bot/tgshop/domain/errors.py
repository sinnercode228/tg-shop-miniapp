"""Domain-level exceptions. The API and bot layers translate them to transport errors."""

from __future__ import annotations


class DomainError(Exception):
    """Base class for expected, user-facing business errors."""

    code: str = "domain_error"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        self.message = message
        if code is not None:
            self.code = code


class ValidationFailed(DomainError):
    code = "validation_failed"


class NotFound(DomainError):
    code = "not_found"


class InvalidTransition(DomainError):
    code = "invalid_transition"


class PaymentError(DomainError):
    code = "payment_error"
