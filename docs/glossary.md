# A-Share Pilot 术语表

- 版本：1.2
- 日期：2026-07-23
- 范围：自动调度、交易日期语义、Agent 无关架构与盘中主题证据链
- 关联：[ADR-0001](adr/0001-multi-task-trading-day-scheduler.md)、[ADR-0002](adr/0002-agent-neutral-core-library.md)、[ADR-0003](adr/0003-intraday-theme-evidence-contract.md)

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
| 概念（Concept） | 东方财富维护的股票板块及其原始成员集合，例如“算力概念”“PCB”。概念成员关系是主题库的外部数据源。 |
| 主题（Theme） | 项目在多个概念之上定义的投资语义聚合，例如“AI算力”“PCB/被动元件”。一个主题包含一个或多个概念。 |
| 主题成员关系（Theme Membership） | 从“主题→概念→股票”推导出的股票与主题关系。它描述相关性，不直接表示股票值得买入。 |
| `core` 成员 | 主题成员中的核心关系；股票为主题 anchor，或 `industry_score` 达到配置的产业代表阈值。 |
| `qualified` 成员 | 通过主题库 eligibility、但未达到 core 条件的有效主题成员。 |
| `edge` 成员 | 未通过 eligibility 的原始主题成员。它可以反映边缘扩散或事件炒作，但不贡献 `core_heat`。 |
| `core_leader` | ComputePool 中主题核心领涨者。优先从 core 选择；没有 core 时可由 qualified 显式兜底；edge 禁止入选。 |
| `momentum_leader` | ComputePool 中所有主题成员里当日涨幅最高者，可以是 edge。它表达价格动量，不等同于产业龙头。 |
| `core_heat` | 由 core 和 qualified 成员加权聚合的主题核心热度。它是主题数据，不直接构成买入指令。 |
| `diffusion_heat` | 由 edge 成员加权聚合的主题边缘扩散热度。它用于识别扩散，不代表主题核心强度。 |
| `library_version` | 已发布主题库的版本标识，本期使用成功构建日期 `YYYY-MM-DD`。 |
| `membership_as_of` | 主题成员关系所对应的主题库构建日期。 |
| `market_as_of` | 盘中主题排名所使用的 ComputePool 行情快照时间。 |
| `contributors` | Top 主题中实际参与本次热度、资金或领涨计算的池内股票及其贡献明细。 |
| `stock_themes` | ComputePool 全股票的确定性主题关系、成员身份及可用评分，不受 Top 主题展示截断影响。 |
| `market_board` | 沪市主板、深市主板、创业板等交易板属性，不是投资主题。 |
| `primary_theme` | mapper 按确定性成员身份和评分规则选择的股票主要投资主题。 |
| `sector` | 盘中合同的过渡兼容字段，由构建器令其等于 `primary_theme`；LLM 不得编写。 |
| 主题感知层 | 使用已发布主题关系和今日行情生成主题观察数据的确定性能力；不负责最终选股、方向和仓位。 |
| 策略层 | 消费主题、资金、价格和执行数据，决定候选优先级、方向、仓位和 T+1 计划的能力。 |
