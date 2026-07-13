---
name: intraday-market-scan
description: Use when dispatched at ~14:30 as Step 1 perception of the intraday overnight pipeline. Reads compute-layer market JSON and checks breadth, indices, capital direction, and active concepts. NEVER outputs stock-level scoring, Direction, RiskSeverity, or trading recommendations.
---

# Intraday Market Scan (Skill 1 — Perception)

## Purpose

Determine what the market is REALLY trading today at ~14:30. Market → Hot Spots.

This is the **market perception** check after compute. Output is structured perception only — no reasoning, no scoring, no trading recommendations.

## Pipeline Position

```
[14:30 Trigger]
    ↓
Compute once: run_intraday_pipeline.py → .cache/intraday/{date}/*.json
    ↓
Skill 1: intraday-market-scan (THIS) — read market JSON, verify MarketState
    ↓
Skill 2: intraday-stock-discovery — verify ComputePool + ThemeRanking
    ↓
Skill 3: intraday-strategy — annotations → intraday_mapper.json + overnight_strategy.json
```

Orchestrator: skill `intraday-market-analysis`.

## Inputs (read only)

Prefer files already produced by `run_intraday_pipeline.py`:

- `.cache/intraday/{date}/market_breadth.json`
- `.cache/intraday/{date}/indices.json`
- `.cache/intraday/{date}/concept_dashboard.json`
- `.cache/intraday/{date}/scan_pool.json` (existence / size check only)

Do **not** re-run compute if these files exist for the date. Only if the orchestrator has **not** run compute for this date, fetch via:

```bash
python .opencode/lib/fetch/fetch_market_breadth.py --json -o .cache/intraday/{date}/market_breadth.json
python .opencode/lib/fetch/fetch_stock.py sh000001,sz399001,sz399006,sh000688,sh000852 --json -o .cache/intraday/{date}/indices.json
python .opencode/skills/intraday-market-scan/scripts/build_concept_dashboard.py --json --top 100 -o .cache/intraday/{date}/concept_dashboard.json
python .opencode/skills/intraday-market-scan/scripts/build_scan_pool.py --compute-pool-size 120 --json -o .cache/intraday/{date}/scan_pool.json
```

## Perception checks

ALL numbers come from JSON — LLM generates zero numeric values. Optional brief session narrative is fine; Skill 2/3 only consume cache JSON.

### Market Strength

From `indices.json`: 上证 / 深成 / 创业板 / 科创50 / 中证1000 price and change%.

### Market Breadth

From `market_breadth.json`: up/down counts, up ratio, limit-up / limit-down.

### Capital Direction

From `concept_dashboard.json` Capital ranking — name the capital leader. Any concept cited in prose MUST appear in the Theme Dashboard table (same file).

### Theme Dashboard

From `concept_dashboard.json`, top concepts by Composite rank. Dimension legend:

| Column | Meaning |
|--------|---------|
| Perf | Performance rank — today's market recognition |
| Capital | Capital rank — sustained buying pressure |
| Breadth | Breadth rank — sector resonance vs single-stock hype |
| Momentum | Continuity rank — strengthening or fading |
| Composite | Capital 35% + Breadth 25% + Momentum 25% + Performance 15% |

Narrative claims must match the column they describe (e.g. "资金第一" → Capital column).

### ScanPool sanity

Confirm `scan_pool.json` exists and holds a large basic pool (typically 300–500 names, basic fields only — no MACD/RSI/ATR/Bollinger).

## Constraints

- DO NOT compute technical indicators — Skill 2 / compute territory
- DO NOT output Direction, RiskSeverity, buy/sell recommendations — Skill 3 only
- DO NOT reference news or morning predictions — pure market observation
- All numbers MUST come from script/JSON output under `.cache/intraday/{date}/`
- Prefer orchestrator compute once; do not re-fetch when cache is present
