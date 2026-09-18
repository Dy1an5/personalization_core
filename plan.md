# Personalization Core 实施计划

> 工作名：`personalization-core`  
> Python 包名：`personalization_core`  
> 目标版本：`0.1.0`  
> 实施位置：新建独立项目，本文件作为实施蓝图，不在 Bili Agent 内直接开发 Core。

## 0. 执行规则

- [ ] 严格按阶段顺序实施；当前阶段验收通过后才能进入下一阶段。
- [ ] 每个步骤只完成一个可验证目标，避免同时改动领域模型、存储和 API。
- [ ] 每个公共模型、端口和 HTTP 接口先写契约测试，再写实现。
- [ ] 每次数据库结构变化必须新增迁移，不允许修改已经发布的迁移文件。
- [ ] 所有时间在内部使用带时区 UTC `datetime`；API 使用 RFC 3339。
- [ ] 所有模型输出均视为不可信输入，必须经过结构校验和业务校验。
- [ ] Core 中禁止出现 `bvid`、`cid`、UP 主、收藏夹等 Bilibili 专有概念。
- [ ] Core 不直接依赖某个 LLM、Embedding、向量库或 Web 框架的具体实现。
- [ ] 行为推断不得覆盖用户明确表达；冲突必须被保留并返回。
- [ ] 原始事件是事实来源；Memory、Feature State、Profile Snapshot 都是可重建数据。
- [ ] 每个派生结果必须保存算法版本和证据引用。
- [ ] 每阶段完成后运行单元测试、契约测试、类型检查和格式检查。

## 1. 产品边界

### 1.1 Core 负责

- 接收任意领域已经标准化的用户行为事件。
- 保存、更新、检索用户明确记忆和推断记忆。
- 从事件生成带证据的行为特征观察值。
- 聚合长期兴趣和短期兴趣。
- 合并明确偏好、行为画像、当前任务，输出个性化上下文。
- 保存可审计、可比较的画像快照。
- 提供 Embedded Python SDK 和 HTTP API。
- 提供租户、命名空间和用户级数据隔离。
- 提供软删除、彻底删除、过期和审计能力。

### 1.2 Core 不负责

- 不直接调用 Bilibili、YouTube、GitHub 等业务 API。
- 不解析任何特定平台的原始响应。
- 不实现平台登录、Cookie、OAuth 或业务写操作。
- 不在 `0.1.0` 实现协同过滤、两塔召回或强化学习推荐。
- 不在 `0.1.0` 引入图数据库。
- 不要求使用向量数据库才能运行；纯结构化模式必须可用。
- 不把完整对话历史无条件注入模型上下文。
- 不让 LLM 直接决定最终偏好分数或覆盖明确约束。

### 1.3 核心定位

```text
Domain Adapter
  ├── 标准化实体
  ├── 标准化事件
  └── 注册领域 Feature Extractor / Semantic Enricher
                 ↓
Personalization Core
  ├── Event Store             原始行为事实
  ├── Memory Store            明确偏好、约束、目标、事实
  ├── Feature Engine          行为观察与长短期聚合
  ├── Profile Resolver        晚期融合与冲突处理
  └── Context Retrieval       面向当前任务的相关上下文
                 ↓
Agent / Recommender / Application
```

## 2. 技术决策

### 2.1 基础技术

- Python：`>=3.11`。
- 包管理与构建：`uv` + `hatchling`。
- 公共数据契约：Pydantic v2。
- ORM：SQLAlchemy 2.x。
- 数据库迁移：Alembic。
- Embedded 默认数据库：SQLite。
- Server 推荐数据库：PostgreSQL。
- HTTP：FastAPI，仅由 `api` 层依赖。
- 测试：pytest、pytest-asyncio、Hypothesis。
- 类型检查：pyright。
- 格式与静态检查：ruff。

### 2.2 运行模型

- 所有 Application Service 使用 `async` 接口。
- Repository、Unit of Work、模型提供商和向量索引均使用异步端口。
- SQLite Adapter 可以内部串行执行，但对外保持异步契约。
- 首版后台任务使用进程内 Job Runner；分布式队列留作后续适配器。
- Core 的领域模型不得导入 FastAPI、SQLAlchemy 或具体 Provider SDK。

### 2.3 存储原则

- Event 只追加，不原地修改业务字段。
- Memory 可以更新，但每次更新增加 `revision` 并保留审计记录。
- Feature Observation 只追加。
- Feature State 可以重建和覆盖。
- Profile Snapshot 不可变，只新增版本。
- API 删除默认软删除；`purge subject` 才进行不可恢复的彻底删除。

## 3. 目录结构

```text
personalization-core/
├── AGENTS.md
├── README.md
├── LICENSE
├── pyproject.toml
├── uv.lock
├── alembic.ini
├── plan.md
├── docs/
│   ├── architecture.md
│   ├── data-model.md
│   ├── api.md
│   ├── plugin-development.md
│   ├── privacy.md
│   └── evaluation.md
├── migrations/
│   ├── env.py
│   └── versions/
├── src/
│   └── personalization_core/
│       ├── __init__.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── identifiers.py
│       │   ├── enums.py
│       │   ├── entities.py
│       │   ├── events.py
│       │   ├── evidence.py
│       │   ├── memories.py
│       │   ├── features.py
│       │   ├── profiles.py
│       │   ├── context.py
│       │   ├── jobs.py
│       │   └── errors.py
│       ├── application/
│       │   ├── __init__.py
│       │   ├── dto.py
│       │   ├── event_service.py
│       │   ├── memory_service.py
│       │   ├── feature_service.py
│       │   ├── profile_service.py
│       │   ├── context_service.py
│       │   ├── feedback_service.py
│       │   └── subject_service.py
│       ├── ports/
│       │   ├── __init__.py
│       │   ├── clock.py
│       │   ├── unit_of_work.py
│       │   ├── repositories.py
│       │   ├── memory_extractor.py
│       │   ├── semantic_enricher.py
│       │   ├── embedder.py
│       │   ├── vector_index.py
│       │   ├── reranker.py
│       │   ├── job_runner.py
│       │   └── audit_sink.py
│       ├── plugins/
│       │   ├── __init__.py
│       │   ├── contracts.py
│       │   ├── registry.py
│       │   └── builtins/
│       │       ├── recency.py
│       │       └── frequency.py
│       ├── infrastructure/
│       │   ├── __init__.py
│       │   ├── persistence/
│       │   │   ├── sqlalchemy_models.py
│       │   │   ├── sqlalchemy_uow.py
│       │   │   ├── repositories.py
│       │   │   └── database.py
│       │   ├── providers/
│       │   │   ├── openai_compatible.py
│       │   │   └── deterministic.py
│       │   ├── indexes/
│       │   │   ├── in_memory.py
│       │   │   └── null_index.py
│       │   ├── jobs/
│       │   │   └── inline_runner.py
│       │   └── observability/
│       │       ├── logging.py
│       │       └── metrics.py
│       ├── api/
│       │   ├── __init__.py
│       │   ├── app.py
│       │   ├── dependencies.py
│       │   ├── errors.py
│       │   ├── auth.py
│       │   └── routers/
│       │       ├── health.py
│       │       ├── events.py
│       │       ├── memories.py
│       │       ├── profiles.py
│       │       ├── context.py
│       │       ├── feedback.py
│       │       └── subjects.py
│       └── sdk/
│           ├── __init__.py
│           ├── async_client.py
│           ├── client.py
│           └── errors.py
└── tests/
    ├── unit/
    │   ├── domain/
    │   ├── application/
    │   └── plugins/
    ├── contract/
    │   ├── repositories/
    │   ├── providers/
    │   └── api/
    ├── integration/
    │   ├── sqlite/
    │   ├── postgres/
    │   └── http/
    ├── e2e/
    └── fixtures/
```

