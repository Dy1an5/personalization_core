# Architecture

Personalization Core is a domain-neutral library. An adapter translates a platform
object and behavior into Core's `EntityCreate`, `EventIngestionInput`, and optional
feature plugins. Core stores the raw event as the fact source, derives observations
and states, resolves a profile, and retrieves context for an application.

```text
adapter -> public DTOs -> Event/Memory stores -> Feature Engine
                                      |              |
                                      +-> Profile Resolver -> Context Resolver
```

The dependency direction is `domain <- ports <- infrastructure` and
`domain -> application -> api/sdk`. The domain imports only the standard library
and Pydantic. FastAPI is limited to `api`; SQLAlchemy and Alembic are limited to
`infrastructure`. External adapters must import `personalization_core.public` only.

The embedded engine uses SQLite and async application services. The server factory
uses the same services with PostgreSQL. The remote SDK speaks the versioned `/v1`
HTTP API. Repositories and provider ports are asynchronous so the three forms share
the same business behavior.

Events and observations are append-only. Feature states and profiles are derived and
rebuildable. Memory updates create revisions. Profile snapshots are immutable and
versioned. Every derived result carries an algorithm or extractor version and source
evidence references.

Every operation is scoped by `(tenant_id, namespace, subject_id)`. No repository
operation accepts a subject ID without the complete scope.
