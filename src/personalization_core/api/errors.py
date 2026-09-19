from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from personalization_core.domain.errors import (
    DomainError,
    ErrorCode,
    ProcessingFailedError,
    ProviderInvalidResponseError,
    ProviderNetworkError,
    ProviderTimeoutError,
)

from .dependencies import AuthenticationRequiredError

ERROR_STATUS: Mapping[ErrorCode, int] = {
    ErrorCode.INVALID_ARGUMENT: 400,
    ErrorCode.SUBJECT_NOT_FOUND: 404,
    ErrorCode.SUBJECT_DELETED: 410,
    ErrorCode.ENTITY_NOT_FOUND: 404,
    ErrorCode.MEMORY_NOT_FOUND: 404,
    ErrorCode.MEMORY_ERROR: 500,
    ErrorCode.MEMORY_PROTECTION_ERROR: 409,
    ErrorCode.MEMORY_TRANSITION_ERROR: 409,
    ErrorCode.REVISION_CONFLICT: 409,
    ErrorCode.IDEMPOTENCY_CONFLICT: 409,
    ErrorCode.TENANT_SCOPE_VIOLATION: 403,
    ErrorCode.PROVIDER_TIMEOUT: 504,
    ErrorCode.PROVIDER_NETWORK_ERROR: 502,
    ErrorCode.PROVIDER_INVALID_RESPONSE: 500,
    ErrorCode.PROCESSING_FAILED: 500,
    ErrorCode.PURGE_CONFIRMATION_REQUIRED: 400,
}

REQUEST_TOO_LARGE = "REQUEST_TOO_LARGE"
UNAUTHENTICATED = "UNAUTHENTICATED"


class RequestTooLargeError(Exception):
    pass


def request_id(request: Request) -> str:
    return getattr(request.state, "request_id", "")


def error_response(
    request: Request,
    status_code: int,
    code: str,
    message: str,
    details: dict[str, Any] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "code": code,
                "message": message,
                "details": details or {},
            },
            "request_id": request_id(request),
        },
        headers={"X-Request-Id": request_id(request)},
    )


def success_response(
    request: Request, data: Any, status_code: int = 200
) -> JSONResponse:
    request_id_value = request_id(request)
    return JSONResponse(
        status_code=status_code,
        content={"data": jsonable_encoder(data), "request_id": request_id_value},
        headers={"X-Request-Id": request_id_value},
    )


def _safe_validation_details(exc: RequestValidationError) -> dict[str, Any]:
    return {
        "errors": [
            {
                "loc": list(error.get("loc", ())),
                "type": error.get("type", "validation_error"),
                "message": error.get("msg", "invalid value"),
            }
            for error in exc.errors()
        ]
    }


def install_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(DomainError)
    async def domain_error_handler(request: Request, exc: DomainError) -> JSONResponse:
        return error_response(
            request,
            ERROR_STATUS.get(exc.code, 500),
            exc.code.value,
            exc.message,
            exc.details,
        )

    @app.exception_handler(AuthenticationRequiredError)
    async def authentication_error_handler(
        request: Request, exc: AuthenticationRequiredError
    ) -> JSONResponse:
        return error_response(request, 401, UNAUTHENTICATED, exc.message)

    @app.exception_handler(RequestValidationError)
    async def validation_error_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        return error_response(
            request,
            400,
            ErrorCode.INVALID_ARGUMENT.value,
            "request validation failed",
            _safe_validation_details(exc),
        )

    @app.exception_handler(RequestTooLargeError)
    async def request_too_large_handler(
        request: Request, _: RequestTooLargeError
    ) -> JSONResponse:
        return error_response(
            request, 413, REQUEST_TOO_LARGE, "request body is too large"
        )

    @app.exception_handler(StarletteHTTPException)
    async def http_error_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        return error_response(
            request,
            exc.status_code,
            ErrorCode.INVALID_ARGUMENT.value,
            str(exc.detail),
        )

    @app.exception_handler(TimeoutError)
    async def timeout_error_handler(
        request: Request, exc: TimeoutError
    ) -> JSONResponse:
        mapped = ProviderTimeoutError(str(exc) or "provider timed out")
        return error_response(request, 504, mapped.code.value, mapped.message)

    @app.exception_handler(OSError)
    async def network_error_handler(request: Request, exc: OSError) -> JSONResponse:
        mapped = ProviderNetworkError(str(exc) or "provider network failure")
        return error_response(request, 502, mapped.code.value, mapped.message)

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        if isinstance(
            exc,
            (
                ProviderTimeoutError,
                ProviderNetworkError,
                ProviderInvalidResponseError,
                ProcessingFailedError,
            ),
        ):
            code = exc.code
            return error_response(request, ERROR_STATUS[code], code.value, exc.message)
        return error_response(
            request,
            500,
            ErrorCode.PROCESSING_FAILED.value,
            "request processing failed",
        )
