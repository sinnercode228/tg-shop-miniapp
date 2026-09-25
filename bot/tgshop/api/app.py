from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from tgshop import __version__

from .context import ApiContext
from .errors import install_error_handlers
from .routes import catalog, orders


def create_app(ctx: ApiContext) -> FastAPI:
    app = FastAPI(
        title="Zernolist Mini App API",
        version=__version__,
        description="Catalog, pricing and orders for the Telegram Mini App (demo project).",
        docs_url="/api/docs",
        openapi_url="/api/openapi.json",
        redoc_url=None,
    )
    app.state.ctx = ctx
    app.add_middleware(
        CORSMiddleware,
        allow_origins=ctx.cors_origins,
        allow_methods=["GET", "POST"],
        allow_headers=["Authorization", "Content-Type"],
        max_age=600,
    )
    install_error_handlers(app)
    app.include_router(catalog.router, prefix="/api")
    app.include_router(orders.router, prefix="/api")
    return app
