# HTTP API

The FastAPI application is mounted under `/v1`. Requests authenticate with
`Authorization: Bearer <token>`. The authenticated tenant is used as the trusted
tenant; `X-Tenant-Id` may repeat it and `X-Namespace` selects the namespace (default
`default`). A request ID is accepted in `X-Request-Id` or generated and returned in
the response header.

The operation baseline for `0.1.0` is in `openapi-0.1.0.json`. It covers health,
entity/event ingestion and listing, memory CRUD/search/extraction/transitions,
profile refresh/read/compare, context resolution, export, soft delete, and purge.

Single event writes use the event's `idempotency_key`; a replay returns the original
event and changed content returns `IDEMPOTENCY_CONFLICT`. Batch writes support atomic
and best-effort modes. All subject paths enforce the full tenant/namespace/subject
scope.

Errors have the shape:

```json
{"error": {"code": "INVALID_ARGUMENT", "message": "...", "details": {}}, "request_id": "..."}
```

`DELETE /subjects/{subject_id}` is a soft delete. Purge requires a short-lived token
from `POST /subjects/{subject_id}:purge-token` and is irreversible. The complete
privacy contract is documented in `privacy.md`.
