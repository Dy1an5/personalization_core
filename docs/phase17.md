# 阶段 17：PostgreSQL 与生产运行实现设计

## 目标与边界

在不改变 domain、Repository 和 Application Service 公共契约的前提下，增加 PostgreSQL Server 运行路径，并保持 SQLite Embedded 行为一致。生产路径只增加基础设施和运维能力：连接池、迁移锁、readiness、容器、优雅关闭和内存指标；不引入新的业务字段或平台专有概念。

## 文件责任

- `pyproject.toml`：提供 `postgres` optional extra，使用 `asyncpg`；默认 Embedded 安装不拉取 PostgreSQL 驱动。
- `src/personalization_core/infrastructure/persistence/database.py`：增加 `DatabaseSettings`、通用 async URL 工厂、PostgreSQL engine 工厂、连接探针；保留 SQLite WAL/foreign-key 配置。
- `migrations/env.py`：从 `DATABASE_URL` 覆盖迁移 URL，并在 PostgreSQL 在线迁移期间持有 advisory lock；SQLite 使用现有事务路径。
- `src/personalization_core/api/routers/health.py`：readiness 检查 engine 状态和 `SELECT 1`，失败返回 503，live 不访问数据库。
- `src/personalization_core/api/app.py`：lifespan 关闭设置超时且幂等，保证连接池在 shutdown 时释放。
- `src/personalization_core/infrastructure/observability/metrics.py`：无第三方依赖的 counters、gauges、latency observations 和 provider-call counters；输出只包含聚合数值。
- `src/personalization_core/api/app.py`：记录 HTTP 请求数、错误数和延迟到 registry；runtime 暴露 metrics 读取对象。
- `Dockerfile`、`docker-compose.yml`：安装 `.[postgres]`，启动时运行 Alembic，再启动 API；PostgreSQL 提供 healthcheck。
- `.github/workflows/ci.yml`：保留离线 unit job，增加 PostgreSQL service/integration job，只有数据库可用时执行真实 round-trip。
- `tests/integration/postgres/`：复用 SQLite Repository contract/E2E fixture；缺少 `POSTGRES_TEST_URL` 时 skip，禁止把 skip 当作通过。

## 数据库契约

现有 `UUIDType`、`JSONType` 和 `UTCDateTime` 继续作为唯一映射入口：PostgreSQL 使用 UUID/JSONB/timestamptz，SQLite 使用 TEXT/序列化 TEXT/UTC-naive 存储并在模型边界恢复为 UTC。所有 Repository 继续实现 `ports/repositories.py`，PostgreSQL 不增加平行 Repository。

`DatabaseSettings` 字段：`url`、`pool_size`、`max_overflow`、`pool_timeout`、`pool_recycle`、`pool_pre_ping`、`connect_timeout`、`echo`。SQLite 忽略池参数但保留现有 PRAGMA；PostgreSQL 默认启用 `pool_pre_ping` 和连接回收，避免失效连接长期占用。

现有 active Memory partial unique index 和所有唯一约束在两种方言中都必须存在。并发行为依赖数据库约束而非应用内存锁：重复 Event/Observation 只能落一行；Snapshot 版本冲突回滚后由调用方重试整个生成事务，不能在失败事务上继续使用 Session。

## 迁移与锁

在线 PostgreSQL migration 在执行 Alembic upgrade 前调用固定 key 的 `pg_advisory_lock`，完成后在 `finally` 中 unlock；锁只保护迁移过程，不持有业务请求事务。`DATABASE_URL` 优先于 `alembic.ini`，脱敏后的 URL 不写日志。SQLite 不执行 PostgreSQL 函数。

## Readiness 与关闭

- `/v1/health/live` 只表示进程存活。
- `/v1/health/ready` 要求应用未关闭且数据库连接可建立并执行 `SELECT 1`；连接失败、engine 已关闭或探针异常统一返回 503，响应不暴露 DSN/凭据。
- FastAPI lifespan 初始化失败时不启动服务；正常关闭使用有限 timeout 调用 `engine.close()`，重复关闭安全。

## 指标

`MetricsRegistry` 提供线程安全/事件循环安全的聚合快照：

- `http_requests_total{method,path,status}`、`http_errors_total{path,status}`；
- `http_request_latency_ms{path}` 的 count/sum/max；
- `processing_backlog` gauge；
- `provider_calls_total{provider,operation,status}`。

标签经过白名单/长度限制，不记录 tenant、subject、query、content、token 或 DSN。Provider 和后台处理适配器通过 registry 的公共方法记录调用/积压，不让指标模块依赖具体 Provider。

## 容器运行

Compose 使用 `POSTGRES_DB/USER/PASSWORD` 和 `DATABASE_URL`，API 启动命令先执行 `alembic upgrade head` 再启动 Uvicorn；API healthcheck 调用 `/v1/health/ready`。Dockerfile 不包含开发缓存和测试数据。

## 测试与验收

1. 纯单元：DatabaseSettings、SQLite/PG URL、metrics 标签脱敏、readiness 分支、关闭幂等、迁移锁方言分支。
2. SQLite 集成：现有 Repository contract、Embedded E2E、唯一约束并发写和 Snapshot/Observation 冲突重试。
3. PostgreSQL 集成：在 `POSTGRES_TEST_URL` 存在时运行同一 contract、JSONB/UUID/UTC round-trip、partial unique index、迁移和 readiness；未配置时明确 skip。
4. 质量门禁：ruff、pyright、`pytest -m unit`；CI PostgreSQL job 运行 integration/e2e。

阶段验收只有在真实 PostgreSQL job 成功时才勾选 SQLite/PostgreSQL E2E 和多进程验收项；本地无数据库时只报告未执行，不虚报通过。
