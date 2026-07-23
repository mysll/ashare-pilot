---
name: intraday-stock-discovery
description: Use when dispatched as Step 2 perception of the intraday overnight pipeline. Reads enriched ComputePool and bottom-up ThemeRanking JSON (stock→theme, NOT news). NEVER outputs Direction, RiskSeverity, or trading recommendations.
---

# Intraday Stock Discovery (Skill 2 — Perception)

## Purpose

Verify the enriched ComputePool and statistical ThemeRanking produced by compute (stock → theme, NOT news → theme).

This is the **theme/pool perception** check. Output is structured perception with confidence, never trading reasoning.

## Pipeline Position

```
Compute once: uv run --frozen ashare-pilot automation intraday run
    → scan_pool, compute_pool_enriched, theme_ranking, opportunity_pool (under .cache)
    ↓
Skill 1 → market perception (breadth / indices / concepts)
    ↓
Skill 2 → pool + theme perception (THIS)
    ↓
Skill 3 → annotations → intraday_mapper.json + overnight_strategy.json
```

Orchestrator: skill `intraday-market-analysis`.

## Inputs (read only)

Prefer files already produced by `uv run --frozen ashare-pilot automation intraday run`:

- `.cache/intraday/{date}/scan_pool.json`
- `.cache/intraday/{date}/compute_pool_enriched.json`
- `.cache/intraday/{date}/theme_ranking.json`

Do **not** re-run enrichment/ranking if these files exist for the date. Only if compute has **not** been run for this date:

```bash
uv run --frozen ashare-pilot mapping intraday enrich-compute-pool .cache/intraday/{date}/scan_pool.json --json -o .cache/intraday/{date}/compute_pool_enriched.json
uv run --frozen ashare-pilot indicators pool enrich .cache/intraday/{date}/compute_pool_enriched.json --json -o .cache/intraday/{date}/compute_pool_enriched.json
uv run --frozen ashare-pilot themes ranking compute .cache/intraday/{date}/compute_pool_enriched.json --json --date {date} -o .cache/intraday/{date}/theme_ranking.json
```

Skill 3 consumes `theme_ranking.json` via mapper base / cache under `.cache/intraday/{date}/`.

## Theme Heat Formula (compute-owned)

Implemented in `uv run --frozen ashare-pilot themes ranking compute` (LLM does not recompute):

```
Theme Heat = Breadth(20%) + Leader(30%) + Capital(25%) + Momentum(15%) + Continuation(10%)
```

| Component | Weight | Calculation |
|-----------|:------:|-------------|
| Breadth | 20% | Pool member count in theme, normalized |
| Leader | 30% | Max(change_pct) among theme members, normalized |
| Capital | 25% | Sum(main_net_inflow) for members, normalized |
| Momentum | 15% | Avg change_pct of members, normalized |
| Continuation | 10% | Fixed at 10 (V2: historical streak) |

## Perception checks

1. **Pool integrity** — `compute_pool_enriched.json` has real-time + money_flow + technicals for the intended size (~80–150 after filters).
2. **Bottom-up themes** — `theme_ranking.json` themes are derived from pool membership, not news.
3. **Cross-check (optional)** — if a theme is top-5 in both Skill 2 Heat and Skill 1 `concept_dashboard` Composite, note higher confidence.
4. **No Direction** — do not assign Direction, RiskSeverity, Expected Premium, or buy/sell language.

## Constraints

- DO NOT compute overnight scores — `uv run --frozen ashare-pilot strategy overnight score` / Skill 3 compute path
- DO NOT output Direction, RiskSeverity, or buy/sell recommendations
- Theme heat is owned by `uv run --frozen ashare-pilot themes ranking compute`; LLM does NOT re-score
- Theme library is STATIC membership only; live multi-dim concept ranks live in `concept_dashboard.json`
- Handoff to Skill 3 is JSON under `.cache/intraday/{date}/` only
