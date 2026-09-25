"""Composition root: wires settings → infrastructure → services → transports."""

from __future__ import annotations

from dataclasses import dataclass

from aiogram import Bot, Dispatcher
from fastapi import FastAPI
from sqlalchemy.ext.asyncio import AsyncEngine

from .api.app import create_app
from .api.context import ApiContext
from .bot.factory import create_bot, create_dispatcher
from .bot.notifier import TelegramNotifier
from .config import Settings
from .db.session import SessionFactory, create_engine, create_session_factory
from .domain.catalog import Catalog
from .domain.pricing import PricingRules
from .payments import TelegramStarsGateway
from .services.orders import OrderService


@dataclass(slots=True)
class Container:
    settings: Settings
    engine: AsyncEngine
    session_factory: SessionFactory
    catalog: Catalog
    rules: PricingRules
    bot: Bot
    order_service: OrderService

    def dispatcher(self) -> Dispatcher:
        return create_dispatcher(
            order_service=self.order_service,
            catalog=self.catalog,
            admin_ids=self.settings.admin_ids,
            webapp_url=self.settings.webapp_url,
        )

    def api(self) -> FastAPI:
        return create_app(
            ApiContext(
                order_service=self.order_service,
                catalog=self.catalog,
                bot_token=self.settings.bot_token.get_secret_value(),
                init_data_ttl=self.settings.init_data_ttl,
                cors_origins=self.settings.cors_origins,
            )
        )

    async def aclose(self) -> None:
        await self.bot.session.close()
        await self.engine.dispose()


def build_container(settings: Settings) -> Container:
    engine = create_engine(settings.database_url)
    session_factory = create_session_factory(engine)
    catalog = Catalog.from_file(settings.catalog_path)
    rules = PricingRules.from_file(settings.pricing_path)
    bot = create_bot(settings.bot_token.get_secret_value())
    service = OrderService(
        session_factory=session_factory,
        catalog=catalog,
        rules=rules,
        notifier=TelegramNotifier(bot, catalog, settings.admin_ids),
        payments=TelegramStarsGateway(bot) if settings.stars_enabled else None,
    )
    return Container(
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        catalog=catalog,
        rules=rules,
        bot=bot,
        order_service=service,
    )
