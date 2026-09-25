from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from tgshop.domain.errors import (
    DomainError,
    InvalidTransition,
    NotFound,
    PaymentError,
    ValidationFailed,
)

_STATUS: dict[type[DomainError], int] = {
    ValidationFailed: status.HTTP_422_UNPROCESSABLE_CONTENT,
    NotFound: status.HTTP_404_NOT_FOUND,
    InvalidTransition: status.HTTP_409_CONFLICT,
    PaymentError: status.HTTP_409_CONFLICT,
}


class ApiError(Exception):
    def __init__(self, status_code: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message


def error_body(code: str, message: str, **extra: Any) -> dict[str, Any]:
    return {"error": {"code": code, "message": message, **extra}}


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(ApiError)
    async def _api_error(_: Request, exc: ApiError) -> JSONResponse:
        return JSONResponse(error_body(exc.code, exc.message), status_code=exc.status_code)

    @app.exception_handler(DomainError)
    async def _domain_error(_: Request, exc: DomainError) -> JSONResponse:
        code = _STATUS.get(type(exc), status.HTTP_400_BAD_REQUEST)
        return JSONResponse(error_body(exc.code, exc.message), status_code=code)

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        details = [
            {"loc": list(err.get("loc", ())), "msg": err.get("msg", ""), "type": err.get("type")}
            for err in exc.errors()
        ]
        return JSONResponse(
            error_body("invalid_request", "Request validation failed", details=details),
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
        )
