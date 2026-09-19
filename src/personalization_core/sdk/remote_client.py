from __future__ import annotations

import asyncio
import json
from collections.abc import Callable, Mapping, Sequence
from datetime import datetime
from typing import Any, TypeVar, cast
from uuid import UUID, uuid4

import httpx
from pydantic import BaseModel, TypeAdapter

from personalization_core.application.dto import (
    BatchIngestionResult,
    BatchMode,
    EventIngestionInput,
    EventIngestionResult,
    EventPage,
    ExportEntity,
    MemoryCreateInput,
    MemoryExtractionResult,
    MemoryPage,
    MemoryPatchInput,
    ProfileRefreshOptions,
    PurgeResult,
    SubjectExport,
)
from personalization_core.domain.context import ContextBundle, ContextRequest
from personalization_core.domain.entities import EntityCreate
from personalization_core.domain.memory import MemoryRecord
from personalization_core.domain.profile import ProfileDiff, ProfileSnapshot
from personalization_core.domain.subjects import Subject
from personalization_core.ports.memory_extractor import ConversationMessage
from personalization_core.ports.repositories import EventFilter, MemoryFilter, Page

from .errors import (
    HTTPError,
    SDKError,
    SDKIdempotencyConflictError,
    SDKInvalidArgumentError,
    SDKNotFoundError,
    SDKProcessingFailedError,
    SDKProviderError,
    SDKRequestTooLargeError,
    SDKRevisionConflictError,
    SDKSubjectDeletedError,
    SDKTenantScopeViolationError,
    SDKTimeoutError,
    SDKUnauthenticatedError,
    ServerError,
    TransportError,
)

# pyright: reportPrivateUsage=false

_T = TypeVar("_T")
_RetryBackoff = float | Callable[[int], float]
_RETRYABLE_STATUS = frozenset({502, 503, 504})


def _json_model(value: BaseModel | None) -> dict[str, Any] | None:
    if value is None:
        return None
    return value.model_dump(mode="json")


def _enum_or_value(value: Any) -> Any:
    return getattr(value, "value", value)


def _redact(value: Any, secret: str) -> Any:
    if not secret:
        return value
    if isinstance(value, str):
        return value.replace(secret, "[REDACTED]")
    if isinstance(value, Mapping):
        mapping = cast(Mapping[Any, Any], value)
        return {str(key): _redact(item, secret) for key, item in mapping.items()}
    if isinstance(value, list):
        items = cast(list[Any], value)
        return [_redact(item, secret) for item in items]
    return value


class _OperationGroup:
    def __init__(self, client: AsyncPersonalizationClient) -> None:
        self._client = client


class HealthOperations(_OperationGroup):
    async def live(self, *, request_id: str | None = None) -> dict[str, Any]:
        return await self._client._request("GET", "/health/live", request_id=request_id)

    async def ready(self, *, request_id: str | None = None) -> dict[str, Any]:
        return await self._client._request(
            "GET", "/health/ready", request_id=request_id
        )