## 4. 依赖方向

允许的依赖方向：

```text
domain ← application ← api/sdk
   ↑           ↑
 ports ← infrastructure
   ↑
plugins
```

具体约束：

- `domain` 只能依赖 Python 标准库和 Pydantic。
- `ports` 只能依赖 `domain`。
- `application` 只能依赖 `domain` 和 `ports`。
- `plugins` 只能依赖 `domain` 和 `ports`。
- `infrastructure` 实现 `ports`，不得被 `domain` 导入。
- `api` 和 `sdk` 只能调用 Application Service，不直接访问 Repository。
- 领域适配器作为独立包依赖 Core；Core 永远不反向依赖领域适配器。

## 5. 公共标识与作用域

所有用户数据由同一个三元组隔离：

```text
(tenant_id, namespace, subject_id)
```

字段定义：

| 字段 | 类型 | 约束 |
| --- | --- | --- |
| `tenant_id` | string | `1..100`，调用方或组织标识 |
| `namespace` | string | `1..100`，应用或数据域，默认 `default` |
| `subject_id` | string | `1..200`，调用方定义的用户标识 |
| `internal_subject_id` | UUID | Core 内部主键，不暴露业务含义 |

必须实现的值对象：

- `TenantId`
- `Namespace`
- `SubjectId`
- `SubjectRef`
- `EntityRef`
- `EvidenceRef`

验收约束：

- 空白字符串非法。
- 标识符去除首尾空格但保留大小写。
- 日志默认只记录哈希后的 `subject_id`。
- 任意 Repository 查询都必须显式传入 `SubjectRef` 或内部用户主键。

## 6. 核心数据结构

### 6.1 Subject

```python
class Subject:
    id: UUID
    ref: SubjectRef
    metadata: dict[str, JsonValue]
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
```

约束：

- `(tenant_id, namespace, subject_id)` 唯一。
- `metadata` 只保存非敏感、调用方自定义信息。
- 被软删除的 Subject 默认不能继续写入。

### 6.2 Entity

```python
class Entity:
    id: UUID
    subject: SubjectRef
    entity_type: str
    external_id: str
    attributes: dict[str, JsonValue]
    content_text: str | None
    content_hash: str | None
    schema_version: str
    first_seen_at: datetime
    last_seen_at: datetime
    deleted_at: datetime | None
```

约束：

- `(subject, entity_type, external_id)` 唯一。
- `entity_type` 使用领域命名，如 `video`、`article`、`creator`。
- `content_hash` 用于判断语义内容是否需要重新处理。
- Core 不解释 `attributes` 的业务含义。

### 6.3 Event

```python
class Event:
    id: UUID
    subject: SubjectRef
    event_type: str
    entity: EntityRef | None
    source: str
    idempotency_key: str
    value: float | None
    polarity: Polarity
    properties: dict[str, JsonValue]
    occurred_at: datetime
    observed_at: datetime
    schema_version: str
```

`Polarity`：

- `positive`
- `neutral`
- `negative`
- `unknown`

约束：

- `(subject, source, idempotency_key)` 唯一。
- 同一幂等键和相同内容重复写入返回原 Event。
- 同一幂等键但内容不同返回 `IDEMPOTENCY_CONFLICT`。
- `occurred_at` 是行为发生时间；`observed_at` 是系统接收时间。
- Event 创建后不可修改，只能追加纠正事件或执行用户级彻底删除。

### 6.4 Evidence

```python
class Evidence:
    id: UUID
    subject: SubjectRef
    source_type: EvidenceSourceType
    source_ref: str
    event_id: UUID | None
    excerpt: str | None
    metadata: dict[str, JsonValue]
    occurred_at: datetime
    created_at: datetime
```

`EvidenceSourceType`：

- `conversation`
- `event`
- `user`
- `system`
- `import`

约束：

- `(subject, source_type, source_ref)` 唯一。
- `excerpt` 最长 2,000 字符。
- Evidence 必须能够追溯到用户输入、事件或导入记录。

### 6.5 MemoryRecord

```python
class MemoryRecord:
    id: UUID
    subject: SubjectRef
    key: str
    kind: MemoryKind
    content: str
    structured_value: dict[str, JsonValue] | None
    target: PreferenceTarget | None
    authority: MemoryAuthority
    polarity: Polarity
    scope: MemoryScope
    scope_value: str | None
    confidence: float
    state: MemoryState
    valid_from: datetime | None
    valid_until: datetime | None
    evidence_count: int
    revision: int
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None
```

`MemoryKind`：

- `preference`
- `constraint`
- `goal`
- `fact`
- `instruction`

`MemoryAuthority`：

- `explicit`：用户明确表达。
- `confirmed`：用户确认过的推断。
- `inferred`：系统或模型推断。

`MemoryScope`：

- `global`
- `use_case`
- `topic`
- `entity`

`MemoryState`：

- `candidate`
- `active`
- `superseded`
- `expired`
- `deleted`

