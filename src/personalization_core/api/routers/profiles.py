from fastapi import APIRouter, Path, Query, Request

from ..dependencies import SubjectDependency, get_runtime
from ..errors import success_response
from ..models import ProfileRefreshRequest

router = APIRouter(tags=["profiles"])


@router.post("/subjects/{subject_id}/profiles:refresh")
async def refresh_profile(
    request: Request,
    subject: SubjectDependency,
    body: ProfileRefreshRequest | None = None,
):
    runtime = get_runtime(request)
    result = await runtime.engine.profile_service.refresh_profile(
        subject, body.to_domain() if body is not None else None
    )
    return success_response(request, result)


@router.get("/subjects/{subject_id}/profiles/latest")
async def latest_profile(request: Request, subject: SubjectDependency):
    runtime = get_runtime(request)
    result = await runtime.engine.profile_service.get_latest_profile(subject)
    return success_response(request, result)


@router.get("/subjects/{subject_id}/profiles/{version}")
async def profile_version(
    request: Request, subject: SubjectDependency, version: int = Path(ge=1)
):
    runtime = get_runtime(request)
    result = await runtime.engine.profile_service.get_profile_version(subject, version)
    return success_response(request, result)


@router.get("/subjects/{subject_id}/profiles:compare")
async def compare_profiles(
    request: Request,
    subject: SubjectDependency,
    left: int = Query(ge=1),
    right: int = Query(ge=1),
):
    runtime = get_runtime(request)
    result = await runtime.engine.profile_service.compare_profiles(subject, left, right)
    return success_response(request, result)
