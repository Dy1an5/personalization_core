"""Environment-driven PostgreSQL server factory for Uvicorn and containers."""

from __future__ import annotations

import os

from personalization_core.infrastructure.observability.metrics import MetricsRegistry
from personalization_core.sdk.async_client import PersonalizationEngine

from .app import create_app
from .auth import TokenAuthenticator


def create_server_app():
    database_url = os.environ["DATABASE_URL"]
    api_key = os.environ.get("API_KEY", "local-development-key")
    tenant_id = os.environ.get("API_TENANT_ID", "local-development")
    metrics = MetricsRegistry()
    engine = PersonalizationEngine.from_postgres(database_url, metrics=metrics)
    return create_app(
        engine=engine,
        authenticator=TokenAuthenticator({api_key: tenant_id}),
        metrics=metrics,
    )