`PreferenceTarget`：

```python
class PreferenceTarget:
    dimension: str
    value_key: str
```

说明：

- `target` 把自然语言 Memory 映射到可与 Feature State 融合的稳定坐标。
- 例如“我不喜欢入门教程”可以映射为
  `dimension=content_level, value_key=beginner, polarity=negative`。
- 无法可靠结构化的 Memory 允许 `target=None`，此时只参与语义检索，不参与数值融合。
- `structured_value` 保存目标之外的扩展条件，例如时长上下限、语言或排序要求。

约束：

- `confidence` 范围为 `[0, 1]`。
- `global` 的 `scope_value` 必须为空，其余作用域必须有值。
- 持久层额外生成非空 `scope_key`：global 使用空字符串，其余使用规范化后的
  `scope_value`，避免 SQL 中 `NULL` 破坏唯一约束。
- `explicit` 默认直接进入 `active`。
- `inferred` 默认进入 `candidate`，不得直接作为硬约束。
- 相同 `key + scope + scope_value` 的 active Memory 同时最多一个。
- 带 `target` 的 preference/constraint 才参与 Profile Resolver 数值融合。
- 新 Memory 与旧 Memory 冲突时保留两者证据，并将旧版本标记为 `superseded`。
- 行为特征不能直接把明确 Memory 改为 `superseded`。

### 6.6 FeatureObservation

Feature Observation 是领域插件从 Event 或 Entity 提取的不可变观察值。

```python
class FeatureObservation:
    id: UUID
    subject: SubjectRef
    dimension: str
    value_key: str
    value: dict[str, JsonValue]
    score: float
    polarity: Polarity
    confidence: float
    occurred_at: datetime
    source_event_id: UUID
    evidence_id: UUID
    extractor_name: str
    extractor_version: str
    created_at: datetime
```

示例维度：

- `topic`
- `creator`
- `duration_bucket`
- `popularity_bucket`
- `content_format`

约束：

- Core 不预置业务维度枚举，维度由插件注册。
- `(source_event_id, dimension, value_key, extractor_name, extractor_version)` 唯一。
- `score` 范围为 `[-1, 1]`。
- Observation 永不覆盖；Extractor 升级后写入新版本。

### 6.7 FeatureState

```python
class FeatureState:
    subject: SubjectRef
    dimension: str
    value_key: str
    value: dict[str, JsonValue]
    long_term_score: float
    short_term_score: float
    confidence: float
    positive_evidence_count: int
    negative_evidence_count: int
    neutral_evidence_count: int
    first_evidence_at: datetime
    last_evidence_at: datetime
    aggregator_name: str
    algorithm_version: str
    updated_at: datetime
```

约束：

- 长短期分数范围均为 `[-1, 1]`。
- `confidence` 同时考虑样本量、证据一致性和数据新鲜度。
- Feature State 只能由 Observation 重建，不能接受外部直接写入。
- 读取时必须能取得支撑该 State 的 Evidence ID 列表。

### 6.8 ResolvedPreference

Resolved Preference 是 Memory 与 Feature State 的晚期融合结果，不直接作为事实保存。

```python
class ResolvedPreference:
    dimension: str
    value_key: str
    explicit_memory_ids: list[UUID]
    feature_state_key: str | None
    effective_polarity: Polarity
    effective_score: float
    confidence: float
    resolution: ResolutionType
    conflicts: list[PreferenceConflict]
    evidence_refs: list[str]
```

`ResolutionType`：

- `explicit_only`
- `behavior_only`
- `aligned`
- `explicit_overrides_behavior`
- `unresolved_conflict`

优先级：

```text
当前请求中的明确指令
> active explicit Memory
> active confirmed Memory
> 高置信度行为特征
> inferred Memory
> 低置信度行为特征
```

### 6.9 ProfileSnapshot

```python
class ProfileSnapshot:
    id: UUID
    subject: SubjectRef
    version: int
    status: ProfileStatus
    generated_at: datetime
    algorithm_version: str
    source_watermark: datetime | None
    coverage: ProfileCoverage
    preferences: list[ResolvedPreference]
    warnings: list[str]
```

`ProfileStatus`：

- `complete`
- `partial`
- `stale`
- `empty`
- `failed`

约束：

- `(subject, version)` 唯一且版本单调递增。
- Snapshot JSON 必须能够独立反序列化。
- `complete` 只表示处理覆盖完成，不表示推断绝对正确。
- 覆盖率与推断置信度必须使用不同字段表达。

### 6.10 ContextRequest 与 ContextBundle

```python
class ContextRequest:
    subject: SubjectRef
    query: str
    use_case: str
    entity_refs: list[EntityRef]
    max_memories: int
    max_preferences: int
    token_budget: int | None
    as_of: datetime | None


class ContextBundle:
    hard_constraints: list[MemoryRecord]
    explicit_preferences: list[MemoryRecord]
    recent_interests: list[ResolvedPreference]
    long_term_interests: list[ResolvedPreference]
    relevant_memories: list[MemorySearchHit]
    conflicts: list[PreferenceConflict]
    evidence_refs: list[str]
    generated_at: datetime
```

约束：

- `ContextBundle` 面向当前任务生成，不返回整个用户画像。
- 硬约束优先保留，不得因 token budget 被静默删除。
- 返回结果必须经过作用域过滤、时间有效性过滤和租户过滤。
- 同一个证据不得在 Bundle 中重复占用预算。

## 7. 插件协议

### 7.1 FeatureExtractor

```python
class FeatureExtractor(Protocol):
    name: str
    version: str
    supported_event_types: frozenset[str]

    async def extract(
        self,
        event: Event,
        entity: Entity | None,
    ) -> list[FeatureObservationDraft]: ...
```

### 7.2 FeatureAggregator

```python
class FeatureAggregator(Protocol):
    name: str
    version: str
    dimension: str

    def aggregate(
        self,
        observations: Sequence[FeatureObservation],
        now: datetime,
    ) -> FeatureStateDraft: ...
```

### 7.3 MemoryExtractor

```python
class MemoryExtractor(Protocol):
    name: str
    version: str

    async def extract(
        self,
        messages: Sequence[ConversationMessage],
    ) -> list[MemoryCandidate]: ...
```

### 7.4 SemanticEnricher

```python
class SemanticEnricher(Protocol):
    name: str
    version: str

    async def enrich(self, entity: Entity) -> list[SemanticAttribute]: ...
```

