---
name: intraday-strategy
description: Use when dispatched as Step 3 of intraday overnight pipeline. Consumes a deterministic mapper base, writes semantic annotations, and publishes validated intraday_mapper.json. This is the sole Reasoning layer.
---

# Overnight Strategy (Skill 3)

## Purpose

NOT finding today's strongest stocks. Finding stocks that have capital recognition today but haven't fully priced in — expected to have positive premium tomorrow.

This is the SOLE Reasoning layer. All Direction / RiskSeverity / Expected Premium outputs come from here. This step produces the final actionable output.

## Pipeline Role

```
Skill 2 → Enriched ComputePool + ThemeRanking
                    ↓
Skill 3 → Overnight Scoring + intraday_mapper.annotations.json → intraday_mapper.json (THIS)
                    ↓
[14:50 Execute Buy]
```

## Execute: Overnight scores (compute-owned)

In the normal orchestrated flow, `run_intraday_pipeline.py` already writes
`.cache/intraday/{date}/opportunity_pool.json`. Do **not** re-score if that file
exists for the date. Only if compute was skipped:

```bash
python .opencode/skills/intraday-strategy/scripts/score_overnight.py .cache/intraday/{YYYY-MM-DD}/compute_pool_enriched.json --opportunity-pool-size 30 --json -o .cache/intraday/{YYYY-MM-DD}/opportunity_pool.json
```

### Scoring Dimensions (V1.2 Percentile-Based, 9-Dim)

| Dimension | Weight | What it measures |
|-----------|:------:|-----------------|
| Theme Continuity | 18% | source_pool ordinal (limit_up/turnover/gain_range) blended with inflow sigmoid — **not** theme_ranking heat rank (known gap) |
| Capital Continuity | 18% | Main force net inflow vs pool peers (percentile) |
| Tail Strength | 14% | Price position within day range × volume ratio |
| Position Advantage | 9% | Gaussian sweet spot on change% (peak ~4%) |
| Risk Deduction | -10% | Soft penalty: high change%(≥9.5:+0.4,≥7:+0.2,≥5:+0.05), turnover(>25:+0.3,>15:+0.15,>10:+0.05), limit_up source(+0.15) |
| Intensity | 9% | Capital efficiency: main_net_inflow / turnover |
| Conviction | 9% | super_large_net / \|main_net_inflow\| |
| Consistency | 5% | 4-tier capital directional alignment |
| Trend Quality | 8% | Bollinger zone + MA alignment + volume ratio |

Score = Σ(percentile × weight) [I10 may scale capital-family contributions], range 0–100 (`absolute_score`).

Rank tiers (`classify_rank_tier`, pool rank percentile only):
A = top 10% (Leader Watch), B = top 10–40% (Premium), C = top 40–70% (Early), D = rest.
Do not use 75/60/45 as hard tier cuts. Compatibility field `tier` == `rank_tier`.

**Rank tier is not Tradeability.** Suitable/Watch/Extended/Avoid is a separate Reasoning output (`tradeability`). Never map A→Suitable or B→Watch mechanically. Zero Suitable is allowed; threshold changes belong to a later backtest plan.

**Important:** V1.2 uses rule-based initial weights. Calibration is out of scope for dual-truth convergence.

## JSON-first output contract

First run `build_intraday_mapper_base.py`. Generate only
`intraday/{YYYY-MM-DD}/intraday_mapper.annotations.json`; never copy numeric
compute fields into it. The required schema is:

```json
{
  "schema_version": "intraday_mapper_annotations.v1",
  "date": "YYYY-MM-DD",
  "market_assessment": {
    "regime_hint": "string",
    "tomorrow_expectation": "string",
    "risk_severity": "low|medium|high|critical",
    "reasoning_trace": "string"
  },
  "stocks": [{
    "code": "sh600000",
    "sector": "string",
    "tradeability": "Suitable|Watch|Extended|Avoid",
    "direction": "持有偏多|持有|谨慎持有|观望",
    "trading_strategy": "趋势跟随|回调布局|强势接力|防御布局",
    "risk_severity": "low|medium|high|critical",
    "expected_premium": "string",
    "key_reason": "string",
    "position_plan": "string",
    "t_plus_1_exit_plan": "string",
    "t_plus_1_plan": {
      "auction_condition": "string",
      "open_strategy": "string",
      "stop_loss_basis": "day_low|ma5|ma10|ma20|not_applicable",
      "take_profit": "string"
    },
    "rules_applied": ["I01"],
    "reasoning_trace": "string"
  }],
  "strategy": {
    "position_cap": "string",
    "risk_control": ["string"],
    "execution_window": "14:50-14:57"
  }
}
```

