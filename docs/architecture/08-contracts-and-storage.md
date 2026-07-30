# 合同与存储

## 1. 合同模型

当前 schema 由各业务模块中的构建器和 validator 定义，`resources/schemas/` 目前
只是保留目录，并没有一套可独立分发的 JSON Schema 文件。因此下表是集成目录，
代码 validator 才是可执行事实来源。

合同分三类：

- 正式合同：下游和复盘可以依赖；
- 临时合同：只服务一次工作流的 LLM/Compute 交接；
- 可读/观测产物：HTML、Markdown 和 timing，不作为机器事实来源。

## 2. 当前 schema 目录

### 2.1 日线

| schema | 文件 | 类别 |
|---|---|---|
| `daily_news.v1` | `news.json` | 正式 |
| `theme_evidence_input.tmp.v2` | `.theme_evidence_input.json` | 临时 |
| `daily_theme_annotations.v1` | `.theme_annotations.json` | 临时 LLM 输出 |
| `daily_themes.v2` | `themes.json` | 正式 |
| `daily_step1_timing.v1` | `step1_timing.json` | 观测 |
| `daily_theme_stocks_universe.v2` | `theme_stocks.universe.json` | 中间 |
| `daily_theme_stocks_base.v2` | `theme_stocks.base.json` | 中间 |
| `daily_theme_stocks.v2` | `theme_stocks.json` | 正式 |
| `mapper_annotation_input.tmp.v1` | `.mapper_annotation_input.json` | 临时 |
| `daily_mapper_annotations.v1` | `mapper.annotations.json` | LLM 合同 |
| `daily_mapper_base.v2` | `mapper.base.json` | 中间 |
| `daily_mapper.v2` | `mapper.json` | 正式 |
| `daily_strategy_input.v2` | `mapper.strategy_view.json` | 正式桥接 |
| `daily_step2_timing.v1` | `step2_timing.json` | 观测 |
| `strategy_llm_input.tmp.v3` | `.strategy_llm_input.json` | 临时 |
| `daily_strategy_draft.tmp.v3` | `strategy.draft.json` | 临时 LLM 输出 |
| `daily_strategy.v3` | `strategy.json` | 正式 |
| `daily_step3_timing.v1` | `step3_timing.json` | 观测 |

### 2.2 盘中隔夜

| schema | 文件 | 类别 |
|---|---|---|
| `intraday_all_stocks_cache.v2` | `all_stocks_cache.json` | cache |
| `intraday_concept_dashboard.v1` | `concept_dashboard.json` | cache |
| `intraday_theme_ranking.v2` | `theme_ranking.json` | cache |
| `intraday_selection_pools.v1` | `selection_pools.json` | 正式候选桥接 |
| `intraday_mapper_base.v2` | `intraday_mapper.base.json` | 中间 |
| `intraday_mapper_annotations.v3` | `intraday_mapper.annotations.json` | LLM 合同 |
| `intraday_mapper.v3` | `intraday_mapper.json` | 正式 |
| `intraday_overnight_strategy.v3` | `overnight_strategy.json` | 正式 |

### 2.3 操作、复盘和自动化

| schema | 文件 | 类别 |
|---|---|---|
| `intraday_operation_snapshot.v3` | `operation_snapshot_*.json` | immutable 正式 |
| `intraday_operation_decision.v2` | `operation_decision_*.json` | immutable 正式 |
| `intraday_operation_run_state.v1` | `operation_run_state.json` | 生命周期状态 |
| `intraday_operation_run_manifest.v1` | `operation_run_*.json` | 原子 manifest |
| `daily_verification.v1` | `memory/daily/{date}/verification.json` | 正式复盘数据 |
| `cron_tasks.v1` | `config/cron-tasks.json` | 配置合同 |

## 3. 存储布局

```text
predict/{date}/        日线步骤和正式策略
intraday/{date}/       mapper、隔夜策略和 HTML
operation/{date}/      操作链 immutable 文件与 latest 投影
.cache/intraday/{date}/同一时点的盘中 Compute
memory/daily/{date}/   日线机器验证和人类复盘
memory/intraday/{date}/隔夜人类复盘
data/theme-library/    跨日持久主题知识
logs/                  调度和任务日志
```

日期目录使用策略日期，不使用复盘实际运行日期替代策略日期。

## 4. 正式与非正式产物

- JSON 正式合同可供下游机器读取；
- HTML 必须由已验证 JSON 渲染，不能反向作为事实源；
- Markdown 复盘服务审计和知识积累，不作为策略阶段输入合同；
- dotfile、draft、base 和 timing 不应被外部消费者当作稳定 API；
- cache 可以重建，但同一工作流必须维持 snapshot 一致性。

## 5. Lineage、hash 与原子性

日线 Step 3 使用输入 SHA-256 防止旧 draft 对新输入发布。操作指南进一步把
predecessor、source snapshot 和最终 HTML 都纳入 hash 链，并以 run manifest
作为跨文件权威。

普通 `latest` 投影方便人类和工具发现最新文件，但不能替代 immutable 文件和
manifest。任何需要跨文件一致性的消费者都应先读取 manifest，再核对 hash。

## 6. 兼容策略

当前主流程采用严格 schema 版本，不维护旧版本的静默兼容读取。历史旧产物可用于
fixture 或审计，但不能直接进入当前生产流水线。升级 schema 时应同步：

1. 构建器；
2. validator；
3. Skill 输入输出；
4. 下游消费者和 review；
5. fixture、单元和等价性测试；
6. 本目录合同表。