### 7.5 Retrieval 端口

- `Embedder.embed_documents()`
- `Embedder.embed_query()`
- `VectorIndex.upsert()`
- `VectorIndex.search()`
- `VectorIndex.delete_subject()`
- `Reranker.rerank()`

约束：

- 没有 Embedder 时，系统退回结构化过滤和全文匹配。
- 更换 Embedding 模型时必须使用不同 `index_version`。
- Provider 错误必须映射为稳定的 Core Error Code。

## 8. 数据库结构

### 8.1 必需表

首个迁移创建：

1. `subjects`
2. `entities`
3. `events`
4. `evidence`
5. `memories`
6. `memory_evidence`
7. `memory_revisions`
8. `feature_observations`
9. `feature_states`
10. `feature_state_evidence`
11. `profile_snapshots`
12. `processing_runs`
13. `audit_log`

### 8.2 关键唯一约束

- `subjects(tenant_id, namespace, external_subject_id)`
- `entities(subject_pk, entity_type, external_id)`
- `events(subject_pk, source, idempotency_key)`
- `evidence(subject_pk, source_type, source_ref)`
- active Memory 的部分唯一索引：
  `(subject_pk, key, scope, scope_key) WHERE state = 'active'`
- `memory_evidence(memory_id, evidence_id)`
- Feature Observation：
  `(source_event_id, dimension, value_key, extractor_name, extractor_version)`
- `feature_states(subject_pk, dimension, value_key, aggregator_name)`
- `feature_state_evidence(feature_state_id, evidence_id)`
- `profile_snapshots(subject_pk, version)`

### 8.3 必需索引

- Event：`(subject_pk, occurred_at DESC)`。
- Event：`(subject_pk, event_type, occurred_at DESC)`。
- Memory：`(subject_pk, state, updated_at DESC)`。
- Memory：`(subject_pk, scope, scope_value, state)`。
- `memories.scope_key` 为非空派生列或由 Repository 写入的规范化列。
- `memories.target_dimension`、`memories.target_value_key` 为可空列，用于结构化融合查询。
- Observation：`(subject_pk, dimension, value_key, occurred_at DESC)`。
- Feature State：`(subject_pk, dimension, long_term_score DESC)`。
- Feature State：`(subject_pk, dimension, short_term_score DESC)`。
- Snapshot：`(subject_pk, version DESC)`。
- Processing Run：`(subject_pk, started_at DESC)`。

### 8.4 SQLite 与 PostgreSQL 一致性

- JSON 在模型层统一验证；SQLite 使用 TEXT，PostgreSQL 使用 JSONB。
- UUID 在模型层统一为 UUID；SQLite 使用 TEXT，PostgreSQL 使用 UUID。
- 部分唯一索引必须在两种数据库分别进行集成测试。
- SQLite 测试启用 `PRAGMA foreign_keys = ON` 和 WAL。
- PostgreSQL 测试通过 Testcontainers 或 CI Service 启动。

## 9. 应用服务契约

### 9.1 EventService

- `upsert_entity(subject, entity_input) -> Entity`
- `ingest_event(subject, event_input) -> EventIngestionResult`
- `ingest_batch(subject, events) -> BatchIngestionResult`
- `list_events(subject, filters, page) -> EventPage`

### 9.2 MemoryService

- `add_memory(subject, input) -> MemoryRecord`
- `extract_memories(subject, messages) -> MemoryExtractionResult`
- `search_memories(subject, request) -> list[MemorySearchHit]`
- `update_memory(subject, memory_id, patch, expected_revision) -> MemoryRecord`
- `confirm_memory(subject, memory_id) -> MemoryRecord`
- `delete_memory(subject, memory_id) -> MemoryRecord`
- `restore_memory(subject, memory_id) -> MemoryRecord`

### 9.3 FeatureService

- `process_event(subject, event_id) -> FeatureProcessingResult`
- `process_pending(subject, limit) -> ProcessingRun`
- `rebuild_dimension(subject, dimension) -> ProcessingRun`
- `list_feature_states(subject, filters) -> list[FeatureState]`

### 9.4 ProfileService

- `refresh_profile(subject, options) -> ProfileSnapshot`
- `get_latest_profile(subject) -> ProfileSnapshot | None`
- `get_profile_version(subject, version) -> ProfileSnapshot`
- `compare_profiles(subject, left, right) -> ProfileDiff`

### 9.5 ContextService

- `resolve_context(request) -> ContextBundle`
- `explain_preference(subject, dimension, value_key) -> PreferenceExplanation`

### 9.6 SubjectService

- `create_or_get_subject(ref) -> Subject`
- `soft_delete_subject(ref) -> Subject`
- `export_subject(ref) -> SubjectExport`
- `purge_subject(ref, confirmation) -> PurgeResult`

## 10. HTTP API 草案

基础路径：`/v1`。

### 10.1 Events

- `POST /v1/subjects/{subject_id}/entities`
- `POST /v1/subjects/{subject_id}/events`
- `POST /v1/subjects/{subject_id}/events:batch`
- `GET /v1/subjects/{subject_id}/events`

### 10.2 Memories

- `POST /v1/subjects/{subject_id}/memories`
- `POST /v1/subjects/{subject_id}/memories:extract`
- `POST /v1/subjects/{subject_id}/memories:search`
- `GET /v1/subjects/{subject_id}/memories/{memory_id}`
- `PATCH /v1/subjects/{subject_id}/memories/{memory_id}`
- `POST /v1/subjects/{subject_id}/memories/{memory_id}:confirm`
- `DELETE /v1/subjects/{subject_id}/memories/{memory_id}`

### 10.3 Profiles 与 Context

- `POST /v1/subjects/{subject_id}/profiles:refresh`
- `GET /v1/subjects/{subject_id}/profiles/latest`
- `GET /v1/subjects/{subject_id}/profiles/{version}`
- `GET /v1/subjects/{subject_id}/profiles:compare?left=1&right=2`
- `POST /v1/subjects/{subject_id}/context:resolve`
- `GET /v1/subjects/{subject_id}/preferences/{dimension}/{value_key}:explain`

### 10.4 数据治理

- `GET /v1/health/live`
- `GET /v1/health/ready`
- `GET /v1/subjects/{subject_id}:export`
- `DELETE /v1/subjects/{subject_id}`：软删除。
- `POST /v1/subjects/{subject_id}:purge`：二次确认后彻底删除。

