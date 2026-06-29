---
name: intraday-strategy
description: >
  Generate tail-position trading strategy from V5 intraday_mapper.md.
  Step 3 is the REASONING layer — consumes Step 2 Computed Perception,
  produces Direction / RiskSeverity / Tail Action / Tomorrow Expectation
  via structured ReasoningTrace. Morning strategy is read ONLY for optional
  Prediction Review (Audit, after reasoning, never input).
---

# Intraday Tail Strategy (V5 Reasoning)

Loaded by trading-strategist when dispatched for intraday strategy generation.

## V5 架构角色

```
Compute (Python)
    ↓
Perception (Step 2 — intraday_mapper.md)
    ↓
Reasoning (Step 3 — this skill ← 你在这里)
    ↓
Decision (tail_strategy.md formatting)
    ↓
Prediction Review (Audit — Morning 对照, 在 Reasoning 之后, 可选)
```

Step 3 is the sole Reasoning Layer. It produces Direction / RiskSeverity /
OverrideHint application / Tail Action / Tomorrow Expectation.

## V5 Invariants

| Invariant | Step 3 含义 |
|-----------|------------|
| 1. Minimal Inference Whitelist | 不越界做 perception — 不重做 Tradeability/OvernightScore/TailFlow 分类 |
| 2. Unidirectional Info Flow | 不重读 market_snapshot.md — 仅从 intraday_mapper.md 取 perception |
| 3. Execution 永不新增信息 | tail_strategy.md 严格消费 Step 3 Reasoning 输出 |
| 5. Python 嵌套 Schema | 读 `comp.value` / `comp.conf` / `tech.value` / `tech.conf` 等前缀列 |

## Workflow

```
Inputs:
  Date:           provided in prompt (YYYY-MM-DD)
  Mapper:         predict/{date}/intraday_mapper.md   (Step 2 V5 output, 7 sections)
  SharedRules:    memory/SHARED_RULES.md              (通用规则, LLM 语义匹配)
  IntradayRules:  memory/INTRADAY_RULES.md            (尾盘规则, LLM 语义匹配)
  MorningStrat:   predict/{date}/strategy.md          (可选 — 仅 for Prediction Review, 不存在则跳过)
```

1. Read `intraday_mapper.md` **Market State** — DominantThemes, Breadth, CapitalDirection
2. Read `intraday_mapper.md` **Candidate Pool** — Tradeability, OvernightScore, TailFlow, comp, tech, pattern.*, risk_type, anomaly, RoleTags
3. Read `intraday_mapper.md` **Strategy Inputs** — Price (Live), PriceSource, MA20, MA5, ATR, ATR%, High20, Low20
4. Fetch market indices via `fetch_stock.py sh000001,sz399001,sh000688 --json` — 评 RegimeHint
5. Read `memory/SHARED_RULES.md` + `memory/INTRADAY_RULES.md` 全文 — LLM 语义匹配
6. **对每个 Candidate Pool stock 执行 Intraday Reasoning Flow**
7. Generate `tail_strategy.md` (含 ReasoningTrace + PredictionReview)

---

## Intraday Reasoning Flow (per stock)

V5 Step 3 per-stock reasoning:

### Step 3-A — RegimeHint (per market, once)

| RegimeHint | 条件 (14:30 实时) |
|-----------|------|
| `panic` | 上证实时 < -1.5% |
| `weak` | -1.5% ~ -0.5% |
| `neutral` | ±0.5% |
| `strong-sector` | neutral index BUT dominant theme heat ≥ 85 OR 科创50 > +2% |

### Step 3-B — Direction 推理 (per stock)

```
1. 读 comp.value → DirectionBase 倾向:
   ≥ 70 → bullish
   55-69 → neutral-bull
   45-54 → neutral
   < 45 → bearish

2. 读 Tradeability (Step 2 已分类):
   Suitable → Direction 维持
   Watch → Direction 维持但 confidence 降一档
   Extended → Direction cap at neutral-bull
   Avoid → Direction force to bearish (override composite)

3. 读 risk_type.value → 评 RiskSeverity (Step 3-C)

4. 读 SHARED_RULES + INTRADAY_RULES → 语义匹配应用 → 记 ReasoningTrace

5. Final Direction ∈ {bullish, neutral-bull, neutral, bearish}
```

### Step 3-C — RiskSeverity 评定

| RiskType + Regime | Severity | 处理 |
|-------------------|:--------:|------|
| `trend_weak` + (weak/panic) | **3** | Tradeability→Avoid |
| `trend_weak` + strong-sector | **2** | Tradeability→Watch |
| `overbought` + strong-sector | **1** | 不回避 (SHARED R37) |
| `overbought` + (weak/neutral) | **2** | caution |
| `broken_board` + weak | **3** | Tradeability→Avoid |
| `broken_board` + strong-sector | **2** | Watch |
| 多 flag 并存 | max(severity) | 逐 flag ReasoningTrace |

**Intraday-specific severity modifiers:**
- Extension (I04) 触发 → severity +1
- TailFlow = Outflow → severity +1
- OvernightScore < 60 → severity = 3 (无论其他条件)

