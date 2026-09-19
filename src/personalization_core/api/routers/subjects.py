from fastapi import APIRouter, Request

from ..dependencies import SubjectDependency, get_runtime
from ..errors import success_response
from ..models import PurgeRequest

router = APIRouter(tags=["subjects"])


@router.get("/subjects/{subject_id}:export")
async def export_subject(request: Request, subject: SubjectDependency):
    runtime = get_runtime(request)
    result = await runtime.engine.subject_service.export_subject(subject)
    return success_response(request, result)


@router.delete("/subjects/{subject_id}")
async def delete_subject(request: Request, subject: SubjectDependency):
    runtime = get_runtime(request)
    result = await runtime.engine.subject_service.soft_delete_subject(subject)
    return success_response(request, result)


@router.post("/subjects/{subject_id}:purge")
async def purge_subject(
    request: Request, subject: SubjectDependency, body: PurgeRequest
):
    runtime = get_runtime(request)
    result = await runtime.engine.subject_service.purge_subject(
        subject, body.confirmation
    )
    return success_response(request, result)
