# A股早盘推荐系统操作手册

> 版本：v1  
> 日期：2026-07-11  
> 适用工作流：`daily-market-analysis`、`intraday-operation-guide`  
> 示例交易日：2026-07-13  
> 核心约束：沪深A股新仓按T+1管理，当日买入后不能依赖当日卖出止损

---

## 一、每日操作总览

```text
09:20       运行 daily-market-analysis
    ↓
09:29前     校验 news / mapper / strategy
    ↓
09:30-09:35 只观察，不直接买入
    ↓
09:35:05    intraday-operation-guide 第一次确认
    ↓
09:40:05    intraday-operation-guide 第二次确认
    ↓
09:40-10:00 只执行验证通过的A类标的
    ↓
成交后      记录T+1风险，不执行当日止损卖出
```

系统不自动下单。最终操作由人工完成。

---

## 二、交易日前准备

建议在09:15前完成。

### 2.1 环境检查

- Chrome和东方财富Cookie可用；
- `.env`配置存在；
- 网络和行情接口正常；
- Theme Library近期已更新；
- cron daemon或`auto.bat`正在运行；
- 当天目录没有残留的失败运行产物。

### 2.2 检查自动调度

```bash
python .opencode/scripts/cron-daemon.py --dry-run
```

如果没有自动运行计划，当天需要手动启动盘前工作流。

---

## 三、09:20盘前分析

### 3.1 Codex操作口令

```text
运行 daily-market-analysis，日期 {date}
```

示例：

```text
运行 daily-market-analysis，日期 2026-07-13
```

### 3.2 预期产物

```text
predict/{date}/news.json
predict/{date}/news.md
predict/{date}/themes.json
predict/{date}/theme_stocks.universe.json
predict/{date}/pool_indicators.json
predict/{date}/theme_stocks.json
predict/{date}/mapper.json
predict/{date}/mapper.strategy_view.json
predict/{date}/strategy.json
predict/{date}/daily_report.html
```

其中：

- `strategy.json`是盘前条件计划；
- `daily_report.html`是人读盘前报告；
- 盘前看多、评级和仓位预算不等于09:30立即买入；
- 最终A/B/C/D必须由开盘后二次确认生成。

---

## 四、09:29前产物验收

### 4.1 校验策略

```bash
python .opencode/skills/daily-strategy/scripts/validate_strategy_json.py \
  predict/{date}/strategy.json --require-v2
```

示例：

```bash
python .opencode/skills/daily-strategy/scripts/validate_strategy_json.py \
  predict/2026-07-13/strategy.json --require-v2
```

### 4.2 校验mapper

```bash
python .opencode/skills/daily-stock-mapping/scripts/validate_mapper_json.py \
  --date {date}
```

### 4.3 检查关键文件

```bash
test -f predict/{date}/news.json
test -f predict/{date}/strategy.json
test -f predict/{date}/daily_report.html
```

### 4.4 失败处理

任意校验失败时：

1. 不执行盘前推荐；
2. 不使用前一交易日文件代替；
3. 修复失败阶段或重新运行工作流；
4. 如果09:35前仍未完成，当天默认降级为观察，不追赶开盘。

---

## 五、09:30至09:35观察窗口

这五分钟默认不买入。

禁止：

- 根据竞价涨幅直接追入；
- 根据5星、看多或高主题热度直接买入；
- 人工把B/C类候选提前视为A类；
- 因担心踏空而绕过首根完整5分钟K线。

等待系统获得：

- 09:30至09:35完整K线；
- 三指数实时方向；
- VWAP与高开回落状态；
- 主题内策略标的一致性；
- 个股相对MA5/MA20/ATR的位置。

---

## 六、09:35第一次确认

### 6.1 Codex操作口令

```text
运行 intraday-operation-guide，日期 {date}，执行09:35第一次确认
```

### 6.2 构建快照

必须在09:35:05之后运行：

```bash
python .opencode/skills/intraday-operation-guide/scripts/build_operation_snapshot.py \
  --date {date} \
  --slot 09:35 \
  --write-latest \
  -o operation/{date}/operation_snapshot_0935.json
```

### 6.3 校验快照

