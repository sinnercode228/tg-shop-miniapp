from __future__ import annotations

from fastapi import APIRouter, Response

from tgshop import __version__
from tgshop.api.deps import Context, Orders
from tgshop.domain.catalog import Catalog
from tgshop.domain.schemas import QuoteOut, QuoteRequest

router = APIRouter(tags=["catalog"])


@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "version": __version__}


@router.get("/catalog", response_model=Catalog)
async def get_catalog(ctx: Context, response: Response) -> Catalog:
    response.headers["Cache-Control"] = "public, max-age=300"
    return ctx.catalog


@router.post("/quote", response_model=QuoteOut)
async def quote(body: QuoteRequest, orders: Orders) -> QuoteOut:
    """Server-side price calculation for the cart (the client never decides prices)."""
    return await orders.quote(body)
