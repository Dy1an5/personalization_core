from __future__ import annotations

from collections.abc import Mapping, Sequence

from personalization_core.domain.memory import MemoryCandidate
from personalization_core.ports.memory_extractor import (
    ConversationMessage,
    MemoryExtraction,
    MemoryExtractor,
)


class DeterministicMemoryExtractor(MemoryExtractor):
    """A stable, network-free extractor used by tests and local deployments."""

    name = "deterministic-fake"
    version = "1"

    def __init__(
        self,
        candidates: Mapping[str, MemoryCandidate],
        quote_mapping: Mapping[str, str] | None = None,
    ) -> None:
        self._candidates = dict(candidates)
        self._quotes = dict(quote_mapping or {})

    async def extract(
        self, messages: Sequence[ConversationMessage]
    ) -> list[MemoryExtraction]:
        result: list[MemoryExtraction] = []
        for message in messages:
            candidate = self._candidates.get(message.evidence_ref)
            if candidate is None:
                continue
            result.append(
                MemoryExtraction(
                    candidate=candidate,
                    evidence_ref=message.evidence_ref,
                    evidence_quote=self._quotes.get(
                        message.evidence_ref, candidate.content
                    ),
                )
            )
        return result
