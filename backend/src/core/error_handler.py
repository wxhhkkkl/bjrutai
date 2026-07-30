import uuid
from datetime import datetime, timezone

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from .exceptions import AppException


def _build_response(code: int, message: str, data: object = None) -> dict:
    return {
        "code": code,
        "message": message,
        "data": data,
        "requestId": uuid.uuid4().hex,
        "serverTime": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }


async def app_exception_handler(request: Request, exc: AppException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_response(exc.code, exc.message, exc.detail),
    )


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content=_build_response(exc.status_code * 100, exc.detail or "HTTP error"),
    )


async def validation_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    """Handle pydantic validation errors (422)."""
    from fastapi.exceptions import RequestValidationError

    if isinstance(exc, RequestValidationError):
        details = []
        for error in exc.errors():
            details.append({
                "loc": error.get("loc", []),
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            })
        return JSONResponse(
            status_code=422,
            content=_build_response(42200, "Validation error", details),
        )
    # Fallback: re-raise so the generic handler catches it
    raise exc


async def generic_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    return JSONResponse(
        status_code=500,
        content=_build_response(50000, "Internal server error"),
    )


def register_error_handlers(app: FastAPI) -> None:
    """Register all custom exception handlers on the FastAPI app."""
    app.add_exception_handler(AppException, app_exception_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)

    from fastapi.exceptions import RequestValidationError

    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(Exception, generic_exception_handler)