### 10.5 Header

- `Authorization: Bearer <token>`
- `X-Tenant-Id: <tenant>`
- `X-Namespace: <namespace>`，默认 `default`
- `Idempotency-Key: <key>`，Event 写入必须提供
- `X-Request-Id: <id>`，可选；服务端缺失时生成

### 10.6 稳定错误码

- `INVALID_ARGUMENT`
- `SUBJECT_NOT_FOUND`
- `SUBJECT_DELETED`
- `ENTITY_NOT_FOUND`
- `MEMORY_NOT_FOUND`
- `REVISION_CONFLICT`
- `IDEMPOTENCY_CONFLICT`
- `TENANT_SCOPE_VIOLATION`
- `PROVIDER_TIMEOUT`
- `PROVIDER_NETWORK_ERROR`
- `PROVIDER_INVALID_RESPONSE`
- `PROCESSING_FAILED`
- `PURGE_CONFIRMATION_REQUIRED`

## 11. 分阶段实施清单

[x] 表示已经完成

### 阶段 0：创建仓库和质量门禁

- [x] 0.1 创建新的 `personalization-core` Git 仓库。
- [x] 0.2 创建 `src/` layout 和 `personalization_core` 包。
- [x] 0.3 配置 Python `>=3.11` 和 hatchling 构建。
- [x] 0.4 添加 runtime 依赖：Pydantic、SQLAlchemy。
- [x] 0.5 添加 dev 依赖：pytest、pytest-asyncio、Hypothesis、ruff、pyright。
- [x] 0.6 配置 ruff format 和 lint。
- [x] 0.7 配置 pyright strict 模式。
- [x] 0.8 配置 pytest marker：`unit`、`contract`、`integration`、`e2e`。
- [x] 0.9 创建最小 `README.md`，写明产品边界和非目标。
- [x] 0.10 创建 CI：lint、typecheck、unit test。
- [x] 0.11 添加 `make check` 或等价 `uv run` 聚合命令。
- [x] 0.12 验证空项目可以 build wheel 和安装。

阶段验收：

- [x] `uv build` 成功。
- [x] `ruff check .` 成功。
- [x] `pyright` 成功。
- [x] `pytest -m unit` 成功。

### 阶段 1：定义领域基础类型

- [x] 1.1 实现 `JsonValue` 递归类型。
- [x] 1.2 实现 Tenant、Namespace、Subject 标识值对象。
- [x] 1.3 实现 `SubjectRef`。
- [x] 1.4 实现 `EntityRef`。
- [x] 1.5 实现 UTC 时间校验器。
- [x] 1.6 实现 `Polarity` 和通用状态枚举。
- [x] 1.7 实现领域错误基类和稳定 error code。
- [x] 1.8 为标识符空白、长度、大小写编写参数化测试。
- [x] 1.9 为 naive datetime 拒绝策略编写测试。
- [x] 1.10 为所有公共模型配置 `extra='forbid'`。
- [x] 1.11 导出首批公共类型并冻结命名。

阶段验收：

- [x] 所有领域类型不依赖数据库和 Web 框架。
- [x] 非法时间和越界标识均产生稳定错误。

### 阶段 2：定义 Subject、Entity、Event、Evidence

- [x] 2.1 实现 `Subject` 和输入模型。
- [x] 2.2 实现 `Entity`、`EntityCreate`、`EntityPatch`。
- [x] 2.3 实现 `Event`、`EventCreate`。
- [x] 2.4 实现 `Evidence`、`EvidenceCreate`。
- [x] 2.5 实现 Event 内容规范化和内容摘要。
- [x] 2.6 定义幂等重放与幂等冲突判定函数。
- [x] 2.7 测试同内容同幂等键得到相同摘要。
- [x] 2.8 测试字段变化触发幂等冲突。
- [x] 2.9 测试 Event 创建后不可变。
- [x] 2.10 测试任意 JSON 属性可以稳定序列化。

阶段验收：

- [ ] 使用纯内存对象能够完成 Entity + Event + Evidence 的合法建模。
- [ ] Bilibili 专有字段没有进入公共模型。

### 阶段 3：定义 Memory 领域模型和状态机

- [x] 3.1 实现 Memory 枚举和模型。
- [x] 3.2 实现 `MemoryCandidate`。
- [x] 3.3 实现显式 Memory 默认激活规则。
- [x] 3.4 实现推断 Memory 默认候选规则。
- [x] 3.5 实现 confirm 状态转换。
- [x] 3.6 实现 supersede 状态转换。
- [x] 3.7 实现 expire 状态转换。
- [x] 3.8 实现 soft delete 和 restore 状态转换。
- [x] 3.9 实现 `revision` 乐观锁规则。
- [x] 3.10 实现有效时间判断。
- [x] 3.11 实现 Memory 冲突数据模型，不实现自动语义判断。
- [x] 3.12 为每条合法和非法状态转换编写测试。
- [x] 3.13 测试行为推断不能覆盖 explicit Memory。

阶段验收：

- [ ] Memory 生命周期可以完全由纯领域测试验证。
- [ ] 任意状态变化都能说明操作者、原因和前后 revision。

### 阶段 4：定义 Feature 与 Profile 领域模型

- [x] 4.1 实现 `FeatureObservation` 和 Draft。
- [x] 4.2 实现 `FeatureState` 和 Draft。
- [x] 4.3 实现正负证据计数约束。
- [x] 4.4 实现长短期分数范围约束。
- [x] 4.5 实现 `ResolvedPreference`。
- [x] 4.6 实现 `PreferenceConflict`。
- [x] 4.7 实现确定性的权威级别比较器。
- [x] 4.8 实现 `ProfileCoverage`。
- [x] 4.9 实现 `ProfileSnapshot`。
- [x] 4.10 实现 `ProfileDiff`。
- [x] 4.11 测试 complete 与 confidence 相互独立。
- [x] 4.12 测试显式与行为一致时生成 `aligned`。
- [x] 4.13 测试显式与行为冲突时生成 `explicit_overrides_behavior`。

阶段验收：

- [ ] 给定固定 Memory 和 Feature State，可以生成确定性相同的 Profile。
- [ ] Profile 中每项偏好都能返回证据引用。

### 阶段 5：定义端口和内存测试实现

