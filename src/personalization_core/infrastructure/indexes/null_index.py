from __future__ import annotations

from collections.abc import Sequence

from personalization_core.domain.identifiers import SubjectRef
from personalization_core.ports.vector_index import (
    VectorDocument,
    VectorIndex,
    VectorSearchHit,
)


class NullVectorIndex(VectorIndex):
    index_version = "null-1"

    async def upsert(self, documents: Sequence[VectorDocument]) -> None:
        return None

    async def search(
        self, subject: SubjectRef, query_vector: Sequence[float], limit: int
    ) -> list[VectorSearchHit]:
        return []

    async def delete_subject(self, subject: SubjectRef) -> None:
        return None
