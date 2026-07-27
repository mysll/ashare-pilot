# A股早盘推荐与二次确认系统 Spec

> 状态：Draft v1  
> 日期：2026-07-11  
> 适用范围：`daily-market-analysis`、`intraday-operation-guide`  
> 交易范围：沪深 A 股普通股票，遵循项目 `config/trading-scope.json`
> 核心约束：A 股新开仓按 T+1 管理，当日买入后不得依赖当日卖出止损

---

## 一、背景与目标

当前项目已经形成两层能力：

1. `daily-market-analysis` 在盘前完成新闻、主题、股票池、技术指标和交易策略生成；
2. `intraday-operation-guide` 读取盘前策略与实时行情，将股票分为 A/B/C/D 操作类别。

这两个 Skill 的方向正确，但当前职责边界仍不够严格：盘前的市场判断可能被直接当作开盘后的真实状态，盘中操作层也可能在缺少市场级确认时放大仓位或输出无法在 T 日执行的“止损离场”。

本次改造目标不是增加第三套推荐系统，而是将现有两个 Skill 组合成一个明确的双阶段早盘推荐系统：

```text
09:20～09:29  daily-market-analysis
                生成盘前候选、策略意图和条件
                         ↓
09:30～09:35  只采集开盘数据，默认不直接买入
                         ↓
09:35:05      intraday-operation-guide 第一次确认
                         ↓
09:40:05      intraday-operation-guide 第二次确认
                         ↓
09:35～10:00  人工执行通过确认的标的
```

### 1.1 产品目标

系统最终回答三个不同的问题：

| 阶段 | 问题 | 产物 |
|---|---|---|
| 盘前研究 | 今天值得关注什么，什么条件下才可以买 | `strategy.json` |
| 开盘确认 | 盘前逻辑是否被真实市场确认 | `operation_snapshot.json` |
| 人工执行 | 现在能买、等待、观察还是放弃 | `operation_guide.md` |

### 1.2 非目标

- 不自动下单；
- 不承诺收益；
- 不在执行层重新发明新闻、主题和选股逻辑；
- 不允许盘中操作层扩大盘前仓位预算；
- 不把 T 日新仓的风险位描述为当日可执行卖出止损；
- 不用单日复盘直接修改正式交易规则。

---

## 二、设计原则

### 2.1 盘前选择，开盘确认

`daily-market-analysis` 负责缩小研究范围并生成条件计划，但其 `regime` 只能作为 `regime_prior`，不能作为全天固定事实。

`intraday-operation-guide` 负责用开盘后的真实指数、市场宽度、主题宽度和个股价格行为生成 `regime_live`，再得出 `regime_confirmed`。

### 2.2 T+1 风险优先于踏空成本

当天不能退出意味着开仓错误会转化为隔夜风险，因此系统默认接受一定踏空，换取更高的入场质量。

优先级：

```text
避免不可逆错误
> 控制组合暴露
> 确认市场和板块
> 确认个股
> 减少踏空
```

### 2.3 机器做硬约束，LLM 做有限解释

Python 脚本负责：

- 数据抓取和时间切片；
- 完整 K 线识别；
- 指标和信号计算；
- 市场状态基础分类；
- 硬风险和最大类别计算；
- 仓位上限计算；
- schema、日期、引用和覆盖校验。

LLM 负责：

- 对已计算信号进行简短解释；
- 在机械上限以内对类别降级；
- 为 B 类选择一个明确触发条件；
- 生成人工可执行的中文卡片。

LLM 不得：

- 把 `max_allowed_class=B` 升为 A；
- 把盘前 0.3% 仓位改为 0.5%；
- 用叙述覆盖 `global_action=NO_NEW_BUY`；
- 将不完整 K 线判断为收盘确认；
- 为 T 日新仓生成“跌破立即卖出”的当日操作。

### 2.4 JSON-first

机器消费者只依赖 JSON。Markdown 和 HTML 只作为人读层，不作为下游数据源。

---

## 三、总体架构

```text
news.json
    ↓
themes.json
    ↓
theme_stocks.json + pool_indicators.json
    ↓
mapper.json → mapper.strategy_view.json
    ↓
strategy.json
    │
    ├────────── 盘前策略意图、仓位上限、买前失效条件
    │
    ↓
operation_snapshot_0935.json
    ↓
operation_snapshot_0940.json
    ↓
operation_decision.json
    ↓
operation_guide.md
    ↓
人工执行记录 execution_log.json
    ↓
T+1 verification.json / entry confirmation backtest
```

