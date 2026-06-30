---
name: overnight-market-analysis
description: Use when users request comprehensive intraday overnight alpha analysis workflow — runs market scan at ~14:30, discovers stocks with capital continuity, scores for tomorrow expected premium. Generates intraday_mapper.md with A/B/C tier opportunity pool.
---

# Overnight Market Analysis Workflow (V1)

3-step pipeline implementing the Compute → Perception → Reasoning architecture:

| Layer | Step | Agent | Output |
|-------|------|-------|--------|
| Compute | Python | `run_pipeline.py` | market_breadth.json, indices.json, concept_ranking.json, north_bound.json, scan_pool.json, compute_pool_enriched.json, opportunity_pool.json |
| Perception | Step 1+2 | general + general | market_state.md → theme_ranking.md |
| Reasoning | Step 3 | trading-strategist | intraday_mapper.md (Direction / RiskSeverity / Expected Premium + ReasoningTrace) |

Step 1 and Step 2 NEVER produce Direction or RiskSeverity. Step 3 is the sole Reasoning layer.

## Workflow

```
[14:30 Trigger]
        │
        ▼
Compute Phase        ←  run_pipeline.py (once, ~8s)
        │
        ├→ market_breadth.json
        ├→ indices.json
        ├→ concept_ranking.json
        ├→ north_bound.json
        ├→ scan_pool.json
        ├→ compute_pool_enriched.json
        └→ opportunity_pool.json
        │
        ▼
Step 1 (Perception)  ←  general + intraday-market-scan
        │               reads JSON → market_state.md
        ▼
Step 2 (Perception)  ←  general + intraday-stock-discovery
        │               reads JSON → theme_ranking.md
        ▼
Step 3 (Reasoning)   ←  trading-strategist + overnight-strategy
                        reads JSON + market_state.md + theme_ranking.md
                        → intraday_mapper.md (7-section)
```

## Execution Timing

The pipeline is designed to run at **14:30** (20-minute execution window before 14:50 buy deadline).

| Data Type | Source | Available at 14:30? | Note |
|-----------|--------|:------------------:|------|
| Market breadth (涨跌/涨停) | `fetch_market_breadth.py` (push2 API) | ✓ | Real-time, based on current price vs yesterday close |
| Index quotes | `fetch_stock.py` (Sina) | ✓ | Real-time |
| Concept ranking | `fetch_concept_ranking.py` (push2 API) | ✓ | Real-time |
| North-bound capital | `fetch_north_bound.py` (push2 API) | ✓ | Real-time (may be empty pre-market) |
| Stock money flow | `enrich_compute_pool.py` (East Money + Sina) | ✓ | Real-time stock-level flow |
| Stock technical indicators | — | ✗ | No MACD/RSI/ATR in V1 (computed from close data only) |
| Stock 5-min K-line | `fetch_stock.py --intraday` | ✓ | Available but NOT used in V1 pipeline |
| Theme library membership | `query_theme.py stock` | ✓ | Static offline index (concept → stock mapping) |
| News / events | — | ✗ | Overnight alpha is market-behavior-driven, not news-driven |

## Performance Constraints

- Target wall-clock: Compute (8s) + Step 1 (LLM, ~3s) + Step 2 (LLM, ~3s) + Step 3 (LLM, ~5s) = **< 20s**
- `run_pipeline.py` fetches data for the Scan Pool (300-500 stocks) using push2 API batch calls (pz=6000), NOT per-stock queries
- Compute Pool enrichment (80-150 stocks) uses Sina batch quote API + single East Money money flow page
- All output files are markdown written directly by the LLM — do NOT write scripts to generate them

---

## Compute Phase: Run the Pipeline

**Before dispatching any subagent**, run the compute phase once:

```bash
python .opencode/skills/intraday-market-scan/scripts/run_pipeline.py --date {YYYY-MM-DD} --compute-pool-size 120 --opportunity-size 30
```

