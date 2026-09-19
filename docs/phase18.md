# 阶段 18：验证领域抽象

## 目标与验收边界

本阶段用两个相互独立的 Python adapter 验证 Core 的领域抽象：

1. `personalization-bilibili` 将匿名化的视频、创作者和观看行为映射为
   Core 的 Entity、Event、Evidence，并注册四类 Feature Extractor：
   `creator`、`duration`、`topic`、`popularity`。
2. `personalization-article` 将文章阅读事件映射为相同的 Core 契约，并注册
   `topic` Extractor，作为最小的非 Bilibili 领域。
3. 两个 adapter 只导入 `personalization_core.public`，不导入 Core 的
   `domain.*`、`application.*`、`infrastructure.*` 或其他内部模块。
4. 两个 adapter 使用不同 namespace 和 dimension/value key 同时运行时，事件、
   observation、state 和画像互不污染。
5. Core 的数据库表、迁移和平台无关模型不增加领域专有字段；平台属性只进入
   adapter 自己的输入模型、Entity `attributes`、Event `properties` 或 Evidence
   `metadata`。

独立仓库在当前单仓库工作区内以 `adapters/<package-name>` 子项目表示。每个子项目
有独立的 `pyproject.toml`、`src` 和 `tests`，生产依赖声明为已发布的
`personalization-core`，测试通过本地 Core 源码运行。这保留了独立包边界，同时让
阶段验收可以在当前仓库一次完成。

## 公共 Core 契约

新增 `src/personalization_core/public.py`，作为 adapter 唯一允许依赖的稳定入口，
导出：

- 标识和通用值：`SubjectRef`、`TenantId`、`Namespace`、`SubjectId`、`EntityRef`、
  `UtcDatetime`、`JsonValue`、`Polarity`、`EvidenceSourceType`。
- 写入 DTO：`EntityCreate`、`EventCreate`、`EvidenceCreate`、
  `EventIngestionInput`。
- Feature DTO：`FeatureObservationDraft`、`FeatureState`。
- 插件协议和注册表：`FeatureExtractor`、`FeatureAggregator`、
  `FeatureExtractorRegistry`。
- Embedded 门面：`PersonalizationEngine` 及其 `EventOperations`、
  `FeatureOperations`、`ProfileOperations`。

`PersonalizationEngine` 增加 `features` 操作组，提供 `process_event`、
`process_pending`、`rebuild_dimension` 和 `list_states`。`from_components`、
`from_sqlite`、`from_database` 和 `from_postgres` 接受可选的
`feature_registry`；缺省使用 Core 内置 aggregators。该改动不改变数据库结构。

## Bilibili adapter 设计

路径：`adapters/personalization-bilibili/`，包名 `personalization_bilibili`。

### 输入模型

- `BilibiliVideo`：`video_id`、`title`、`creator_id`、`duration_seconds`、`topics`、
  `popularity_score`。
- `BilibiliWatchEvent`：`video`、`event_id`、`event_type`、`occurred_at`、
  `watched_seconds`、`polarity`。

输入模型只表达平台输入，不传入 Core。`video_id` 映射为通用 `external_id`；其余
平台数据进入通用 attributes/properties。

### 映射函数

- `to_entity(video, subject) -> EntityCreate`
- `to_event_input(watch, subject) -> EventIngestionInput`

事件类型使用 `bilibili.video.viewed`、`bilibili.video.liked` 和
`bilibili.video.completed`。Evidence 使用 `source_type=import`，source ref 使用
adapter 生成的匿名事件标识，平台原始信息仅放入 metadata。

### Feature Extractor

四个 Extractor 均只读取通用 Core `Event`/`Entity`：

- `CreatorExtractor`：从 `entity.attributes.creator_id` 生成
  `dimension=creator`。
- `DurationExtractor`：从 `duration_seconds` 和 `watched_seconds` 生成短/中/长
  时长值，score 为观看完成度并限制在 `[-1, 1]`。
- `TopicExtractor`：为 `attributes.topics` 的每个主题生成 `dimension=topic`。
- `PopularityExtractor`：从 `attributes.popularity_score` 生成 low/medium/high
  的 `dimension=popularity`。

每个 observation 都包含可重建的 `value`、合法的 score/confidence、事件发生时间，
由 Core 统一补充 event/evidence 引用和 extractor 版本。`register_feature_plugins`
只注册 Extractor；aggregator 由 `FeatureExtractorRegistry.with_builtins()` 提供。

## Article adapter 设计

路径：`adapters/personalization-article/`，包名 `personalization_article`。

- `Article`：`article_id`、`title`、`topics`。
- `ArticleRead`：`article`、`event_id`、`occurred_at`、`progress`。
- `to_entity` 和 `to_event_input` 映射到通用 `article` Entity 与
  `article.read` Event。
- `ArticleTopicExtractor` 只注册 `dimension=article_topic`，使用独立的
  `article:<topic>` value key。

该 adapter 不依赖 Bilibili adapter。使用 `article_topic` 而不是 `topic` 是为了让
阶段验证清晰证明不同领域的 feature state 不发生隐式合并；两者仍然共享同一 Core
表结构和相同插件协议。

## 数据流与错误行为

```text
adapter input
  -> EntityCreate/EventIngestionInput
  -> engine.events.upsert_entity/ingest_event
  -> engine.features.process_event
  -> FeatureObservation/FeatureState
  -> engine.profiles.refresh
```

映射层拒绝空 ID、空 creator、负 duration、超出 `[0, 1]` 的 popularity/progress
以及无时区时间；Core 的 Pydantic DTO 继续负责通用结构校验。事件幂等键由 adapter
生成并保留输入 event ID，重复提交得到 Core 的 replay 结果，内容变化得到幂等冲突。

## 测试与验收

### Adapter 单元/契约测试

- DTO 映射保留 subject scope、UTC、幂等键和 Evidence metadata。
- 四类 Bilibili extractor 的 dimension/value/score/confidence 和空数据行为。
- Article extractor 的输出和 Bilibili extractor 的无交叉导入。
- 源码 AST import allowlist：adapter 只能导入标准库、Pydantic 和
  `personalization_core.public`。

### Core 集成验收

- SQLite Embedded 中同时写入 Bilibili 与 Article 样本，处理 pending events，
  检查 feature states 的 namespace/dimension/value key 隔离。
- 刷新 profile，确认 profile 能引用两类行为且证据链可追溯；重复事件不会产生
  第二份 observation。
- 读取匿名化 JSON fixture，完成 Bilibili Entity/Event/Evidence -> Feature State
  -> Profile 的迁移链路。
- 比较 `migrations/`、SQLAlchemy 表名和列名快照，确认阶段实施不增加或修改
  Core schema。
- 通过 import hook 拒绝 `personalization_core.domain`、`application`、
  `infrastructure` 等内部模块后，adapter 仍可导入并运行。

阶段完成后再更新 `plan.md` 的 18.1--18.10 和阶段验收复选框；若任一测试证明
需要平台专有公共列，先退回 JSON 属性方案。本阶段预期不需要迁移。
