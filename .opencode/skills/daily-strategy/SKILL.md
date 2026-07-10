---
name: daily-strategy
description: Generate daily trading strategy from V5 mapper.strategy_view.json. Used as Step 3 of daily-market-analysis pipeline. Step 3 is the REASONING layer — consumes Step 2 Computed Perception, produces Direction / RiskSeverity / 历史规则应用 / Trade Profile via structured ReasoningTrace, then renders daily_report.html.
---

# Daily Strategy Generation (V5)

Loaded by the `portfolio-manager` subagent when dispatched for pipeline strategy generation.

## V5 架构角色

```
Compute (Python)
    ↓
Perception (Step 2 — mapper.json -> mapper.strategy_view.json)
    ↓
Reasoning (Step 3 — this skill ← 你在这里)
    ↓
Decision (Execution — strategy.json + daily_report.html)
```

Step 3 不只是“在 Direction 内交易” — Step 3 **是 Direction 的产生者**。V5 把 Direction / RiskSeverity / OverrideHint 应用从 Step 2 拿回 Step 3。V4-U 越权由 Step 2 算 Direction 的设计在 V5 已废止。

---

## V5 Invariants（Step 3 必须遵守）

| Invariant | Step 3 含义 |
|-----------|------------|
| 1. Minimal Inference 白名单 | Step 3 不越界做 perception — 不重做主题匹配、不重算 tech_score、不重映射 R×P cell |
| 2. Unidirectional Information Flow | 默认不重读新闻全集；仅在 3 类 Conditional Reread 触发时按 `NewsLink=news#<id>` 回查 `news.json` 单条 |
| 3. Execution 永不新增信息 | HTML 阅读层严格消费 JSON 输出；不自行加仓 / 改 stop |
| 4. 白名单修改需 Regression Audit | V5+ 修订白名单须 30 日命中回测 — Phase 5 companion 阶段绑定 |
| 5. Python 嵌套 Schema | Step 3 读 `candidates[*].scores.*` / `pattern.*` / `strategy_inputs` 等 JSON fields |

---

## Workflow

```
Inputs:
  Date:       provided in prompt (YYYY-MM-DD)
  StrategyView: predict/{date}/mapper.strategy_view.json (Step 3 compact input, daily_strategy_input.v1)
  Mapper:     predict/{date}/mapper.json    (full Step 2 V5 source contract, daily_mapper.v1)
  Rules:      memory/RULES.md + memory/SHARED_RULES.md  (LLM 全文语义匹配)
  Indicators: predict/{date}/pool_indicators.json       (V5 nested, for compute_trade_profile.py)
  News:       predict/{date}/news.json      (仅按 news#<id> Conditional Reread 单条回查)
```

**If `pool_indicators.json` does not exist** — generate it with the Step 2 script (**NOT** `lib/fetch/fetch_indicators.py`):

```bash
python .opencode/skills/daily-stock-mapping/scripts/fetch_pool_indicators.py <code_1>,<code_2>,... --json -o predict/{date}/pool_indicators.json
```

`fetch_pool_indicators.py` produces V5 nested format `[{code, raw_observation, computed_perception}, ...]`.
Do **NOT** use `lib/fetch/fetch_indicators.py` — it outputs K-line time-series without `code` fields, incompatible with `compute_trade_profile.py`.

1. Validate `mapper.json`, then build/read the compact Step 3 view:
   ```bash
   python .opencode/skills/daily-stock-mapping/scripts/validate_mapper_json.py --date {date}
   python .opencode/skills/daily-stock-mapping/scripts/build_strategy_view.py --date {date}
   ```
