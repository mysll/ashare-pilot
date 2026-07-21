# docs — 项目文档索引

Trading Office 的纪要、设计与决策文档归档处。新增文档时在下表登记一行。

## 纪要 / 设计

| 文档 | 摘要 |
|------|------|
| [入场质量回测纪要](entry-quality-backtest-memo.md) | 早盘策略入场环节的质量回测:要解决的问题、数据口径、如何复跑(`entry_quality_backtest.py`)、首轮结论(MA5/MA20 锚保留、格式已锁、确认闸门待前向数据) |
| [A股早盘推荐与二次确认系统 Spec](morning-recommendation-system-spec.md) | `daily-market-analysis` 与 `intraday-operation-guide` 的职责边界、时序、数据合同、T+1 风控和阶段验收标准。 |
| [A股早盘推荐与二次确认系统开发实施文档](morning-recommendation-system-development.md) | 逐文件开发任务、函数设计、v1→v2 迁移、离线 fixture、测试命令、提交切片与实施顺序。 |
| [A股早盘推荐系统操作手册](morning-recommendation-operation-runbook.md) | 交易日前检查、09:20盘前分析、09:35/09:40二次确认、人工执行纪律、T+1处理与异常降级。 |
| [交易日多任务调度器 ADR](adr/0001-multi-task-trading-day-scheduler.md) | 四任务配置合同、交易日 fail-closed、串行排队、漏跑、失败、CLI 与日志决策。 |
| [术语表](glossary.md) | 自动调度中的 T0、TP1、T+1、交易日、排队和漏跑等统一定义。 |

## 子目录

| 目录 | 内容 |
|------|------|
| [superpowers/](superpowers/) | superpowers 框架文档(bug、plans、specs) |
| [adr/](adr/) | 已接受的架构决策记录。 |

---

## 约定

- 文档用中文,文件名用英文 kebab-case(如 `entry-quality-backtest-memo.md`)。
- 纪要类文档开头写 `版本 / 日期 / 范围 / 关联`,便于追溯。
- 文档引用了脚本或 skill 的具体路径/字段时,**改动源文件后回来同步文档**。
- 新增文档后,在本 README 的表格登记一行。
