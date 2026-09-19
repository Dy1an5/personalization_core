from __future__ import annotations

import inspect
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Protocol, TypeAlias

from personalization_core.domain.identifiers import TenantId


@dataclass(frozen=True, slots=True)
class AuthenticationContext:
    """The only tenant identity trusted by the HTTP adapter."""

    tenant_id: TenantId


AuthenticationResult: TypeAlias = AuthenticationContext | TenantId | str | None


class Authenticator(Protocol):
    def authenticate(self, token: str) -> AuthenticationResult | object:
        """Return an authenticated tenant, or ``None`` for an unknown token.

        Implementations may return an awaitable as well as a regular value.
        """


class TokenAuthenticator:
    """Small deterministic authenticator useful for embedded deployments/tests."""

    def __init__(self, tokens: Mapping[str, str | TenantId]) -> None:
        self._tokens = dict(tokens)

    def authenticate(self, token: str) -> AuthenticationContext | None:
        tenant = self._tokens.get(token)
        if tenant is None:
            return None
        return AuthenticationContext(
            tenant_id=tenant if isinstance(tenant, TenantId) else TenantId(tenant)
        )


async def authenticate_token(
    authenticator: Authenticator, token: str
) -> AuthenticationContext | None:
    result = authenticator.authenticate(token)
    if inspect.isawaitable(result):
        result = await result
    if result is None:
        return None
    if isinstance(result, AuthenticationContext):
        return result
    if isinstance(result, TenantId):
        return AuthenticationContext(tenant_id=result)
    if isinstance(result, str):
        return AuthenticationContext(tenant_id=TenantId(result))
    raise TypeError("authenticator returned an invalid result")
