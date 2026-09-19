# Data model

All timestamps are timezone-aware UTC datetimes internally and RFC 3339 at the HTTP
boundary.

| Object | Purpose | Mutability |
| --- | --- | --- |
| `Subject` | tenant/namespace/user scope and metadata | soft-deletable |
| `Entity` | generic domain object identified by type and external ID | patchable |
| `Event` | immutable behavior fact with source and idempotency key | append-only |
| `Evidence` | source reference for a fact or inference | append-only |
| `MemoryRecord` | explicit or inferred preference, constraint, goal, fact, or instruction | revisioned |
| `FeatureObservation` | one extractor result tied to an event/evidence | append-only |
| `FeatureState` | long/short-term aggregate for dimension/value | rebuildable |
| `ProfileSnapshot` | immutable resolved preference view | versioned |
| `ContextBundle` | task-specific memory/profile retrieval result | ephemeral/audited |

The public scope is the value object `SubjectRef(tenant_id, namespace, subject_id)`;
the database adds an internal UUID subject primary key. Event idempotency is scoped
by `(subject, source, idempotency_key)`: identical content is a replay and changed
content is an `IDEMPOTENCY_CONFLICT`.

Explicit memories have higher authority than behavior inference. Conflicting values
are retained and surfaced as unresolved conflicts. Deleting a subject is a soft
delete; purge removes its relational and index data while retaining only a minimal
sanitized purge audit row.

The `attributes`, `properties`, and `metadata` JSON fields are the extension points
for adapters. Core tables do not contain platform-specific columns.