### 3.1 两个 Skill 的职责边界

| 能力 | daily-market-analysis | intraday-operation-guide |
|---|:---:|:---:|
| 新闻与主题匹配 | 负责 | 不负责 |
| 股票池和技术计算 | 负责 | 只读取 |
| 盘前评分和交易画像 | 负责 | 不重算 |
| 盘前市场先验 | 负责 | 读取并复核 |
| 实时指数与宽度 | 不负责 | 负责 |
| 完整 5 分钟 K 线 | 不负责 | 负责 |
| 开盘确认 | 不负责 | 负责 |
| A/B/C/D | 不输出 | 负责 |
| 最大仓位 | 给出原始上限 | 只能维持或降低 |
| 当日下单 | 不负责 | 不负责，仅给人工说明 |
| T+1 退出计划 | 给出基础计划 | 按实际入场风险补充，不改变策略意图 |

---

## 四、时间线与运行策略

### 4.1 标准运行时间

| 时间 | 阶段 | 要求 |
|---|---|---|
| 09:20:00 | 启动盘前流水线 | 开始新闻、主题、股票池和指标处理 |
| 09:25:10 | 最终竞价数据可用 | 计算竞价价格、金额和缺口 |
| 09:27～09:29 | 盘前策略完成 | `strategy.json` 必须通过校验 |
| 09:30～09:35 | 观察窗口 | 默认不得把盘前候选直接升级为可买 |
| 09:35:05 | 第一次二次确认 | 只使用已经完成的 09:30～09:35 K 线 |
| 09:40:05 | 第二次二次确认 | 作为主要正式执行清单 |
| 09:45～10:00 | 条件触发窗口 | B 可转 A；不再无条件追开盘涨幅 |
| 10:00 后 | 早盘追涨关闭 | 只保留标准回踩、观察或取消 |

### 4.2 超时处理

- `daily-market-analysis` 在 09:29:30 前未完成：标记 `PREMARKET_LATE`；
- 盘前策略晚于 09:35 才生成：当天只允许 C/D，除非人工明确重新启动研究；
- 09:35 快照失败：不得复用昨日或较早快照；
- 09:40 快照失败：沿用 09:35 的类别上限，但不得自动升级；
- 实时行情严重缺失：`global_action=NO_NEW_BUY`。

### 4.3 完整 K 线定义

任何 5 分钟 K 线只有在其结束时间小于等于快照时间时才能参与确认。

示例：

| 快照时间 | 可用的最后一根 K 线 |
|---|---|
| 09:34:59 | 无完整开盘 5 分钟 K |
| 09:35:05 | 09:30～09:35 |
| 09:39:59 | 09:30～09:35 |
| 09:40:05 | 09:35～09:40 |

脚本必须保留：

- `bar_start`；
- `bar_end`；
- `is_complete`；
- `snapshot_time`；
- `data_lag_seconds`。

---

## 五、daily-market-analysis 改造方案

### 5.1 职责调整

盘前系统输出“条件化候选”，不输出“开盘后无条件立即买入”。

每只策略股票必须回答：

1. 为什么进入候选；
2. 最早允许什么时候买；
3. 需要怎样的市场状态；
4. 需要怎样的板块状态；
5. 需要怎样的个股确认；
6. 什么情况下当天取消；
7. 仓位意图是仅观察、轻仓还是标准仓；
8. 当天买入后，T+1 如何处理。

### 5.2 `strategy.json` 契约升级

当前 schema 为 `daily_strategy.v3`，只接受定性仓位档位，不兼容旧数值仓位合同。

顶层新增：

```json
{
  "schema_version": "daily_strategy.v3",
  "date": "2026-07-13",
  "generated_at": "2026-07-13T09:28:10+08:00",
  "run_id": "daily-20260713-092000-...",
  "strategy_cutoff": "09:29:30",
  "market": {
    "regime_prior": "strong-sector",
    "regime_confidence": 68,
    "regime_evidence": [],
    "requires_open_confirmation": true
  },
  "portfolio_limits": {
    "max_new_positions": 7,
    "max_theme_positions": 3,
    "max_correlated_names": 2
  },
  "stocks": []
}
```

