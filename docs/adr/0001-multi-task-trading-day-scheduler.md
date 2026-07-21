# ADR-0001：交易日多任务调度器

- 状态：Accepted
- 日期：2026-07-21
- 范围：`.opencode/scripts/cron-daemon.py`、`.opencode/config/cron-tasks.json`
- 关联：`.opencode/config/trading-calendar.json`、`auto.bat`

## 背景

原调度器通过命令行参数维护单个 cron 表达式，只能运行一条 OpenCode
命令。交易工作流实际包含早盘分析、隔夜策略复盘、尾盘分析和早盘策略
复盘四个任务，并且必须遵守 A 股交易日、任务日期口径和文件写入串行性。

完整 cron 表达式还重复表达了“周一至周五”这一不完整的交易日规则：它
无法排除交易所节假日。多任务并发则可能同时读写规则和记忆文件。

## 决策

### 配置合同

调度器启动时一次性加载 `.opencode/config/cron-tasks.json`。配置使用
`cron_tasks.v1` JSON 合同，包含交易日历路径、全局默认值和有序任务列表。

每个任务包含：

- `id`：唯一任务标识，也是 `--once` 参数和日志文件名。
- `enabled`：是否参与调度。
- `time`：`Asia/Shanghai` 时区的零填充 `HH:MM`。
- `command`：传给 `opencode run` 的 slash command。
- `date_policy`：`T0` 或 `TP1`。
- `model`、`timeout_seconds`：可选的任务级全局默认覆盖。

配置只在启动时读取。未知字段、重复任务 ID、非法时间、空任务集、非法日期
策略或无启用任务都会导致启动失败；不进行部分加载或热加载。

### 默认任务

| 时间 | 任务 | 命令 | 日期策略 |
|------|------|------|----------|
| 09:20 | `daily-analysis` | `/daily-analysis` | `T0` |
| 09:45 | `intraday-review` | `/intraday-review` | `TP1` |
| 14:30 | `intraday-analysis` | `/intraday-analysis` | `T0` |
| 15:10 | `daily-review` | `/daily-review` | `T0` |

日期会被解析为 ISO 日期并追加到命令，例如：

```text
opencode run "/intraday-review 2026-07-20" ...
```

### 交易日和年份

调度器使用配置日历中的时区、年度休市区间和周末规则。它逐日寻找全局下一
个实际任务，因此同一已知年份内尚未执行的任务不会被更远期的缺年问题阻断。

当全局下一任务落入日历未配置的年份时，调度器报错退出，并要求先补充
`.opencode/config/trading-calendar.json`。调度层不采用“未知年份退化为普通
工作日”的策略。

### 排队、漏跑和失败

- 同一进程最多运行一个 OpenCode 任务。
- 同一时刻的任务按配置顺序执行。
- 前一任务运行期间到点的任务保留在内存调度序列中，前一任务结束后执行。
- daemon 停止期间错过的任务不补跑；进程启动后只寻找未来时点。
- 单个任务失败或超时不重试，也不阻止后续任务。
- `Ctrl+C` 终止当前任务进程树并退出；重启不会恢复被中断任务。
- 调度器不检查策略产物或业务依赖，输入校验仍归各 command/skill 所有。

### CLI

```bash
python .opencode/scripts/cron-daemon.py
python .opencode/scripts/cron-daemon.py --config path/to/tasks.json
python .opencode/scripts/cron-daemon.py --dry-run
python .opencode/scripts/cron-daemon.py --once daily-analysis
```

`--once TASK_ID` 仍受启用状态、交易日和日期策略约束。旧的 `--cron`、
`--cmd`、`--model` 参数被移除，避免绕过配置合同。

### 日志

- `.opencode/logs/cron-daemon.log` 只保存调度事件。
- `.opencode/logs/cron-tasks/{YYYY-MM-DD}/{task-id}.log` 保存任务的完整
  stdout/stderr；同日手动再次执行时追加。

## 结果与权衡

收益：四条工作流共享一个明确、可校验的调度合同；节假日和复盘日期不再靠
命令自行猜测；串行执行消除了调度层引入的并发写入风险；单任务日志更易排查。

代价：配置修改必须重启；长任务会推迟后续任务；daemon 停机期间的任务不会
自动恢复；每年必须在下一任务进入新年份前维护交易日历。这些行为都是显式的
安全边界，而不是隐式降级。

## 验证

```bash
python -m unittest discover -s .opencode/scripts/tests -p "test_cron_daemon.py" -v
python .opencode/scripts/cron-daemon.py --dry-run
```
