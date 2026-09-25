from __future__ import annotations

from fastapi import APIRouter, status

from tgshop.api.deps import CurrentCustomer, Orders
from tgshop.domain.base import CamelModel
from tgshop.domain.schemas import OrderCreate, OrderCreated, OrderOut

router = APIRouter(prefix="/orders", tags=["orders"])


class InvoiceOut(CamelModel):
    invoice_url: str


@router.post("", response_model=OrderCreated, status_code=status.HTTP_201_CREATED)
async def create_order(
    body: OrderCreate, customer: CurrentCustomer, orders: Orders
) -> OrderCreated:
    return await orders.place_order(customer, body)


@router.get("", response_model=list[OrderOut])
async def list_orders(customer: CurrentCustomer, orders: Orders) -> list[OrderOut]:
    return await orders.list_for_user(customer.user_id)


@router.get("/{order_id}", response_model=OrderOut)
async def get_order(order_id: int, customer: CurrentCustomer, orders: Orders) -> OrderOut:
    return await orders.get_for_user(customer.user_id, order_id)


@router.post("/{order_id}/invoice", response_model=InvoiceOut)
async def create_invoice(order_id: int, customer: CurrentCustomer, orders: Orders) -> InvoiceOut:
    """Re-issue a Stars invoice link for an order that is still awaiting payment."""
    return InvoiceOut(invoice_url=await orders.invoice_link(customer.user_id, order_id))
