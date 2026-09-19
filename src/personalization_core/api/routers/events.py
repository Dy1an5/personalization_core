from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Header, Query, Request

from personalization_core.domain.enums import Polarity
from personalization_core.domain.errors import InvalidArgumentError
from personalization_core.ports.repositories import EventFilter, Page

from ..dependencies import SubjectDependency, get_runtime
from ..errors import success_response
from ..models import BatchEventRequest, EntityRequest, EventRequest

router = APIRouter(tags=["events"])


@router.post("/subjects/{subject_id}/entities", status_code=201)
async def upsert_entity(
    request: Request, subject: SubjectDependency, body: EntityRequest
):
    runtime = get_runtime(request)
    entity = await runtime.engine.event_service.upsert_entity(subject, body.to_domain())
    return success_response(request, vars(entity), 201)


@router.post("/subjects/{subject_id}/events", status_code=201)
async def ingest_event(
    request: Request,
    subject: SubjectDependency,
    body: EventRequest,
    idempotency_key: str | None = Header(default=None, alias="Idempotency-Key"),
):
    if not idempotency_key or idempotency_key != body.event.idempotency_key:
        raise InvalidArgumentError("Idempotency-Key must match event.idempotency_key")
    runtime = get_runtime(request)
    result = await runtime.engine.event_service.ingest_event(subject, body.to_domain())
    return success_response(
        request, result, 201 if result.status.value == "created" else 200
    )


@router.post("/subjects/{subject_id}/events:batch", status_code=201)
async def ingest_batch(
    request: Request, subject: SubjectDependency, body: BatchEventRequest
):
    runtime = get_runtime(request)
    events, mode = body.to_domain()
    result = await runtime.engine.event_service.ingest_batch(subject, events, mode=mode)
    return success_response(request, result, 201)


@router.get("/subjects/{subject_id}/events")
async def list_events(
    request: Request,
    subject: SubjectDependency,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    event_type: str | None = None,
    source: str | None = None,
    polarity: Polarity | None = None,
    occurred_from: datetime | None = None,
    occurred_until: datetime | None = None,
):
    runtime = get_runtime(request)
    filters = EventFilter(event_type, source, polarity, occurred_from, occurred_until)
    result = await runtime.engine.event_service.list_events(
        subject, filters, Page(limit, offset)
    )
    return success_response(request, result)
