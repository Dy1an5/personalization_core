# Embedded SDK Quickstart

The embedded SDK runs the existing application services directly in Python; it
does not start an HTTP server. SQLite can be temporary or persistent. The
factory is synchronous, while initialization and all operations are
asynchronous.

## Complete asynchronous flow

```python
import asyncio
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from personalization_core.public import (
    ContextRequest,
    EventCreate,
    EventIngestionInput,
    MemoryCreateInput,
    MemoryKind,
    Namespace,
    PersonalizationEngine,
    Polarity,
    PreferenceTarget,
    SubjectId,
    SubjectRef,
    TenantId,
)


async def run(path: str | Path) -> None:
    subject = SubjectRef(
        tenant_id=TenantId("demo-tenant"),
        namespace=Namespace("demo"),
        subject_id=SubjectId("user-1"),
    )
    occurred_at = datetime.now(UTC)

    # The async context creates the schema on first entry and disposes the
    # engine on exit. Repeating initialize() is also safe when explicit setup
    # is preferred.
    async with PersonalizationEngine.from_sqlite(path) as engine:
        await engine.initialize()

        batch = await engine.events.ingest_batch(
            subject,
            [
                EventIngestionInput(
                    event=EventCreate(
                        event_type="article.viewed",
                        source="demo",
                        idempotency_key="view-1",
                        occurred_at=occurred_at,
                        schema_version="1",
                        polarity=Polarity.POSITIVE,
                        properties={"topic": "python"},
                    )
                )
            ],
        )
        assert batch.created_count == 1

        memory = await engine.memories.add(
            subject,
            MemoryCreateInput(
                key="preference.language",
                kind=MemoryKind.PREFERENCE,
                content="The user prefers Python.",
                target=PreferenceTarget(dimension="language", value_key="python"),
                polarity=Polarity.POSITIVE,
            ),
        )

        profile = await engine.profiles.refresh(subject)
        context = await engine.context.resolve(
            ContextRequest(subject=subject, query="python")
        )
        assert memory.id in {hit.memory.id for hit in context.memories}
        assert profile.subject == subject


async def temporary_database() -> None:
    with TemporaryDirectory() as directory:
        await run(Path(directory) / "personalization.sqlite")


asyncio.run(temporary_database())
```

For a persistent database, pass a stable path instead of a temporary
directory. Parent directories are created automatically (except for
`:memory:`). Closing and reopening the same path preserves subjects, events,
memories, and profile snapshots:

```python
async def persistent_database(path: Path) -> None:
    async with PersonalizationEngine.from_sqlite(path) as engine:
        await engine.initialize()
        # Perform writes here.

    async with PersonalizationEngine.from_sqlite(path) as engine:
        subject = SubjectRef(
            tenant_id=TenantId("demo-tenant"),
            namespace=Namespace("demo"),
            subject_id=SubjectId("user-1"),
        )
        events = await engine.events.list_events(subject)
        assert events.items
```

`from_components(...)` is available when the application owns the schema and
infrastructure. It reuses the supplied `UnitOfWorkFactory` and optional
`Clock`, extractor, indexes, providers, and audit sink; it does not call
`create_all` and does not close an injected SQLAlchemy engine.

## Synchronous wrapper boundary

Code that does not already run an event loop can use the synchronous wrapper:

```python
from personalization_core.sdk import PersonalizationClient

client = PersonalizationClient.from_sqlite("./data/personalization.sqlite")
try:
    events = client.events.list_events(subject)
finally:
    client.close()
```

`PersonalizationClient` uses `asyncio.run` for each operation. It must not be
used from an async function, notebook cell, ASGI handler, or any other thread
with a running event loop; it raises
`SyncClientInAsyncContextError` before creating a coroutine. Use
`PersonalizationEngine` and `await` its operations in those contexts.
