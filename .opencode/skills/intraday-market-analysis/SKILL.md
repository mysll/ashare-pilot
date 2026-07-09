---
name: intraday-market-analysis
description: Run the 14:30 overnight-alpha workflow and produce a validated JSON mapper contract with A/B/C opportunities.
---

# Intraday Market Analysis (JSON-first V2)

The pipeline follows Compute → Perception → Reasoning. JSON is the only
inter-step contract. Markdown may be rendered for people, but MUST NOT be read
by a downstream step.

| Layer | Owner | Canonical output |
|---|---|---|
| Compute | `run_intraday_pipeline.py` | `.cache/intraday/{date}/*.json` |
| Perception | Python + analyst agents | compute JSON (no duplicate Markdown handoff) |
| Reasoning | `portfolio-manager` + `intraday-strategy` | `intraday_mapper.annotations.json` |
| Contract build | Python | `intraday_mapper.base.json` → `intraday_mapper.json` → `overnight_strategy.json` |

Only the Reasoning layer may produce Direction, RiskSeverity, Expected Premium,
or ReasoningTrace. Numeric market, theme, quote, flow, technical, and score
fields always come from the compute layer.

## 1. Compute once

Run before dispatching any agent:

```bash
python .opencode/scripts/run_intraday_pipeline.py --date {YYYY-MM-DD} --compute-pool-size 120 --opportunity-size 30
```

Use a timeout of at least 180 seconds. Do not run this again in substeps.

Required outputs:

```text
.cache/intraday/{date}/
├── market_breadth.json
├── indices.json
├── concept_dashboard.json
├── scan_pool.json
├── compute_pool_enriched.json
├── theme_ranking.json
└── opportunity_pool.json
```

The workflow runs at about 14:30. Market breadth, index quotes, concepts,
stock-level money flow, and quotes are real-time. Technicals use daily K-lines.
The execution window is 14:50–14:57.

## 2. Perception checks

### Market perception

Agent: `market-microstructure-analyst`, skill: `intraday-market-scan`.

Read these files directly:

- `.cache/intraday/{date}/market_breadth.json`
- `.cache/intraday/{date}/indices.json`
- `.cache/intraday/{date}/concept_dashboard.json`

Check market strength, breadth, capital direction, and active concepts. Do not
create `market_state.md` as a data handoff.

### Theme perception

Agent: `equity-analyst`, skill: `intraday-stock-discovery`.

Read these files directly:

- `.cache/intraday/{date}/scan_pool.json`
- `.cache/intraday/{date}/compute_pool_enriched.json`
- `.cache/intraday/{date}/theme_ranking.json`

Check that the bottom-up theme ranking is consistent with the compute pool. Do
not transcribe it into `theme_ranking.md` for Step 3.

Step 1 and Step 2 NEVER output Direction or RiskSeverity.

## 3. Build the deterministic mapper base

```bash
python .opencode/skills/intraday-strategy/scripts/build_intraday_mapper_base.py --date {YYYY-MM-DD}
```

This copies authoritative market, theme, pool, score, and exclusion data into:

`intraday/{YYYY-MM-DD}/intraday_mapper.base.json`

The LLM must not reproduce or edit these numeric fields.

## 4. Generate reasoning annotations

Agent: `portfolio-manager`, skill: `intraday-strategy`.

Dispatch with this exact compact prompt:

```text
Load skill `intraday-strategy` and execute.

Date: {YYYY-MM-DD}

Inputs:
- .cache/intraday/{YYYY-MM-DD}/market_breadth.json
- .cache/intraday/{YYYY-MM-DD}/indices.json
- .cache/intraday/{YYYY-MM-DD}/concept_dashboard.json
- .cache/intraday/{YYYY-MM-DD}/theme_ranking.json
- .cache/intraday/{YYYY-MM-DD}/opportunity_pool.json
- intraday/{YYYY-MM-DD}/intraday_mapper.base.json

Output:
- intraday/{YYYY-MM-DD}/intraday_mapper.annotations.json
```

The annotations contain only semantic interpretation: market assessment,
Direction, RiskSeverity, Expected Premium, Key Reason, position/T+1 plan,
applied rules, and ReasoningTrace.

## 5. Validate and publish

```bash
python .opencode/skills/intraday-strategy/scripts/validate_intraday_mapper_annotations.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/build_intraday_mapper_json.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/validate_intraday_mapper_json.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/build_overnight_strategy_json.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/validate_overnight_strategy_json.py --date {YYYY-MM-DD}
python .opencode/skills/intraday-strategy/scripts/render_overnight_strategy_html.py --date {YYYY-MM-DD}
```

If annotation validation fails, ask the LLM to regenerate
`intraday_mapper.annotations.json`. Do not patch numeric fields and do not
publish a partial final contract.

Final outputs:

| File | Role |
|---|---|
| `intraday_mapper.base.json` | deterministic compute-layer base |
| `intraday_mapper.annotations.json` | LLM semantic fields only |
| `intraday_mapper.json` | validated canonical downstream contract |
| `overnight_strategy.json` | validated execution-focused view for review and T+1 consumers |
| `overnight_strategy.html` | 中文阅读看板，展示可执行持仓、T+1计划、风控和观察池 |

`intraday_mapper.json` supersedes `intraday_mapper.md`; `overnight_strategy.json`
supersedes `overnight_strategy.md`. Markdown/HTML renderers may consume these
contracts for human reading.

## Invariants

- A-share scope only: `sh`/`sz`; exclude `sh688*` and `bj*` from buy candidates
  according to `.opencode/config/trading-scope.json`.
- A sealed limit-up stock is observation-only, never a B-tier tail-buy.
- Apply `memory/INTRADAY_RULES.md` and `memory/SHARED_RULES.md` in Reasoning.
- All scores come from `score_overnight.py`; the LLM never recalculates them.
- Themes are detected bottom-up from stocks, not from news.
- Run the compute phase once and keep all stages on the same dated snapshot.