单股新增 `preopen_plan`：

```json
{
  "code": "sz000977",
  "direction": "看多",
  "rating": "4★",
  "position_tier": "LIGHT",
  "horizon": "T+1",
  "preopen_plan": {
    "decision": "CONDITIONAL",
    "earliest_entry_time": "09:35:05",
    "latest_entry_time": "10:00:00",
    "required_regimes": ["neutral", "strong-sector"],
    "requires_first_bar": true,
    "requires_market_confirmation": true,
    "requires_theme_confirmation": true,
    "max_open_gap_pct": 4.0,
    "min_auction_amount": 50000000,
    "entry_setup": "FIRST_BAR_OR_PULLBACK",
    "pre_entry_invalidations": [
      "regime_confirmed in [weak, panic]",
      "theme_breadth < 0.50",
      "high_open_fade = true"
    ]
  },
  "t1_risk_plan": {
    "overnight_risk": "high",
    "gap_up_action": "次日高开后承接不足则分批兑现",
    "flat_open_action": "观察昨收与VWAP，反弹失败退出",
    "gap_down_action": "禁止补仓，按竞价和首30分钟承接处理",
    "max_holding_days": 2
  }
}
```

### 5.3 策略类型与最早执行时间

| `entry_setup` | 默认最早时间 | 说明 |
|---|---|---|
| `LIMIT_UP_CONT` | 09:35:05 | 必须经过首根 K、市场和板块确认 |
| `MOMENTUM` | 09:35:05 | 只允许试探仓，不允许无条件开盘追入 |
| `FIRST_BAR_OR_PULLBACK` | 09:35:05 | 首根确认或后续回踩 |
| `PULLBACK` | 09:40:05 | 等待锚点与承接 |
| `DEFENSIVE` | 09:40:05 | 弱市中只允许更低风险入场 |
| `WATCH_ONLY` | 不可执行 | 当天默认不升级，除非盘前明确允许重评 |

### 5.4 盘前硬风险

出现以下任一情况，盘前只能输出 `WATCH_ONLY` 或 `CONDITIONAL`，不得输出开盘可执行：

- 关键行情数据缺失；
- 竞价数据未到 09:25:10；
- 指数间明显背离；
- 前一交易日大涨且融资明显净流出；
- 推荐标的高开幅度超过策略上限；
- 同一主题候选过度集中；
- T+1 退出计划缺失；
- 策略晚于 cutoff 生成。

### 5.5 验证器升级

`validate_strategy_json.py` 应新增：

- v3 schema 校验；
- `run_id`、日期和生成时间；
- `earliest_entry_time >= 09:35:05`，除非显式白名单；
- 所有新仓 `horizon=T+1`；
- `position_tier` 只能为 `WATCH_ONLY|LIGHT|STANDARD`；
- 禁止百分比、金额、股数、手数和数值 exposure 上限；
- 同主题与全组合可参与只数不超限；
- 每只股票存在 `pre_entry_invalidations`；
- 每只股票存在 `t1_risk_plan`；
- 禁止把 T 日卖出动作写进新仓计划；
- mapper 股票覆盖及关键数值一致性；
- 上游 artifact hash 或 run_id 一致性。

---

## 六、intraday-operation-guide 改造方案

### 6.1 目标

把当前“逐股盘中信号解释器”升级为真正的开盘执行闸门：

```text
市场确认
    ↓
主题确认
    ↓
个股确认
    ↓
组合约束
    ↓
A/B/C/D
```

任意上层失败，下层不得绕过。

### 6.2 快照脚本拆分

保留 `build_operation_snapshot.py` 作为统一入口，内部拆分为以下模块或函数：

1. `load_morning_contracts()`：读取并验证 strategy/mapper；
2. `fetch_market_snapshot()`：指数和市场宽度；
3. `fetch_theme_snapshot()`：主题实时宽度；
4. `fetch_stock_snapshots()`：个股行情和分时；
5. `select_completed_bars()`：排除未完成 K 线；
6. `compute_market_confirmation()`；
7. `compute_stock_signals()`；
8. `compute_mechanical_class()`；
9. `apply_portfolio_limits()`；
10. `validate_operation_snapshot()`。