```bash
python .opencode/skills/intraday-operation-guide/scripts/validate_operation_snapshot.py \
  operation/{date}/operation_snapshot_0935.json
```

### 6.4 构建机器决策

```bash
python .opencode/skills/intraday-operation-guide/scripts/build_operation_decision.py \
  --snapshot operation/{date}/operation_snapshot_0935.json \
  -o operation/{date}/operation_decision_0935.json
```

### 6.5 校验机器决策

```bash
python .opencode/skills/intraday-operation-guide/scripts/validate_operation_decision.py \
  operation/{date}/operation_decision_0935.json
```

### 6.6 09:35执行原则

先读取：

```text
market_confirmation.global_action
```

| global_action | 操作 |
|---|---|
| `NORMAL` | 可以考虑A类 |
| `SELECTIVE` | 只考虑最强A类，仓位已折减 |
| `WAIT` | 不买，等待09:40 |
| `NO_NEW_BUY` | 当前阶段禁止新开仓 |

然后读取每只股票：

```text
final_class
final_position_max
trigger
t1_controls
```

| 类别 | 操作 |
|---|---|
| A | 条件已确认，可在仓位上限内人工执行 |
| B | 等触发，不提前买入 |
| C | 只观察，不主动买 |
| D | 当天放弃，后续不得升级 |

09:35没有A类属于正常结果，不需要强行交易。

---

## 七、09:40第二次正式确认

### 7.1 Codex操作口令

```text
运行 intraday-operation-guide，日期 {date}，使用09:35快照执行09:40第二次确认
```

### 7.2 构建第二次快照

必须在09:40:05之后运行：

```bash
python .opencode/skills/intraday-operation-guide/scripts/build_operation_snapshot.py \
  --date {date} \
  --slot 09:40 \
  --write-latest \
  --previous-snapshot operation/{date}/operation_snapshot_0935.json \
  -o operation/{date}/operation_snapshot_0940.json
```

### 7.3 校验和生成决策

```bash
python .opencode/skills/intraday-operation-guide/scripts/validate_operation_snapshot.py \
  operation/{date}/operation_snapshot_0940.json

python .opencode/skills/intraday-operation-guide/scripts/build_operation_decision.py \
  --snapshot operation/{date}/operation_snapshot_0940.json \
  -o operation/{date}/operation_decision_0940.json

python .opencode/skills/intraday-operation-guide/scripts/validate_operation_decision.py \
  operation/{date}/operation_decision_0940.json
```

### 7.4 类别变化处理

| 09:35→09:40 | 操作 |
|---|---|
| B→A | 第二根K线确认，可以考虑执行 |
| A→A | 信号持续，维持机器仓位上限 |
| A→B/C/D | 未成交则取消；已成交标记T+1风险 |
| B→C/D | 等待失败，停止执行 |
| C→A | 默认禁止 |
| D→A/B/C | 系统禁止 |

09:40是主要执行窗口。

---

## 八、实际买入纪律

只买同时满足以下条件的股票：

1. `final_class=A`；
2. snapshot和decision均通过验证；
3. `global_action`不是`WAIT`或`NO_NEW_BUY`；
4. 当前价格没有在决策生成后快速偏离；
5. 没有个人已有持仓或风险冲突；
6. 买入仓位不超过`final_position_max`；
7. 能接受买入后当天无法卖出的T+1风险。

### 8.1 仓位约束

必须满足：

```text
final_position_max
<= signal_adjusted_max
<= market_adjusted_max
<= morning_budget
```

例如：

```text
morning_budget       = 2.0%
market_adjusted_max  = 1.0%
final_position_max   = 1.0%
```

实际最多买账户资金的1%，不能人工恢复成盘前2%。

### 8.2 多股票选择

- 不把同主题所有A类全部买入；
- 优先主题状态为`CONFIRMED`的标的；
- 优先09:35至09:40保持或升级的标的；
- 优先不远离锚点、没有高开回落的标的；
- 遵守strategy中的总仓、单主题和单股预算。

---

## 九、09:45可选确认

如果09:40仍没有合适A类，可在09:45:05后运行一次：