2. Read `mapper.strategy_view.json` **market_state** — dominant themes, board policy, financing flow, risk flags
3. Read `mapper.strategy_view.json` **candidates** — `scores.*`, `major_event`, `risk_type`, `pattern`, `anomaly`, `news_link`, `role_tags`
4. Read `mapper.strategy_view.json` **candidates[*].strategy_inputs** — Price, PriceSource, MA20, MA5, ATR, ATR%, High20, Low20 (**authoritative projection from mapper.json**)
5. If `mapper.strategy_view.json` is missing but `mapper.json` exists, build it with `build_strategy_view.py`; if both JSON files are missing, stop and fix Step 2
6. Fetch market indices via `fetch_stock.py sh000001,sz399001,sh000688 --json` — 评 RegimeHint
7. Read `memory/RULES.md` + `memory/SHARED_RULES.md` 全文 — LLM 语义匹配
8. **Generate Trade Profiles** via `compute_trade_profile.py` — per-stock 交易策略 + 入场条件 (§ Trade Profile Generation)
9. **对每个 Candidate Pool stock 执行 Reasoning Flow**（见 § Reasoning Flow）
10. Generate `predict/{date}/strategy.json` — machine-readable strategy data for review/backtests
11. Validate `strategy.json` with `validate_strategy_json.py`
12. Render `predict/{date}/daily_report.html` with `render_daily_report_html.py`

---

## Reasoning Flow (per stock)

V5 Step 3 对每个 Candidate Pool stock 按 4 步推理：

### Step 3-A — Conditional Reread 判定（先于此处）

默认**不扫描**新闻全集。检查三类触发条件：

| 触发条件 | 判据 | 回读范围 |
|---------|------|---------|
| Anomaly 存在 | row.anomaly != "—" 且非空 | `NewsLink` 指向的 `news.json` 单条 item |
| 低 Confidence | 任一 `comp.conf`, `tech.conf`, `th_heat.conf`, `news_imp.conf` < 60 | `NewsLink` 指向的 `news.json` 单条 item |
| 硬矛盾 | 下三条之一成立 | `news.json` 单条 item + cross_rank highlights 复核 |

**三条 Hard Contradictions（机器可判）**：
1. `th_heat.value ≥ 80 AND tech.value < 40`（主题高热但个股技术面极弱）
2. `maj_ev.pol = "Positive" AND comp.value < 50`（公司利好但综合分极低）
3. `auc_change_pct > +3% AND news_imp.value < 40`（竞价强但新闻关联弱）

**严禁**：扫描完整 `news.json` 或 `news.md` 重新做主题映射（违反 Invariant 2）。

若任一触发：从 `news.json.items` 回读 `NewsLink=news#<id>` 指向的单条新闻（仅此一条），并在 `ReasoningTrace.RereadTriggered` 写明：触发条件 / 回读结果（≤30 字）。

### Step 3-B — RegimeHint 评定（per market 一次）

读 fetch_stock.py 返回的上证 / 科创 50：

| RegimeHint | 条件 |
|-----------|------|
| `panic` | 上证竞价 < -1.5% |
| `weak` | -1.5% ~ -0.5% |
| `neutral` | ±0.5% |
| `strong-sector` | neutral index BUT dominant theme heat ≥ 85 OR 科创50 > +2% |

RegimeHint 是 Step 3 独有的 reasoning 输出（不在 mapper.json 中）。

### Step 3-C — Direction 推理（per stock）

V5 Step 3 **必须自算 Direction**（V4-U 的 DirectionBase/Final 已删除）。

输出到 `strategy.json.stocks[*].direction` 时使用中文枚举：`看多` / `偏多` / `中性` / `看空`。