可以先在单文件内实现，测试稳定后再拆文件，避免为了结构重构阻塞功能修复。

### 6.3 顶层市场确认契约

`operation_snapshot.json` 新增：

```json
{
  "schema_version": "intraday_operation_snapshot.v2",
  "date": "2026-07-13",
  "snapshot_time": "2026-07-13T09:35:08+08:00",
  "snapshot_slot": "09:35",
  "source_run_id": "daily-20260713-092000-...",
  "market_confirmation": {
    "regime_prior": "strong-sector",
    "regime_live": "neutral",
    "regime_confirmed": "neutral",
    "regime_changed": true,
    "indices": {
      "sh000001": {"open_pct": -0.10, "current_pct": -0.20},
      "sz399001": {"open_pct": -0.35, "current_pct": -0.55},
      "sh000688": {"open_pct": 0.20, "current_pct": -0.40}
    },
    "breadth": {
      "advance_count": 1800,
      "decline_count": 3200,
      "advance_ratio": 0.36,
      "limit_up_count": 18,
      "limit_down_count": 6
    },
    "global_action": "SELECTIVE",
    "blocking_reasons": []
  }
}
```

`global_action` 枚举：

| 枚举 | 含义 | 类别上限 |
|---|---|---|
| `NORMAL` | 市场确认正常 | 可出现 A |
| `SELECTIVE` | 分化，只做最强确认 | A 数量和仓位受限 |
| `WAIT` | 状态未确认 | 所有股票最高 B |
| `NO_NEW_BUY` | 弱势、恐慌或数据异常 | 所有股票最高 C/D |

### 6.4 主题确认

每个策略主题新增：

```json
{
  "theme": "AI算力",
  "preopen_heat": 88,
  "current_pct": 1.20,
  "member_advance_ratio": 0.64,
  "core_confirmation_ratio": 0.67,
  "leader_above_vwap": true,
  "theme_confirmed": true,
  "theme_state": "CONFIRMED"
}
```

`theme_state`：

- `CONFIRMED`：主题价格与宽度确认；
- `NARROW`：只有少数龙头上涨；
- `FADING`：高开后明显回落；
- `FAILED`：主题转弱或核心股一致走弱；
- `UNKNOWN`：数据不足。

主题为 `FAILED` 时，该主题股票不得为 A。

### 6.5 K 线信号修复

修复当前 `first_bar_red_flag` 实际读取最新 K 线的问题。

单股 signals 改为：

```json
{
  "first_bar": {
    "bar_start": "09:30:00",
    "bar_end": "09:35:00",
    "is_complete": true,
    "return_pct": 0.42,
    "close_position": 0.76,
    "red_flag": false,
    "volume_vs_recent": 1.20,
    "volume_vs_yesterday_same_bar": 1.46,
    "confirmed": true
  },
  "latest_completed_bar": {
    "bar_end": "09:40:00",
    "return_pct": -0.20,
    "volume_multiple": 0.82,
    "price_strength_confirmed": false
  }
}
```

不得再把正在形成的 `09:40` K 线用于 `09:36` 的确认。

### 6.6 机械分类

每只股票先由脚本生成 `mechanical_class` 和 `max_allowed_class`。

#### A 类必要条件

全部满足才允许：

- 盘前方向为 `看多` 或 `偏多`；
- 当前时间达到 `earliest_entry_time`；
- `global_action` 为 `NORMAL` 或允许 A 的 `SELECTIVE`；
- `regime_confirmed` 在股票允许范围内；
- `theme_state=CONFIRMED`；
- 首根或最新完整 K 线确认；
- 不低于 VWAP，或属于经定义的回踩收回；
- 没有高开回落硬风险；
- 没有触发盘前不买条件；
- 数据完整；
- 组合预算仍有余额。

#### B 类

- 盘前逻辑仍有效；
- 市场或个股尚未完成确认；
- 存在一个清晰且可机器验证的触发条件；
- 未触发硬取消条件。

#### C 类

- 方向可能仍正确，但没有安全入场点；
- 主题过窄；
- 远离锚点；
- 超过 `latest_entry_time`；
- 市场为 `NO_NEW_BUY` 但股票未出现个股硬风险；
- 数据不足但不是严重错误。

#### D 类

