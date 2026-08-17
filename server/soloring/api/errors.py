"""Stable SoloRing API error envelope + exception handlers (plan §42, §43).

All SoloRing domain errors and request-validation failures render as one shape:

    {"error_code": "...", "message": "...", "details": {}}
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from soloring.errors import ErrorCode, SoloRingError


def error_response(
    code: str, message: str, *, status_code: int, details: dict | None = None
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"error_code": code, "message": message, "details": details or {}},
    )


def _safe_validation_errors(errors: list[dict]) -> list[dict]:
    """Reduce Pydantic errors to JSON-safe fields (drop non-serializable ctx)."""
    return [
        {"loc": list(e.get("loc", [])), "msg": e.get("msg"), "type": e.get("type")}
        for e in errors
    ]


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SoloRingError)
    async def _soloring_error(_: Request, exc: SoloRingError) -> JSONResponse:
        return error_response(
            exc.code, exc.message, status_code=exc.status_code, details=exc.details
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
        return error_response(
            ErrorCode.VALIDATION_ERROR,
            "Request validation failed.",
            status_code=422,
            details={"errors": _safe_validation_errors(exc.errors())},
        )
