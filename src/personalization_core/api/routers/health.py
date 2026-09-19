from fastapi import APIRouter, Request

from ..errors import success_response

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live(request: Request):
    return success_response(request, {"status": "ok"})


@router.get("/health/ready")
async def ready(request: Request):
    engine = request.app.state.api_runtime.engine
    status = "not_ready" if engine.is_closed else "ready"
    return success_response(
        request, {"status": status}, 200 if status == "ready" else 503
    )
