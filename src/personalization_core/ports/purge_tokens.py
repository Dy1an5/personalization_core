from __future__ import annotations

import asyncio
import hashlib
import secrets
from datetime import datetime, timedelta
from typing import Protocol, runtime_checkable

from personalization_core.domain.base import StrictFrozenDomainModel
from personalization_core.domain.identifiers import SubjectRef
from personalization_core.domain.types import NonEmptyString, UtcDatetime


class PurgeToken(StrictFrozenDomainModel):
    token: NonEmptyString
    subject: SubjectRef
    expires_at: UtcDatetime


@runtime_checkable
class PurgeTokenStore(Protocol):
    async def issue(
        self, subject: SubjectRef, now: UtcDatetime, ttl: timedelta
    ) -> PurgeToken:
        raise NotImplementedError

    async def consume(
        self, subject: SubjectRef, token: str, now: UtcDatetime
    ) -> PurgeToken | None:
        raise NotImplementedError


class InMemoryPurgeTokenStore:
    """Single-process, one-time purge token store.

    Only SHA-256 digests are retained, so a database or memory dump does not
    contain a usable purge credential.
    """

    def __init__(self) -> None:
        self._tokens: dict[str, tuple[SubjectRef, datetime]] = {}
        self._lock = asyncio.Lock()

    async def issue(
        self, subject: SubjectRef, now: UtcDatetime, ttl: timedelta
    ) -> PurgeToken:
        if ttl <= timedelta(0):
            raise ValueError("purge token ttl must be positive")
        token = secrets.token_urlsafe(32)
        expires_at = now + ttl
        async with self._lock:
            self._tokens[self._digest(token)] = (subject, expires_at)
        return PurgeToken(token=token, subject=subject, expires_at=expires_at)

    async def consume(
        self, subject: SubjectRef, token: str, now: UtcDatetime
    ) -> PurgeToken | None:
        digest = self._digest(token)
        async with self._lock:
            stored = self._tokens.get(digest)
            if stored is None:
                return None
            stored_subject, expires_at = stored
            if expires_at <= now:
                del self._tokens[digest]
                return None
            if stored_subject != subject:
                return None
            del self._tokens[digest]
        return PurgeToken(token=token, subject=subject, expires_at=expires_at)

    @staticmethod
    def _digest(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()


MemoryPurgeTokenStore = InMemoryPurgeTokenStore
