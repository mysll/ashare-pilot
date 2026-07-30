# A-Share Pilot 当前架构

- 文档性质：当前实现快照
- 基准日期：2026-07-29
- 基准版本：`ashare-pilot 1.0.0`
- 适用范围：仓库根目录、`src/ashare_pilot/`、`.agents/skills/`、
  `.opencode/`、`config/`、运行产物和 memory

本目录描述仓库当前已经落地的架构。它回答“系统现在如何工作”，不把历史
提案、实施计划或兼容期设计当作现状。架构变更时，应先修改实现和合同，再同步
本目录中受影响的文档。

## 阅读导航

| 文档 | 主题 | 建议读者 |
|---|---|---|
| [系统总览](01-system-overview.md) | 目标、分层、边界、主数据流和安全约束 | 所有人 |
| [Python 核心与 CLI](02-runtime-core-and-cli.md) | 工作区、包结构、公共 API、命令树和错误边界 | 开发者、Agent 维护者 |
| [Agent 与 Skill 编排](03-agent-and-skill-orchestration.md) | 角色、所有权、编排协议和 LLM/Compute 边界 | Agent/Skill 维护者 |
| [日线盘前流水线](04-daily-pipeline.md) | 新闻、主题、个股映射、策略 V5 全流程 | 日线工作流维护者 |
| [14:30 隔夜流水线](05-intraday-overnight-pipeline.md) | Compute、双池、感知、推理和发布 | 盘中工作流维护者 |
| [开盘操作确认](06-operation-guide.md) | 09:35/09:40 状态机、快照链和 A/B/C/D | 操作指南维护者 |
| [数据与主题平台](07-data-and-theme-platform.md) | 行情源、缓存、指标、交易范围和主题库 | 数据模块维护者 |
| [合同与存储](08-contracts-and-storage.md) | schema 目录、正式/临时产物、原子性和 lineage | 上下游集成者 |
| [自动化、复盘与记忆](09-automation-review-and-memory.md) | 调度、交易日、复盘、规则治理和 memory | 运维、复盘维护者 |
| [测试与演进](10-testing-and-evolution.md) | 测试分层、验证命令、变更顺序和文档维护 | 贡献者 |

## 与其他文档的关系

- 本目录是当前架构入口。
- `docs/adr/` 解释重要决策的背景与权衡。
- `docs/*-plan.md`、`docs/*-development.md` 是实施过程或未来计划。
- `.agents/skills/*/SKILL.md` 是工作流运行时的权威操作指令。
- `src/ashare_pilot/` 与 `config/` 是确定性行为的最终事实来源。

发现冲突时，以当前代码、配置和 Skill 合同为准，并修正本目录。
