"""Entry point: ``python -m tgshop [--mode all|bot|api]``."""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import logging
from typing import Literal

import uvicorn
from fastapi import FastAPI

from .bot.factory import setup_bot_ui
from .config import Settings
from .container import build_container
from .db.session import init_models

Mode = Literal["all", "bot", "api"]
log = logging.getLogger("tgshop")


async def run(settings: Settings, mode: Mode) -> None:
    container = build_container(settings)
    await init_models(container.engine)
    try:
        if mode == "api":
            await _api_server(container.api(), settings).serve()
            return

        dp = container.dispatcher()
        await setup_bot_ui(
            container.bot, webapp_url=settings.webapp_url, admin_ids=settings.admin_ids
        )
        if mode == "bot":
            await dp.start_polling(container.bot)
            return

        server = _api_server(container.api(), settings)

        async def api_then_stop_bot() -> None:
            await server.serve()  # returns after SIGINT/SIGTERM (uvicorn owns the signals)
            with contextlib.suppress(RuntimeError):
                await dp.stop_polling()

        await asyncio.gather(
            dp.start_polling(container.bot, handle_signals=False), api_then_stop_bot()
        )
    finally:
        await container.aclose()


def _api_server(app: FastAPI, settings: Settings) -> uvicorn.Server:
    config = uvicorn.Config(
        app,
        host=settings.api_host,
        port=settings.api_port,
        log_level=settings.log_level.lower(),
        proxy_headers=True,
    )
    return uvicorn.Server(config)


def main() -> None:
    parser = argparse.ArgumentParser(prog="tgshop", description=__doc__)
    parser.add_argument("--mode", choices=["all", "bot", "api"], default="all")
    args = parser.parse_args()

    settings = Settings()  # values come from the environment / .env
    logging.basicConfig(
        level=settings.log_level.upper(),
        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
    )
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(run(settings, args.mode))


if __name__ == "__main__":
    main()