class EventRemoteOperations(_OperationGroup):
    async def upsert_entity(
        self,
        subject_id: str,
        entity: EntityCreate,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any] | ExportEntity:
        data = await self._client._request(
            "POST",
            f"/subjects/{subject_id}/entities",
            json_body=_json_model(entity),
            request_id=request_id,
            response_type=dict[str, Any],
        )
        # The API intentionally returns the legacy Entity as a JSON object.  A
        # validated ExportEntity is returned when all fields are present.
        try:
            return ExportEntity.model_validate(data)
        except Exception:
            return data

    async def ingest_event(
        self,
        subject_id: str,
        event: EventIngestionInput,
        *,
        request_id: str | None = None,
        idempotency_key: str | None = None,
    ) -> EventIngestionResult:
        event_key = str(event.event.idempotency_key)
        if idempotency_key is not None and idempotency_key != event_key:
            raise ValueError("idempotency_key must match event.idempotency_key")
        key = idempotency_key or event_key
        return await self._client._request(
            "POST",
            f"/subjects/{subject_id}/events",
            json_body=_json_model(event),
            request_id=request_id,
            idempotency_key=key,
            response_type=EventIngestionResult,
            retryable=True,
        )

    async def ingest_batch(
        self,
        subject_id: str,
        events: Sequence[EventIngestionInput],
        *,
        mode: BatchMode = BatchMode.ATOMIC,
        request_id: str | None = None,
    ) -> BatchIngestionResult:
        body = {
            "events": [event.model_dump(mode="json") for event in events],
            "mode": mode.value,
        }
        return await self._client._request(
            "POST",
            f"/subjects/{subject_id}/events:batch",
            json_body=body,
            request_id=request_id,
            response_type=BatchIngestionResult,
        )

    async def list_events(
        self,
        subject_id: str,
        filters: EventFilter | None = None,
        page: Page | None = None,
        *,
        limit: int | None = None,
        offset: int | None = None,
        request_id: str | None = None,
    ) -> EventPage:
        active_page = page or Page()
        query: dict[str, Any] = {
            "limit": limit if limit is not None else active_page.limit,
            "offset": offset if offset is not None else active_page.offset,
        }
        if filters is not None:
            for name in (
                "event_type",
                "source",
                "polarity",
                "occurred_from",
                "occurred_until",
            ):
                value = getattr(filters, name)
                if value is not None:
                    query[name] = _enum_or_value(value)
                    if isinstance(value, datetime):
                        query[name] = value.isoformat()
        return await self._client._request(
            "GET",
            f"/subjects/{subject_id}/events",
            params=query,
            request_id=request_id,
            response_type=EventPage,
        )

    async def list(self, subject_id: str, *args: Any, **kwargs: Any) -> EventPage:
        return await self.list_events(subject_id, *args, **kwargs)


