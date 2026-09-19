# Server quickstart

Install the server extras and configure a database and deterministic development
token:

```bash
uv sync --extra postgres
export DATABASE_URL='postgresql+asyncpg://user:password@localhost:5432/personalization'
export API_KEY='local-development-key'
export API_TENANT_ID='demo-tenant'
uv run uvicorn 'personalization_core.api.server:create_server_app' --factory --port 8080
```

The server runs Alembic migrations separately; apply them with
`uv run alembic upgrade head`. A minimal health and event request is:

```bash
curl http://localhost:8080/v1/health/live
curl -X POST http://localhost:8080/v1/subjects/user-1/events \
  -H 'Authorization: Bearer local-development-key' \
  -H 'X-Namespace: demo' -H 'Content-Type: application/json' \
  -H 'Idempotency-Key: view-1' \
  -d '{"event":{"event_type":"article.viewed","source":"demo","idempotency_key":"view-1","occurred_at":"2026-09-19T00:00:00Z","schema_version":"1","polarity":"positive","properties":{"topic":"python"}}}'
```

For local development the embedded SQLite quickstart is simpler. Production
deployments should provide a real authenticator and rotate tokens outside Core.