- [x] 5.1 定义 Clock 端口和 FakeClock。
- [x] 5.2 定义 UnitOfWork 端口。
- [x] 5.3 定义 Subject Repository。
- [x] 5.4 定义 Entity Repository。
- [x] 5.5 定义 Event Repository。
- [x] 5.6 定义 Evidence Repository。
- [x] 5.7 定义 Memory Repository。
- [x] 5.8 定义 Feature Repository。
- [x] 5.9 定义 Profile Repository。
- [x] 5.10 定义 Processing Run Repository。
- [x] 5.11 定义 Provider 和 Retrieval 端口。
- [x] 5.12 编写 Repository 共享契约测试套件。
- [x] 5.13 实现仅供测试使用的 In-memory Repository。
- [x] 5.14 让 In-memory 实现通过全部 Repository 契约。

阶段验收：

- [ ] Application 层可以只使用端口和内存实现运行。
- [ ] 契约测试可以复用于后续 SQLite/PostgreSQL 实现。

### 阶段 6：实现数据库和迁移

- [ ] 6.1 创建 SQLAlchemy Base 和命名约定。
- [ ] 6.2 实现 13 张表的 ORM 映射。
- [ ] 6.3 添加外键和删除策略。
- [ ] 6.4 添加唯一约束和部分索引。
- [ ] 6.5 创建 Alembic 初始迁移。
- [ ] 6.6 实现 SQLite Engine 配置。
- [ ] 6.7 启用 SQLite foreign keys 和 WAL。
- [ ] 6.8 实现 SQLAlchemy Unit of Work。
- [ ] 6.9 逐个实现 Repository。
- [ ] 6.10 让 SQLite Adapter 通过共享 Repository 契约。
- [ ] 6.11 添加事务回滚测试。
- [ ] 6.12 添加并发 revision conflict 测试。
- [ ] 6.13 添加幂等唯一约束竞争测试。
- [ ] 6.14 添加迁移 upgrade/downgrade 冒烟测试。

阶段验收：

- [ ] 新数据库可以从零迁移到 head。
- [ ] SQLite 下所有 Repository 契约通过。
- [ ] 失败事务不会留下部分写入。

### 阶段 7：实现 Event 与 Evidence 写入链路

- [ ] 7.1 实现 Subject create-or-get。
- [ ] 7.2 实现 Entity upsert。
- [ ] 7.3 实现单 Event 幂等写入。
- [ ] 7.4 实现批量 Event 写入。
- [ ] 7.5 定义批量结果中的 created/replayed/failed 项。
- [ ] 7.6 同事务创建 Event Evidence。
- [ ] 7.7 实现 Event 分页和过滤。
- [ ] 7.8 实现删除 Subject 后拒绝新 Event。
- [ ] 7.9 测试批量中单项非法时的原子模式。
- [ ] 7.10 测试批量中单项非法时的 best-effort 模式。
- [ ] 7.11 测试跨租户幂等键互不冲突。

阶段验收：

- [ ] 外部系统可以安全、重复地推送同一批事件。
- [ ] 每条 Event 都有对应可追溯 Evidence。

### 阶段 8：实现 Memory CRUD 和提取管线

- [ ] 8.1 实现手动添加 explicit Memory。
- [ ] 8.2 实现 Memory 列表和结构化过滤。
- [ ] 8.3 实现 revision-aware patch。
- [ ] 8.4 实现 confirm、delete、restore。
- [ ] 8.5 每次更新写入 `memory_revisions`。
- [ ] 8.6 实现 Evidence 绑定和去重。
- [ ] 8.7 定义 MemoryExtractor 输入输出契约。
- [ ] 8.8 实现 Deterministic Fake Extractor。
- [ ] 8.9 实现提取结果的 schema 和 evidence quote 校验。
- [ ] 8.10 实现敏感信息过滤 Hook，不内置业务敏感词表。
- [ ] 8.11 实现相同 key 的精确合并。
- [ ] 8.12 将语义相似合并放在可选策略接口，不写死阈值。
- [ ] 8.13 实现推断候选确认门槛策略。
- [ ] 8.14 测试 Provider 超时不影响已经完成的主业务事务。
- [ ] 8.15 测试无效模型输出不写数据库。

阶段验收：

- [ ] Memory CRUD 不依赖 LLM 即可完整使用。
- [ ] 开启 Extractor 后可以从对话生成候选且不越权激活。

### 阶段 9：实现插件注册和 Feature Engine

- [ ] 9.1 实现 FeatureExtractor Registry。
- [ ] 9.2 拒绝同名同版本插件重复注册。
- [ ] 9.3 按 Event Type 路由 Extractor。
- [ ] 9.4 实现 Observation 幂等保存。
- [ ] 9.5 实现单 Event Feature 处理。
- [ ] 9.6 实现未处理 Event 扫描。
- [ ] 9.7 实现 Processing Run 审计。
- [ ] 9.8 实现内置 frequency Aggregator。
- [ ] 9.9 实现内置 recency decay Aggregator。
- [ ] 9.10 分别计算 short-term 与 long-term score。
- [ ] 9.11 实现正负证据抵消但不互相删除。
- [ ] 9.12 实现样本量和一致性置信度。
- [ ] 9.13 实现 dimension 全量重建。
- [ ] 9.14 测试 Extractor 升级后生成新 Observation。
- [ ] 9.15 测试同版本重复处理不增加 Observation。

阶段验收：

- [ ] 使用测试插件可以从通用 Event 生成并聚合 Feature State。
- [ ] 所有 Feature State 都能追溯到 Observation 和 Evidence。

### 阶段 10：实现 Profile Resolver

- [ ] 10.1 按作用域筛选 active Memory。
- [ ] 10.2 按时间有效性筛选 Memory。
- [ ] 10.3 加载 long-term 和 short-term Feature State。
- [ ] 10.4 实现明确偏好与行为一致判定。
- [ ] 10.5 实现明确偏好覆盖行为判定。
- [ ] 10.6 实现无法自动解决的冲突保留。
- [ ] 10.7 实现 Profile Coverage 统计。
- [ ] 10.8 实现 Snapshot 版本递增。
- [ ] 10.9 实现无变化刷新检测。
- [ ] 10.10 无变化时默认返回原 Snapshot，不生成重复版本。
- [ ] 10.11 提供 `force_new_snapshot` 覆盖选项。
- [ ] 10.12 实现 Snapshot Diff。
- [ ] 10.13 测试同输入生成稳定相同内容摘要。
- [ ] 10.14 测试 explicit Memory 永远不被行为结果覆盖。

