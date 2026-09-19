from __future__ import annotations

import asyncio
from contextlib import asynccontextmanager
from time import monotonic
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from personalization_core.infrastructure.observability.metrics import (
    MetricsRegistry,
    elapsed_milliseconds,
    safe_metric_path,
)
from personalization_core.sdk.async_client import PersonalizationEngine

from .auth import Authenticator
from .dependencies import ApiRuntime
from .errors import install_exception_handlers
from .models import MAX_BODY_BYTES
from .routers import context, events, health, memories, profiles, subjects


class RequestContextMiddleware:
    def __init__(self, app: ASGIApp, metrics: MetricsRegistry | None = None) -> None:
        self.app = app
        self.metrics = metrics

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        started = monotonic()
        status_code = 500
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw_request_id = headers.get(b"x-request-id", b"").strip()
        request_id = (
            raw_request_id.decode("utf-8", errors="replace")[:200]
            if raw_request_id
            else str(uuid4())
        )
        scope.setdefault("state", {})["request_id"] = request_id
        content_length = headers.get(b"content-length")
        too_large = False
        if content_length is not None:
            try:
                too_large = int(content_length) > MAX_BODY_BYTES
            except ValueError:
                too_large = True
        if too_large:
            from starlette.responses import JSONResponse

            response = JSONResponse(
                status_code=413,
                content={
                    "error": {
                        "code": "REQUEST_TOO_LARGE",
                        "message": "request body is too large",
                        "details": {},
                    },
                    "request_id": request_id,
                },
                headers={"X-Request-Id": request_id},
            )
            await response(scope, receive, send)
            return

        async def send_with_request_id(message: Message) -> None:
            if message["type"] == "http.response.start":
                message = dict(message)
                nonlocal status_code
                status_code = int(message.get("status", 500))
                message["headers"] = [
                    *[
                        (key, value)
                        for key, value in message.get("headers", [])
                        if key.lower() != b"x-request-id"
                    ],
                    (b"x-request-id", request_id.encode("utf-8")),
                ]
            await send(message)

        try:
            await self.app(scope, receive, send_with_request_id)
        finally:
            if self.metrics is not None:
                path = safe_metric_path(str(scope.get("path", "unknown")))
                labels: dict[str, Any] = {
                    "method": scope.get("method", "unknown"),
                    "path": path,
                    "status": status_code,
                }
                self.metrics.increment("http_requests_total", labels=labels)
                if status_code >= 400:
                    self.metrics.increment("http_errors_total", labels=labels)
                self.metrics.observe_latency(
                    "http_request_latency_ms",
                    elapsed_milliseconds(started),
                    labels={"path": path},
                )


def create_app(
    *,
    engine: PersonalizationEngine,
    authenticator: Authenticator,
    initialize_engine: bool = True,
    shutdown_timeout: float = 10.0,
    metrics: MetricsRegistry | None = None,
) -> FastAPI:
    active_metrics = metrics or MetricsRegistry()

    @asynccontextmanager
    async def lifespan(app: FastAPI):
        if initialize_engine:
            await engine.initialize()
        try:
            yield
        finally:
            if initialize_engine:
                await asyncio.wait_for(engine.close(), timeout=shutdown_timeout)

    app = FastAPI(
        title="Personalization Core API",
        version="0.1.0",
        root_path="",
        lifespan=lifespan,
    )
    app.state.api_runtime = ApiRuntime(
        engine=engine, authenticator=authenticator, metrics=active_metrics
    )
    app.add_middleware(RequestContextMiddleware, metrics=active_metrics)
    install_exception_handlers(app)
    app.include_router(health.router, prefix="/v1")
    app.include_router(events.router, prefix="/v1")
    app.include_router(memories.router, prefix="/v1")
    app.include_router(profiles.router, prefix="/v1")
    app.include_router(context.router, prefix="/v1")
    app.include_router(subjects.router, prefix="/v1")
    return app
