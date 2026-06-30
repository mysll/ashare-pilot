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

## Execute: Data Enrichment

```bash
python .opencode/skills/stock-analysis/scripts/enrich_compute_pool.py .cache/intraday/scan_pool.json --json -o .cache/intraday/compute_pool_enriched.json
```

This fetches Sina real-time quotes and East Money stock-level money flow for every stock in the Compute Pool.

## Theme Detection (Bottom-Up, Statistical)

Themes are detected STATISTICALLY from the Compute Pool, NOT from news.

Process:
1. For each stock in Compute Pool, identify its theme/concept membership via theme library
2. Count how many stocks from each theme appear in the Compute Pool
3. Compute Theme Heat from stock-level metrics

### Theme Membership Lookup

For each stock code in the Compute Pool (top 20 scorers or all if pool < 50):
```bash
python .opencode/skills/theme-library/scripts/query_theme.py stock {code} --roles --json
```

This returns the themes and concepts each stock belongs to.

### Theme Heat Formula (V1)

```
Theme Heat = Breadth(20%) + Leader(30%) + Capital(25%) + Momentum(15%) + Continuation(10%)
```

| Component | Weight | Calculation |
|-----------|:------:|-------------|
| Breadth | 20% | Count of Compute Pool stocks in theme / total theme members in library |
| Leader | 30% | Max(change_pct) among theme members in pool, normalized to 0-1 |
| Capital | 25% | Sum(main_net_inflow) for theme members, normalized |
| Momentum | 15% | Avg change_pct of theme members |
| Continuation | 10% | Days since theme first appeared in top ranks (V2: from daily tracking) |

## Output

Update `.cache/intraday/compute_pool_enriched.json` with theme assignments:
```json
{
  "theme_assignment": [
    {"theme": "AI算力", "heat": 85.0, "stocks_in_pool": 12, "leader": "sh688256", "leader_change": "+8.5%"},
    ...
  ],
  "compute_pool": [ ... stocks with "themes" field added ... ]
}
```

Also produce `intraday/{date}/theme_ranking.md`:

```markdown
## Theme Ranking ({date} 14:30)

| # | Theme | Heat | Stocks | Avg Chg% | Leader | Leader Chg% | NetFlow(亿) |
|---|-------|------|--------|----------|--------|-------------|-------------|
```

## Constraints

- DO NOT compute overnight scores — Skill 3 does that
- DO NOT output Direction, RiskSeverity, or buy/sell recommendations
- Theme heat is purely statistical from stock count + stock performance, NEVER from news
- The theme library is used for STATIC membership lookup only; live concept ranking from Skill 1 provides real-time data
- This skill serves as a V1 handoff layer: structured JSON for Skill 3 to consume
