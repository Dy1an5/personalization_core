# Personalization Core

> 工作名：`personalization-core`  
> Python 包名：`personalization_core`  
> 目标版本：`0.1.0`

面向任意领域应用的用户个性化核心。它接收已经标准化的用户行为事件与明确记忆，
生成可审计、可重建的行为特征和个性化上下文，并同时提供 Embedded Python SDK 与
HTTP API 两种运行形态。

Core 是领域无关的基础设施：任何平台专有概念都由外部 Domain Adapter 负责翻译，
Core 本身不感知它们。

## 定位

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

## Core 负责

- 接收任意领域已经标准化的用户行为事件。
- 保存、更新、检索用户明确记忆和推断记忆。
- 从事件生成带证据的行为特征观察值。
- 聚合长期兴趣和短期兴趣。
- 合并明确偏好、行为画像、当前任务，输出个性化上下文。
- 保存可审计、可比较的画像快照。
- 提供 Embedded Python SDK 和 HTTP API。
- 提供租户、命名空间和用户级数据隔离。
- 提供软删除、彻底删除、过期和审计能力。

## 非目标（Core 不负责）

- 不直接调用 Bilibili、YouTube、GitHub 等业务 API。
- 不解析任何特定平台的原始响应。
- 不实现平台登录、Cookie、OAuth 或业务写操作。
- 不在 `0.1.0` 实现协同过滤、两塔召回或强化学习推荐。
- 不在 `0.1.0` 引入图数据库。
- 不要求使用向量数据库才能运行；纯结构化模式必须可用。
- 不把完整对话历史无条件注入模型上下文。
- 不让 LLM 直接决定最终偏好分数或覆盖明确约束。

## 核心设计原则

- Core 中禁止出现 `bvid`、`cid`、UP 主、收藏夹等 Bilibili 专有概念。
- Core 不直接依赖某个 LLM、Embedding、向量库或 Web 框架的具体实现。
- 行为推断不得覆盖用户明确表达；冲突必须被保留并返回。
- 原始事件是事实来源；Memory、Feature State、Profile Snapshot 都是可重建数据。
- 每个派生结果必须保存算法版本和证据引用。
- 所有时间在内部使用带时区 UTC `datetime`；API 使用 RFC 3339。
- 所有模型输出均视为不可信输入，必须经过结构校验和业务校验。

## 技术栈

- Python `>=3.11`，`uv` + `hatchling` 构建。
- Pydantic v2 数据契约，SQLAlchemy 2.x ORM，Alembic 迁移。
- Embedded 默认 SQLite，Server 推荐 PostgreSQL。
- HTTP 使用 FastAPI，仅由 `api` 层依赖。
- 测试：pytest / pytest-asyncio / Hypothesis；类型检查 pyright；格式与静态检查 ruff。

## 状态

项目处于早期实施阶段，尚未发布。完整实施蓝图见 `plan.md`。

## 开发

```bash
uv run ruff format .
uv run ruff check . --fix
uv run pytest
```
