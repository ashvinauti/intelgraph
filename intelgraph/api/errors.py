from __future__ import annotations

from typing import Any

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(
        self,
        code: str,
        message: str,
        status_code: int = 400,
        details: list[dict[str, str]] | None = None,
    ) -> None:
        self.code = code
        self.message = message
        self.status_code = status_code
        self.details = details or []


def _error_body(
    code: str, message: str, details: list[dict[str, str]] | None = None
) -> dict[str, Any]:
    body: dict[str, Any] = {"code": code, "message": message}
    if details:
        body["details"] = details
    return body


def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_error_body(exc.code, exc.message, exc.details),
    )


def validation_error_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    details = []
    for err in exc.errors():
        field = ".".join(str(loc) for loc in err.get("loc", []))
        details.append({"field": field, "error": err.get("msg", "invalid")})
    return JSONResponse(
        status_code=422,
        content=_error_body("VALIDATION_ERROR", "Request validation failed", details),
    )


def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    import structlog

    structlog.get_logger(__name__).error("unhandled exception", error=str(exc), exc_info=True)
    return JSONResponse(
        status_code=500,
        content=_error_body("INTERNAL_ERROR", "Internal server error"),
    )
