from fastapi import APIRouter, Request

from personalization_core.infrastructure.persistence.database import probe_database

from ..errors import success_response

router = APIRouter(tags=["health"])


@router.get("/health/live")
async def live(request: Request):
    return success_response(request, {"status": "ok"})


@router.get("/health/ready")
async def ready(request: Request):
    engine = request.app.state.api_runtime.engine
    database_engine = engine.database_engine
    database_ready = database_engine is None or await probe_database(database_engine)
    ready = not engine.is_closed and database_ready
    status = "ready" if ready else "not_ready"
    return success_response(
        request,
        {"status": status, "database": "ok" if database_ready else "unavailable"},
        200 if ready else 503,
    )
