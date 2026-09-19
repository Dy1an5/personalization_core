from __future__ import annotations

from dataclasses import dataclass, field
from typing import Annotated

from fastapi import Depends, Request
from pydantic import ValidationError

from personalization_core.domain.errors import (
    InvalidArgumentError,
    TenantScopeViolationError,
)
from personalization_core.domain.identifiers import (
    Namespace,
    SubjectId,
    SubjectRef,
)
from personalization_core.infrastructure.observability.metrics import MetricsRegistry
from personalization_core.sdk.async_client import PersonalizationEngine

from .auth import AuthenticationContext, Authenticator, authenticate_token


@dataclass(frozen=True, slots=True)
class ApiRuntime:
    engine: PersonalizationEngine
    authenticator: Authenticator
    metrics: MetricsRegistry = field(default_factory=MetricsRegistry)


def get_runtime(request: Request) -> ApiRuntime:
    return request.app.state.api_runtime


async def get_authentication(
    request: Request,
    runtime: Annotated[ApiRuntime, Depends(get_runtime)],
) -> AuthenticationContext:
    header = request.headers.get("authorization", "")
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip() or " " in token.strip():
        raise AuthenticationRequiredError("Bearer authentication is required")
    try:
        context = await authenticate_token(runtime.authenticator, token.strip())
    except (ValidationError, ValueError, TypeError) as exc:
        raise AuthenticationRequiredError("Bearer token is invalid") from exc
    if context is None:
        raise AuthenticationRequiredError("Bearer token is invalid")
    return context


class AuthenticationRequiredError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


async def get_subject_ref(
    request: Request,
    subject_id: str,
    auth: Annotated[AuthenticationContext, Depends(get_authentication)],
) -> SubjectRef:
    tenant_header = request.headers.get("x-tenant-id")
    if tenant_header is not None and tenant_header.strip() != str(auth.tenant_id):
        raise TenantScopeViolationError("X-Tenant-Id does not match Bearer tenant")
    namespace_header = request.headers.get("x-namespace", "default")
    try:
        return SubjectRef(
            tenant_id=auth.tenant_id,
            namespace=Namespace(namespace_header),
            subject_id=SubjectId(subject_id),
        )
    except ValidationError as exc:
        raise InvalidArgumentError(
            "invalid tenant, namespace, or subject identifier"
        ) from exc


SubjectDependency = Annotated[SubjectRef, Depends(get_subject_ref)]
TenantDependency = Annotated[AuthenticationContext, Depends(get_authentication)]