- 盘前不买条件已确认；
- 主题失败且个股走弱；
- 高开回落叠加大阴线；
- 数据严重异常；
- 股票不在交易范围；
- 策略本身为看空或暂不参与；
- 价格行为已破坏原始交易逻辑。

### 6.7 类别不可越权规则

快照输出：

```json
{
  "mechanical_class": "B",
  "max_allowed_class": "B",
  "llm_final_class": null,
  "class_reasons": ["volume_not_confirmed"],
  "hard_blocks": [],
  "position_tier": {
    "morning": "STANDARD",
    "market_adjusted": "LIGHT",
    "signal_adjusted": "LIGHT",
    "portfolio_adjusted": "LIGHT",
    "final": "LIGHT"
  }
}
```

类别强弱顺序：

```text
A > B > C > D
```

LLM 只能保持或向右降级，不能向左升级。

档位只能保持或降低：

```text
final
<= portfolio_adjusted
<= signal_adjusted
<= market_adjusted
<= morning
```

### 6.8 09:35 与 09:40 状态迁移

允许迁移：

| 09:35 | 09:40 | 含义 |
|---|---|---|
| B | A | 第二根确认后可执行 |
| A | A | 信号持续，维持仓位上限 |
| A | B/C/D | 信号恶化，未成交则取消；已成交则标记风险 |
| B | C/D | 等待条件失败 |
| C | A | 默认禁止，除非盘前计划显式允许重评 |
| D | 任意更高 | 禁止 |

每次运行写独立快照，不覆盖：

```text
operation/{date}/operation_snapshot_0935.json
operation/{date}/operation_snapshot_0940.json
operation/{date}/operation_snapshot_0945.json
```

另写 `operation_snapshot.latest.json` 供人工查看。

### 6.9 T+1 风控表达

操作层必须区分三类条件：

```json
{
  "pre_entry_invalidation": "买入前跌破40.50则取消",
  "post_entry_t_risk_alert": "买入后跌破40.50，标记次日优先处理，不得描述为当天卖出",
  "t1_exit_plan": {
    "gap_up": "承接不足分批兑现",
    "flat_open": "反弹失败退出",
    "gap_down": "禁止补仓，优先控制风险"
  }
}
```

操作文案禁止：

```text
今天新买后，跌破 X 立即止损卖出
```

允许：

```text
买入前跌破 X 则取消；若成交后转弱，记录为 T+1 高风险仓，次日按退出计划处理
```

---

## 七、`operation_decision.json` 与人读输出

### 7.1 增加机器决策产物

当前只有 snapshot 和 Markdown。建议增加：

```text
operation/{date}/operation_decision_0935.json
operation/{date}/operation_decision_0940.json
```

内容：

```json
{
  "schema_version": "intraday_operation_decision.v2",
  "date": "2026-07-13",
  "snapshot_slot": "09:40",
  "source_snapshot": "operation_snapshot_0940.json",
  "global_action": "SELECTIVE",
  "portfolio": {
    "actionable_positions": 1
  },
  "stocks": [
    {
      "code": "sz000977",
      "mechanical_class": "A",
      "final_class": "B",
      "final_position_tier": "LIGHT",
      "trigger": "下一根完整5分钟K放量站稳VWAP",
      "pre_entry_invalidation": "跌破开盘区间低点则取消",
      "t1_risk_level": "high"
    }
  ]
}
```

### 7.2 `operation_guide.md` 输出原则

人读报告保留 A/B/C/D，但需要增加：

- 快照时间和最后完整 K 线时间；
- `regime_prior → regime_confirmed`；
- `global_action`；
- 本次相对上次的升级/降级；
- 新仓 T+1 风险说明；
- 盘前预算、调整后预算和最终上限。

操作卡必须在 30 秒内读完，不重复盘前长逻辑。

---

## 八、执行记录与复盘

### 8.1 人工执行记录

系统不自动交易，但需要记录用户真实执行，才能评估推荐效果。

新增可选文件：

```text
operation/{date}/execution_log.json
```

```json
{
  "schema_version": "manual_execution_log.v1",
  "date": "2026-07-13",
  "orders": [
    {
      "code": "sz000977",
      "decision_slot": "09:40",
      "decision_class": "A",
      "executed": true,
      "execution_time": "09:41:12",
      "execution_price": 70.20,
      "position": 0.005,
      "not_executed_reason": null
    }
  ]
}
```