```
1. 读 comp.value (Python 已给)
   └─ 使用 DirectionBase 阈值表：
      >= 70 → 看多 倾向
      55-69 → 偏多 倾向
      45-54 → 中性 倾向
      < 45 → 看空 倾向

2. 读 comp.conf
   └─ 若 < 60: Direction ConfidenceFlag=True (考虑警告)
   └─ 若 < 30: Direction 维持倾向 但加 "低置信" tag

3. 读 risk_type.value (list, e.g., ["overbought"])
   └─ Step 3 评 RiskSeverity (见 Step 3-D)

4. 读 maj_ev.pol
   └─ Positive: Direction +1 level (cap 看多)
   └─ Negative: Direction -1 level (cap 看空)
   └─ Neutral: no shift

5. 评 RiskSeverity (Step 3-D)
   └─ RiskSeverity = 3 AND RegimeHint not strong-sector → cap at 偏多
   └─ RiskSeverity = 2 → no auto cap; 记 ReasoningTrace
   └─ RiskSeverity = 1 → no cap; 记 ReasoningTrace

6. 读 RULES.md 全文，若匹配场景则应用并记 ReasoningTrace

7. Clamp to [看空 .. 看多]
   └─ 最终 Direction ∈ {看多, 偏多, 中性, 看空}

8. DirectionPivot 检查（见下）
```

**DirectionBase 阈值表**（V5 Step 3 参考，非硬约束）：

| comp.value | 倾向 (DirectionBase) |
|-----------|---------------------|
| >= 70 | 看多 |
| 55-69 | 偏多 |
| 45-54 | 中性 |
| < 45 | 看空 |

阈值是参考框架；Step 3 据完整 Context（confidence + pattern + risk_type + Regime + MajorEvent）综合判定 Direction final。允许偏离 DirectionBase 但必须写理由（ReasoningTrace）。

**DirectionPivot**（V5 新增）：如果 `anomaly` 非空且 LLM 判定 anomaly 暗示 Base 阈值不够（如"龙头断板但板块未退潮" → 即使 comp 在 50-55 中性区，仍可升 Direction 一档 看多）— 必须在 ReasoningTrace 写 "DirectionPivot: anomaly-driven +1 level; reason=..."。

### Step 3-D — RiskSeverity 评定

读 `risk_type.value` (list) + RegimeHint 评 severity：

| RiskType + Regime | Severity | 理由 |
|-------------------|:--------:|------|
| `trend_weak` + (weak/panic/neutral) | **3** | 结构性弱势，硬压 |
| `trend_weak` + strong-sector | **2** | 大盘强势下 trend_weak 降级 |
| `overbought` + strong-sector | **1** | 强市场 RSI 超买 — 仅 informational，视为机会 hint 非风险 |
| `overbought` + (weak/neutral) | **2** | caution |
| `oversold_opportunity` + any | **1** | 深超卖是机会 hint, 非 risk |
| `broken_board` + strong-sector | **2** | caution; R39/R35 watch |
| `broken_board` + weak | **3** | 弱市场炸板危险 |
| `auction_anomaly` + any | **2** | caution |
| 多 flag 并存 | 取 max(severity) | 但 ReasoningTrace 必须逐 flag 记录 |

**Severity 应用到 Direction（Step 3-C 第 5 步）**：
- Severity 3: cap Direction at `neutral-bull`（若 RegimeHint != strong-sector）
- Severity 2: no cap; 记 ReasoningTrace
- Severity 1: no cap; 记 ReasoningTrace

### Step 3-E — Trade Profile（V1.2 per stock）

Direction 评定后，调用 `compute_trade_profile.py` 为每只非 bearish 标的生成 Trade Profile：

| 参数 | 类型 | 说明 |
|------|------|------|
| `codes` | str | 逗号分隔股票代码 |
| `--regime` | enum | 市场状态: `panic` / `weak` / `neutral` / `strong-sector` |
| `--from-indicators` | path | pool_indicators.json 路径 |
| `--json` | flag | 输出 JSON 数组 |
| `--mainline` | flag | 该批次股票是否为主线标的 |
| `--sector-heat` | float | 板块热度 0-100（主线时传入） |
| `--kcb-pct` | float | 科创50涨跌幅%（MOMENTUM 时传入） |
| `--sector-pct` | float | 板块涨跌幅%（MOMENTUM 时传入） |
| `--open-pct` | float | 开盘竞价涨跌幅%（可选，9:25+ 可用时传入） |
| `--yesterday-limit-up` | flag | LIMIT_UP_CONT 候选时传入 |