### Step 3-D — Entry Plan Generation (V1.1 替代旧 Tail Action 矩阵)

Call `compute_entry_plan.py` for concrete prices + Tail Action:

```bash
python .opencode/skills/daily-stock-mapping/scripts/compute_entry_plan.py \
  <codes> --session intraday \
  --profile predict/{date}/strategy.md \
  --indicators predict/{date}/pool_indicators.json \
  --intraday-data predict/{date}/intraday_features.json \
  --json
```

Entry Plan outputs per stock: `can_execute`, `buy_lo`/`buy_hi`, `anchor`, `entry_mode`, `stop`, `position`, `tail_action`, `profile_match`, `profile_note`.

LLM then:
1. Validates ProfileMatch (Aligned / Degraded / Invalidated / New)
2. Confirms or overrides EntryMode with reasoning
3. Writes Tomorrow Expectation per I06
4. **Does NOT** hand-write prices (prices come from script)

---

## Output: tail_strategy.md

### Structure

1. **Market Context** (inline)
   - 上证/深证/科创50 14:30 实时
   - RegimeHint + 市场状态

2. **Tail Position Table** (max 8, min 0 — 允许空仓)

```markdown
| # | 代码 | 名称 | 主题 | 可交易性 | 画像匹配 | 尾盘操作 | 买入区间 | 锚点价 | 入场方式 | 止损 | 仓位 | 次日预期 |
|---|------|------|------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|
| 1 | sh603986 | 兆易创新 | AI算力 | 可布局 | 一致 | 推荐 | 745~752 | 尾盘均价≈748 | 尾盘试仓 | 738 | 1.5% | 高 |
| 2 | sz000977 | 浪潮信息 | AI算力 | 观察 | 降级 | 等待 | — | — | 等待 | — | — | 中等 |
```

**锚点价**: `MA20≈价格` / `MA5≈价格` / `尾盘均价≈价格` / `开盘价≈价格` / `VWAP≈价格`
**入场方式枚举**: `限价入区` / `开盘试仓` / `尾盘试仓` / `市价执行` / `等待` / `不追`
**画像匹配枚举**: `一致` / `降级` / `失效` / `新发现`
**尾盘操作枚举**: `推荐` / `轻仓` / `等待` / `不追` / `跳过`
**次日预期枚举**: `高` / `中等` / `低` / `风险`

3. **ReasoningTrace** (per stock)

```markdown
| 代码 | 方向路径 | 规则应用 | 风险追溯 | 画像追溯 |
|------|----------|----------|----------|----------|
| sh603986 | 88.5→看多; profile=追涨→尾盘试仓 | SHARED R37: 强市超买豁免 | 超买+强市=1 | 追涨+尾盘均价≈748→一致 |
```

**风险追溯 (SeverityTrace) 格式**: `{风险类型}+{市态}={等级}`<br>
**风险类型枚举**: `超买`(overbought) / `趋势弱`(trend_weak) / `炸板`(broken_board) / `超卖机会`(oversold_opportunity)<br>
**市态枚举**: `强市`(strong-sector) / `中性`(neutral) / `弱市`(weak) / `恐慌`(panic)<br>
**等级**: `1`(观察) / `2`(谨慎) / `3`(规避)<br>
**画像追溯 格式**: `{打法}→{锚点价}→{匹配状态}`<br>
**打法枚举**: `追涨`(MOMENTUM) / `低吸`(PULLBACK) / `打板`(LIMIT_UP_CONT) / `防守`(DEFENSIVE) / `观望`(WATCH_ONLY)

4. **Prediction Review** (Audit, optional — after reasoning)

```markdown
| 早盘排名 | 代码 | 名称 | 早盘方向 | 当前排名 | 当前操作 | 状态 |
|:---:|------|------|:---:|:---:|------|------|
| 1 | sh603986 | 兆易创新 | 看多 | 1 | 推荐 | 增强 |
| 2 | sz000977 | 浪潮信息 | 看多 | 5 | 等待 | 失效 |
| — | szxxxxxx | xxx | — | 2 | 推荐 | 新出现 |

Deletion fallback: 若 strategy.md 不存在 → 输出 "Prediction Review: N/A (Morning pipeline 未执行)"
```

## Coverage & Scope

- All Candidate Pool stocks with comp.value ≥ 55
- Maximum 8 tail-position recommendations
- Minimum 0 (允许空仓)
- All prices from `compute_entry_plan.py` — **禁止手写价格**

## Rules Integration

- **BEFORE** generating → READ SHARED_RULES.md + INTRADAY_RULES.md 全文
- **AFTER** generating → append entry to `memory/daily/INDEX.md`

## Red Flags — STOP and Fix

| Symptom | Fix |
|---------|-----|
| Tail Action column missing or hand-written | Must come from `compute_entry_plan.py` output. |
| Buy Zone hand-calculated instead of script output | **Violation**. Prices come from script only. |
| ProfileMatch not documented | Add. Must show Aligned/Degraded/Invalidated/New. |
| Entry Plan not run | Run `compute_entry_plan.py --session intraday` before writing tail_strategy.md. |
