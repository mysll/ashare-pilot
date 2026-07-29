---
name: daily-stock-mapping
description: Step 2 of daily-market-analysis. Consume validated daily_themes.v2 plus canonical news, build the scoped theme stock pool and indicators, annotate stock-level perception, and publish mapper v2 contracts.
---

# Daily Stock Mapping

Run only Step 2. Theme retrieval, Theme semantics, Theme annotations, and
`themes.json` publication belong to Step 1 and must never be repeated or
repaired here.

## Inputs and outputs

Required inputs:

- `predict/{date}/news.json` (`daily_news.v1`)
- `predict/{date}/themes.json` (`daily_themes.v2`)

Outputs:

- `theme_stocks.extra.json` (optional)
- `theme_stocks.universe.json` (`daily_theme_stocks_universe.v2`)
- `theme_stocks.base.json` (`daily_theme_stocks_base.v2`)
- `theme_stocks.json` (`daily_theme_stocks.v2`)
- `.mapper_annotation_input.json` (non-contract)
- `mapper.annotations.json` (`daily_mapper_annotations.v1`)
- `mapper.base.json` (`daily_mapper_base.v2`)
- `mapper.json` (`daily_mapper.v2`)
- `mapper.strategy_view.json` (`daily_strategy_input.v2`)
- `step2_timing.json`

Only `sh` and `sz` are tradeable. Exclude `sh688*`, `bj*`, HK, US, and
futures through `config/trading-scope.json`. Never fetch all market stocks.

## Execute

1. Prepare the deterministic stock layer:

   ```bash
   uv run --frozen ashare-pilot mapping daily prepare --date {YYYY-MM-DD}
   ```

   This command resolves only tradeable themes against the Theme Library,
   applies trading scope, fetches pool indicators, applies hard/soft filters,
   publishes `theme_stocks.json`, and writes compact Mapper annotation input.
   Keep network requests sequential where the command owns them.

2. Read only `.mapper_annotation_input.json` and
   [references/mapper-semantics-rubric.md](references/mapper-semantics-rubric.md)
   for the Mapper LLM stage. Do not reopen Theme evidence, Theme annotations,
   `news.md`, full Theme Library files, strategy artifacts, or memory rules.

3. Write candidate-complete `mapper.annotations.json`:

   ```json
   {
     "schema_version": "daily_mapper_annotations.v1",
     "date": "YYYY-MM-DD",
     "stocks": [
       {
         "code": "sz000001",
         "news_relevance": {
           "r": "R2",
           "p": "P3",
           "confidence": 80,
           "trace": "主题新闻直接支持",
           "evidence": "news#12"
         },
         "major_event": {
           "polarity": "none",
           "confidence": 100,
           "trace": "无公司级离散事件"
         },
         "pattern_overrides": {},
         "anomaly": null
       }
     ]
   }
   ```

   Include exactly one row for every compact-input candidate. Do not add or
   remove candidates, themes, source flags, role tags, technical values,
   Direction, RiskSeverity, price levels, or recommendations.

4. Validate and repair at most once:

   ```bash
   uv run --frozen ashare-pilot mapping daily validate-annotations \
     predict/{YYYY-MM-DD}/mapper.annotations.json \
     --date {YYYY-MM-DD}
   ```

   Correct only reported annotation fields, then rerun once. Stop after a
   second failure.

5. Finalize:

   ```bash
   uv run --frozen ashare-pilot mapping daily finalize \
     --date {YYYY-MM-DD} --validation-retries <0-or-1>
   ```

## Stock-level semantic rules

### News relevance

Select one relevance and prominence pair:

| Relevance | Meaning |
|---|---|
| R4 | Company name/code is directly named |
| R3 | Named customer, supplier, or contract partner |
| R2 | Theme-level evidence without company name |
| R1 | Index, peer, or broad industry proxy |
| R0 | No supported connection |

| Prominence | Meaning |
|---|---|
| P3 | Headline or lead |
| P2 | Material body mention |
| P1 | List/chain mention |
| P0 | Absent |

Python owns the R×P score matrix. Evidence must be a canonical ref supplied in
the compact input. Do not cite news that is not present there.

### Major event

Use `positive` or `negative` only for a named company and a discrete material
event such as a major order, restructuring, large earnings surprise, approval,
penalty, investigation, fraud, suspension, or major reduction. Sector
sentiment and industry pricing are `none`.

### Pattern overrides and anomaly

Python supplies deterministic five-dimensional Pattern defaults. Add a sparse
override only when supplied evidence clearly contradicts a default. `anomaly`
is `string|null`, at most 50 characters, and may describe a genuine structural
pattern; it must not contain advice, targets, or predictions.

## Ownership invariants

- Python owns stock/theme membership, filters, technical calculations, source
  flags, role tags, score assembly, formal contract assembly, and projections.
- Step 2 LLM owns only stock-level semantic annotations.
- Step 2 never emits Direction, RiskSeverity, overrides, trade decisions, or
  strategy recommendations.
- Missing structured sources remain unavailable/neutral; never fabricate
  observations.
- JSON is the only inter-step contract. Do not produce Markdown sidecars.

Step 3 reads only the validated `daily_strategy_input.v2` projection through
the `daily-strategy` workflow.