```bash
python .opencode/skills/daily-strategy/scripts/compute_trade_profile.py <codes> --regime <RegimeHint> --from-indicators predict/{date}/pool_indicators.json --json
```

LLM then:
1. Validates 交易策略 against Pattern 5-dim states
2. Applies RULES semantic matching for 交易策略/入场条件 overrides
3. Confirms or adjusts Profile fields
4. **Does NOT** produce Buy Zone / Stop / Target (Entry Plan territory)

## PerceptionOverride Mechanism (V5 新增)

Step 3 在严格条件下可异议 Step 2 perception 字段。**非默认行为，必须有 audit**。

### 可 override 字段白名单

- `news_imp.value`, `news_imp.conf`
- `maj_ev.pol`
- `pattern.heat.state`, `pattern.leader.state`, `pattern.auction.state`, `pattern.rotation.state`, `pattern.volume.state`
- `anomaly`

**不可 override 字段**：

- `th_heat`, `comp`（Python 算）
- `tech_score`（Python 算）
- `risk_type`（机器查表）
- 任何 `raw_observation.*`（Python 取值）

### Override 触发条件

仅允许在 Perception 不一致 + Conditional Reread 触发了之后：
- Anomaly reread 后发现新闻与 step 2 Perception 不一致
- 硬矛盾 reread 后 Step 3 认定 Step 2 perception 误判

**严重 White-list 违规**：不可因 "Step 3 自己觉得" 没 reread 触发就 override。

### Override 输出格式（在 ReasoningTrace 中）

```markdown
| Field | Old | New | Reason | NewConfidence |
|-------|-----|-----|--------|---------------|
| news_imp.value | 70 | 95 | reread news#3 发现公司直接被点名于标题，原 R2 误判应 R4 | 90 |
```

### Override 率监控

- 单日 override / candidate_pool_size ≥ 15% → trigger V6 perception rubric 复审
- 单字段 override 率滚动 30 日 > 30% → 该字段 rubric 失效（Phase 5 companion 阶段绑定）
- T+1 验证：T+1 收盘后验 override 方向 vs 实际市场表现；命中率 < 50% 则抑制该字段 override 权限

---

## Market Context Fetch

Fetch 3 index quotes in a single batch call (fast, ~3s):

```bash
python .opencode/lib/fetch/fetch_stock.py sh000001,sz399001,sh000688 --json
```

| Index | Code | Purpose |
|-------|------|---------|
| 上证指数 | sh000001 | 大盘方向（全市场情绪）/ RegimeHint 主输入 |
| 深证成指 | sz399001 | 深圳市场水位 |
| 科创50 | sh000688 | 科技权重指标（结构性强度 / strong-sector 判定关键） |

Compute signals:

| Signal | Calculation | Interpretation |
|--------|-------------|----------------|
| **大盘方向** | sh000001.percent | >+0.5%=强, ±0.5%=震荡, <-0.5%=弱, <-1.5%=恐慌 |
| **结构性强度** | sh000688.percent - sh000001.percent | >2%=科技主线虹吸 |
| **成交水位** | from news.md market overview | ≥2万亿=活跃, 1-2万亿=正常, <1万亿=冷清 |

**Timing note**：MUST NOT run fetch before 09:25:10. Must sleep until 09:25:10 if entered earlier (`time.sleep(seconds_until)`).

---

## Market State → Parameter Adjustment

Use signals computed above + mapper Market State (DominantThemes, RiskFlags, FinancingFlow) + Step 3 评定的 RegimeHint：