阶段验收：

- [ ] Profile 是可重建派生视图。
- [ ] 无数据变化的 refresh 不制造无意义版本。
- [ ] Snapshot Diff 能说明新增、删除、增强、减弱和冲突变化。

### 阶段 11：实现 Memory 检索和 Context Resolver

- [ ] 11.1 实现结构化 Memory 过滤。
- [ ] 11.2 实现作用域匹配。
- [ ] 11.3 实现有效时间过滤。
- [ ] 11.4 实现基础全文检索 Adapter。
- [ ] 11.5 实现 Null Vector Index。
- [ ] 11.6 实现 In-memory Vector Index 供测试。
- [ ] 11.7 实现可选 Embedding 检索。
- [ ] 11.8 合并结构化、全文和向量候选。
- [ ] 11.9 实现去重和可选 Reranker。
- [ ] 11.10 实现 Context Request 查询意图输入。
- [ ] 11.11 始终优先加入 hard constraints。
- [ ] 11.12 分别选择 recent 和 long-term interests。
- [ ] 11.13 实现 token budget 裁剪。
- [ ] 11.14 实现 Evidence 去重。
- [ ] 11.15 返回冲突但不让模型自行覆盖明确偏好。
- [ ] 11.16 写入 Context Resolution 审计，不记录完整 query 明文。
- [ ] 11.17 测试跨租户检索永远返回空而非泄露。

阶段验收：

- [ ] 给定当前任务，只返回相关个性化上下文。
- [ ] 没有 Embedding Provider 时功能仍然完整可用。
- [ ] token budget 很小时硬约束仍被保留。

### 阶段 12：实现 Embedded SDK

- [ ] 12.1 实现 `PersonalizationEngine` 异步入口。
- [ ] 12.2 暴露 Event、Memory、Profile、Context 服务。
- [ ] 12.3 提供 `from_sqlite(path)` 工厂。
- [ ] 12.4 提供依赖注入式 `from_components(...)` 工厂。
- [ ] 12.5 实现资源关闭和 async context manager。
- [ ] 12.6 提供同步 Client Wrapper。
- [ ] 12.7 防止在运行中的 event loop 误用同步 Wrapper。
- [ ] 12.8 编写 Embedded quickstart。
- [ ] 12.9 编写完整本地 E2E 测试。

Embedded API 目标形态：

```python
async with PersonalizationEngine.from_sqlite("personalization.db") as engine:
    await engine.events.ingest_batch(subject, events)
    await engine.memories.add(subject, memory)
    profile = await engine.profiles.refresh(subject)
    context = await engine.context.resolve(request)
```

阶段验收：

- [ ] 不启动 HTTP Server 即可嵌入其他 Python 项目。
- [ ] Quickstart 可以在临时目录从零运行成功。

### 阶段 13：实现 HTTP API

- [ ] 13.1 创建 FastAPI App Factory。
- [ ] 13.2 实现 request ID middleware。
- [ ] 13.3 实现 Bearer Token 到 tenant 的认证端口。
- [ ] 13.4 实现 namespace 解析。
- [ ] 13.5 实现统一成功响应和错误响应。
- [ ] 13.6 实现 Event 路由。
- [ ] 13.7 实现 Memory 路由。
- [ ] 13.8 实现 Profile 路由。
- [ ] 13.9 实现 Context 路由。
- [ ] 13.10 实现 Subject export/delete/purge 路由。
- [ ] 13.11 生成并固定 OpenAPI snapshot。
- [ ] 13.12 测试所有 error code 到 HTTP status 的映射。
- [ ] 13.13 测试租户 Header 无法覆盖 Token 绑定租户。
- [ ] 13.14 测试 Event Idempotency-Key。
- [ ] 13.15 测试请求大小、批量数量和分页上限。
- [ ] 13.16 添加超时和 Provider 错误映射。

建议限制：

- 单 Event 请求体最大 256 KiB。
- Batch 首版最多 500 条。
- Memory content 最大 2,000 字符。
- Context query 最大 4,000 字符。
- 列表分页默认 50，最大 200。

阶段验收：

- [ ] OpenAPI 可以生成客户端。
- [ ] HTTP E2E 覆盖完整写入、刷新、检索、删除流程。
- [ ] 任意请求都不能跨 tenant 或 namespace 访问数据。

### 阶段 14：实现远程 Python SDK

- [ ] 14.1 实现 Async HTTP Client。
- [ ] 14.2 实现同步 Client。
- [ ] 14.3 实现 timeout 配置。
- [ ] 14.4 实现只对幂等请求自动重试。
- [ ] 14.5 支持调用方传入 request ID 和 idempotency key。
- [ ] 14.6 映射服务端稳定错误为 SDK Exception。
- [ ] 14.7 为每个 HTTP Endpoint 添加 SDK 方法。
- [ ] 14.8 用 OpenAPI 契约测试检查 SDK 请求与响应。
- [ ] 14.9 添加 README 示例。

目标调用方式：

```python
client = PersonalizationClient(
    base_url="http://localhost:8080",
    api_key="...",
    tenant_id="example-app",
)

client.events.ingest_batch(subject_id="user-1", events=events)
context = client.context.resolve(
    subject_id="user-1",
    query="推荐适合今晚看的内容",
    use_case="recommendation",
)
```

阶段验收：

- [ ] SDK 不泄露 HTTP 细节给普通调用方。
- [ ] SDK 与 Embedded Engine 使用同一组公共 DTO。

### 阶段 15：隐私、删除和审计

- [ ] 15.1 实现日志字段脱敏器。
- [ ] 15.2 默认不记录 Memory content、query 和 Evidence excerpt。
- [ ] 15.3 实现审计事件：create/update/delete/search/resolve/export/purge。
- [ ] 15.4 实现 Subject 导出。
- [ ] 15.5 实现 Subject 软删除。
- [ ] 15.6 实现带一次性确认 Token 的 purge。
- [ ] 15.7 purge 删除关系库数据。
- [ ] 15.8 purge 删除向量索引数据。
- [ ] 15.9 purge 后验证无法检索任何 Subject 数据。
- [ ] 15.10 实现 Memory 和 Event 保留期限 Hook。
- [ ] 15.11 编写威胁模型文档。
- [ ] 15.12 编写第三方 Provider 数据出站说明。

