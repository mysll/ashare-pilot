# 测试与架构演进

## 1. 测试分层

根级测试按目的组织：

| 目录 | 目的 |
|---|---|
| `tests/unit/` | 领域函数、schema、不变量、workspace、状态机 |
| `tests/cli/` | 命令树、参数、帮助和失败退出 |
| `tests/equivalence/` | 新核心与迁移基线的行为等价 |
| `tests/integration/` | 少量显式 live 集成验证 |
| `tests/fixtures/` | 脱敏冻结输入、期望输出和 manifest |
| `tests/tools/` | 冻结回放辅助工具 |

默认测试不应依赖实时网络。Live 测试必须显式运行，并不得作为离线合同测试的替代。

## 2. 关键测试面

- workspace 解析和路径隔离；
- 数据源 fallback、缓存迁移和分页完整性；
- 日线 Theme/Mapper/Strategy exact coverage；
- intraday scoreability、executability、双池互斥；
- mapper/strategy schema v3；
- 操作状态迁移、bar 完整性和 hash lineage；
- scheduler 交易日、串行、失败和日期策略；
- memory 初始化幂等及规则治理增长。

## 3. 常用验证

```bash
uv lock --check
uv run --frozen ashare-pilot --version
uv run --frozen pytest -q
uv run --frozen ashare-pilot automation rules check
uv run --frozen ashare-pilot automation scheduler run --dry-run
```

业务合同可按模块单独验证：

```bash
uv run --frozen ashare-pilot strategy daily validate predict/DATE/strategy.json
uv run --frozen ashare-pilot mapping intraday validate-mapper --date DATE
uv run --frozen ashare-pilot strategy overnight validate --date DATE
uv run --frozen ashare-pilot operations snapshot validate operation/DATE/operation_snapshot.latest.json
uv run --frozen ashare-pilot operations decision validate operation/DATE/operation_decision.latest.json
```

## 4. 变更顺序

跨模块修改应按依赖方向推进：

1. 明确字段 owner、正式/临时属性和失败语义；
2. 修改配置或确定性核心；
3. 修改 builder 与 validator；
4. 更新公共 API/CLI；
5. 更新 orchestrator/leaf Skill 和 Agent 输入边界；
6. 更新下游 operations/review；
7. 增加 unit、CLI、equivalence fixture；
8. 更新本架构目录和相关 ADR。

不得先改 LLM prompt 再让 Python 猜测新合同。

## 5. Schema 演进

发生以下变化时应升级 schema：

- 字段语义改变；
- required/coverage 规则改变；
- 池成员含义改变；
- 下游无法安全区分新旧行为。

只增加观测字段且下游明确忽略时，是否升级由所属合同决定。当前生产合同原则上
fail closed，不提供未经声明的旧版自动转换。

## 6. 架构决策

改变以下稳定边界时应新增或修订 ADR：

- Agent 与 Python 的所有权；
- 正式合同或存储权威；
- 交易范围、双池或主题成员模型；
- 调度并发/漏跑语义；
- memory 和规则生命周期；
- 自动执行或账户层边界。

实施计划描述“怎么做”，ADR 描述“为什么这样决定”，本目录描述“现在是什么”。

## 7. 文档维护检查表

每次架构变更后检查：

- `docs/architecture/README.md` 导航是否仍完整；
- 总览依赖方向是否改变；
- 命令树和公共 API 是否新增；
- pipeline 输入输出和 owner 是否改变；
- `08-contracts-and-storage.md` schema 版本是否同步；
- 调度时间、memory 写路径和失败行为是否改变；
- 历史计划文档是否应标记为 superseded，而非删除审计记录。