```bash
python .opencode/skills/intraday-operation-guide/scripts/build_operation_snapshot.py \
  --date {date} \
  --slot 09:45 \
  --write-latest \
  --previous-snapshot operation/{date}/operation_snapshot_0940.json \
  -o operation/{date}/operation_snapshot_0945.json
```

09:45只处理原有B类等待条件：

- D类不得恢复；
- C类默认不得升级；
- 不因为股票突然拉升而追入；
- 超过盘前`latest_entry_time`的股票自动失效。

10:00后停止开盘追涨策略。没有确认的候选视为当天不交易。

---

## 十、T+1风险处理

### 10.1 买入前

失效位的含义是：

```text
尚未成交时，条件失效则取消买入。
```

### 10.2 买入后

当天新仓不能按普通T+0系统执行“跌破立即卖出”。

成交后如果条件失效：

- 不在当天补仓；
- 标记为T+1高风险仓；
- 记录实际买入时间、价格、仓位；
- 准备次日退出；
- 不把风险提示错误描述为当天可执行止损。

### 10.3 次日处理

| 次日场景 | 原则 |
|---|---|
| 高开 | 承接不足时分批兑现 |
| 平开 | 观察昨收和VWAP，反弹失败退出 |
| 低开 | 禁止补仓，优先控制风险 |

具体动作以每只股票的`t1_exit_plan`为准。

---

## 十一、异常处理

| 异常 | 操作 |
|---|---|
| `strategy.json`缺失或校验失败 | 当天不执行推荐 |
| mapper覆盖不完整 | 停止，不猜测 |
| 指数数据缺失 | `global_action=WAIT` |
| 市场明显弱势 | `global_action=NO_NEW_BUY` |
| 个股行情缺失 | 该股D类 |
| 完整5分钟K缺失 | 该股降级，不提前确认 |
| 主题确认失败 | 该主题股票最高C类 |
| 09:40运行失败 | 不允许根据09:35结果自动升级 |
| 上次快照缺失 | 不伪造状态迁移，重新评估或停止 |
| 没有A类 | 不交易 |

### 11.1 盘前工作流超时

以Step 3完成“生成→归一化→校验→渲染”的时间为准，不使用草稿文件的
`generated_at`冒充完成时间。

| 完成时间 | 确认安排 |
|---|---|
| 09:35前 | 正常09:35初筛、09:40正式确认 |
| 09:35～09:40 | 立即运行09:35，继续09:40 |
| 09:40～09:45 | 跳过09:35；09:40首次快照最高B且仓位0，09:45再确认 |
| 09:45以后 | 不补跑历史快照，当天早盘策略只观察 |

09:40首次快照不得传不存在的`--previous-snapshot`。系统会输出：

```text
delivery_status = LATE_0940_INITIAL
execution_action = WAIT_SECOND_CONFIRMATION
```

随后09:45使用09:40快照，只有合法B→A才可执行。09:45以后首次启动会输出：

```text
delivery_status = LATE_OBSERVE_ONLY
execution_action = OBSERVE_ONLY
```

---

## 十二、每日最简执行清单

```text
[ ] 09:15 检查环境与自动调度
[ ] 09:20 运行 daily-market-analysis
[ ] 09:29前校验 news、mapper、strategy v2
[ ] 09:30-09:35 不直接买入
[ ] 09:35:05 运行第一次 operation confirmation
[ ] 检查 global_action
[ ] 只记录A类，不执行B/C/D
[ ] 09:40:05 使用09:35快照运行第二次确认
[ ] 只执行验证通过的A类
[ ] 仓位不超过 final_position_max
[ ] 记录实际成交
[ ] 成交后按T+1管理，不做当天卖出止损
[ ] 10:00后停止开盘追涨
```

---

## 十三、每日三条操作口令

```text
09:20
运行 daily-market-analysis，日期 {date}

09:35:05
运行 intraday-operation-guide，日期 {date}，执行09:35第一次确认

09:40:05
运行 intraday-operation-guide，日期 {date}，使用09:35快照执行09:40第二次确认
```

最终纪律：

> 盘前只选候选；09:30不直接买；09:35初筛；09:40正式决策；只执行验证通过的A类和机器仓位上限；没有A类就不交易。
