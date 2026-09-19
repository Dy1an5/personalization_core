from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from personalization_core.domain.identifiers import SubjectRef
from personalization_core.ports.full_text_search import (
    FullTextIndex,
    TextDocument,
    TextSearchHit,
)


def _scope(subject: SubjectRef) -> tuple[str, str, str]:
    return (
        subject.tenant_id.root,
        subject.namespace.root,
        subject.subject_id.root,
    )


def _tokens(value: str) -> list[str]:
    result: list[str] = []
    current: list[str] = []
    for character in value.casefold():
        if character.isalnum():
            current.append(character)
        elif current:
            result.append("".join(current))
            current = []
    if current:
        result.append("".join(current))
    return result


def _updated_at(document: TextDocument) -> str:
    value = document.metadata.get("updated_at")
    return value if isinstance(value, str) else ""


class SimpleFullTextIndex(FullTextIndex):
    name = "simple-full-text"
    index_version = "simple-full-text-1"

    def __init__(self) -> None:
        self._documents: dict[tuple[tuple[str, str, str], UUID], TextDocument] = {}

    async def upsert(self, documents: Sequence[TextDocument]) -> None:
        for document in documents:
            self._documents[(_scope(document.subject), document.id)] = document

    async def search(
        self, subject: SubjectRef, query: str, limit: int
    ) -> list[TextSearchHit]:
        if limit <= 0:
            return []
        query_terms = list(dict.fromkeys(_tokens(query)))
        if not query_terms:
            return []
        query_scope = _scope(subject)
        matches: list[tuple[TextDocument, float, list[str]]] = []
        for (document_scope, _), document in self._documents.items():
            if document_scope != query_scope:
                continue
            document_terms = set(_tokens(document.text))
            matched = [term for term in query_terms if term in document_terms]
            if not matched:
                continue
            matches.append((document, len(matched) / len(query_terms), matched))
        matches.sort(key=lambda item: str(item[0].id))
        matches.sort(key=lambda item: _updated_at(item[0]), reverse=True)
        matches.sort(key=lambda item: item[1], reverse=True)
        return [
            TextSearchHit(id=document.id, score=score, matched_terms=terms)
            for document, score, terms in matches[:limit]
        ]

    async def delete_subject(self, subject: SubjectRef) -> None:
        query_scope = _scope(subject)
        self._documents = {
            key: document
            for key, document in self._documents.items()
            if key[0] != query_scope
        }
