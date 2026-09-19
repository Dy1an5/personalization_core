# 阶段 16：评测框架实现设计

## 目标

为 Core 建立可离线、可复现、可审计的确定性评测框架，覆盖记忆抽取、记忆检索、偏好冲突、上下文硬约束、画像变化，以及跨租户隔离和 Provider 故障映射。评测输入使用匿名 JSON 数据，不把用户正文、凭据或外部 Provider 请求带入仓库。

## 文件责任

- `src/personalization_core/evaluation/models.py`：评测数据集、测试样例、指标结果和报告的数据契约。所有外部 JSON 先经 Pydantic 校验。
- `src/personalization_core/evaluation/metrics.py`：纯函数指标实现，不访问数据库、网络或具体 Provider。
- `src/personalization_core/evaluation/runner.py`：加载数据集并按固定顺序运行确定性评测。
- `src/personalization_core/evaluation/report.py`：输出稳定排序的 JSON 和 Markdown 报告。
- `src/personalization_core/evaluation/cli.py`：`personalization-core-eval` 命令行入口，支持默认匿名数据集和自定义数据集目录。
- `src/personalization_core/evaluation/datasets/minimal.json`：最小匿名合成数据集，包含明确偏好、反转偏好、短期兴趣、跨租户负向和 Provider 故障样例。
- `tests/evaluation/`：数据契约、指标边界、数据集运行、报告和 CLI 回归测试。
- `.github/workflows/evaluation-external.yml`：手动/定时触发的外部模型评测占位工作流；默认确定性 CI 不访问网络。

## 数据契约

`EvaluationDataset` 包含以下样例集合：

1. `memory_extraction`：`expected_keys` 和 `predicted_keys`，按集合计算 precision/recall；同一 case 内重复 key 只保留一个，空集合场景按契约拒绝。
2. `memory_retrieval`：`relevant_ids`、`ranked_ids`、`k`，计算逐 case Recall@K 和 MRR，再取算术平均。
3. `preference_conflicts`：预期与观测的 `ResolutionType`，计算精确匹配率。
4. `constraint_retention`：`constraint_ids` 与 Bundle 返回的 `retained_ids`，计算硬约束保留率；不允许把不存在于输入的约束计为保留。
5. `profiles`：前后画像的匿名 preference 状态；稳定性只在声明无变化的样例上计算，为 unchanged coordinates / union coordinates；变化敏感度为 expected changed coordinates 中实际变化的比例。
6. `tenant_isolation`：允许返回的 ID 与实际返回的 ID，跨作用域返回项数必须为 0。
7. `provider_failures`：预期 Provider 错误码与适配器观测错误码，检查稳定错误映射。

每个指标结果统一包含 `name`、`value`、`numerator`、`denominator`、`target`、`passed`。分母为零的非法/未定义数据由模型校验拒绝；不静默生成通过结果。

## 指标与最低门槛

- Memory Extraction Precision：`>= 0.90`；Recall 同时输出但不以 Recall 单独替代 Precision 门槛。
- Memory Retrieval Recall@5：`>= 0.85`；同时输出 MRR。
- Preference Conflict Accuracy：`1.0`。
- Context Constraint Retention Rate：`1.0`。
- Profile Stability 和 Change Sensitivity：输出 `[0, 1]` 值，默认目标 `1.0`，用于确定性回归比较。
- Tenant Isolation：泄露率 `0.0`，等价于跨租户泄露为 0。
- Provider Failure Mapping：所有样例映射正确。

## 执行与输出

`run_evaluation(dataset)` 只执行内存中的纯计算，固定指标顺序并返回 `EvaluationReport`。`render_json` 使用 Pydantic JSON 序列化；`render_markdown` 使用固定列顺序和稳定的小数格式。CLI：

```text
personalization-core-eval [--dataset path/to/minimal.json]
                         [--json-out report.json]
                         [--markdown-out report.md]
```

无输出路径时 JSON 写 stdout；指定路径时创建父目录并写文件。数据格式错误返回非零退出码；有指标未达门槛时仍输出完整报告并返回 1。

## 测试与 CI

- 单元测试覆盖集合为空/重复、Recall@K、MRR 首次命中、冲突匹配、硬约束额外返回、画像新增/反转、跨租户泄露和 Provider 错误映射。
- 确定性测试加载仓库内最小匿名数据集，要求 extraction precision、retrieval Recall@5、硬约束保留率、租户隔离和 Provider 映射通过，并将 CLI JSON/Markdown 输出纳入回归。
- 常规 `.github/workflows/ci.yml` 通过 `pytest -m unit` 执行离线评测。
- 外部模型评测不进入默认 CI；`.github/workflows/evaluation-external.yml` 只在 schedule 或 `workflow_dispatch` 下运行，并由环境变量显式开启。

## 验收顺序

1. 先校验数据契约和匿名数据集。
2. 再验证纯函数指标与报告稳定性。
3. 运行 CLI，确认 JSON/Markdown 均可生成。
4. 运行 `pytest -m unit`、ruff、pyright。
5. 确认默认 CI 不需要网络或外部模型，最后更新阶段状态。
