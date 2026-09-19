# 阶段 19：发布 0.1.0 实施文档

## 目标

把当前阶段 18 已验证的 Core 发布为 `0.1.0`，冻结可供独立 adapter 使用的公共
契约，补齐架构/数据模型/API/插件/隐私文档和三条 quickstart，并留下可重复执行的
OpenAPI、迁移兼容性、测试和打包验收证据。

本阶段不增加领域字段、不修改既有迁移、不改变应用服务语义；发布材料和验收测试
必须能够在干净环境重跑。

## 设计与文件职责

### 1. 公共契约冻结

- `src/personalization_core/public.py` 继续作为外部 adapter 的唯一稳定入口，补充
  `PUBLIC_API_VERSION` 和明确的导出快照；公共 DTO、`FeatureExtractor`、
  `FeatureAggregator` 和 registry 的名称、字段、方法签名作为 `0.1.0` 契约。
- `tests/contract/test_public_api_freeze.py` 固定 `public.__all__`、版本和插件协议
  签名，防止未记录的 breaking change。
- 领域内部模块不作为发布契约；文档和 quickstart 只引用 `personalization_core.public`
  或正式 SDK 入口。

### 2. HTTP 契约基线

- `docs/openapi-0.1.0.json` 保存 `create_app(...).openapi()` 的规范化 JSON。
- `tests/contract/test_openapi_compatibility.py` 生成当前规范并与基线比较；允许新增
  非破坏性 operation/schema，但删除 operation、改变方法/参数位置、请求必填字段、
  响应状态或响应 schema 时失败并要求更新发布说明。
- `docs/api.md` 说明 endpoint、认证、作用域 header、错误格式、幂等和删除语义。

### 3. 发布文档

新增或更新以下文档，内容以当前代码和 `plan.md` 为准：

- `docs/architecture.md`：依赖方向、运行形态、数据流和端口边界。
- `docs/data-model.md`：Subject/Entity/Event/Evidence/Memory/Feature/Profile/Context
  字段、作用域、可变性和重建规则。
- `docs/plugin-development.md`：稳定 public 导入、extractor/aggregator 协议、注册
  方式、版本化和错误约束。
- `docs/privacy.md`：补齐导出、软删除、purge、审计、日志和 provider 最小出境规则。
- `docs/embedded-quickstart.md`：示例改用稳定 public/SDK 导入。
- `docs/server-quickstart.md`：启动内置 FastAPI server、配置 token、curl 写入和读取。
- `docs/sdk-quickstart.md`：远程 async/sync SDK、base URL、headers、异常和重试边界。

### 4. 数据库与质量证据

- `docs/migration-compatibility-0.1.0.md` 记录 Alembic chain、当前 head、表/索引/约束
  清单、SQLite/PostgreSQL 类型策略和升级/回滚结论。
- `tests/contract/test_migration_compatibility.py` 校验迁移链连续、当前 head 与报告
  一致、历史迁移文件不被修改、ORM 表名与迁移表名一致。
- `Makefile` 增加 `test-matrix`、`build`、`release-check` 等可重复命令；已有 `check`
  语义保持兼容。

### 5. 打包、干净安装和变更记录

- `scripts/release_smoke.py` 只依赖已安装包，执行 Embedded quickstart 最小流程并
  验证事件幂等；脚本失败返回非零退出码。
- `CHANGELOG.md` 记录 `0.1.0` 的 Added/Changed/Privacy/Compatibility 和未包含范围。
- `tests/e2e/test_release_smoke.py` 或等价测试覆盖已安装发布包可导入、quickstart
  所需公开符号和最小 Embedded 流程。
- 构建 `dist/*.whl` 与 `dist/*.tar.gz`；在新的临时 virtualenv 中安装 wheel，运行
  release smoke 和 quickstart。版本号、wheel metadata、source distribution 名称必须
  为 `0.1.0`。
- 最终验收创建轻量 tag `v0.1.0`；若 tag 已存在但指向不同提交则失败，不覆盖已有 tag。

## 执行顺序

1. 生成公共契约/OpenAPI 基线和迁移兼容性报告。
2. 完成五类设计文档与三条 quickstart。
3. 添加冻结契约、OpenAPI、迁移和发布 smoke 测试及 Makefile 命令。
4. 运行 `ruff format --check`、`ruff check`、`pyright`、unit/contract/integration/e2e
   测试；需要外部服务的 PostgreSQL 与 external 标记单独记录结果。
5. 构建 wheel/source distribution，在临时环境安装并运行 smoke。
6. 更新 `plan.md` 的 19.1--19.10 和阶段验收复选框，写入最终测试矩阵和产物摘要，
   创建 `v0.1.0` tag。

## 错误和兼容性规则

- 发现公共 DTO、插件协议或 OpenAPI breaking change 时不得静默改变；必须停止发布
  并在 `CHANGELOG.md` 记录，或回到兼容实现。
- 迁移只允许向前新增；本阶段不得改写 `0001_initial.py` 或 `0002_privacy_audit.py`。
- 干净安装不能依赖源码目录、未声明的 dev dependency、工作区环境变量或本地路径。
- PostgreSQL 未配置时只报告环境未启用，不伪造通过；SQLite、API 契约和核心测试必须
  实际运行。

## 验收产物

完成后应存在：阶段文档、五类产品文档、三条 quickstart、OpenAPI 基线、迁移兼容性
报告、发布 smoke/契约测试、`CHANGELOG.md`、`dist` 中两种分发包，以及指向发布提交
的 `v0.1.0` tag。
