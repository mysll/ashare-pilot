# docs — 项目文档索引

A-Share Pilot 项目的纪要、设计与决策文档归档处。
新增文档时在下表登记一行。

## 纪要 / 设计

| 文档 | 摘要 |
|------|------|
| [入场质量回测纪要](entry-quality-backtest-memo.md) | 早盘策略入场环节的质量回测:要解决的问题、数据口径、如何复跑(`entry_quality_backtest.py`)、首轮结论(MA5/MA20 锚保留、格式已锁、确认闸门待前向数据) |
| [A股早盘推荐与二次确认系统 Spec](morning-recommendation-system-spec.md) | `daily-market-analysis` 与 `intraday-operation-guide` 的职责边界、时序、数据合同、T+1 风控和阶段验收标准。 |
| [A股早盘推荐与二次确认系统开发实施文档](morning-recommendation-system-development.md) | 逐文件开发任务、函数设计、v1→v2 迁移、离线 fixture、测试命令、提交切片与实施顺序。 |
| [A股早盘推荐系统操作手册](morning-recommendation-operation-runbook.md) | 交易日前检查、09:20盘前分析、09:35/09:40二次确认、人工执行纪律、T+1处理与异常降级。 |
| [交易日多任务调度器 ADR](adr/0001-multi-task-trading-day-scheduler.md) | 四任务配置合同、交易日 fail-closed、串行排队、漏跑、失败、CLI 与日志决策。 |
| [Agent 无关 Python 核心工程 ADR](adr/0002-agent-neutral-core-library.md) | A-Share Pilot 的包边界、CLI、旁路迁移、严格等价、配置数据和切换策略。 |
| [盘中主题证据链 ADR](adr/0003-intraday-theme-evidence-contract.md) | 概念成员分页、core/qualified/edge、双领涨、双热度、主题时点与 mapper 确定性主题合同。 |
| [盘中主题证据链实施清单](intraday-theme-evidence-implementation.md) | ADR-0003 的逐阶段代码任务、测试范围、全量重建和验收步骤。 |
| [主题成分抓取排除清单](theme-member-fetch-exclusions.md) | 主题成员抓取排除项、审计依据、盘中 Dashboard 边界、延期项和后续复审流程。 |
| [东方财富概念板块接口样本](api.md) | 网页双接口请求/响应样本、生产字段边界、分页 checkpoint 和双源一致性验证。 |
| [Python 核心工程实施计划](core-refactor-plan.md) | 已完成的七批旁路建设、验收门槛和第二阶段统一 CLI 切换。 |
| [Python 核心工程迁移映射](core-refactor-migration-map.md) | 旧 Python 入口到 `ashare-pilot` 新功能模块和 CLI 的完整映射。 |
| [Python 核心工程最终验收矩阵](core-refactor-acceptance-matrix.md) | 68 个旧入口的正常、边界、失败、统一 CLI 和公共 API 验收状态。 |
| [术语表](glossary.md) | 自动调度中的 T0、TP1、T+1、交易日、排队和漏跑等统一定义。 |

## 子目录

| 目录 | 内容 |
|------|------|
| [superpowers/](superpowers/) | superpowers 框架文档(bug、plans、specs) |
| [adr/](adr/) | 架构决策记录。 |

---

## 约定

- 文档用中文,文件名用英文 kebab-case(如 `entry-quality-backtest-memo.md`)。
- 纪要类文档开头写 `版本 / 日期 / 范围 / 关联`,便于追溯。
- 文档引用了脚本或 skill 的具体路径/字段时,**改动源文件后回来同步文档**。
- 新增文档后,在本 README 的表格登记一行。
