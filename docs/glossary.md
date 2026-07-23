# A-Share Pilot 术语表

- 版本：1.1
- 日期：2026-07-21
- 范围：自动调度、交易日期语义与 Agent 无关架构
- 关联：[ADR-0001](adr/0001-multi-task-trading-day-scheduler.md)、[ADR-0002](adr/0002-agent-neutral-core-library.md)

| 术语 | 定义 |
|------|------|
| `T0` | 任务计划触发日；该日期必须是交易日。早盘分析、尾盘分析和当日复盘使用此日期。 |
| `TP1` | Trading Previous 1；`T0` 之前最近一个交易日。隔夜策略复盘使用此日期定位上一交易日策略。不要将其理解为自然日昨天。 |
| `T+1` | 策略日之后的首个交易日。它表示未来方向，与 `TP1` 相反。 |
| 交易日 | `trading-calendar.json` 已知年份内，非周末且不在交易所休市区间的日期。 |
| 计划时点 | 任务配置的 `time`，采用交易日历声明的 `Asia/Shanghai` 时区，格式为 `HH:MM`。 |
| 到期排队 | daemon 持续运行期间，任务到点但执行器忙碌；任务在前一任务结束后立即串行执行。 |
| 漏跑 | 计划时点发生时 daemon 未运行。漏跑任务不会在下次启动时自动执行。 |
| 任务失败 | 子进程非零退出、超时或启动异常。失败不自动重试，也不阻断其他已配置任务。 |
| 调度事件日志 | `.opencode/logs/cron-daemon.log` 中的启动、下一任务、开始、完成、失败和退出记录。 |
| 任务输出日志 | `.opencode/logs/cron-tasks/{YYYY-MM-DD}/{task-id}.log` 中单个 OpenCode 任务的 stdout/stderr。 |
| Python 核心工程 | 位于仓库根级、按业务功能组织且不依赖具体 Agent 或 Skill 目录的公共 Python 实现；它不接管 Skill 中由 Agent 执行的语义编排。 |
| A-Share Pilot | 项目产品名；表示 A 股 Agent 决策领航系统，不表示无人值守自动交易。发行包和 CLI 为 `ashare-pilot`，Python 命名空间为 `ashare_pilot`。 |
| Agent 适配器 | 某种 Agent 使用的 Skill、指令或工具声明；它描述功能流并调用 Python 核心工程，不保存重复的 Python 实现。 |
| 薄适配器 | 只负责向特定 Agent 暴露功能流和公共入口的适配层；它不重新实现 Python 业务能力。 |
| 公共接口 | 核心库承诺给 CLI、Agent 适配器或其他调用者使用，并受兼容策略约束的 Python API、CLI 或数据合同。 |
| 旁路建设 | 在不修改现有生产入口的前提下新增核心工程；旧链路继续运行，新链路独立开发和验证。 |
| 切换阶段 | 新核心工程通过验收后，修改 Skill 调用、停止旧入口并清理重复实现的独立迁移阶段。 |