`stop_loss_basis` is the only stop-loss field authored by the LLM. The mapper
builder resolves `stop_loss_price` and readable `stop_loss` from the same
stock's compute-owned quote/technical fields. The LLM must never transcribe a
stop-loss number. Observation-only stocks use `not_applicable`.

Then run:

```bash
python .opencode/skills/intraday-strategy/scripts/validate_intraday_mapper_annotations.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/build_intraday_mapper_json.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/validate_intraday_mapper_json.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/build_overnight_strategy_json.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/validate_overnight_strategy_json.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/render_overnight_strategy_html.py --date {YYYY-MM-DD}
```

The following seven headings describe logical data groups in the final JSON.

### 1. Market State
Copy from Skill 1 output — indices, breadth, capital direction, Theme Dashboard (top 10 by Composite rank).

### 2. Theme Ranking
Copy from Skill 2 output — statistical theme ranking, top 10. Heat scores with breakdown.

### 3. Tomorrow Opportunity Pool

| 级别 | 含义 | 操作 |
|------|------|------|
| A: Leader Watch | 真正龙头 | 观察，不一定买 |
| B: Premium Candidates | 最值得隔夜持有 | 系统主要推荐 |
| C: Early Breakout | 刚启动位置低 | 补涨机会 |

Table per tier:
```
| Code | Name | Theme | Score | Change | Expected Premium | Key Reason |
```

### 4. Stock Details
For each B-tier stock (most important section):
- Full score breakdown (9 dimensions)
- Money flow: main/super_large/large/medium/small
- Position analysis: price vs VWAP, within day range
- QuickScore (from Skill 1)

### 5. Overnight Score Trace
Show the formula with actual values:
```
Stock [code] [name]:
  Theme:        [x]/100 × 0.18 = [weighted]
  Capital:      [x]/100 × 0.18 = [weighted]
  Tail:         [x]/100 × 0.14 = [weighted]
  Position:     [x]/100 × 0.09 = [weighted]
  Intensity:    [x]/100 × 0.09 = [weighted]
  Conviction:   [x]/100 × 0.09 = [weighted]
  Consistency:  [x]/100 × 0.05 = [weighted]
  TrendQuality: [x]/100 × 0.08 = [weighted]
  Risk:        -[x]/100 × 0.10 = -[weighted]
  ─────────────────────────────────
  OVERNIGHT: [total]/100 — Tier [A/B/C]
```

### 6. Observation Pool
Stocks in Compute Pool near threshold (score 42-44, tier D but close to C). Include reason for exclusion.

### 7. Excluded Stocks
Stocks that were in Compute Pool but scored < 45 with clear reason (e.g., "净流出", "涨幅>9%追高风险", "换手>25%").

## Memory Integration

### BEFORE generating

Read full content of:
- `memory/INTRADAY_RULES.md` — 尾盘/T+1 隔夜专属规则
- `memory/SHARED_RULES.md` — 通用规则（两Agent共用）

Apply rules via semantic matching in ReasoningTrace (see § ReasoningTrace).

### AFTER generating

Append entry to `memory/intraday/INDEX.md`:

```
| Date | Regime | Top Pick | Tier | Score | File |
|------|:------:|---------|:----:|:----:|------|
| 2026-07-01 | neutral | code(name) | B | 72 | [intraday_mapper](intraday/2026-07-01/intraday_mapper.json) |
```

### Position Sizing

Apply size based on tier (A: observe, B: standard position, C: half position)
- Set stop-loss based on ATR (from enriched data)
- Note: buy execution window is 14:50-14:57

## Strategy fields

Store the following content under `market_assessment`, per-stock `reasoning`,
and top-level `strategy` in `intraday_mapper.json`. Publish path:
annotations → validate → `intraday_mapper.json` → `overnight_strategy.json` →
`overnight_strategy.html`.

