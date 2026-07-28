---
name: intraday-strategy
description: Use when dispatched as Step 3 of intraday overnight pipeline. Consumes mapper base v2, performs LLM-only portfolio convergence, and publishes validated mapper/strategy v3 contracts. This is the sole Reasoning layer.
---

# Intraday Strategy — Reasoning Layer

## Purpose and ownership

Find positive T+1 premium among stocks that already passed deterministic
execution eligibility. This is the sole layer allowed to author Direction,
Tradeability, RiskSeverity, Expected Premium, execution roles, execution
conditions, and reasoning.

Python owns and the LLM must never reproduce or override:

- quote, VWAP, money flow, technicals;
- Scoreability, OvernightScore, score trace, rank, `rank_tier`, `tier`;
- `execution_state`, execution eligibility, pool membership;
- `primary_theme`, themes, market board, Theme Support Shadow;
- deterministic stop-loss price and text.

Theme Support Shadow is read-only evidence. It never changes score, rank,
eligibility, pool membership, or execution role.

## Inputs

Read these complete inputs:

```text
.cache/intraday/{date}/selection_pools.json
.cache/intraday/{date}/theme_ranking.json
intraday/{date}/intraday_mapper.base.json
memory/INTRADAY_RULES.md
memory/SHARED_RULES.md
```

Missing memory files in a zero-history project mean no learned rules. Do not
re-score when `selection_pools.json` exists. Validate compute and build the
base before Reasoning:

```bash
uv run --frozen ashare-pilot strategy overnight validate-selection --date {date}
uv run --frozen ashare-pilot mapping intraday build-mapper-base --date {date}
```

## Score semantics

The nine dimensions and their weights remain compute-owned. There is one
`rank/rank_tier/tier` over the Scored Pool. Tier is relative rank only. Never
map it mechanically to Tradeability or execution role, and never use it to
decide executable membership.

## Required four-stage reasoning

Perform Reasoning in this order:

1. Read the complete mapper base and both rule files. Compute fields and pool
   membership are read-only.
2. Judge each executable stock independently: Tradeability, preliminary
   Direction, Expected Premium, RiskSeverity, T+1 risk, stop-loss basis, and
   actually applied formal rules.
3. Compare the complete executable set and converge the portfolio. Decide
   which stocks are simultaneous `primary` selections, which are
   `alternative` choices that must not execute alongside their primary, and
   which remain `watch`. Then finalize Direction and `execution_condition`.
4. Complete the publish checklist before writing annotations.

Executable exact coverage means every stock was judged. It does not mean every
stock is a recommendation. Never derive `primary` from executable membership,
Watch, score, rank, or tier. There is no hard-coded recommendation count.

## Annotation contract

Write only `intraday/{date}/intraday_mapper.annotations.json`:

```json
{
  "schema_version": "intraday_mapper_annotations.v3",
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
      "execution_role": "primary|alternative|watch",
      "trading_strategy": "趋势跟随|回调布局|强势接力|防御布局",
      "risk_severity": "low|medium|high|critical",
      "expected_premium": "string",
      "key_reason": "string",
      "execution_condition": "string",
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
    "risk_posture": "zero|very_light|light|normal",
    "execution_principle": "string",
    "risk_control": ["string"],
    "execution_window": "14:50-14:57"
  }
}
```

Coverage is exact and the two arrays do not overlap. Observation annotations
contain no Direction, Tradeability, execution role, execution condition,
stop-loss, T+1 plan, rules, or other execution field.

## Direction, role, and stop-loss constraints

- `primary` requires an actionable Direction:
  `持有偏多|持有|谨慎持有`.
- `alternative` and `watch` require Direction `观望`.
- `Watch + primary` is legal only with Direction `谨慎持有`.
- `Extended` and `Avoid` require `watch + 观望`.
- `i14_exemption=cautious_hold` caps Direction at `谨慎持有`.
- A primary uses a deterministic basis other than `not_applicable`.
- Alternative/watch use `stop_loss_basis=not_applicable`.
- The LLM authors only the basis; Python resolves stop price and text.
- `risk_posture=zero` if and only if there is no primary.
- Empty executable pool is valid and requires `risk_posture=zero`.
- Never output stock or portfolio percentages, cash amounts, share counts, or
  lots. Account sizing belongs to a future account execution layer.

## Memory integration

Apply formal rules semantically, resolve conflicts in the LLM, and record only
actually applied formal rule IDs. Candidate rules must not affect Direction,
execution role, execution condition, or the T+1 plan. `rules_applied` is an
audit string array; Python must not parse or apply its meaning.

Do not add, upgrade, retire, or change rule thresholds during strategy
generation.

## Publish checklist

- Executable annotations exactly cover the pool but are not all recommendations.
- Every primary belongs to the final simultaneous execution set.
- Every alternative/watch is `观望`.
- Watch was not mechanically converted to `谨慎持有`.
- Every Avoid/Extended stock is `watch + 观望`.
- Candidate rules did not affect Direction, role, condition, or T+1 plans.
- `rules_applied` contains only actually applied formal rules.
- Applied rules do not contradict the final primary/alternative set.
- Every `execution_condition` matches its role.
- Risk posture, controls, and the primary set are consistent.
- No percentage, amount, share count, or lot sizing is present.

## Publish

```bash
uv run --frozen ashare-pilot mapping intraday validate-annotations --date {date}
uv run --frozen ashare-pilot mapping intraday build-mapper --date {date}
uv run --frozen ashare-pilot mapping intraday validate-mapper --date {date}
uv run --frozen ashare-pilot strategy overnight build --date {date}
uv run --frozen ashare-pilot strategy overnight validate --date {date}
uv run --frozen ashare-pilot strategy overnight render-report --date {date}
```

If validation fails, regenerate annotations. Never patch compute facts, pool
membership, scores, theme fields, or stop-loss numbers.

Final JSON views:

- `primary` executable with actionable Direction → `recommendations`;
- `alternative|watch` executable with Direction `观望` →
  `eligible_watchlist`;
- deterministic observation pool → `observations`.

The HTML keeps those sections separate and never presents rank tier as a buy
grade.