阶段验收：

- [ ] 一条命令或 API 可以完整导出用户数据。
- [ ] purge 通过关系库、向量索引和审计豁免规则验证。
- [ ] 日志测试确认没有用户正文和凭据。

### 阶段 16：评测框架

- [ ] 16.1 定义 Memory Extraction Precision/Recall 数据格式。
- [ ] 16.2 定义 Memory Retrieval Recall@K 和 MRR。
- [ ] 16.3 定义 Preference Conflict Accuracy。
- [ ] 16.4 定义 Context Constraint Retention Rate。
- [ ] 16.5 定义 Profile Stability 和 Change Sensitivity。
- [ ] 16.6 创建最小匿名合成数据集。
- [ ] 16.7 创建明确偏好、反转偏好、短期兴趣测试集。
- [ ] 16.8 创建跨租户泄露负向测试集。
- [ ] 16.9 创建 Provider 故障测试集。
- [ ] 16.10 实现评测 CLI。
- [ ] 16.11 输出 JSON 和 Markdown 报告。
- [ ] 16.12 将确定性评测加入 CI。
- [ ] 16.13 将需要外部模型的评测放入手动或定时 CI。

`0.1.0` 最低指标：

- 结构化作用域过滤准确率：100%。
- 跨租户泄露：0。
- 显式硬约束保留率：100%。
- Event 幂等重放正确率：100%。
- Profile 确定性测试：100%。
- Memory Extraction Precision：优先高于 Recall，目标 `>= 0.90`。
- Memory Retrieval Recall@5：目标 `>= 0.85`。

### 阶段 17：PostgreSQL 与生产运行

- [ ] 17.1 添加 PostgreSQL Driver extra。
- [ ] 17.2 让 PostgreSQL 通过 Repository 共享契约。
- [ ] 17.3 验证 JSONB 和 UUID 映射。
- [ ] 17.4 验证部分唯一索引。
- [ ] 17.5 添加连接池配置。
- [ ] 17.6 添加事务隔离和并发写测试。
- [ ] 17.7 添加迁移锁策略。
- [ ] 17.8 添加 readiness 数据库探针。
- [ ] 17.9 提供 Dockerfile。
- [ ] 17.10 提供 Docker Compose 示例。
- [ ] 17.11 添加优雅关闭。
- [ ] 17.12 添加基础指标：延迟、错误、处理积压、Provider 调用。

阶段验收：

- [ ] SQLite Embedded 和 PostgreSQL Server 通过同一业务 E2E。
- [ ] 多进程运行不会生成重复 Snapshot 版本或重复 Observation。

### 阶段 18：验证领域抽象

- [ ] 18.1 在独立仓库创建 `personalization-bilibili` Adapter。
- [ ] 18.2 仅通过公共 API/插件协议接入，不导入 Core 内部模块。
- [ ] 18.3 映射 Bilibili Entity、Event 和 Evidence。
- [ ] 18.4 注册 creator、duration、topic、popularity Feature 插件。
- [ ] 18.5 用当前匿名化样本验证画像迁移。
- [ ] 18.6 再创建一个最小非 Bilibili Adapter，例如文章阅读。
- [ ] 18.7 检查第二个 Adapter 是否要求修改 Core 表结构。
- [ ] 18.8 若只需新增插件则通过抽象验收。
- [ ] 18.9 若必须新增领域字段，先尝试移动到 Entity/Event JSON 属性。
- [ ] 18.10 只有两个以上领域都需要时，才提升为 Core 公共字段。

阶段验收：

- [ ] Bilibili 和第二领域同时运行且互不污染。
- [ ] Core 不包含任何平台专有字段或平台 API 依赖。

### 阶段 19：发布 0.1.0

- [ ] 19.1 冻结公共 DTO 和 Plugin Protocol。
- [ ] 19.2 检查 OpenAPI breaking changes。
- [ ] 19.3 完成架构、数据模型、API、插件和隐私文档。
- [ ] 19.4 完成 Embedded、Server、SDK 三条 quickstart。
- [ ] 19.5 生成 migration compatibility 报告。
- [ ] 19.6 运行完整测试矩阵。
- [ ] 19.7 构建 wheel 和 source distribution。
- [ ] 19.8 在干净环境安装产物并运行 quickstart。
- [ ] 19.9 创建 changelog。
- [ ] 19.10 标记 `v0.1.0`。

## 12. Core MVP 完成定义

只有同时满足以下条件，Core MVP 才算完成：

- [ ] 任意领域可以写入标准 Entity 和 Event。
- [ ] Event 写入幂等且可审计。
- [ ] 用户可以添加、修改、确认、删除和检索 Memory。
- [ ] 插件可以从 Event 生成 Feature Observation。
- [ ] 系统可以生成独立的长期和短期 Feature State。
- [ ] Profile 可以晚期融合 explicit Memory 与 behavior Feature。
- [ ] 冲突不会被静默平均或覆盖。
- [ ] Context Resolver 能按任务返回有限且相关的上下文。
- [ ] 所有结果能够追溯到 Evidence。
- [ ] SQLite Embedded 模式可用。
- [ ] PostgreSQL HTTP Server 模式可用。
- [ ] Python SDK 可用。
- [ ] 用户数据可导出、软删除和彻底删除。
- [ ] 跨租户隔离测试通过。
- [ ] Bilibili 和至少一个非 Bilibili Adapter 验证通过。

## 13. 推迟到 0.2.0 之后

- 图记忆和时态知识图谱。
- 分布式后台任务队列。
- 多语言全文索引优化。
- 自动学习行为权重。
- Recommendation Candidate Generation。
- 多目标 Ranking。
- 在线实验和 A/B Test。
- Web 管理界面。
- 跨设备 Identity Resolution。
- 联邦学习或跨租户特征共享。
- 自动迁移 Mem0/Letta 数据。

## 14. 开工前最后检查

- [ ] 确认新仓库名称和 Python 包名。
- [ ] 确认许可证。
- [ ] 确认第一版只支持单节点部署。
- [ ] 确认 Embedded 和 Server 共享相同 Application Service。
- [ ] 确认 Bilibili Adapter 不在 Core 仓库内实现。
- [ ] 确认 Event、Memory、Feature、Profile 的边界不再变更。
- [ ] 确认先完成阶段 0～5，再开始写数据库实现。