This produces all JSON files under `intraday/{YYYY-MM-DD}/`.

**CRITICAL:** Run this ONCE before Step 1. Do NOT re-run in each subagent. All steps read from the same JSON files.

The output directory structure after compute:
```
intraday/{date}/
├── market_breadth.json
├── indices.json
├── concept_ranking.json
├── north_bound.json
├── scan_pool.json              (Scan Pool: 300-500 stocks)
├── compute_pool_enriched.json  (Compute Pool: 80-150 stocks with money_flow)
└── opportunity_pool.json       (Opportunity Pool: 20-40 stocks scored)
```

---

## Step 1: Market State (Perception Layer)

**Agent:** `general`

**Action:** Load skill `intraday-market-scan` and follow its workflow.

**Task:**

- Read `intraday/{YYYY-MM-DD}/market_breadth.json`, `indices.json`, `concept_ranking.json`, `north_bound.json`
- Synthesize into a structured `market_state.md` covering: Market Strength, Market Breadth, Capital Direction, Active Concepts (top 10)
- ALL numbers must come from the JSON files; LLM generates zero numeric values

**Prompt (exact format, MUST NOT deviate):**

```
Load skill `intraday-market-scan` and execute.

Date: {YYYY-MM-DD}

Inputs:
- intraday/{YYYY-MM-DD}/market_breadth.json
- intraday/{YYYY-MM-DD}/indices.json
- intraday/{YYYY-MM-DD}/concept_ranking.json
- intraday/{YYYY-MM-DD}/north_bound.json

Output:
- intraday/{YYYY-MM-DD}/market_state.md
```

**CRITICAL:** Do NOT inline any file content, scoring formulas, or analysis. Keep the prompt clean.

**Output:** `intraday/{YYYY}-{MM}-{DD}/market_state.md`

---

## Step 2: Stock Discovery (Perception Layer)

**Agent:** `general`

**Action:** Load skill `intraday-stock-discovery` and follow its workflow.

**V1 note:** Step 2 is the Perception Layer. It produces `theme_ranking.md` as a statistical theme ranking derived from stock composition, NOT from news. Step 2 NEVER produces Direction or RiskSeverity — these are solely Step 3 territory.

**Task:**

- Read `intraday/{YYYY-MM-DD}/scan_pool.json` and `compute_pool_enriched.json`
- For stocks in the Compute Pool, query theme library for concept membership
- Compute Theme Heat statistically (Breadth + Leader + Capital + Momentum + Continuation)
- Generate `theme_ranking.md` with top 10-15 themes and their heat breakdown

**Prompt (exact format, MUST NOT deviate):**

```
Load skill `intraday-stock-discovery` and execute.

Date: {YYYY-MM-DD}

Inputs:
- intraday/{YYYY-MM-DD}/scan_pool.json
- intraday/{YYYY-MM-DD}/compute_pool_enriched.json
- intraday/{YYYY-MM-DD}/market_state.md (reference only)

Output:
- intraday/{YYYY-MM-DD}/theme_ranking.md
```

**CRITICAL:** Do NOT inline any file content, stock tables, theme names, or analysis. Keep the prompt clean.

**Output:** `intraday/{YYYY}-{MM}-{DD}/theme_ranking.md`

---

## Step 3: Overnight Strategy (Reasoning Layer)

**Agent:** `trading-strategist`

**Action:** Load skill `overnight-strategy` (V1 Reasoning) and follow its workflow.

**V1 note:** Step 3 is the sole Reasoning Layer. It consumes the opportunity_pool.json (already scored by Python), reads the market context from Step 1+2 outputs, and produces the final `intraday_mapper.md` with Direction, RiskSeverity, and Expected Premium interpretations.

The Python `score_overnight.py` has ALREADY computed all scores. The LLM's job is to:
- Interpret the scores in context of market state
- Validate score reasonableness against market conditions
- Write natural-language reasoning trace for each stock
- Apply position sizing based on A/B/C tier
- Generate the 7-section `intraday_mapper.md`

