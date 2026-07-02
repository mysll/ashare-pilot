---
name: intraday-strategy
description: Use when dispatched as Step 3 of intraday overnight pipeline. Consumes enriched ComputePool + ThemeRanking, scores for tomorrow expected premium, outputs OpportunityPool with A/B/C tiers + intraday_mapper.md. This is the sole Reasoning layer.
---

# Overnight Strategy (Skill 3)

## Purpose

NOT finding today's strongest stocks. Finding stocks that have capital recognition today but haven't fully priced in — expected to have positive premium tomorrow.

This is the SOLE Reasoning layer. All Direction / RiskSeverity / Expected Premium outputs come from here. This step produces the final actionable output.

## Pipeline Role

```
Skill 2 → Enriched ComputePool + ThemeRanking
                    ↓
Skill 3 → Overnight Scoring + intraday_mapper.md (THIS)
                    ↓
[14:50 Execute Buy]
```

## Execute: Compute Overnight Scores

```bash
python .opencode/skills/intraday-strategy/scripts/score_overnight.py .cache/intraday/{YYYY-MM-DD}/compute_pool_enriched.json --opportunity-pool-size 30 --json -o .cache/intraday/{YYYY-MM-DD}/opportunity_pool.json
```

### Scoring Dimensions (V1 Rule Based, Initial Weights)

| Dimension | Weight | What it measures |
|-----------|:------:|-----------------|
| Theme Continuity | 30% | Is the stock in a hot theme? (limit_up > turnover > gain_range) |
| Capital Continuity | 25% | Is main force capital flowing in? (超1亿=strong, 净流出=weak) |
| Tail Strength | 20% | Price position within day range, healthy turnover (5-12%, near high) |
| Position Advantage | 15% | Gain in sweet spot 2-6% (ideal); >9% or <0.5% penalized |
| Risk Deduction | -10% | High turnover >25%, near limit-up, consecutive gains |

Score = Σ(dimension × weight) × 100, range 0-100.

Tiers: A (75+) = Leader Watch, B (60-74) = Premium Candidates, C (45-59) = Early Breakout, D (<45) = Drop.

**Important:** V1 uses Rule Based Initial Weights. These will be calibrated via historical backtesting in V2. See spec § 八.

## Output: intraday_mapper.md

Generate `intraday/{YYYY-MM-DD}/intraday_mapper.md` with 7 sections.

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
- Full score breakdown (5 dimensions)
- Money flow: main/super_large/large/medium/small
- Position analysis: price vs VWAP, within day range
- QuickScore (from Skill 1)

### 5. Overnight Score Trace
Show the formula with actual values:
```
Stock [code] [name]:
  Theme:        [x]/100 × 0.30 = [weighted]
  Capital:      [x]/100 × 0.25 = [weighted]
  Tail:         [x]/100 × 0.20 = [weighted]
  Position:     [x]/100 × 0.15 = [weighted]
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
| 2026-07-01 | neutral | code(name) | B | 72 | [intraday_mapper](intraday/2026-07-01/intraday_mapper.md) |
```

### Position Sizing

Apply size based on tier (A: observe, B: standard position, C: half position)
- Set stop-loss based on ATR (from enriched data)
- Note: buy execution window is 14:50-14:57

## Output: overnight_strategy.md

Alongside `intraday_mapper.md`, generate `overnight_strategy.md` with:

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

### Board Exclusion (config-driven)

Read `.opencode/config/trading-scope.json`. Apply board exclusion.

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

涨停股票在 overnight_strategy.md 中：
- ✅ 可放在 A-Tier Leader Watch（标注"涨停封板不可尾盘买入，明日竞价关注"）
- ❌ 不可放在 B-Tier 核心持仓中建议尾盘买入
- ❌ 不可给出 T+1 持仓意图为"隔夜持有"

### 持仓质量过滤器

评分前按基础质量条件过滤：

| 条件 | 阈值 | 规则 |
|------|:------:|------|
| 分时均价线 | 全天运行在均价线上方 | 价格始终 > VWAP，弱势股剔除 |
| 换手率 | 5% ≤ 换手率 ≤ 12% | <5%无量无关注，>12%短期过热 |
| 当天涨幅 | 2% ≤ 涨幅 ≤ 6% | <2%动能不足，>6%追高风险 |

不满足任意条件的股票：
- 标记为 `quality-filter` 排除
- 放入 Excluded Stocks 表，注明 `ExclusionSource=quality-filter`
- 不参与 overnight scoring

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

## Constraints

- This is the ONLY skill that outputs Direction, RiskSeverity, or Expected Premium
- All scores come from `score_overnight.py` output; LLM does NOT compute scores
- LLM role: interpret scores, write reasoning trace, generate natural-language strategy, query rules
- Do NOT recalculate any numbers — trust the compute layer
- When referencing concept themes in reasoning, use Skill 1's `concept_dashboard.json` Composite rank as cross-validation (NOT as primary input — `score_overnight.py` output is authoritative)
- **涨停封板股票 (seal_quality="封死") 不得出现在B-Tier尾盘买入推荐中**
- **sh688/bj 前缀股票不得出现在B-Tier买入推荐中 (per .opencode/config/trading-scope.json)**
- **不满足持仓质量过滤器（VWAP/换手率/涨幅）的股票不得参与评分**
- Excluded-board 和涨停封板股票可出现在 A-Tier 观察区，但必须标注排除原因
- Output language: 中文
