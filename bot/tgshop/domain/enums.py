"""Domain enumerations shared by the API, the bot and the persistence layer."""

from enum import StrEnum


class DeliveryMethod(StrEnum):
    COURIER = "courier"
    PICKUP = "pickup"


class PaymentMethod(StrEnum):
    STARS = "stars"
    ON_RECEIPT = "on_receipt"


class OrderSource(StrEnum):
    API = "api"
    WEB_APP_DATA = "web_app_data"


class DeliverySlot(StrEnum):
    ASAP = "asap"
    MORNING = "morning"
    EVENING = "evening"


class OrderStatus(StrEnum):
    AWAITING_PAYMENT = "awaiting_payment"
    NEW = "new"
    PAID = "paid"
    CONFIRMED = "confirmed"
    IN_DELIVERY = "in_delivery"
    READY_FOR_PICKUP = "ready_for_pickup"
    COMPLETED = "completed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"

    @property
    def is_final(self) -> bool:
        return self in _FINAL


_FINAL = frozenset({OrderStatus.COMPLETED, OrderStatus.CANCELLED, OrderStatus.REFUNDED})