| 市场状态 | 仓位系数 | 止损倍数 | 推荐标的数 | 非主线处理 |
|---------|:---:|:---:|:---:|------|
| 强市 + 放量 | ×1.0 | 1.5×ATR | 10只 | 可轻度参与(≤2只) |
| 震荡 | ×1.0 | 1.5×ATR | 10只 | 降权(≤1只) |
| 弱市(-0.5~-1.5%) | ×0.7 | 2×ATR | 7只 | 全部剔除 |
| 恐慌(<-1.5%) | ×0.5 | 2×ATR（放宽防洗） | 5只 | 全部剔除 |
| 极端分化(科创-上证>3%) | 主线×1.0 非主线×0.5 | 主线1.5× 非主线2× | 8只 | 只在主线板块选 |

Stop-loss widens in weak markets (2×ATR) to avoid noise stops, tightens in strong markets (1.5×ATR) to protect gains. **Systematic — no LLM ad-hoc judgment**.

---

## Trade Profile Generation (V1.2)

For each stock in Candidate Pool with `comp.value >= 55` and `Direction != bearish`,
generate a **Trade Profile** — not a price. Trade Profile defines "how to trade this stock"
(交易策略, 入场条件, position budget).

### Script Call

参数同上 § Step 3-E 参数表。按以下条件追加额外参数：
- `mainline` 标的：追加 `--mainline --sector-heat <heat>`
- MOMENTUM 候选：追加 `--kcb-pct <pct> --sector-pct <pct>`
- LIMIT_UP_CONT 候选：追加 `--yesterday-limit-up`

```bash
python .opencode/skills/daily-strategy/scripts/compute_trade_profile.py \
  <code_1>,<code_2>,...,<code_N> \
  --regime <RegimeHint> \
  --from-indicators predict/{date}/pool_indicators.json \
  --json
```

### 交易策略决策 (LLM confirms/overrides Python output)

Python `compute_trade_profile.py` produces a default Profile based on regime + position_state.
Step 3 LLM reads the Profile JSON, then:

1. Validates: does the entry profile match Pattern 5-dim states?
2. Applies RULES semantic matching for overrides
3. Confirms or adjusts: 交易策略, 入场条件
4. **Does NOT produce** Buy Zone / Stop / Target (these are Entry Plan territory)

### Trade Profile Fields

| Field | Type | Meaning |
|-------|------|---------|
| `entry_profile` | enum | 交易策略: `趋势跟随` / `回调布局` / `强势接力` / `防御布局` / `暂不参与` |
| `entry_trigger` | str | 入场条件: 简短定性描述 如 `开盘站稳MA5` / `回踩MA20` / `竞价确认` / `首根K线确认` |
| `position_budget` | float | 仓位预算上限 (e.g. 0.02 = 2%) |
| `time_horizon` | enum | 持仓意图: `T+0` / `T+1` / `SWING` |
| `ref_ma20` | float | 参考 MA20 |
| `ref_ma5` | float | 参考 MA5 |
| `ref_high20` | float | 参考 High20 |

### 交易策略 → 规则映射

| 交易策略 | 触发条件 | 隐含规则 |
|----------|---------|---------------|
| `趋势跟随` | 主线 + 科创50>2% or 板块>2.5% | R68 → 锚MA5, 开盘入场 |
| `强势接力` | 昨涨停 + 主线≥4★ | R35-v4 → 竞价确认追入 |
| `回调布局` | 震荡/弱市, PULLBACK state | 锚MA20, 等回踩 |
| `防御布局` | 弱市 but direction偏多 | 观测30min, 等待确认信号 |
| `暂不参与` | Extended / RiskSeverity≥3 | 当日不交易, 等Intraday or 次日 |

---

## Output: daily_report.html (Readable Daily Report)

Step 3 no longer writes `strategy.md`. The LLM writes `strategy.json`; scripts render the daily human-readable report from JSON:

```bash
python .opencode/skills/daily-strategy/scripts/render_daily_report_html.py --date {date}
```

