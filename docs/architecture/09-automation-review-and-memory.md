# 自动化、复盘与记忆

## 1. 调度架构

调度器读取 `config/cron-tasks.json`，以 `Asia/Shanghai` 和
`config/trading-calendar.json` 计算交易日。默认任务为：

| 时间 | ID | Command | 日期策略 |
|---|---|---|---|
| 09:20 | `daily-analysis` | `/daily-analysis` | T0 |
| 09:45 | `intraday-review` | `/intraday-review` | TP1 |
| 14:30 | `intraday-analysis` | `/intraday-analysis` | T0 |
| 15:10 | `daily-review` | `/daily-review` | T0 |

操作指南默认按需运行，不在四任务调度中。

## 2. 调度行为

```bash
uv run --frozen ashare-pilot automation scheduler run --dry-run
uv run --frozen ashare-pilot automation scheduler run
uv run --frozen ashare-pilot automation scheduler run --once daily-analysis
```

- 一个 daemon 同时只运行一个 OpenCode 任务；
- 同时到点按配置顺序串行；
- 运行中到点的任务在内存中排队；
- daemon 停机期间错过的任务不补跑；
- 单任务失败或超时不自动重试，也不阻止后续任务；
- 配置只在启动时加载，修改后必须重启；
- 缺少目标年份交易日历时 fail closed。

`auto.bat` 和 `auto.sh` 是平台入口。`logs/cron-daemon.log` 保存调度事件，
`logs/cron-tasks/{date}/{task-id}.log` 保存任务输出。

## 3. 日线复盘

`daily-trading-review` 读取当天 `daily_strategy.v3`，调用：

```bash
uv run --frozen ashare-pilot review daily verify \
  --date YYYY-MM-DD --pretty
```

生成 `daily_verification.v1`，再由 `performance-analyst` 写
`memory/daily/{date}/verification.md`。复盘区分实际结果、规则触发、关键教训和
次日调整，不把 Markdown 反向解析成机器验证。

可积累执行：

```bash
uv run --frozen ashare-pilot review daily backtest-entry-band --since YYYY-MM-DD
uv run --frozen ashare-pilot review daily backtest-entry-quality ...
```

## 4. 隔夜复盘

`intraday-trading-review` 在 T+1 开盘后读取 T 日：

- `intraday_mapper.v3`；
- `intraday_overnight_strategy.v3`；
- 实际 T+1 报价和 K 线。

复盘分别统计 recommendations、eligible watchlist 和 observations。只有 primary
进入推荐胜率；alternative/watch 用于机会成本和降级质量；unscored observations
不评价评分质量。输出为 `memory/intraday/{T}/intraday_verification.md`。

## 5. Memory 布局

```text
memory/
├── MEMORY.md
├── RULE_GOVERNANCE.md
├── PERFORMANCE.md
├── RULES.md
├── INTRADAY_RULES.md
├── SHARED_RULES.md
├── EXPERT_RULES.md
├── daily/INDEX.md
├── daily/{date}/...
├── intraday/INDEX.md
└── intraday/{date}/...
```

- `RULES.md`：日线规则；
- `INTRADAY_RULES.md`：隔夜规则；
- `SHARED_RULES.md`：跨流程规则；
- `EXPERT_RULES.md`：专家直接授权、立即生效的 Daily/Overnight 自然语言规则；
- `PERFORMANCE.md`：真实样本累计表现；
- 两个 INDEX：复盘导航。

## 6. 零历史初始化

```bash
uv run --frozen ashare-pilot automation memory init
uv run --frozen ashare-pilot automation rules check
```

初始化幂等，只补缺失模板，不覆盖已有 memory。空规则表表示没有已学习规则，不是
异常；不得填充示例规则、虚构胜率或占位历史。

专家规则由 `$manage-expert-rules` 访谈和能力检查后通过 CLI 写入；直接 CLI
是绕过语义检查的可信旁路。它们不进入 learned-rule 生命周期、不统计有效性，也
不作用于 Operation Guide。

## 7. 规则治理

修改规则生命周期前必须读取 `RULE_GOVERNANCE.md`。核心原则：

- 当日新发现只能作为候选或观察；
- 规则必须引用真实 verification 证据；
- 状态、容量、ID 和引用通过 `automation rules check`；
- 策略生成只应用正式规则，不在生成过程中新增、升级或退休规则；
- learned rules 可以收紧建议，不能覆写 Compute 事实或把 observation 升入
  executable pool；
- 历史复盘和原始策略不可为了支持新规则而回写。
