---
name: overnight-strategy
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
python .opencode/skills/stock-analysis/scripts/score_overnight.py .cache/intraday/compute_pool_enriched.json --opportunity-pool-size 30 --json -o .cache/intraday/opportunity_pool.json
```

### Scoring Dimensions (V1 Rule Based, Initial Weights)

| Dimension | Weight | What it measures |
|-----------|:------:|-----------------|
| Theme Continuity | 30% | Is the stock in a hot theme? (limit_up > turnover > gain_range) |
| Capital Continuity | 25% | Is main force capital flowing in? (超1亿=strong, 净流出=weak) |
| Tail Strength | 20% | Price position within day range, healthy turnover (2-15%, near high) |
| Position Advantage | 15% | Gain in sweet spot 2-5% (ideal); >9% or <0.5% penalized |
| Risk Deduction | -10% | High turnover >25%, near limit-up, consecutive gains |

Score = Σ(dimension × weight) × 100, range 0-100.

Tiers: A (75+) = Leader Watch, B (60-74) = Premium Candidates, C (45-59) = Early Breakout, D (<45) = Drop.

**Important:** V1 uses Rule Based Initial Weights. These will be calibrated via historical backtesting in V2. See spec § 八.

## Output: intraday_mapper.md

Generate `intraday/{YYYY-MM-DD}/intraday_mapper.md` with 7 sections.

### 1. Market State
Copy from Skill 1 output — indices, breadth, capital direction, top 5 active concepts.

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

## Strategy Integration

If generating tomorrow's trading plan:
- Read `memory/RULES.md` for active rules
- Apply position sizing based on tier (A: observe, B: standard position, C: half position)
- Set stop-loss based on ATR (from enriched data)
- Note: buy execution window is 14:50-14:57

## Constraints

- This is the ONLY skill that outputs Direction, RiskSeverity, or Expected Premium
- All scores come from `score_overnight.py` output; LLM does NOT compute scores
- LLM role: interpret scores, write reasoning trace, generate natural-language strategy, query rules
- Do NOT recalculate any numbers — trust the compute layer
- Output language: 中文