class MemoryRemoteOperations(_OperationGroup):
    async def add(
        self,
        subject_id: str,
        input: MemoryCreateInput,
        *,
        request_id: str | None = None,
    ) -> MemoryRecord:
        return await self._client._request(
            "POST",
            f"/subjects/{subject_id}/memories",
            json_body=_json_model(input),
            request_id=request_id,
            response_type=MemoryRecord,
        )

    async def list(
        self,
        subject_id: str,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
        *,
        limit: int | None = None,
        offset: int | None = None,
        request_id: str | None = None,
    ) -> MemoryPage:
        active_page = page or Page()
        query = {
            "limit": limit if limit is not None else active_page.limit,
            "offset": offset if offset is not None else active_page.offset,
        }
        # The list endpoint only exposes pagination in the current OpenAPI
        # contract; retain filters for symmetry with the Embedded facade.
        del filters
        return await self._client._request(
            "GET",
            f"/subjects/{subject_id}/memories",
            params=query,
            request_id=request_id,
            response_type=MemoryPage,
        )

    async def extract(
        self,
        subject_id: str,
        messages: Sequence[ConversationMessage],
        *,
        request_id: str | None = None,
    ) -> MemoryExtractionResult:
        return await self._client._request(
            "POST",
            f"/subjects/{subject_id}/memories:extract",
            json_body={
                "messages": [message.model_dump(mode="json") for message in messages]
            },
            request_id=request_id,
            response_type=MemoryExtractionResult,
        )

    async def search(
        self,
        subject_id: str,
        filters: MemoryFilter | None = None,
        page: Page | None = None,
        *,
        limit: int | None = None,
        offset: int | None = None,
        request_id: str | None = None,
    ) -> MemoryPage:
        active_page = page or Page()
        active_limit = limit if limit is not None else active_page.limit
        active_offset = offset if offset is not None else active_page.offset
        body: dict[str, Any] = {"limit": active_limit, "offset": active_offset}
        if filters is not None:
            for name in (
                "key",
                "kind",
                "authority",
                "scope",
                "scope_value",
                "target_dimension",
                "target_value_key",
            ):
                value = getattr(filters, name)
                if value is not None:
                    body[name] = _enum_or_value(value)
        return await self._client._request(
            "POST",
            f"/subjects/{subject_id}/memories:search",
            json_body=body,
            request_id=request_id,
            response_type=MemoryPage,
        )

    async def get(
        self, subject_id: str, memory_id: UUID, *, request_id: str | None = None
    ) -> MemoryRecord:
        return await self._client._request(
            "GET",
            f"/subjects/{subject_id}/memories/{memory_id}",
            request_id=request_id,
            response_type=MemoryRecord,
        )

    async def patch(
        self,
        subject_id: str,
        memory_id: UUID,
        patch: MemoryPatchInput,
        *,
        request_id: str | None = None,
    ) -> MemoryRecord:
        return await self._client._request(
            "PATCH",
            f"/subjects/{subject_id}/memories/{memory_id}",
            json_body=_json_model(patch),
            request_id=request_id,
            response_type=MemoryRecord,
        )

    async def _action(
        self,
        action: str,
        subject_id: str,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
        request_id: str | None,
    ) -> MemoryRecord:
        return await self._client._request(
            "POST" if action != "delete" else "DELETE",
            f"/subjects/{subject_id}/memories/{memory_id}"
            + (f":{action}" if action != "delete" else ""),
            json_body={
                "expected_revision": expected_revision,
                "actor": actor,
                "reason": reason,
            },
            request_id=request_id,
            response_type=MemoryRecord,
        )

    async def confirm(
        self,
        subject_id: str,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
        *,
        request_id: str | None = None,
    ) -> MemoryRecord:
        return await self._action(
            "confirm",
            subject_id,
            memory_id,
            expected_revision,
            actor,
            reason,
            request_id,
        )

    async def restore(
        self,
        subject_id: str,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
        *,
        request_id: str | None = None,
    ) -> MemoryRecord:
        return await self._action(
            "restore",
            subject_id,
            memory_id,
            expected_revision,
            actor,
            reason,
            request_id,
        )

    async def delete(
        self,
        subject_id: str,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
        *,
        request_id: str | None = None,
    ) -> MemoryRecord:
        return await self._action(
            "delete",
            subject_id,
            memory_id,
            expected_revision,
            actor,
            reason,
            request_id,
        )

    async def add_memory(
        self, subject_id: str, input: MemoryCreateInput, **kwargs: Any
    ) -> MemoryRecord:
        return await self.add(subject_id, input, **kwargs)

    async def list_memories(
        self, subject_id: str, *args: Any, **kwargs: Any
    ) -> MemoryPage:
        return await self.list(subject_id, *args, **kwargs)

    async def patch_memory(
        self, subject_id: str, memory_id: UUID, patch: MemoryPatchInput, **kwargs: Any
    ) -> MemoryRecord:
        return await self.patch(subject_id, memory_id, patch, **kwargs)

    async def confirm_memory(
        self,
        subject_id: str,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
        **kwargs: Any,
    ) -> MemoryRecord:
        return await self.confirm(
            subject_id, memory_id, expected_revision, actor, reason, **kwargs
        )

    async def restore_memory(
        self,
        subject_id: str,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
        **kwargs: Any,
    ) -> MemoryRecord:
        return await self.restore(
            subject_id, memory_id, expected_revision, actor, reason, **kwargs
        )

    async def delete_memory(
        self,
        subject_id: str,
        memory_id: UUID,
        expected_revision: int,
        actor: str,
        reason: str,
        **kwargs: Any,
    ) -> MemoryRecord:
        return await self.delete(
            subject_id, memory_id, expected_revision, actor, reason, **kwargs
        )

    async def extract_memories(
        self, subject_id: str, messages: Sequence[ConversationMessage], **kwargs: Any
    ) -> MemoryExtractionResult:
        return await self.extract(subject_id, messages, **kwargs)

    async def search_memories(
        self, subject_id: str, *args: Any, **kwargs: Any
    ) -> MemoryPage:
        return await self.search(subject_id, *args, **kwargs)


