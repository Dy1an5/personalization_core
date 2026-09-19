"""Run the smallest release smoke test using only the installed package."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from tempfile import TemporaryDirectory

from personalization_core.public import (
    EventCreate,
    EventIngestionInput,
    Namespace,
    PersonalizationEngine,
    Polarity,
    SubjectId,
    SubjectRef,
    TenantId,
)


async def smoke() -> None:
    subject = SubjectRef(
        tenant_id=TenantId("release-tenant"),
        namespace=Namespace("release"),
        subject_id=SubjectId("user-1"),
    )
    event = EventIngestionInput(
        event=EventCreate(
            event_type="release.smoke",
            source="release-smoke",
            idempotency_key="release-event-1",
            occurred_at=datetime.now(UTC),
            schema_version="1",
            polarity=Polarity.POSITIVE,
        )
    )
    with TemporaryDirectory() as directory:
        async with PersonalizationEngine.from_sqlite(
            Path(directory) / "release.sqlite"
        ) as engine:
            first = await engine.events.ingest_event(subject, event)
            replay = await engine.events.ingest_event(subject, event)
            assert first.status.value == "created"
            assert replay.status.value == "replayed"


def main() -> None:
    asyncio.run(smoke())


if __name__ == "__main__":
    main()
