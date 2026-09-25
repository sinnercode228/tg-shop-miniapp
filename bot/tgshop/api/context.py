from __future__ import annotations

from dataclasses import dataclass, field

from tgshop.domain.catalog import Catalog
from tgshop.services.orders import OrderService


@dataclass(frozen=True, slots=True)
class ApiContext:
    """Everything the HTTP layer needs — built once at startup, stored on ``app.state``."""

    order_service: OrderService
    catalog: Catalog
    bot_token: str
    init_data_ttl: int = 24 * 60 * 60
    cors_origins: list[str] = field(default_factory=list)