class ProfileRemoteOperations(_OperationGroup):
    async def refresh(
        self,
        subject_id: str,
        options: ProfileRefreshOptions | None = None,
        *,
        request_id: str | None = None,
    ) -> ProfileSnapshot:
        return await self._client._request(
            "POST",
            f"/subjects/{subject_id}/profiles:refresh",
            json_body=_json_model(options),
            request_id=request_id,
            response_type=ProfileSnapshot,
        )

    async def get_latest(
        self, subject_id: str, *, request_id: str | None = None
    ) -> ProfileSnapshot | None:
        return await self._client._request(
            "GET",
            f"/subjects/{subject_id}/profiles/latest",
            request_id=request_id,
            response_type=ProfileSnapshot | None,
        )

    async def get_version(
        self, subject_id: str, version: int, *, request_id: str | None = None
    ) -> ProfileSnapshot | None:
        return await self._client._request(
            "GET",
            f"/subjects/{subject_id}/profiles/{version}",
            request_id=request_id,
            response_type=ProfileSnapshot | None,
        )

    async def compare(
        self,
        subject_id: str,
        left: int,
        right: int,
        *,
        request_id: str | None = None,
    ) -> ProfileDiff:
        return await self._client._request(
            "GET",
            f"/subjects/{subject_id}/profiles:compare",
            params={"left": left, "right": right},
            request_id=request_id,
            response_type=ProfileDiff,
        )

    async def refresh_profile(
        self,
        subject_id: str,
        options: ProfileRefreshOptions | None = None,
        **kwargs: Any,
    ) -> ProfileSnapshot:
        return await self.refresh(subject_id, options, **kwargs)

    async def get_latest_profile(
        self, subject_id: str, **kwargs: Any
    ) -> ProfileSnapshot | None:
        return await self.get_latest(subject_id, **kwargs)

    async def get_profile_version(
        self, subject_id: str, version: int, **kwargs: Any
    ) -> ProfileSnapshot | None:
        return await self.get_version(subject_id, version, **kwargs)

    async def compare_profiles(
        self, subject_id: str, left: int, right: int, **kwargs: Any
    ) -> ProfileDiff:
        return await self.compare(subject_id, left, right, **kwargs)


