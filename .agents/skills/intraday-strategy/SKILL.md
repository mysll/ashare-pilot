---
name: intraday-strategy
description: Use when dispatched as Step 3 of intraday overnight pipeline. Consumes mapper base v2, writes separated semantic annotations, and publishes validated mapper/strategy v2 contracts. This is the sole Reasoning layer.
---

# Intraday Strategy — Reasoning Layer

## Purpose and ownership

Find positive T+1 premium among stocks that already passed deterministic
execution eligibility. This is the sole layer allowed to author Direction,
Tradeability, RiskSeverity, Expected Premium, position plans, and reasoning.

Python owns and the LLM must never reproduce or override:

- quote, VWAP, money flow, technicals;
- Scoreability, OvernightScore, score trace, rank, `rank_tier`, `tier`;
- `execution_state`, execution eligibility, pool membership;
- `primary_theme`, themes, market board, Theme Support Shadow;
- deterministic stop-loss price and text.

Theme Support Shadow is read-only evidence from `theme_ranking.json`. It never
changes score, rank, eligibility, pool membership, or position.

## Inputs

Normal orchestration already produces:

```text
.cache/intraday/{date}/selection_pools.json
.cache/intraday/{date}/theme_ranking.json
intraday/{date}/intraday_mapper.base.json
memory/INTRADAY_RULES.md       # optional in zero-history projects
memory/SHARED_RULES.md         # optional in zero-history projects
```

Do not re-score when `selection_pools.json` exists. If compute was not run:

```bash
uv run --frozen ashare-pilot strategy overnight score \
  .cache/intraday/{date}/compute_pool_enriched.json \
  --breadth .cache/intraday/{date}/market_breadth.json \
  --indices .cache/intraday/{date}/indices.json \
  --executable-pool-size 30 \
  --observation-pool-size 30 \
  --date {date} \
  --json -o .cache/intraday/{date}/selection_pools.json
```

Validate compute before Reasoning:

```bash
uv run --frozen ashare-pilot strategy overnight validate-selection --date {date}
uv run --frozen ashare-pilot mapping intraday build-mapper-base --date {date}
```

## V1.3 score semantics

Nine dimensions remain percentile-based:

| Dimension | Weight |
|---|---:|
| `source_capital_proxy` | 18% |
| capital continuity | 18% |
| tail strength | 14% |
| position advantage | 9% |
| risk penalty | -10% |
| intensity | 9% |
| conviction | 9% |
| consistency | 5% |
| trend quality | 8% |

`source_capital_proxy` is the recall-source ordinal blended with the stock's
main-inflow sigmoid. It is not theme heat. Theme Ranking remains a shadow.

There is one `rank/rank_tier/tier` over the Scored Pool:
A=top 10%, B=top 40%, C=top 70%, D=rest. `tier == rank_tier`.
Tier is relative rank only. Never map it mechanically to Tradeability, and
never use it to decide whether a stock belongs to the executable pool.

## Annotation contract

Write only `intraday/{date}/intraday_mapper.annotations.json`:

```json
{
  "schema_version": "intraday_mapper_annotations.v2",
  "date": "YYYY-MM-DD",
  "market_assessment": {
    "regime_hint": "string",
    "tomorrow_expectation": "string",
    "risk_severity": "low|medium|high|critical",
    "reasoning_trace": "string"
  },
  "executable_annotations": [
    {
      "code": "sh600000",
      "tradeability": "Suitable|Watch|Extended|Avoid",
      "direction": "持有偏多|持有|谨慎持有|观望",
      "trading_strategy": "趋势跟随|回调布局|强势接力|防御布局",
      "risk_severity": "low|medium|high|critical",
      "expected_premium": "string",
      "key_reason": "string",
      "position_plan": "string",
      "t_plus_1_plan": {
        "auction_condition": "string",
        "open_strategy": "string",
        "stop_loss_basis": "day_low|ma5|ma10|ma20|not_applicable",
        "take_profit": "string"
      },
      "rules_applied": [],
      "reasoning_trace": "string"
    }
  ],
  "observation_annotations": [
    {
      "code": "sz000001",
      "observation_summary": "string",
      "watch_condition": "string",
      "risk_note": "string"
    }
  ],
  "strategy": {
    "position_cap": "string",
    "risk_control": ["string"],
    "execution_window": "14:50-14:57"
  }
}
```

Coverage is exact:

- executable annotation codes equal base `executable_stocks`;
- observation annotation codes equal base `observation_stocks`;
- the arrays do not overlap;
- observation annotations contain no Direction, Tradeability, position,
  stop-loss, T+1 plan, rules, or other execution field.

Learned rules may downgrade an executable stock to non-actionable. They can
never upgrade an observation stock or change deterministic facts.

## Direction and stop-loss constraints

- Actionable directions require an executable base stock.
- `i14_exemption=cautious_hold` caps Direction at `谨慎持有`.
- Non-actionable executable stocks use `stop_loss_basis=not_applicable`.
- The LLM authors only `stop_loss_basis`; Python resolves price and text.
- Extreme weak-market learned rules may set all executable directions to
  `观望` and position cap to zero without claiming that scores changed.
- Empty executable pool is valid: write an empty executable array, cover every
  observation, and set position cap to zero.

## Memory integration

Before annotations, read the full contents of these files when present:

- `memory/INTRADAY_RULES.md`;
- `memory/SHARED_RULES.md`.

Empty or absent rule tables mean no learned rules and are not an error. Apply
rules semantically, record only actually applied rule IDs, and preserve the
governance priority. A learned rule can only tighten the executable outcome.

Do not add, upgrade, retire, or change rule thresholds during strategy
generation.

## Publish

```bash
uv run --frozen ashare-pilot mapping intraday validate-annotations --date {date}
uv run --frozen ashare-pilot mapping intraday build-mapper --date {date}
uv run --frozen ashare-pilot mapping intraday validate-mapper --date {date}
uv run --frozen ashare-pilot strategy overnight build --date {date}
uv run --frozen ashare-pilot strategy overnight validate --date {date}
uv run --frozen ashare-pilot strategy overnight render-report --date {date}
```

If validation fails, regenerate semantic annotations. Never patch compute
facts, pool membership, scores, theme fields, or stop-loss numbers.

Final JSON views:

- actionable executable → `recommendations`;
- non-actionable executable → `eligible_watchlist`;
- deterministic observation pool → `observations`.

The HTML must keep those sections separate and must not label rank tier as a
buy grade.
