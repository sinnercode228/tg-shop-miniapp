"""SQLAlchemy 2.0 ORM models."""

from __future__ import annotations

from datetime import UTC, datetime
from enum import StrEnum
from typing import Any, ClassVar

from sqlalchemy import BigInteger, DateTime, Enum, ForeignKey, Integer, String, Text
from sqlalchemy.engine import Dialect
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship
from sqlalchemy.types import TypeDecorator

from tgshop.domain.enums import (
    DeliveryMethod,
    DeliverySlot,
    OrderSource,
    OrderStatus,
    PaymentMethod,
)


def utcnow() -> datetime:
    return datetime.now(UTC)


class UTCDateTime(TypeDecorator[datetime]):
    """Timezone-aware datetime that survives SQLite (which drops tzinfo on read)."""

    impl = DateTime(timezone=True)
    cache_ok = True

    def process_bind_param(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            raise ValueError("naive datetimes are not allowed")
        return value.astimezone(UTC) if value is not None else None

    def process_result_value(self, value: datetime | None, dialect: Dialect) -> datetime | None:
        if value is not None and value.tzinfo is None:
            return value.replace(tzinfo=UTC)
        return value


def _enum(enum_cls: type[StrEnum]) -> Enum:
    return Enum(
        enum_cls,
        native_enum=False,
        length=24,
        values_callable=lambda members: [m.value for m in members],
        validate_strings=True,
    )


class Base(DeclarativeBase):
    type_annotation_map: ClassVar[dict[Any, Any]] = {datetime: UTCDateTime}


class Order(Base):
    __tablename__ = "orders"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, index=True)
    username: Mapped[str | None] = mapped_column(String(64))
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus), index=True)
    source: Mapped[OrderSource] = mapped_column(_enum(OrderSource))

    customer_name: Mapped[str] = mapped_column(String(64))
    phone: Mapped[str] = mapped_column(String(20))
    delivery_method: Mapped[DeliveryMethod] = mapped_column(_enum(DeliveryMethod))
    address: Mapped[str | None] = mapped_column(String(200))
    pickup_point_id: Mapped[str | None] = mapped_column(String(64))
    delivery_slot: Mapped[DeliverySlot] = mapped_column(_enum(DeliverySlot))
    comment: Mapped[str | None] = mapped_column(Text)

    payment_method: Mapped[PaymentMethod] = mapped_column(_enum(PaymentMethod))
    promo_code: Mapped[str | None] = mapped_column(String(32))
    subtotal: Mapped[int] = mapped_column(Integer)
    discount: Mapped[int] = mapped_column(Integer)
    delivery_fee: Mapped[int] = mapped_column(Integer)
    total: Mapped[int] = mapped_column(Integer)
    stars_amount: Mapped[int | None] = mapped_column(Integer)
    telegram_payment_charge_id: Mapped[str | None] = mapped_column(String(128), unique=True)

    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(default=utcnow, onupdate=utcnow)

    items: Mapped[list[OrderItem]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OrderItem.id",
    )
    events: Mapped[list[OrderEvent]] = relationship(
        back_populates="order",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="OrderEvent.id",
    )

    def set_status(self, status: OrderStatus, note: str | None = None) -> None:
        self.status = status
        self.events.append(OrderEvent(status=status, note=note))


class OrderItem(Base):
    __tablename__ = "order_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    product_id: Mapped[str] = mapped_column(String(64))
    variant_id: Mapped[str] = mapped_column(String(32))
    grind: Mapped[str | None] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(128))
    variant_label: Mapped[str] = mapped_column(String(64))
    unit_price: Mapped[int] = mapped_column(Integer)
    quantity: Mapped[int] = mapped_column(Integer)

    order: Mapped[Order] = relationship(back_populates="items")


class OrderEvent(Base):
    __tablename__ = "order_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    order_id: Mapped[int] = mapped_column(ForeignKey("orders.id", ondelete="CASCADE"), index=True)
    status: Mapped[OrderStatus] = mapped_column(_enum(OrderStatus))
    note: Mapped[str | None] = mapped_column(String(200))
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

    order: Mapped[Order] = relationship(back_populates="events")
