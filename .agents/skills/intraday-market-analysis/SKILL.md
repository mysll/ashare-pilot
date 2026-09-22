---
name: intraday-market-analysis
description: Run the 14:30 overnight-alpha workflow and publish validated executable/observation dual-pool contracts.
---

# Intraday Market Analysis (JSON-first V3)

The pipeline follows Compute → Perception → Reasoning. JSON is the only
inter-step contract. Human-facing board is `overnight_strategy.html`.

| Layer | Owner | Canonical output |
|---|---|---|
| Compute | `uv run --frozen ashare-pilot automation intraday run` | `.cache/intraday/{date}/*.json` |
| Perception | Python + analyst agents | read compute JSON only |
| Reasoning | `portfolio-manager` + `intraday-strategy` | `intraday_mapper.annotations.json` |
| Contract build | Python | `intraday_mapper.base.json` → `intraday_mapper.json` → `overnight_strategy.json` |

Only the Reasoning layer may produce Direction, RiskSeverity, Expected Premium,
or ReasoningTrace. Numeric market, theme, quote, flow, technical, and score
fields always come from the compute layer.

## 1. Compute once

Run before dispatching any agent:

```bash
uv run --frozen ashare-pilot automation intraday run --date {YYYY-MM-DD} --compute-pool-size 120 --executable-size 30 --observation-size 30
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
└── selection_pools.json
```

The limit-up cluster screen is **not** part of this compute command. It is slow
(per-candidate K-line history) and informational only, so it is dispatched
separately as a side-car after compute (see Section 1.5). Its
`screen_limit_up_cluster.json` output is rendered as an independent section in
`overnight_strategy.html` but must never feed the mapper, the selection pools,
or the overnight strategy, and Reasoning must not treat it as a candidate
contract.

The workflow runs at about 14:30. Market breadth, index quotes, concepts,
stock-level money flow, and quotes are real-time. Technicals use daily K-lines.
The execution window is 14:50–14:57.

## 1.5 Side-car limit-up cluster screen (parallel with perception)

Immediately after compute completes, dispatch the side-car screen as a
**`general` sub-agent** in the **same parallel batch** as the Step 2 perception
agents, so it runs concurrently with them and has no 120-second cap. A screen
failure or timeout must never stop, gate, or alter Step 3 reasoning or the
published strategy; the screen is informational only.

Dispatch this exact prompt:

```text
Run the side-car limit-up cluster screen for {YYYY-MM-DD}. This is
informational only and must never feed any strategy.

Execute:
uv run --frozen ashare-pilot screen limit-up-cluster --date {YYYY-MM-DD} \
  --all-stocks .cache/intraday/{YYYY-MM-DD}/all_stocks_cache.json \
  --json -o .cache/intraday/{YYYY-MM-DD}/screen_limit_up_cluster.json

Use a 300-second (5-minute) timeout for this command; the screen fetches
per-candidate K-line history and is slow. Do not modify any other file, do not
re-run the pipeline, and do not change any strategy contract. If the command
fails, report the error and stop; leave any existing screen file untouched.
```

Because it is dispatched with the perception batch, the screen normally
finishes before the report is rendered. `render-report` reads
`.cache/intraday/{date}/screen_limit_up_cluster.json` when present and otherwise
renders the section as "旁路筛选未运行"; both outcomes are valid and neither
affects the strategy.

## 2. Perception checks

Perception agents **read** compute JSON only. They do not re-run the pipeline
and do not rewrite cache files. If a required cache file is missing or
obviously empty, stop and re-run Step 1 compute for the same date — do not
patch numbers by hand.

### Market perception

Agent: `market-microstructure-analyst`, skill: `intraday-market-scan`.

Read these files directly:

- `.cache/intraday/{date}/market_breadth.json`
- `.cache/intraday/{date}/indices.json`
- `.cache/intraday/{date}/concept_dashboard.json`
- `.cache/intraday/{date}/scan_pool.json` (existence / size only)

Check market strength, breadth, capital direction, and active concepts.

### Theme perception

