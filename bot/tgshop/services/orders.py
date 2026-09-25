"""Order use-cases. The only place where catalog, pricing, persistence, payments and
notifications meet — transports (REST API, bot updates) stay thin."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import dataclass

from tgshop.db.models import Order, OrderItem
from tgshop.db.repository import OrderRepository
from tgshop.db.session import SessionFactory
from tgshop.domain.catalog import Catalog
from tgshop.domain.enums import DeliveryMethod, OrderSource, OrderStatus, PaymentMethod
from tgshop.domain.errors import NotFound, PaymentError, ValidationFailed
from tgshop.domain.pricing import PricedLine, PricingRules, Quote, calculate_quote
from tgshop.domain.schemas import (
    CartItemIn,
    OrderCreate,
    OrderCreated,
    OrderOut,
    QuoteOut,
    QuoteRequest,
)
from tgshop.domain.status import ensure_transition
from tgshop.payments import PaymentGateway, build_invoice, check_payment, parse_payload

from .notifier import Notifier

log = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class Customer:
    user_id: int
    username: str | None = None
    language: str | None = None


@dataclass(frozen=True, slots=True)
class ResolvedItem:
    product_id: str
    variant_id: str
    grind: str | None
    title: str
    variant_label: str
    unit_price: int
    quantity: int


def _to_dto(order: Order) -> OrderOut:
    return OrderOut.model_validate(order, from_attributes=True)


class OrderService:
    def __init__(
        self,
        *,
        session_factory: SessionFactory,
        catalog: Catalog,
        rules: PricingRules,
        notifier: Notifier,
        payments: PaymentGateway | None,
    ) -> None:
        self._sessions = session_factory
        self._catalog = catalog
        self._rules = rules
        self._notifier = notifier
        self._payments = payments

    @property
    def stars_enabled(self) -> bool:
        return self._payments is not None

    # ------------------------------------------------------------------ pricing
    def _resolve(self, items: Sequence[CartItemIn], lang: str | None) -> list[ResolvedItem]:
        """Resolve client items against the catalog. Client-side prices are never trusted."""
        merged: dict[tuple[str, str, str | None], ResolvedItem] = {}
        for item in items:
            product, variant = self._catalog.variant(item.product_id, item.variant_id)
            if not product.in_stock:
                raise ValidationFailed(f"'{product.id}' is out of stock", code="out_of_stock")
            grind: str | None = None
            if product.grindable:
                grind = self._catalog.grind(item.grind or "beans").id
            elif item.grind:
                raise ValidationFailed(f"'{product.id}' can't be ground", code="unknown_grind")

            key = (product.id, variant.id, grind)
            previous = merged.get(key)
            merged[key] = ResolvedItem(
                product_id=product.id,
                variant_id=variant.id,
                grind=grind,
                title=product.name.get(lang),
                variant_label=variant.label.get(lang),
                unit_price=variant.price,
                quantity=item.quantity + (previous.quantity if previous else 0),
            )
        return list(merged.values())

    def _quote(
        self, items: Sequence[ResolvedItem], delivery: DeliveryMethod, promo: str | None
    ) -> Quote:
        lines = [PricedLine(unit_price=i.unit_price, quantity=i.quantity) for i in items]
        return calculate_quote(lines, delivery, promo, self._rules)

    async def quote(self, request: QuoteRequest) -> QuoteOut:
        items = self._resolve(request.items, lang=None)
        quote = self._quote(items, request.delivery_method, request.promo_code)
        return QuoteOut(
            subtotal=quote.subtotal,
            discount=quote.discount,
            delivery_fee=quote.delivery_fee,
            total=quote.total,
            stars=quote.stars,
            promo_code=quote.promo_code,
            promo_error=quote.promo_error,
        )

    # ------------------------------------------------------------------ placing orders
    async def create_order(
        self, customer: Customer, data: OrderCreate, *, source: OrderSource
    ) -> OrderOut:
        items = self._resolve(data.items, customer.language)
        quote = self._quote(items, data.delivery_method, data.promo_code)
        if quote.promo_error:
            raise ValidationFailed("Unknown promo code", code="unknown_promo")

        is_pickup = data.delivery_method is DeliveryMethod.PICKUP
        if is_pickup:
            self._catalog.pickup_point(data.pickup_point_id or "")

        pays_with_stars = data.payment_method is PaymentMethod.STARS
        if pays_with_stars and not self.stars_enabled:
            raise ValidationFailed("Stars payments are disabled", code="payment_unavailable")

        order = Order(
            user_id=customer.user_id,
            username=customer.username,
            source=source,
            customer_name=data.customer.name,
            phone=data.customer.phone,
            delivery_method=data.delivery_method,
            address=None if is_pickup else data.address,
            pickup_point_id=data.pickup_point_id if is_pickup else None,
            delivery_slot=data.delivery_slot,
            comment=data.comment or None,
            payment_method=data.payment_method,
            promo_code=quote.promo_code,
            subtotal=quote.subtotal,
            discount=quote.discount,
            delivery_fee=quote.delivery_fee,
            total=quote.total,
            stars_amount=quote.stars if pays_with_stars else None,
            items=[
                OrderItem(
                    product_id=i.product_id,
                    variant_id=i.variant_id,
                    grind=i.grind,
                    title=i.title,
                    variant_label=i.variant_label,
                    unit_price=i.unit_price,
                    quantity=i.quantity,
                )
                for i in items
            ],
            events=[],
        )
        order.set_status(OrderStatus.AWAITING_PAYMENT if pays_with_stars else OrderStatus.NEW)

        async with self._sessions() as session, session.begin():
            await OrderRepository(session).add(order)
            dto = _to_dto(order)

        log.info("order %s created by %s via %s", dto.id, customer.user_id, source)
        if dto.status is OrderStatus.NEW:
            await self._notifier.order_placed(dto)
        return dto

    async def place_order(self, customer: Customer, data: OrderCreate) -> OrderCreated:
        """API flow: create the order and, for Stars, an invoice link for ``openInvoice``."""
        order = await self.create_order(customer, data, source=OrderSource.API)
        invoice_url = None
        if order.status is OrderStatus.AWAITING_PAYMENT:
            invoice_url = await self.invoice_link(customer.user_id, order.id)
        return OrderCreated(order=order, invoice_url=invoice_url)

    def _gateway(self) -> PaymentGateway:
        if self._payments is None:
            raise PaymentError("Payments are disabled", code="payment_unavailable")
        return self._payments

    async def invoice_link(self, user_id: int, order_id: int) -> str:
        order = await self.get_for_user(user_id, order_id)
        if order.status is not OrderStatus.AWAITING_PAYMENT:
            raise PaymentError("Order doesn't await payment", code="not_payable")
        return await self._gateway().create_invoice_link(build_invoice(order))

    async def send_invoice(self, chat_id: int, order: OrderOut) -> None:
        await self._gateway().send_invoice(chat_id, build_invoice(order))

    # ------------------------------------------------------------------ queries
    async def get(self, order_id: int) -> OrderOut | None:
        async with self._sessions() as session:
            order = await OrderRepository(session).get(order_id)
            return _to_dto(order) if order else None

    async def get_for_user(self, user_id: int, order_id: int) -> OrderOut:
        order = await self.get(order_id)
        if order is None or order.user_id != user_id:
            # Same error for "missing" and "foreign" so ids can't be enumerated.
            raise NotFound("Order not found")
        return order

    async def list_for_user(self, user_id: int, *, limit: int = 50) -> list[OrderOut]:
        async with self._sessions() as session:
            orders = await OrderRepository(session).list_for_user(user_id, limit=limit)
            return [_to_dto(o) for o in orders]

    async def list_recent(
        self, *, statuses: Sequence[OrderStatus] | None = None, limit: int = 20
    ) -> list[OrderOut]:
        async with self._sessions() as session:
            orders = await OrderRepository(session).list_recent(statuses=statuses, limit=limit)
            return [_to_dto(o) for o in orders]

    # ------------------------------------------------------------------ lifecycle
    async def change_status(
        self, order_id: int, target: OrderStatus, *, note: str | None = None
    ) -> OrderOut:
        if target is OrderStatus.REFUNDED:
            return await self.refund(order_id)
        async with self._sessions() as session, session.begin():
            order = await OrderRepository(session).get(order_id, for_update=True)
            if order is None:
                raise NotFound(f"Order {order_id} not found")
            previous = order.status
            ensure_transition(
                previous, target, delivery=order.delivery_method, payment=order.payment_method
            )
            order.set_status(target, note)
            await session.flush()
            dto = _to_dto(order)
        await self._notifier.status_changed(dto, previous)
        return dto

    async def pre_checkout_error(
        self, *, payload: str, currency: str, total_amount: int, payer_id: int
    ) -> str | None:
        order_id = parse_payload(payload)
        order = await self.get(order_id) if order_id is not None else None
        return check_payment(order, currency=currency, total_amount=total_amount, payer_id=payer_id)

    async def mark_paid(
        self, *, payload: str, currency: str, total_amount: int, payer_id: int, charge_id: str
    ) -> OrderOut:
        order_id = parse_payload(payload)
        if order_id is None:
            raise PaymentError(f"Unexpected invoice payload {payload!r}")

        async with self._sessions() as session, session.begin():
            order = await OrderRepository(session).get(order_id, for_update=True)
            if order is not None and order.telegram_payment_charge_id == charge_id:
                return _to_dto(order)  # duplicated update — already processed
            error = check_payment(
                _to_dto(order) if order else None,
                currency=currency,
                total_amount=total_amount,
                payer_id=payer_id,
            )
            if error is None and order is not None:
                previous = order.status
                order.telegram_payment_charge_id = charge_id
                order.set_status(OrderStatus.PAID)
                await session.flush()
                dto = _to_dto(order)

        if error is not None or order is None:
            # Money was taken but the order can't accept it (e.g. cancelled meanwhile):
            # give the Stars back immediately instead of leaving it for manual support.
            log.warning("refunding orphan payment %s for order %s: %s", charge_id, order_id, error)
            await self._gateway().refund(payer_id, charge_id)
            raise PaymentError(error or "Order not found")

        await self._notifier.order_placed(dto)
        await self._notifier.status_changed(dto, previous)
        return dto

    async def refund(self, order_id: int) -> OrderOut:
        async with self._sessions() as session, session.begin():
            order = await OrderRepository(session).get(order_id, for_update=True)
            if order is None:
                raise NotFound(f"Order {order_id} not found")
            previous = order.status
            ensure_transition(
                previous,
                OrderStatus.REFUNDED,
                delivery=order.delivery_method,
                payment=order.payment_method,
            )
            if not order.telegram_payment_charge_id:
                raise PaymentError("Order has no captured payment", code="not_refundable")
            await self._gateway().refund(order.user_id, order.telegram_payment_charge_id)
            order.set_status(OrderStatus.REFUNDED)
            await session.flush()
            dto = _to_dto(order)
        await self._notifier.status_changed(dto, previous)
        return dto
