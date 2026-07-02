---
name: intraday-stock-discovery
description: Use when dispatched as Step 2 of intraday overnight pipeline. Consumes ScanPool + MarketState, produces enriched ComputePool + statistical ThemeRanking (bottom-up from stocks, NOT from news). NEVER outputs Direction, RiskSeverity, or trading recommendations.
---

# Intraday Stock Discovery (Skill 2)

## Purpose

Build ComputePool from ScanPool, enrich with real-time quotes and money flow, then detect active themes statistically from the stock pool (stock → theme, NOT news → theme).

This is the Perception layer — output is structured data with confidence, never reasoning.

## Pipeline Position

```
Skill 1 → MarketState + ScanPool (300-500)
                ↓
Skill 2 → Enriched ComputePool (80-150) + ThemeRanking (THIS)
                ↓
Skill 3 → OpportunityPool (20-40) + intraday_mapper.md
```

## Execute: Compute Phase

If NOT already run by `run_intraday_pipeline.py`, run these scripts sequentially:

### Data Enrichment

```bash
python .opencode/skills/intraday-stock-discovery/scripts/enrich_compute_pool.py .cache/intraday/{YYYY-MM-DD}/scan_pool.json --json -o .cache/intraday/{YYYY-MM-DD}/compute_pool_enriched.json
```

Fetches Sina real-time quotes and East Money stock-level money flow for every stock in the Compute Pool.

### Technical Indicators

```bash
python .opencode/skills/intraday-stock-discovery/scripts/enrich_technicals.py .cache/intraday/{YYYY-MM-DD}/compute_pool_enriched.json --json -o .cache/intraday/{YYYY-MM-DD}/compute_pool_enriched.json
```

Computes MA5/10/20/60, Bollinger Bands, boll_zone, ma_alignment for each stock.

### Theme Ranking

```bash
python .opencode/skills/intraday-stock-discovery/scripts/compute_theme_ranking.py .cache/intraday/{YYYY-MM-DD}/compute_pool_enriched.json --json --date {YYYY-MM-DD} -o .cache/intraday/{YYYY-MM-DD}/theme_ranking.json
python .opencode/skills/intraday-stock-discovery/scripts/compute_theme_ranking.py .cache/intraday/{YYYY-MM-DD}/compute_pool_enriched.json --date {YYYY-MM-DD} -o intraday/{YYYY-MM-DD}/theme_ranking.md
```

This script imports `query_stock()` from the theme library directly (no subprocess), scores each theme using the V1 Theme Heat formula, and outputs both JSON (for machine consumption) and markdown (for the final report).

**Theme Heat Formula (V1, implemented in `compute_theme_ranking.py`):**

```
Theme Heat = Breadth(20%) + Leader(30%) + Capital(25%) + Momentum(15%) + Continuation(10%)
```

| Component | Weight | Calculation |
|-----------|:------:|-------------|
| Breadth | 20% | Number of Compute Pool stocks in this theme, normalized across all themes |
| Leader | 30% | Max(change_pct) among theme members in pool, normalized |
| Capital | 25% | Sum(main_net_inflow) for theme members, normalized |
| Momentum | 15% | Avg change_pct of theme members, normalized |
| Continuation | 10% | Fixed at 10 (V2: historical streak tracking) |

## Output

The compute scripts produce:
- `compute_pool_enriched.json` — enriched with `enriched` (real_time + money_flow) and `technicals`
- `theme_ranking.json` — `{"theme_ranking": [...], "total_themes": N}`

The LLM reads `theme_ranking.json` and generates `theme_ranking.md` with a rich table:

```markdown
## Theme Ranking ({date} 14:30)

| # | Theme | Heat | Stocks | Avg Chg% | Leader | Leader Chg% | NetFlow(亿) |
|---|-------|------|--------|----------|--------|-------------|-------------|

### 热度分项构成
| # | Theme | Total | Breadth(20%) | Leader(30%) | Capital(25%) | Momentum(15%) | Continuation(10%) |
|---|-------|-------|-------------|------------|-------------|--------------|-----------------|
```

## Constraints

- DO NOT compute overnight scores — Skill 3 does that
- DO NOT output Direction, RiskSeverity, or buy/sell recommendations
- Theme heat computation is handled by `compute_theme_ranking.py`; LLM does NOT re-compute scores
- LLM role: read the JSON output, generate a well-formatted markdown table with commentary
- The theme library is used for STATIC membership lookup only; live concept dashboard from Skill 1 (`concept_dashboard.json`) provides real-time multi-dimensional data
- (Optional) Cross-reference Skill 1's Composite rank for validation: if a bottom-up theme ranks top-5 in both Skill 2 Heat and Skill 1 Composite, confidence is reinforced
- This skill serves as a V1 handoff layer: structured JSON for Skill 3 to consume
