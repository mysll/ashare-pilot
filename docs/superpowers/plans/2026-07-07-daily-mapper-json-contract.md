# Daily Mapper JSON Contract Refactor

Date: 2026-07-07

## Goal

Move the Step 2 -> Step 3 daily-analysis contract from `mapper.md` tables to a stable JSON-first artifact:

```text
predict/{date}/mapper.json   authoritative machine input
predict/{date}/mapper.md     human-readable render
```

`mapper.md` remains useful for review and debugging, but Step 3 should not depend on Markdown table parsing as its normal path.

## Current Problem

`daily-stock-mapping` currently asks the LLM to author `mapper.md` as a machine-consumable dataset. This is a workable transition state, but it mixes two roles:

- data contract for Step 3
- human report for inspection

The current script validation only protects the `Strategy Inputs` table. Other Step 3 inputs, such as `Candidate Pool`, `Theme Ranking`, `NewsImpact`, `MajorEvent`, `pattern.*`, `anomaly`, and `NewsLink`, are still exposed to Markdown drift.

## Target Architecture

```text
news.md
theme-library JSON
pool_indicators.json
market/auction/money-flow fetches
        |
        v
mapper.base.json             script-owned observations and deterministic fields
        +
mapper.annotations.json      LLM-owned perception annotations
        |
        v
mapper.json                  validated Step 2 output
        |
        +--> mapper.md        rendered human report
        |
        v
daily-strategy Step 3        reads mapper.json by default
```

## Ownership Model

### Script-Owned Fields

These should be generated or recomputed by scripts, not handwritten by the LLM:

- stock code/name normalization
- theme-library membership and role tags
- board policy and hard exclusions
- raw market/technical observations
- `Strategy Inputs`
- `risk_flags` and `risk_type`
- auction score
- money-flow score when data is available
- composite score and rank
- Candidate/Observation/Excluded partitioning
- schema validation and Markdown rendering

### LLM Perception Fields

These fields may still need semantic judgment, but the LLM should emit them as strict JSON annotations:

- theme policy polarity
- theme emotion classification
- catalyst exception decision
- stock-news relevance cell (`R0`-`R4`, `P0`-`P3`)
- `news_impact`
- `major_event.polarity`
- `pattern.heat`
- `pattern.leader`
- `pattern.auction`
- `pattern.rotation`
- `pattern.volume`
- `anomaly`
- evidence `NewsLink`

Each LLM-owned field must include:

- `value`
- `confidence`
- `evidence`
- `trace`

### Step 3-Owned Fields

These must stay out of Step 2 and are produced only by `daily-strategy`:

- Direction
- RiskSeverity
- OverrideHint application
- RegimeHint final interpretation
- entry profile final decision
- anchor
- buy/no-buy condition
- position budget
- stop/target or entry execution plan

## Proposed Files

```text
predict/{date}/mapper.base.json
predict/{date}/mapper.annotations.json
predict/{date}/mapper.json
predict/{date}/mapper.md
```

`mapper.base.json` and `mapper.annotations.json` can be treated as debug artifacts. `mapper.json` is the stable public contract.

## mapper.json Shape

