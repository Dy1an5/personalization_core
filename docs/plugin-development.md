# Plugin development

An independently distributed adapter must depend on `personalization_core.public`,
not `domain`, `application`, `infrastructure`, or SDK implementation modules.

## Feature extractor

Implement the frozen protocol:

```python
class FeatureExtractor(Protocol):
    name: str
    version: str
    supported_event_types: frozenset[str]

    async def extract(self, event: Event, entity: Entity | None) -> Sequence[FeatureObservationDraft]: ...
```

An extractor reads only generic event/entity fields and returns validated drafts.
Scores and confidence are constrained to `[-1, 1]` and `[0, 1]`; the engine adds
event/evidence references and persists the extractor version.

## Aggregation and registration

Aggregators implement `aggregate(observations, now)` for one feature dimension.
Register extractors with `FeatureExtractorRegistry`; use
`FeatureExtractorRegistry.with_builtins()` when the standard recency/frequency
aggregators are desired. Names and versions must be stable, and changing their
meaning requires a new version plus a rebuild.

Platform-specific values belong in adapter input models and generic JSON attributes,
never in Core columns. Empty or malformed adapter inputs should be rejected before
calling Core. Tests should verify DTO mapping, namespace isolation, idempotency, and
that imports do not reach Core internals.