### 8.2 复盘应回答的问题

分别评价：

1. 盘前选股是否正确；
2. 09:35 确认是否过滤错误；
3. 09:40 确认是否继续改善；
4. A 类实际成交后 T+1 表现；
5. B→A 与直接 09:30 买入相比的增量；
6. A→D 是否成功避免损失；
7. C/D 中是否存在系统性踏空；
8. 市场级闸门贡献了多少风险改善。

### 8.3 核心回测组

至少对比：

| 组别 | 定义 |
|---|---|
| `PREOPEN_BASELINE` | 按盘前计划 09:30 假设成交 |
| `CONFIRM_0935` | 只执行 09:35 A 类 |
| `CONFIRM_0940` | 只执行 09:40 A 类 |
| `CONFIRM_ANY` | 09:35～10:00 首次变为 A 时执行 |
| `NO_TRADE` | 不交易基线 |
| `SIMPLE_THEME_MOMENTUM` | 简单主题动量基线 |

### 8.4 评价指标

- 实际可成交率；
- T 日收盘收益，仅作风险观察；
- T+1 开盘、09:35、收盘收益；
- MAE/MFE；
- 隔夜跳空损失；
- 胜率、盈亏比、期望值；
- 最大连续亏损；
- 最大组合回撤；
- 主题集中度；
- A 类准确率；
- B→A 增量；
- A→降级避免损失；
- 等待导致的踏空成本；
- 相对沪深300/中证1000等适用基准的超额。

### 8.5 规则升级门槛

- 正式版本至少冻结 20 个交易日；
- 同一场景有效执行样本不少于 20；
- 新规则先进入 shadow 状态；
- 连续两个独立窗口改善，且尾部风险不恶化，才可进入人工审核；
- 禁止用规则产生前的数据同时作为发现集和样本外验证集；
- 正式规则必须记录启用日、版本、适用场景和退役条件。

---

## 九、验证器与测试

### 9.1 新增或升级验证器

建议：

```text
uv run --frozen ashare-pilot strategy daily validate
uv run --frozen ashare-pilot operations snapshot validate
uv run --frozen ashare-pilot operations decision validate
```

验证内容包括：

- schema 和日期；
- source run_id；
- 快照时间与 K 线完成时间；
- 股票覆盖和重复代码；
- strategy/mapper 数值一致性；
- 市场状态和 global action 枚举；
- 类别不可越权；
- 仓位单调递减；
- T+1 风控字段完整；
- 禁止 T 日新仓当日卖出表述；
- 09:35/09:40 状态迁移合法性；
- 数据警告与降级一致性。

### 9.2 必须补充的自动化测试

使用固定 fixture，不依赖实时网络。

#### 时间边界

- 09:34:59 不得读取 09:35 完整 K；
- 09:35:05 只能读取第一根完整 K；
- 09:36 不得读取标记为 09:40 的未完成 K；
- 午间休市和下午时段正确处理。

#### 信号

- `first_bar_red_flag` 只来自首根 K；
- 最新完整 K 与首根 K 分离；
- VWAP 缺失触发降级；
- 高开回落计算使用昨收作为缺口基准；
- 不完整成交量不参与放量确认。

#### 分类

- `NO_NEW_BUY` 下不存在 A/B；
- theme failed 时不存在 A；
- 数据 warning 不得升级；
- B 不得由 LLM 升 A；
- 仓位不得超过盘前预算；
- D 在后续快照不得升级。

#### T+1

- 新仓必须有 T+1 退出计划；
- 当日“跌破即卖”文案校验失败；
- 买入前取消条件与买入后风险提示分离。

---

## 十、故障与降级策略

| 故障 | 系统动作 |
|---|---|
| strategy 缺失或校验失败 | 停止，不生成操作建议 |
| mapper 覆盖不完整 | 停止，不允许部分猜测 |
| 指数数据缺失 | `global_action=WAIT`，全部最高 B |
| 市场宽度缺失 | `global_action` 不得为 NORMAL |
| 个股行情缺失 | 该股 D |
| 分时 K 缺失 | 该股最高 C，除非仅观察 |
| 主题宽度缺失 | 相关股票最高 B |
| 快照时间异常 | 整体失败，不使用旧快照冒充当前数据 |
| 09:40 运行失败 | 维持 09:35 上限，不自动升级 |
| 上游 run_id 不一致 | 标记 stale，停止执行 |

