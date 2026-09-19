from __future__ import annotations

from typing import Any


class SyncClientInAsyncContextError(RuntimeError):
    """Raised when the synchronous SDK wrapper is used inside an event loop."""


class SDKError(Exception):
    """Base class for errors raised by the remote SDK.

    The exception deliberately stores only the server's structured error data.
    Authorization headers and client credentials are never included.
    """

    def __init__(
        self,
        message: str,
        *,
        code: str | None = None,
        details: dict[str, Any] | None = None,
        status_code: int | None = None,
        request_id: str | None = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code
        self.details = details or {}
        self.status_code = status_code
        self.request_id = request_id


class TransportError(SDKError):
    """A network or HTTP transport failure."""


class SDKTimeoutError(TransportError):
    """The request exceeded its configured timeout."""


class HTTPError(SDKError):
    """The server returned a non-success HTTP status."""


class ServerError(HTTPError):
    """The server or an upstream provider returned a 5xx response."""


class SDKInvalidArgumentError(HTTPError):
    pass


class SDKUnauthenticatedError(HTTPError):
    pass


class SDKTenantScopeViolationError(HTTPError):
    pass


class SDKNotFoundError(HTTPError):
    pass


class SDKSubjectDeletedError(HTTPError):
    pass


class SDKRevisionConflictError(HTTPError):
    pass


class SDKIdempotencyConflictError(HTTPError):
    pass


class SDKRequestTooLargeError(HTTPError):
    pass


class SDKProviderError(ServerError):
    pass


class SDKProcessingFailedError(ServerError):
    pass


# Friendly aliases for callers that prefer the shorter stable names.
InvalidArgumentError = SDKInvalidArgumentError
UnauthenticatedError = SDKUnauthenticatedError
TenantScopeViolationError = SDKTenantScopeViolationError
NotFoundError = SDKNotFoundError
SubjectDeletedError = SDKSubjectDeletedError
RevisionConflictError = SDKRevisionConflictError
IdempotencyConflictError = SDKIdempotencyConflictError
RequestTooLargeError = SDKRequestTooLargeError
ProviderError = SDKProviderError
ProcessingFailedError = SDKProcessingFailedError
TimeoutError = SDKTimeoutError
RemoteHTTPError = HTTPError
RemoteServerError = ServerError