Agent: `equity-analyst`, skill: `intraday-stock-discovery`.

Read these files directly:

- `.cache/intraday/{date}/scan_pool.json`
- `.cache/intraday/{date}/compute_pool_enriched.json`
- `.cache/intraday/{date}/theme_ranking.json`

Check that the bottom-up theme ranking is consistent with the compute pool.

Step 1 and Step 2 NEVER output Direction or RiskSeverity.

## 3. Build the deterministic mapper base

```bash
uv run --frozen ashare-pilot mapping intraday build-mapper-base --date {YYYY-MM-DD}
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
- .cache/intraday/{YYYY-MM-DD}/selection_pools.json
- intraday/{YYYY-MM-DD}/intraday_mapper.base.json

Output:
- intraday/{YYYY-MM-DD}/intraday_mapper.annotations.json
```

The annotations contain two exact-coverage arrays. `executable_annotations`
must explicitly assign `primary|alternative|watch` after portfolio
convergence. Exact coverage means all executable stocks were judged, not that
all are recommended.
`observation_annotations` may contain only observation summary, watch
condition, and risk note. Observation stocks can never be upgraded by
Reasoning or learned rules.

## 5. Validate and publish

```bash
uv run --frozen ashare-pilot mapping intraday validate-annotations --date {YYYY-MM-DD}
uv run --frozen ashare-pilot mapping intraday build-mapper --date {YYYY-MM-DD}
uv run --frozen ashare-pilot mapping intraday validate-mapper --date {YYYY-MM-DD}
uv run --frozen ashare-pilot strategy overnight build --date {YYYY-MM-DD}
uv run --frozen ashare-pilot strategy overnight validate --date {YYYY-MM-DD}
uv run --frozen ashare-pilot strategy overnight render-report --date {YYYY-MM-DD}
```

If annotation validation fails, ask the LLM to regenerate
`intraday_mapper.annotations.json`. Do not patch numeric fields and do not
publish a partial final contract.

Final outputs:

| File | Role |
|---|---|
| `intraday_mapper.base.json` | deterministic compute-layer base |
| `intraday_mapper.annotations.json` | LLM semantic fields, `intraday_mapper_annotations.v3` |
| `intraday_mapper.json` | validated `intraday_mapper.v3` downstream contract |
| `overnight_strategy.json` | validated `intraday_overnight_strategy.v3` view for review and T+1 consumers |
| `overnight_strategy.html` | 中文阅读看板，展示可执行持仓、T+1计划、风控和观察池 |

Downstream consumers and review skills read `intraday_mapper.json` and
`overnight_strategy.json`. Humans use `overnight_strategy.html`.

## Invariants

- A-share scope only: `sh`/`sz`; exclude `sh688*` and `bj*` from buy candidates
  according to `config/trading-scope.json`.
- A sealed limit-up stock is observation-only, never a B-tier tail-buy.
- `selection_pools.json` is the only candidate contract. A/B/C/D is one
  Scored Pool relative rank and never decides executable membership.
- `screen_limit_up_cluster.json` is an informational side-car screen, produced
  by a separate sub-agent dispatched with the perception batch (Section 1.5),
  never by compute. It never feeds the mapper, selection pools, or overnight
  strategy.
- An empty executable pool is a valid result; publish `risk_posture=zero` and the
  observation view rather than treating it as a compute failure.
- Recommendations contain only `primary`; alternative/watch stocks remain in
  `eligible_watchlist` and are not simultaneous execution instructions.
- Do not publish account-independent position percentages, amounts, shares, or
  lots.
- Apply `memory/INTRADAY_RULES.md`, `memory/SHARED_RULES.md`, and only
  `OVERNIGHT_STRATEGY` entries from `memory/EXPERT_RULES.md` in Reasoning when
  they exist. In a zero-history project, absence means no corresponding rules
  and is not an error.
- All scores come from `uv run --frozen ashare-pilot strategy overnight score`; the LLM never recalculates them.
- Themes are detected bottom-up from stocks, not from news.
- Run the compute phase once and keep all stages on the same dated snapshot.