```json
{
  "schema_version": "daily_mapper.v1",
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601",
  "market_state": {
    "dominant_themes": [],
    "financing_flow": null,
    "risk_flags": [],
    "board_policy": {}
  },
  "themes": [
    {
      "name": "AI Compute",
      "rank": 1,
      "final_heat": 72,
      "subscores": {
        "market_action": {"value": 70, "confidence": 80, "trace": "..."},
        "emotion": {"value": 85, "confidence": 80, "trace": "..."},
        "news_density": {"value": 80, "confidence": 100, "trace": "..."},
        "capital": {"value": 45, "confidence": 50, "trace": "..."}
      },
      "policy_bonus": {"value": 0, "polarity": "neutral", "evidence": null},
      "catalyst_exception": null
    }
  ],
  "candidate_pool": [
    {
      "code": "sz000977",
      "name": "Inspur Information",
      "source_themes": ["AI Compute"],
      "role_tags": ["Anchor", "IndustryLeader"],
      "scores": {
        "composite": {"value": 67.3, "confidence": 82, "trace": "..."},
        "tech": {"value": 79.4, "confidence": 100, "trace": "..."},
        "theme_heat": {"value": 72, "confidence": 80, "trace": "..."},
        "news_impact": {"value": 80, "confidence": 80, "trace": "..."},
        "auction": {"value": 50, "confidence": 100, "trace": "pre-market neutral"},
        "money_flow": {"value": 50, "confidence": 50, "trace": "stale/default"}
      },
      "major_event": {"polarity": "none", "confidence": 90, "evidence": null},
      "risk_type": {"value": [], "confidence": 100},
      "pattern": {
        "heat": {"state": "RISING", "confidence": 80, "trace": "..."},
        "leader": {"state": "STABLE", "confidence": 80, "trace": "..."},
        "auction": {"state": "NEUTRAL", "confidence": 100, "trace": "..."},
        "rotation": {"state": "PRIMARY", "confidence": 70, "trace": "..."},
        "volume": {"state": "NORMAL", "confidence": 80, "trace": "..."}
      },
      "anomaly": null,
      "news_link": null,
      "strategy_inputs": {
        "price": 69.71,
        "price_source": "PrevClose",
        "ma20": 63.92,
        "ma5": 67.42,
        "atr": 4.25,
        "atr_pct": 6.1,
        "high20": 71.87,
        "low20": 57.15
      }
    }
  ],
  "observation_pool": [],
  "excluded_stocks": []
}
```

## Validator Rules

Create:

```text
.opencode/skills/daily-stock-mapping/scripts/validate_mapper_json.py
```

Required checks:

- `schema_version == daily_mapper.v1`
- date is `YYYY-MM-DD`
- every stock code matches `^(sh|sz)\d{6}$`
- no `sh688*` or `bj*` in `candidate_pool`
- score values are numbers in `[0, 100]`
- confidence values are numbers in `[0, 100]`
- enum fields are valid:
  - policy polarity: `bullish | neutral | bearish | unknown`
  - major event: `positive | negative | none | unknown`
  - pattern states: fixed enum per dimension
  - price source: `PrevClose | Auction | Live`
- every candidate has `strategy_inputs`
- `strategy_inputs` matches `pool_indicators.json` within tolerance
- every LLM-owned non-null field has `confidence` and either `evidence` or `trace`
- `news_link`, when present, follows a compact source pattern such as `flash#155`
- no Step 3 fields appear in `mapper.json`

## Generator Scripts

### 1. Build Base

```text
.opencode/skills/daily-stock-mapping/scripts/build_mapper_base.py
```

Inputs:

- `predict/{date}/themes.md` during transition, later `themes.json`
- `predict/{date}/theme_stocks.md` during transition, later `theme_stocks.json`
- `predict/{date}/pool_indicators.json`
- theme-library query results
- trading scope config

Output:

```text
predict/{date}/mapper.base.json
```

This script should own all deterministic computation and partitioning.

### 2. Merge Annotations

```text
.opencode/skills/daily-stock-mapping/scripts/build_mapper_json.py
```

Inputs:

- `mapper.base.json`
- `mapper.annotations.json`

Output:

```text
predict/{date}/mapper.json
```

It should recompute composite scores after merging LLM perception fields.

### 3. Render Markdown

```text
.opencode/skills/daily-stock-mapping/scripts/render_mapper_md.py
```

Input:

- `mapper.json`

Output:

- `mapper.md`

The renderer should be one-way only. Do not parse `mapper.md` to reconstruct JSON.

## LLM Annotation Contract

The Step 2 LLM should no longer write full `mapper.md`. It should write:

```text
predict/{date}/mapper.annotations.json
```

Suggested shape:

