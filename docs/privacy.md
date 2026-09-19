# Privacy, deletion, and audit

Personalization Core isolates all data by the complete scope
`(tenant_id, namespace, subject_id)`. Application services validate that scope
before every read and write; repositories never use a subject identifier on its
own as a lookup key.

## Threat model

The privacy boundary covers five practical failure modes:

- **Log leakage:** Memory content, context queries, evidence excerpts,
  credentials, authorization headers, and tokens are recursively removed from
  audit metadata. Subject scopes in infrastructure logs are represented by a
  stable digest.
- **Cross-tenant access:** the authenticated tenant and namespace form the
  request scope, and all repository operations carry the full `SubjectRef`.
- **Index residue:** purge removes the scope from the relational database,
  full-text index, and vector index. Index implementations must preserve the
  same three-component scope key.
- **Token replay:** the API and Engine issue short-lived random purge tokens.
  Only a token digest is retained, and a successful consume atomically removes
  the token. A token for another scope, an expired token, or a replay is
  rejected.
- **Provider data egress:** provider adapters must send only the minimum
  normalized request fields needed for the operation.

## Deletion semantics

`DELETE /subjects/{subject_id}` is a soft delete. It is idempotent and blocks
normal export, search, and context resolution while retaining the data for the
configured retention process.

Purge is a separate irreversible operation. A caller first requests
`POST /subjects/{subject_id}:purge-token`, then submits the returned token to
`POST /subjects/{subject_id}:purge`. The database purge is one transaction;
after commit, external indexes are deleted and the retention hook is notified.
The result reports each cleanup status. Direct `SubjectService` instances
created without a token store retain the phase 13 subject-id confirmation
fallback for compatibility; Engine and API construction always inject a strict
token store.

## Audit and exemption boundary

Ordinary audit rows reference a live Subject and are deleted with that Subject.
After purge, one minimal `purge_audit_log` row may remain. It contains only a
row id, scope digest, action, timestamp, and sanitized metadata; it has no
Subject foreign key and must never contain user text or credentials. This is an
accountability record, not a retrievable user-data record.

## Prohibited log fields

The recursive sanitizer removes keys matching (case-insensitively and after
normalizing `-` and `_`): `content`, `query`, `excerpt`, `evidence_quote`,
`authorization`, `api_key`, `password`, `secret`, `credential`, and `token`.
Context audit records retain only `query_hash` and `query_length` for the query.

## Retention and provider egress

Subject export is an explicit, scope-checked operation and returns the normalized
subject, entities, events, evidence, memories, revisions, feature observations,
feature states, and profile snapshots needed to rebuild derived data. It is not an
authorization bypass: callers still authenticate as the owning tenant. Export and
purge operations are audited with sanitized metadata, while user text remains out
of ordinary logs.

`RetentionHook` is notified after successful Memory/Event commits and after a
successful subject purge. The hook receives only the scope and timestamp, so an
external adapter can schedule TTL or archival without Core introducing a queue
or a platform-specific deletion policy.

Third-party providers may receive only the minimum normalized payload: provider
operation name/version, required structured fields, bounded evidence references,
and hashed or length-only diagnostics. Raw Memory content, context query text,
credentials, bearer tokens, and complete conversation history are not sent by
Core's audit path. Provider adapters remain responsible for their own retention
and deletion agreements.