The HTML is the daily decision report. It consumes `strategy.json`, `mapper.strategy_view.json`, `mapper.json`, optional `themes.json`, and canonical `news.json` references. It must not introduce new decisions or parse `news.md`.

### Structure

1. Top summary: date, RegimeHint, dominant themes, strategy count, total position budget, data health
2. Theme Map: `themes.json` if present; otherwise `mapper.strategy_view.json.themes`
3. Strategy Table: `strategy.json.stocks[*]` enriched with Step 2 scores from `mapper.strategy_view.json`
4. Stock Details: reasoning trace, Pattern, MajorEvent, Anomaly, Strategy Inputs, Trade Profile
5. Observation Pool and Excluded Stocks from `mapper.json`
6. Referenced News: only `news.json` items referenced by `NewsLink=news#<id>`

### 3 "super predictions"

从 Strategy 10 中选 3 个：
- 每个 from a **different sector**
- 每个有 clear Trade Profile (交易策略 + 入场条件)
- 至少有 1 个 Rating ≥ 4⭐

### Rating 评级

V5 Rating 是 Step 3 综合以下信号给的 1-5 ⭐：
- `comp.value` 高分加成
- `comp.conf` 高置信加成
- RiskSeverity 反向扣分
- Pattern 多维组合
- MajorEvent Polarity 加减
- 历史经验是否匹配当前场景
- Anomaly 中暗含的 setup
- **V1.2**: 交易策略 与 Pattern 的一致性 (如 pattern.heat=RISING + 趋势跟随 = 满档)

### Memory Integration

**BEFORE** generating → READ `memory/RULES.md` + `memory/SHARED_RULES.md` 全文

**AFTER** generating → append strategy entry to `memory/daily/INDEX.md`

### Red Flags — STOP and Fix

| Symptom | Fix |
|---------|-----|
| `strategy.json` contains `Buy Zone` / `Stop` / `Target` fields | **Remove**. Prices are Entry Plan (Intraday) territory. |
| Trade Profile missing from Candidate Pool stock with Direction != bearish | Add. All non-bearish stocks need a Profile. |
| `WATCH_ONLY` stock has position_budget > 0 | Fix. WATCH_ONLY = no position. |
| Profile not validated against Pattern 5-dim | LLM must validate 交易策略 against pattern.* states. |
| Step 3 hand-writes prices into Profile | **Violation**. Prices belong in Entry Plan only. |
| Strategy stock missing `anchor` or `no_buy_condition` | Add both. Intraday operation guide depends on them. |

---

## Output: strategy.json (Machine-Readable)

Write final Step 3 decisions to:

```text
predict/{date}/strategy.json
```

This JSON is consumed by daily review, backtests, and `daily_report.html`. Do not create ad-hoc conversion scripts from HTML; the LLM already has the final reasoning state, so emit JSON directly.

### Required Schema

```json
{
  "schema_version": "daily_strategy.v1",
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601 timestamp",
  "market": {
    "regime_hint": "panic|weak|neutral|strong-sector",
    "position_multiplier": 1.0,
    "stop_atr_multiplier": 1.5,
    "notes": "short market context"
  },
  "stocks": [
    {
      "code": "sz001309",
      "name": "德明利",
      "sector": "半导体",
      "direction": "看多",
      "rating": "5★",
      "entry_profile": "趋势跟随",
      "anchor": "MA5",
      "entry_trigger": "回踩MA5确认",
      "no_buy_condition": "跌破MA5后放量不能收回",
      "position_budget": 0.02,
      "horizon": "T+1",
      "rules_applied": ["R68", "R37"],
      "profile_trace": "趋势跟随→回踩MA5确认→R68一致",
      "reasoning": {
        "direction_path": "comp=79.8→看多; R68=MA5; final=看多",
        "risk": "—",
        "reread": "—",
        "override": "—"
      },
      "profile": {
        "playbook": "MOMENTUM",
        "preferred_anchor": "MA5",
        "chase_policy": "MA5_ONLY",
        "entry_window": "OPEN",
        "stop_policy": "ATR_1.5",
        "time_horizon": "T+1",
        "position_budget": 0.02,
        "invalidation": "板块涨幅<2%或科创50回落",
        "note": "R68 强势主线MA5基准",
        "ref_ma20": 754.22,
        "ref_ma10": null,
        "ref_ma5": 899.81,
        "ref_high20": 980.0,
        "max_extension_atr": 2.5
      }
    }
  ]
}
```