1. **Market Context** — RegimeHint, 明日预期
2. **Strategy Table** — per-stock: 方向 / 交易策略 / 仓位 / 持仓意图 (T+0/T+1)
   - 方向枚举: `持有偏多` / `持有` / `谨慎持有` / `观望`
   - 交易策略枚举: `趋势跟随` / `回调布局` / `强势接力` / `防御布局`
3. **T+1 兑现计划** — 每只核心持仓如何退出（竞价条件 / 开盘策略 / 止损线）
4. **Risk Control** — 整体风控、仓位上限、止损规则、板块分散
5. **ReasoningTrace** — per-stock 方向推理路径 + 规则应用

对每个 B-Tier 候选执行规则语义匹配，记录应用的规则编号：

```
| 代码 | 方向路径 | 规则应用 | Tier判定依据 |
|------|----------|----------|-------------|
| sz000977 | Score=82→A; capital=强→B; tail=位置高位→降1档; final=B | I01(Suitable→Watch); I05(>75→Suitable) | 主力强但位置偏高降级 |
```

规则应用字段格式：`{规则编号}({匹配结果})`，多个规则以 `;` 分隔。

## Stock Eligibility Filter (Strategy Generation Rule)

Before recommending any stock for **买入/持有** (not Watch), apply these filters:

The deterministic base publishes a compute-owned `execution_state` with
quote-derived `is_limit_up`, `is_sealed`, `limit_up_price`, `quote_complete`,
config-derived `board_excluded`, `eligible`, and `exclusion_reason`. Limit-up
status is calculated from previous close, board/ST limit ratio, and price tick;
sealed additionally requires `price == high`. Missing quote inputs fail closed
with `quote_data_missing`. Reasoning must not reproduce or override this state. Actionable
directions require `execution_state.eligible=true`; tradeability remains governed
by I01/I05, including their existing Watch sizing semantics.

### Board Exclusion (config-driven)

Read `.opencode/config/trading-scope.json`. Apply board exclusion.
Use longest-prefix matching plus explicit code overrides from this file; do not
hard-code excluded board prefixes in the strategy implementation.

| Board Prefix | Default | Rule |
|-------------|:-------:|------|
| `sh688*` | **EXCLUDE** | 科创板 — account scope excluded |
| `bj*` | **EXCLUDE** | 北交所 — account scope excluded |
| `sh60*`, `sz00*`, `sz30*` | OK | 主板+创业板 — allowed |

Excluded-board stocks:
- **NEVER** appear in B-Tier buy recommendations
- May appear in A-Tier (Leader Watch, marked as `board-policy` excluded)
- Must be listed in Excluded Stocks table with `ExclusionSource=board-policy`

### 涨停封板 Filter

| Condition | Rule |
|-----------|------|
| `change_pct` ≥ 涨停阈值（主板10%, 科创/创业20%）AND 封板 | **不可尾盘买入** — 已封板无成交机会 |
| Above + expected to open 涨停 next day | A-Tier (Leader Watch only) |
| Above + expected to open near limit | A-Tier, note "涨停封死尾盘不可成交" |

**Rationale**: 14:50-14:57 执行窗口内，涨停封死股票无人卖出，不存在成交机会。此类股票仅作为次日竞价的观察标的。

涨停股票在 `intraday_mapper.annotations.json` 的策略字段中：
- ✅ 可放在 A-Tier Leader Watch（标注"涨停封板不可尾盘买入，明日竞价关注"）
- ❌ 不可放在 B-Tier 核心持仓中建议尾盘买入
- ❌ 不可给出 T+1 持仓意图为"隔夜持有"

### 持仓质量过滤器

评分前硬排除仅两种真正不合格的标的。涨幅/换手不再硬过滤——交给 `risk_penalty` 软扣分维度处理，避免"活跃日→空池"。

| 条件 | 处理 |
|------|------|
| 无实时行情数据 (price ≤ 0) | 硬排除，不参与评分 |
| 价格跌破 VWAP (price < vwap) | 硬排除（买方未控盘）；弱市 I14 可豁免并打 ceiling 标签 |
| VWAP 数据缺失 | 跳过检查，正常参与评分 |
| I14: 偏离&lt;3% + quick_score≥70 | 入池 `i14_exemption=watch`（Reasoning ≤ 观望） |
| I14: 偏离&lt;5% + quick_score≥80 | 入池 `i14_exemption=cautious_hold`（Reasoning ≤ 谨慎持有） |
| 涨幅/换手偏高 | 不硬排除，通过 `risk_penalty` 软扣分 |

