from fastapi import APIRouter, Request

from personalization_core.domain.errors import InvalidArgumentError

from ..dependencies import SubjectDependency, get_runtime
from ..errors import success_response
from ..models import ContextResolveRequest

router = APIRouter(tags=["context"])


@router.post("/subjects/{subject_id}/context:resolve")
async def resolve_context(
    request: Request, subject: SubjectDependency, body: ContextResolveRequest
):
    runtime = get_runtime(request)
    result = await runtime.engine.context_service.resolve_context(
        body.to_domain(subject)
    )
    return success_response(request, result)


@router.get("/subjects/{subject_id}/preferences/{dimension}/{value_key}:explain")
async def explain_preference(
    request: Request, subject: SubjectDependency, dimension: str, value_key: str
):
    raise InvalidArgumentError(
        "preference explanations are not available in this release"
    )