**Prompt (exact format, MUST NOT deviate):**

```
Load skill `overnight-strategy` and execute.

Date: {YYYY-MM-DD}

Inputs:
- intraday/{YYYY-MM-DD}/opportunity_pool.json
- intraday/{YYYY-MM-DD}/market_state.md
- intraday/{YYYY-MM-DD}/theme_ranking.md

Output:
- intraday/{YYYY-MM-DD}/intraday_mapper.md
```

**CRITICAL:** Do NOT inline any file content, stock tables, rules, formulas, or analysis. Keep the prompt clean.

**Output:** `intraday/{YYYY}-{MM}-{DD}/intraday_mapper.md`

---

## Output Files

| File | Content | Layer / Step |
|------|---------|-------------|
| `intraday/{date}/market_breadth.json` | Raw market width data | Compute |
| `intraday/{date}/indices.json` | Raw index quotes | Compute |
| `intraday/{date}/concept_ranking.json` | Raw concept board ranking | Compute |
| `intraday/{date}/north_bound.json` | Raw north-bound flow | Compute |
| `intraday/{date}/scan_pool.json` | Scan Pool (300-500 stocks, basic data) | Compute |
| `intraday/{date}/compute_pool_enriched.json` | Compute Pool (80-150 stocks, enriched with money flow) | Compute |
| `intraday/{date}/opportunity_pool.json` | Scored Opportunity Pool (A/B/C tiers) | Compute |
| `intraday/{date}/market_state.md` | Market strength, breadth, capital direction, top 10 concepts | Perception (Step 1) |
| `intraday/{date}/theme_ranking.md` | Statistical theme ranking (bottom-up, stock-derived) | Perception (Step 2) |
| `intraday/{date}/intraday_mapper.md` | 7-section: Market State, Theme Ranking, Opportunity Pool (A/B/C), Stock Details, Score Trace, Observation Pool, Excluded Stocks | Reasoning (Step 3) |

## Quick Reference

| Layer | Step | Agent | Input | Output | Key constraint |
|-------|------|-------|-------|--------|----------------|
| Compute | — | bash (run_pipeline.py) | — | 7 JSON files | Run ONCE before all steps |
| Perception | 1 | general + intraday-market-scan | 4 JSON files | market_state.md | No Direction / RiskSeverity |
| Perception | 2 | general + intraday-stock-discovery | 2 JSON files + market_state.md | theme_ranking.md | No Direction / RiskSeverity; themes from stocks NOT news |
| Reasoning | 3 | trading-strategist + overnight-strategy | opportunity_pool.json + market_state.md + theme_ranking.md | intraday_mapper.md | Sole Reasoning authority; scores pre-computed by Python |

## Common Usage

- "Run intraday overnight analysis"
- "午后选股"
- "尾盘分析"
- "Generate overnight alpha pool"

## Notes

- Each step depends on previous output
- Directory: `intraday/{YYYY}-{MM}-{DD}/` (e.g., `intraday/2026-06-30/`)
- All output in Chinese (中文)
- **V1 architecture:** Compute (run_pipeline.py, once) → Perception (Steps 1-2, LLM reads JSON) → Reasoning (Step 3, LLM interprets scores)
- All numeric data comes from Python compute layer; LLM never generates numbers
- Step 1 and Step 2 NEVER produce Direction or RiskSeverity — Step 3 is the sole Reasoning authority
- `run_pipeline.py` calls push2.eastmoney.com → requires `.cookie` file with valid `EASTMONEY_COOKIE`
- Trading execution window: 14:50-14:57 (pipeline must complete before this)
- Theme detection is bottom-up (stocks → themes), NOT top-down (news → themes)
- Weights are V1 Rule Based — explicitly designed for future V2 calibration via backtesting
