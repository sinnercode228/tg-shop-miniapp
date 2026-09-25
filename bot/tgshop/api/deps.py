from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Header, Request, status

from tgshop.security.init_data import InitDataError, WebAppInitData, validate_init_data
from tgshop.services.orders import Customer, OrderService

from .context import ApiContext
from .errors import ApiError


def get_context(request: Request) -> ApiContext:
    ctx: ApiContext = request.app.state.ctx
    return ctx


Context = Annotated[ApiContext, Depends(get_context)]


def get_order_service(ctx: Context) -> OrderService:
    return ctx.order_service


Orders = Annotated[OrderService, Depends(get_order_service)]


def get_init_data(
    ctx: Context, authorization: Annotated[str | None, Header()] = None
) -> WebAppInitData:
    """Authenticate the Mini App user by ``Authorization: tma <initData>``."""
    if not authorization:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "unauthorized", "Missing Authorization")
    scheme, _, init_data = authorization.partition(" ")
    if scheme.lower() != "tma" or not init_data:
        raise ApiError(status.HTTP_401_UNAUTHORIZED, "unauthorized", "Expected 'tma <initData>'")
    try:
        return validate_init_data(init_data.strip(), ctx.bot_token, max_age=ctx.init_data_ttl)
    except InitDataError as exc:
        raise ApiError(
            status.HTTP_401_UNAUTHORIZED, "unauthorized", f"Invalid init data: {exc.reason}"
        ) from exc


def get_customer(init_data: Annotated[WebAppInitData, Depends(get_init_data)]) -> Customer:
    user = init_data.user
    return Customer(user_id=user.id, username=user.username, language=user.language_code)


CurrentCustomer = Annotated[Customer, Depends(get_customer)]