### Field Rules

- `stocks` contains the full Step 3 strategy stock list rendered into `daily_report.html`.
- `entry_profile` values: `趋势跟随` / `回调布局` / `强势接力` / `防御布局` / `暂不参与`.
- `anchor` values: `MA5` / `MA10` / `MA20` / `OPEN` / `VWAP` / `首根5min` / `FLEX` / `无` / `—`.
- `position_budget` is decimal fraction (`0.02` = 2%); use `0` for `暂不参与`.
- `profile` stores the Python default profile after LLM confirmation/override.
- Do not include final `BuyLo` / `BuyHi` / `Stop` / `Target`; those belong to Entry Plan.

### Validation

Always validate after writing:

```bash
python .opencode/skills/daily-strategy/scripts/validate_strategy_json.py predict/{date}/strategy.json
python .opencode/skills/daily-strategy/scripts/render_daily_report_html.py --date {date}
```

If validation fails, fix `strategy.json` before finishing Step 3. Do not generate temporary converter scripts.

---

## Migration: V4-U → V5 Step3

| V4-U Step3 行为 | V5 Step3 行为 |
|----------------|---------------|
| "Do NOT recompute Direction" — 接受 mapper Direction | **RECOMPUTE Direction** via Reasoning Flow |
| "Consume MajorEventFlag as-is" | Consume `maj_ev.pol` as input；may shift Direction per rule |
| 不评 RiskSeverity（沿用 Step 2） | **评 RiskSeverity** per § Step 3-D |
| OverrideHint 仅占位（V4-U） | **真应用** per 语义匹配 RULES.md 历史记忆 |
| 不扫描新闻全集 | Conditional lookup of one `news.json` item via 3 triggers + 3 hard contradictions |
| 无 PerceptionOverride | Override allowed for whitelisted fields with audit |
| 无 ReasoningTrace 输出 | **ReasoningTrace 强制结构化输出** |

**Backward compat**：V5 Step3 defaults to `mapper.strategy_view.json`, rebuilt from `mapper.json` when needed. If JSON inputs are missing, stop and fix Step 2; do not parse legacy Markdown.

---

## Open Questions（Phase 5 companion 阶段定）

1. Confidence 校准起点 +85 阈值是否强制
2. Confidence 校准起点 +85 阈值是否强制
3. Override T+1 验证机制落地形式（人工 vs 自动）
4. Regression Audit 30 日窗口命中口径
5. 跨股协同 Reasoning（如"主题内 3 只龙头同时炸板 → 该主题降级"）— V5 单股为主，跨股进 V6

---

## Summary

V5 Step 3 是 Reasoning Layer：
- **输入**：V5 mapper.strategy_view.json computed perception + Confidence + Pattern + Anomaly + Market Context + RULES.md
- **输出**：`strategy.json` + `daily_report.html`，包含 Direction + RiskSeverity + 历史规则应用 + Trade Profile(交易策略/入场条件) + ReasoningTrace + (可选) PerceptionOverride
- **核心规则**：Unidirectional Flow（不重读新闻）+ Override Audit（写 trace）+ RuleBind（apply 同时记 effect）
- **永远不做**：Execution 层补信息；扫描完整 `news.json` 或 `news.md` 重新映射主题；override 不可 override 字段（如 comp, tech_score）；ad-hoc 创造不在参数表内的止损
