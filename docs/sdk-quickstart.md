# Remote SDK quickstart

The async SDK is intended for applications that already have an event loop:

```python
from datetime import UTC, datetime
from personalization_core.sdk import AsyncPersonalizationClient
from personalization_core.public import EventCreate, EventIngestionInput, Polarity

async with AsyncPersonalizationClient(
    base_url="http://localhost:8080", api_key="local-development-key", tenant_id="demo-tenant", namespace="demo"
) as client:
    event = EventIngestionInput(event=EventCreate(
        event_type="article.viewed", source="demo", idempotency_key="view-1",
        occurred_at=datetime.now(UTC), schema_version="1", polarity=Polarity.POSITIVE,
    ))
    await client.events.ingest_event("user-1", event)
    bundle = await client.context.resolve("user-1", query="python", use_case="recommendation")
```

`PersonalizationClient` exposes the same operation names for synchronous programs;
call `close()` in a `finally` block. Do not use it while an event loop is running.
The client sends bearer, tenant, namespace, request ID, and event idempotency
headers. It retries safe requests and idempotent single-event writes only. Server
errors are raised as SDK exceptions and preserve the latest request ID.