---

## 十一、实施阶段

### P0：修复执行正确性

目标：让现有 `intraday-operation-guide` 可以安全承担 09:35 确认。

- [ ] 只使用完整 5 分钟 K；
- [ ] 修复 `first_bar_red_flag`；
- [ ] 增加 snapshot schema、snapshot slot 和数据延迟；
- [ ] 增加实时三指数与 `regime_live`；
- [ ] 增加 `global_action`；
- [ ] 脚本输出 `mechanical_class/max_allowed_class`；
- [ ] 仓位不得超过盘前预算；
- [ ] 修正 T+1 风控文案；
- [ ] 增加 snapshot/decision 验证器；
- [ ] 增加核心 fixture 测试。

验收：7 月 10 日样本重放时，市场确认能够降级，且不会输出扩大仓位的 A 类建议。

### P1：升级盘前条件契约

- [ ] `strategy.json` 升级为 v2；
- [ ] 增加 `regime_prior`；
- [ ] 增加 `preopen_plan`；
- [ ] 增加最早/最晚执行时间；
- [ ] 增加市场、主题和个股确认条件；
- [ ] 增加组合预算；
- [ ] 增加 T+1 退出计划；
- [ ] 更新两个 Skill 文档和下游消费者。

验收：盘前策略不再包含默认 09:30 无条件买入；所有推荐都能由操作层机械判断是否满足。

### P2：主题宽度与多快照状态机

- [ ] 增加主题实时宽度；
- [ ] 保存 09:35、09:40、09:45 独立快照；
- [ ] 实现类别状态迁移；
- [ ] 增加相对上一快照的变化；
- [ ] 增加 `operation_decision.json`；
- [ ] 增加人工执行日志。

验收：能够回答某笔操作是何时、因何从 B 升 A，或从 A 降 D。

### P3：前向验证与规则治理

- [ ] 固定版本运行至少 20 个交易日；
- [ ] 建立 09:30/09:35/09:40 对照；
- [ ] 统计 T+1 真实执行收益；
- [ ] 加入交易成本和成交可得性；
- [ ] 形成规则候选、审核、启用和退役流程；
- [ ] 达到样本门槛后再调整真实规则。

验收：二次确认相对 09:30 基线在期望收益、最大回撤或尾部损失上至少有一个稳定、可复现的改进，且其他核心指标没有不可接受的恶化。

---

## 十二、完成定义

当以下条件全部满足时，可以把系统称为“可行的早盘推荐系统”而不仅是研究报告生成器：

1. 09:20 启动并在 09:29 前稳定生成盘前策略；
2. 盘前策略全部为条件化计划；
3. 09:35 和 09:40 使用完整 K 线生成确认；
4. 市场、主题、个股三层确认均由结构化数据支撑；
5. A/B/C/D 存在机械上限，LLM 不能越权升级；
6. 所有仓位不超过盘前和组合预算；
7. 所有新仓遵守 T+1 风控语义；
8. 每笔推荐都能追溯到盘前策略、确认快照和最终决策；
9. 实际执行和未执行原因可记录；
10. 至少一个冻结版本完成前向样本验证；
11. 系统表现用可成交的 T+1 收益和组合风险评价，不再只看方向命中率；
12. 数据缺失、超时和状态冲突能够自动降级或停止，而不是继续生成看似完整的操作建议。

---

## 十三、推荐的首个开发切片

第一轮不应同时实现全部功能。推荐先完成一个可在历史样本上验收的最小闭环：

1. 修复完整 K 线选择；
2. 修复首根 K 信号；
3. 为快照加入三指数实时状态；
4. 加入 `global_action`；
5. 由脚本给出 `max_allowed_class`；
6. 禁止仓位扩张；
7. 修正 T+1 风控表达；
8. 用 2026-07-08、2026-07-09、2026-07-10 三天数据做 fixture 重放；
9. 确认 7 月 10 日能够被市场级闸门降级；
10. 再开始 `strategy.json v2` 和主题宽度建设。

这一顺序优先解决“二次确认是否可信”，然后再扩展盘前契约，能够最快降低真实使用风险。
