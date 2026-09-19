# Changelog

## [0.1.0] - 2026-09-19

### Added

- Domain-neutral event, memory, feature, profile, context, privacy and audit core.
- Embedded SQLite engine, FastAPI server, and synchronous/asynchronous remote SDKs.
- Stable `personalization_core.public` adapter contract and feature plugin protocol.
- SQLite and PostgreSQL-compatible Alembic migrations, contract tests, and release smoke test.

### Changed

- First public release; public DTO exports and plugin method signatures are frozen for 0.1.x.
- OpenAPI operation baseline is recorded in `docs/openapi-0.1.0.json`.

### Privacy

- Data is isolated by `(tenant_id, namespace, subject_id)`.
- Soft delete, purge tokens, sanitized audit records, and index cleanup are included.

### Compatibility

- Python `>=3.11`; SQLite is the embedded default and PostgreSQL is the server database option.
- Historical migrations remain unchanged; the release head is `0002_privacy_audit`.

### Not included

- Platform adapters, collaborative filtering, graph storage, distributed job queues, and provider-specific APIs.