```json
{
  "schema_version": "daily_mapper_annotations.v1",
  "date": "YYYY-MM-DD",
  "themes": [
    {
      "name": "AI Compute",
      "emotion": {"value": 85, "confidence": 80, "evidence": "flash#155", "trace": "..."},
      "policy_polarity": {"value": "neutral", "confidence": 70, "evidence": null, "trace": "..."},
      "catalyst_exception": null
    }
  ],
  "stocks": [
    {
      "code": "sz000977",
      "news_relevance": {"r": "R4", "p": "P2", "confidence": 80, "evidence": "flash#155", "trace": "..."},
      "major_event": {"polarity": "none", "confidence": 90, "evidence": null, "trace": "..."},
      "pattern": {
        "heat": {"state": "RISING", "confidence": 80, "trace": "..."},
        "leader": {"state": "STABLE", "confidence": 80, "trace": "..."},
        "auction": {"state": "NEUTRAL", "confidence": 100, "trace": "..."},
        "rotation": {"state": "PRIMARY", "confidence": 70, "trace": "..."},
        "volume": {"state": "NORMAL", "confidence": 80, "trace": "..."}
      },
      "anomaly": null
    }
  ]
}
```

## Skill Changes

### daily-stock-mapping

Replace the current Markdown-only rule with:

- Step 2 LLM writes `mapper.annotations.json`
- scripts build and validate `mapper.json`
- scripts render `mapper.md`
- `mapper.md` is report-only

Keep the V5 boundary:

- Step 2 is perception only
- no Direction
- no RiskSeverity
- no buy/sell recommendation

### daily-market-analysis

Update Step 2 outputs:

```text
predict/{date}/mapper.annotations.json
predict/{date}/mapper.json
predict/{date}/mapper.md
```

Update Step 3 inputs:

```text
predict/{date}/mapper.json
```

Allow `mapper.md` fallback only for legacy dates.

### daily-strategy

Change default input from `mapper.md` to `mapper.json`.

Step 3 should read:

1. `mapper.json`
2. `memory/RULES.md`
3. `memory/SHARED_RULES.md`
4. `news.md` only for conditional reread using `news_link`

## Migration Plan

### Phase 1: Sidecar JSON

Add `mapper.json` generation while leaving `mapper.md` as the active Step 3 input.

Acceptance:

- `mapper.json` validates for a current trading day
- rendered `mapper.md` matches the current 7-section shape
- no current workflow breaks

### Phase 2: Step 3 Reads JSON

Switch `daily-strategy` to read `mapper.json` first.

Acceptance:

- Step 3 produces valid `strategy.json`
- no Step 3 code path parses Markdown when `mapper.json` exists
- strategy output remains semantically consistent with previous pipeline output

### Phase 3: Markdown Becomes Render Only

Remove LLM authorship of full `mapper.md`.

Acceptance:

- `mapper.md` is generated from `mapper.json`
- no machine consumer treats `mapper.md` as the source of truth
- legacy fallback remains documented but non-default

### Phase 4: Optional Upstream JSON

If Step 2.1 and Step 2.2 continue to be fragile, split earlier artifacts too:

```text
themes.json
theme_stocks.json
```

This is useful, but not required for the first `mapper.json` contract.

## Compatibility

Legacy dates may only have `mapper.md`. Keep fallback readers for historical review or ad-hoc analysis, but do not add new machine workflows that depend on Markdown parsing.

## Non-Goals

- Do not move Direction or RiskSeverity into Step 2.
- Do not make the LLM generate the complete final JSON by hand.
- Do not parse `mapper.md` to create `mapper.json` in normal operation.
- Do not change `strategy.json` or `verification.json` schemas in this refactor unless a downstream field is explicitly required.

## Completion Signal

The refactor is complete when this command sequence works for a current date:

```bash
python .opencode/skills/daily-stock-mapping/scripts/build_mapper_base.py --date {YYYY-MM-DD}
python .opencode/skills/daily-stock-mapping/scripts/build_mapper_json.py --date {YYYY-MM-DD}
python .opencode/skills/daily-stock-mapping/scripts/validate_mapper_json.py predict/{YYYY-MM-DD}/mapper.json
python .opencode/skills/daily-stock-mapping/scripts/render_mapper_md.py --date {YYYY-MM-DD}
python .opencode/skills/daily-strategy/scripts/validate_strategy_json.py predict/{YYYY-MM-DD}/strategy.json
```

And the normal daily pipeline uses:

```text
mapper.json -> strategy.json -> verification.json
```

with Markdown artifacts kept as human-readable reports.