### 绝对质量地板

percentile 排序是相对的（弱势日也能排出高分），入池需叠加独立绝对门槛：

| 条件 | 阈值 |
|------|:----:|
| 主力净流入 | > 0 |
| 趋势质量 (trend_quality raw) | ≥ 0.3 |

未通过地板 → `floor_pass=false`，不计入 opportunity_pool。空池触发降级候选兜底，Reasoning 层标注 `pool_warning` 建议观望。

### 应用优先级

```
board-policy → 涨停封板 → 持仓质量过滤 → score tiers → INTRADAY_RULES.md + SHARED_RULES.md 规则
```

先剔除不可交易标的，剩余池中再做评分筛选与规则应用。

## Strategy Table — Direction & Position Rules

### 方向枚举用法

| 方向 | 含义 | 何时用 |
|------|------|--------|
| `持有偏多` | 尾盘买入，隔夜持有 | B-Tier + 非涨停 + 非排除板 + 主线≥4★ |
| `持有` | 尾盘买入，基础仓位 | B-Tier + 非涨停 + 非排除板 |
| `谨慎持有` | 减半仓，预设止损 | B-Tier + 有风险标记（高换手/弱主力/非核心主线） |
| `观望` | 不买，明日观察 | A-Tier / 涨停封板 / 排除板 / 非主线降级 |

### 交易策略枚举用法

| 策略 | 含义 | 适用条件 |
|------|------|----------|
| `趋势跟随` | 追涨型，高开不加仓 | 涨幅3-7%，主力强，位置优势>80分位 |
| `回调布局` | 等回踩买入 | 已大涨但未涨停，次日可能回踩MA5 |
| `强势接力` | 涨停次日接力 | 涨停封板股 → **仅A-Tier观望，不尾盘买** |
| `防御布局` | 低吸稳健型 | 低涨幅+低换手+大市值 |

## Score immutability

- Never recompute OvernightScore, rank_tier, or quality/floor flags in annotations.
- Never reproduce `execution_state`, `stop_loss_price`, or stop-loss text in annotations.
  Select only `stop_loss_basis`; Python resolves the price from the same stock.
- I10/I11/I14 effects appear only via opportunity_pool / base.json fields
  (`regime_snapshot`, `anomaly_flags`, `i14_exemption`, `rank_tier`, `absolute_score`).
- Rank tier and Tradeability are independent. Never translate A→Suitable or B→Watch mechanically.
- `tradeability` is required in convergence outputs and must use exactly one of
  `Suitable`, `Watch`, `Extended`, or `Avoid`.
- When `i14_exemption=watch`, final tradeability cannot exceed Watch; when
  `i14_exemption=cautious_hold`, direction cannot exceed 谨慎持有.
- I13 (extreme weak zero position) is Reasoning-only: set all directions to 观望
  and position_cap to 0 when breadth up_ratio < 15%; do not claim scores changed.
- If annotations disagree with base numeric fields, validation / review treats base as truth.
- Sealed limit-up or board-excluded stocks must use `direction=观望` and
  `stop_loss_basis=not_applicable`; any violation fails publication.

## Constraints

- This is the ONLY skill that outputs Direction, RiskSeverity, or Expected Premium
- All scores come from `score_overnight.py` through `intraday_mapper.base.json`; LLM does NOT compute or transcribe scores
- LLM role: interpret scores, write reasoning trace, generate natural-language strategy, query rules
- Do NOT recalculate any numbers — trust the compute layer
- When referencing concept themes in reasoning, use Skill 1's `concept_dashboard.json` Composite rank as cross-validation (NOT as primary input — `score_overnight.py` output is authoritative)
- **涨停封板股票 (seal_quality="封死") 不得出现在B-Tier尾盘买入推荐中**
- **sh688/bj 前缀股票不得出现在B-Tier买入推荐中 (per .opencode/config/trading-scope.json)**
- **质量过滤器排除（无行情/跌破VWAP且无I14豁免）的股票不得参与评分**
- Excluded-board 和涨停封板股票可出现在 A-Tier 观察区，但必须标注排除原因
- Output language: 中文
