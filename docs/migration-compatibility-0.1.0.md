# Migration compatibility report: 0.1.0

Generated for release `0.1.0` on 2026-09-19.

## Chain

```text
base -> 0001_initial -> 0002_privacy_audit (head)
```

The release does not modify either historical migration and adds no migration. Both
SQLite and PostgreSQL use the same table/constraint contract; JSON uses SQLite text
and PostgreSQL JSONB, while UUIDs use SQLite strings and PostgreSQL UUIDs.

## Tables

`subjects`, `entities`, `events`, `evidence`, `memories`, `memory_evidence`,
`memory_revisions`, `feature_observations`, `feature_states`,
`feature_state_evidence`, `profile_snapshots`, `processing_runs`, `audit_log`, and
`purge_audit_log` are present in ORM metadata and the migration chain.

The key uniqueness boundaries are subject scope, subject/entity external identity,
subject/source/idempotency key, evidence source, memory revision, feature
observation identity, feature state dimension/value, and profile version. Foreign
keys cascade subject-owned data and preserve the minimal purge audit row.

## Compatibility conclusion

An existing database at `0002_privacy_audit` is compatible with `0.1.0` without a
schema operation. A database at `0001_initial` must run `alembic upgrade head` to add
the purge audit table. Downgrade to `0001_initial` removes only that table and loses
purge audit records; it is therefore an operational rollback, not a data-preserving
release rollback.
