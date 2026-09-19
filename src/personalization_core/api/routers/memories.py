from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Query, Request

from personalization_core.ports.repositories import MemoryFilter, Page

from ..dependencies import SubjectDependency, get_runtime
from ..errors import success_response
from ..models import (
    ConversationRequest,
    MemoryActionRequest,
    MemoryCreateRequest,
    MemoryPatchRequest,
    MemorySearchRequest,
)

router = APIRouter(tags=["memories"])


@router.post("/subjects/{subject_id}/memories", status_code=201)
async def add_memory(
    request: Request, subject: SubjectDependency, body: MemoryCreateRequest
):
    runtime = get_runtime(request)
    result = await runtime.engine.memory_service.add_memory(subject, body.to_domain())
    return success_response(request, result, 201)


@router.get("/subjects/{subject_id}/memories")
async def list_memories(
    request: Request,
    subject: SubjectDependency,
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    runtime = get_runtime(request)
    result = await runtime.engine.memory_service.list_memories(
        subject, page=Page(limit, offset)
    )
    return success_response(request, result)


@router.post("/subjects/{subject_id}/memories:extract")
async def extract_memories(
    request: Request, subject: SubjectDependency, body: ConversationRequest
):
    runtime = get_runtime(request)
    result = await runtime.engine.memory_service.extract_memories(
        subject, body.messages
    )
    return success_response(request, result)


def _memory_filter(body: MemorySearchRequest) -> MemoryFilter:
    return MemoryFilter(
        key=body.key,
        kind=body.kind,
        authority=body.authority,
        scope=body.scope,
        scope_value=body.scope_value,
        target_dimension=body.target_dimension,
        target_value_key=body.target_value_key,
    )


@router.post("/subjects/{subject_id}/memories:search")
async def search_memories(
    request: Request, subject: SubjectDependency, body: MemorySearchRequest
):
    runtime = get_runtime(request)
    result = await runtime.engine.memory_service.search_memories(
        subject, _memory_filter(body), Page(body.limit, body.offset)
    )
    return success_response(request, result)


@router.get("/subjects/{subject_id}/memories/{memory_id}")
async def get_memory(request: Request, subject: SubjectDependency, memory_id: UUID):
    runtime = get_runtime(request)
    result = await runtime.engine.memory_service.get_memory(subject, memory_id)
    return success_response(request, result)


@router.patch("/subjects/{subject_id}/memories/{memory_id}")
async def patch_memory(
    request: Request,
    subject: SubjectDependency,
    memory_id: UUID,
    body: MemoryPatchRequest,
):
    runtime = get_runtime(request)
    result = await runtime.engine.memory_service.patch_memory(
        subject, memory_id, body.to_domain()
    )
    return success_response(request, result)


@router.post("/subjects/{subject_id}/memories/{memory_id}:confirm")
async def confirm_memory(
    request: Request,
    subject: SubjectDependency,
    memory_id: UUID,
    body: MemoryActionRequest,
):
    runtime = get_runtime(request)
    result = await runtime.engine.memory_service.confirm_memory(
        subject, memory_id, body.expected_revision, body.actor, body.reason
    )
    return success_response(request, result)


@router.post("/subjects/{subject_id}/memories/{memory_id}:restore")
async def restore_memory(
    request: Request,
    subject: SubjectDependency,
    memory_id: UUID,
    body: MemoryActionRequest,
):
    runtime = get_runtime(request)
    result = await runtime.engine.memory_service.restore_memory(
        subject, memory_id, body.expected_revision, body.actor, body.reason
    )
    return success_response(request, result)


@router.delete("/subjects/{subject_id}/memories/{memory_id}")
async def delete_memory(
    request: Request,
    subject: SubjectDependency,
    memory_id: UUID,
    body: MemoryActionRequest,
):
    runtime = get_runtime(request)
    result = await runtime.engine.memory_service.delete_memory(
        subject, memory_id, body.expected_revision, body.actor, body.reason
    )
    return success_response(request, result)
