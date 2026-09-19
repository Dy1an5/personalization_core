from __future__ import annotations

import math
from collections.abc import Sequence
from uuid import UUID

from personalization_core.domain.identifiers import SubjectRef
from personalization_core.ports.vector_index import (
    VectorDocument,
    VectorIndex,
    VectorSearchHit,
)


def _scope(subject: SubjectRef) -> tuple[str, str, str]:
    return (
        subject.tenant_id.root,
        subject.namespace.root,
        subject.subject_id.root,
    )


def _valid_vector(vector: Sequence[float]) -> bool:
    return bool(vector) and all(math.isfinite(value) for value in vector)


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    left_norm = math.sqrt(sum(value * value for value in left))
    right_norm = math.sqrt(sum(value * value for value in right))
    if left_norm == 0.0 or right_norm == 0.0:
        return 0.0
    return sum(a * b for a, b in zip(left, right, strict=True)) / (
        left_norm * right_norm
    )


class InMemoryVectorIndex(VectorIndex):
    index_version = "in-memory-vector-1"

    def __init__(self) -> None:
        self._documents: dict[tuple[tuple[str, str, str], UUID], VectorDocument] = {}

    async def upsert(self, documents: Sequence[VectorDocument]) -> None:
        for document in documents:
            self._documents[(_scope(document.subject), document.id)] = document

    async def search(
        self, subject: SubjectRef, query_vector: Sequence[float], limit: int
    ) -> list[VectorSearchHit]:
        if not _valid_vector(query_vector):
            raise ValueError("query_vector must be non-empty and finite")
        if limit <= 0:
            return []
        query_scope = _scope(subject)
        dimensions = len(query_vector)
        hits: list[VectorSearchHit] = []
        for (document_scope, _), document in self._documents.items():
            if document_scope != query_scope or len(document.vector) != dimensions:
                continue
            score = max(-1.0, min(1.0, _cosine(document.vector, query_vector)))
            hits.append(
                VectorSearchHit(id=document.id, score=score, metadata=document.metadata)
            )
        hits.sort(key=lambda hit: (-hit.score, str(hit.id)))
        return hits[:limit]

    async def delete_subject(self, subject: SubjectRef) -> None:
        query_scope = _scope(subject)
        self._documents = {
            key: document
            for key, document in self._documents.items()
            if key[0] != query_scope
        }