class ContextRemoteOperations(_OperationGroup):
    async def resolve(
        self,
        subject_id: str | ContextRequest,
        request: ContextRequest | None = None,
        *,
        query: str | None = None,
        use_case: str | None = None,
        topic: str | None = None,
        entity: str | None = None,
        as_of: datetime | None = None,
        token_budget: int | None = None,
        recent_limit: int = 5,
        long_term_limit: int = 10,
        include_inferred: bool = False,
        request_id: str | None = None,
    ) -> ContextBundle:
        if isinstance(subject_id, ContextRequest):
            if request is not None:
                raise ValueError("context request was provided twice")
            request = subject_id
            subject_id = request.subject.subject_id.root
        if request is not None:
            body = request.model_dump(mode="json", exclude={"subject"})
        else:
            body = ContextRequest(
                subject=self._client.subject_ref(str(subject_id)),
                query=query,
                use_case=use_case,
                topic=topic,
                entity=entity,
                as_of=as_of,
                token_budget=token_budget,
                recent_limit=recent_limit,
                long_term_limit=long_term_limit,
                include_inferred=include_inferred,
            ).model_dump(mode="json", exclude={"subject"})
        return await self._client._request(
            "POST",
            f"/subjects/{subject_id}/context:resolve",
            json_body=body,
            request_id=request_id,
            response_type=ContextBundle,
        )

    async def resolve_context(
        self, subject_id: str | ContextRequest, *args: Any, **kwargs: Any
    ) -> ContextBundle:
        return await self.resolve(subject_id, *args, **kwargs)

    async def explain(
        self,
        subject_id: str,
        dimension: str,
        value_key: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._client._request(
            "GET",
            f"/subjects/{subject_id}/preferences/{dimension}/{value_key}:explain",
            request_id=request_id,
        )


class SubjectRemoteOperations(_OperationGroup):
    async def export(
        self, subject_id: str, *, request_id: str | None = None
    ) -> SubjectExport:
        return await self._client._request(
            "GET",
            f"/subjects/{subject_id}:export",
            request_id=request_id,
            response_type=SubjectExport,
        )

    async def delete(
        self, subject_id: str, *, request_id: str | None = None
    ) -> Subject:
        return await self._client._request(
            "DELETE",
            f"/subjects/{subject_id}",
            request_id=request_id,
            response_type=Subject,
        )

    async def purge(
        self,
        subject_id: str,
        confirmation: str,
        *,
        request_id: str | None = None,
    ) -> PurgeResult:
        return await self._client._request(
            "POST",
            f"/subjects/{subject_id}:purge",
            json_body={"confirmation": confirmation},
            request_id=request_id,
            response_type=PurgeResult,
        )


class PreferencesRemoteOperations(_OperationGroup):
    async def explain(
        self,
        subject_id: str,
        dimension: str,
        value_key: str,
        *,
        request_id: str | None = None,
    ) -> dict[str, Any]:
        return await self._client.context.explain(
            subject_id, dimension, value_key, request_id=request_id
        )


class AsyncPersonalizationClient:
    """Async HTTP client for a Personalization Core server."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        tenant_id: str,
        namespace: str = "default",
        timeout: float | httpx.Timeout = 10.0,
        max_retries: int = 2,
        retry_backoff: _RetryBackoff = 0.1,
        http_client: httpx.AsyncClient | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        if not api_key:
            raise ValueError("api_key must not be empty")
        if max_retries < 0:
            raise ValueError("max_retries must be non-negative")
        if http_client is not None and transport is not None:
            raise ValueError("provide http_client or transport, not both")
        normalized = base_url.rstrip("/")
        if not normalized.endswith("/v1"):
            normalized += "/v1"
        self.base_url = normalized
        self.api_key = api_key
        self.tenant_id = tenant_id
        self.namespace = namespace
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_backoff = retry_backoff
        self._owns_http_client = http_client is None
        self._http_client = http_client or httpx.AsyncClient(
            transport=transport, timeout=timeout
        )
        self.last_request_id: str | None = None
        self.health = HealthOperations(self)
        self.events = EventRemoteOperations(self)
        self.memories = MemoryRemoteOperations(self)
        self.profiles = ProfileRemoteOperations(self)
        self.context = ContextRemoteOperations(self)
        self.preferences = PreferencesRemoteOperations(self)
        self.subjects = SubjectRemoteOperations(self)

    def subject_ref(self, subject_id: str):
        from personalization_core.domain.identifiers import (
            Namespace,
            SubjectId,
            SubjectRef,
            TenantId,
        )

        return SubjectRef(
            tenant_id=TenantId(self.tenant_id),
            namespace=Namespace(self.namespace),
            subject_id=SubjectId(subject_id),
        )

    async def initialize(self) -> None:
        """Compatibility no-op matching the Embedded engine lifecycle."""

    async def close(self) -> None:
        if self._owns_http_client:
            await self._http_client.aclose()

    async def __aenter__(self) -> AsyncPersonalizationClient:
        await self.initialize()
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        traceback: object | None,
    ) -> None:
        await self.close()

    async def _request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json_body: Any = None,
        request_id: str | None = None,
        idempotency_key: str | None = None,
        response_type: Any = None,
        retryable: bool = False,
    ) -> Any:
        active_request_id = request_id or str(uuid4())
        self.last_request_id = active_request_id
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "X-Tenant-Id": self.tenant_id,
            "X-Namespace": self.namespace,
            "X-Request-Id": active_request_id,
        }
        if idempotency_key is not None:
            headers["Idempotency-Key"] = idempotency_key
        method_upper = method.upper()
        can_retry = method_upper in {"GET", "HEAD", "OPTIONS"} or (
            retryable and method_upper == "POST" and idempotency_key is not None
        )
        attempts = self.max_retries if can_retry else 0
        url = f"{self.base_url}{path}"
        for attempt in range(attempts + 1):
            try:
                response = await self._http_client.request(
                    method,
                    url,
                    params=params,
                    json=json_body,
                    headers=headers,
                )
            except httpx.TimeoutException as exc:
                if attempt < attempts:
                    await self._sleep(attempt)
                    continue
                raise SDKTimeoutError(
                    "remote request timed out", request_id=active_request_id
                ) from exc
            except httpx.TransportError as exc:
                if attempt < attempts:
                    await self._sleep(attempt)
                    continue
                raise TransportError(
                    "remote transport failed", request_id=active_request_id
                ) from exc

            response_request_id = response.headers.get("X-Request-Id")
            self.last_request_id = response_request_id or active_request_id
            if response.status_code in _RETRYABLE_STATUS and attempt < attempts:
                await self._sleep(attempt)
                continue
            if response.is_error:
                error = self._error_from_response(response, self.last_request_id)
                self.last_request_id = error.request_id or self.last_request_id
                raise error
            try:
                payload_value: Any = response.json()
                if isinstance(payload_value, dict):
                    payload = cast(dict[str, Any], payload_value)
                    data: Any = payload.get("data", payload)
                else:
                    data = payload_value
            except (ValueError, TypeError) as exc:
                raise ServerError(
                    "remote server returned invalid JSON",
                    code="PROVIDER_INVALID_RESPONSE",
                    status_code=response.status_code,
                    request_id=self.last_request_id,
                ) from exc
            if response_type is None:
                return data
            try:
                # Strict public DTOs still need normal JSON enum/datetime
                # conversion at the wire boundary.
                return TypeAdapter(response_type).validate_json(json.dumps(data))
            except Exception as exc:
                raise ServerError(
                    "remote response did not match the expected DTO",
                    code="PROVIDER_INVALID_RESPONSE",
                    status_code=response.status_code,
                    request_id=self.last_request_id,
                ) from exc
        raise AssertionError("unreachable retry loop")

    async def _sleep(self, attempt: int) -> None:
        delay = (
            self.retry_backoff(attempt)
            if callable(self.retry_backoff)
            else self.retry_backoff * (2**attempt)
        )
        if delay > 0:
            await asyncio.sleep(delay)

    def _error_from_response(
        self, response: httpx.Response, request_id: str | None
    ) -> SDKError:
        try:
            payload_value: Any = response.json()
        except (ValueError, TypeError):
            payload_value = {}
        payload: dict[str, Any] = (
            cast(dict[str, Any], payload_value)
            if isinstance(payload_value, dict)
            else {}
        )
        error_value = payload.get("error", {})
        error: dict[str, Any] = (
            cast(dict[str, Any], error_value) if isinstance(error_value, dict) else {}
        )
        code = str(
            error.get("code")
            or ("UNAUTHENTICATED" if response.status_code == 401 else "HTTP_ERROR")
        )
        message = str(
            error.get("message") or response.reason_phrase or "remote request failed"
        )
        details = error.get("details")
        if not isinstance(details, dict):
            details = {}
        response_id = (
            str(payload.get("request_id")) if payload.get("request_id") else request_id
        )
        safe_message = str(_redact(message, self.api_key))
        safe_details_value = _redact(details, self.api_key)
        safe_details = (
            cast(dict[str, Any], safe_details_value)
            if isinstance(safe_details_value, dict)
            else {}
        )
        if code == "INVALID_ARGUMENT":
            error_type: type[SDKError] = SDKInvalidArgumentError
        elif code == "UNAUTHENTICATED":
            error_type = SDKUnauthenticatedError
        elif code == "TENANT_SCOPE_VIOLATION":
            error_type = SDKTenantScopeViolationError
        elif code.endswith("_NOT_FOUND") or response.status_code == 404:
            error_type = SDKNotFoundError
        elif code == "SUBJECT_DELETED":
            error_type = SDKSubjectDeletedError
        elif code in {
            "REVISION_CONFLICT",
            "MEMORY_PROTECTION_ERROR",
            "MEMORY_TRANSITION_ERROR",
        }:
            error_type = SDKRevisionConflictError
        elif code == "IDEMPOTENCY_CONFLICT":
            error_type = SDKIdempotencyConflictError
        elif code == "REQUEST_TOO_LARGE" or response.status_code == 413:
            error_type = SDKRequestTooLargeError
        elif code.startswith("PROVIDER_"):
            error_type = SDKProviderError
        elif code == "PROCESSING_FAILED":
            error_type = SDKProcessingFailedError
        elif response.status_code >= 500:
            error_type = ServerError
        else:
            error_type = HTTPError
        return error_type(
            safe_message,
            code=code,
            details=safe_details,
            status_code=response.status_code,
            request_id=response_id,
        )


AsyncRemotePersonalizationClient = AsyncPersonalizationClient
