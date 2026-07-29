---
name: daily-theme-extraction
description: Fetch canonical daily news, prepare and annotate Theme evidence, then finalize and validate the daily news-to-theme contract. Use as the self-contained Daily Market Analysis Step 1 that produces news.json, news.md, and themes.json.
---

# Daily Theme Extraction

Own all of Daily Step 1, including deterministic news fetch and Theme
extraction. Do not load or delegate to `daily-news-brief`; that skill remains an
independent news-only workflow. Python owns news output, Theme retrieval,
provenance, formulas, rank, status, and formal JSON assembly. The LLM owns only
the semantic Theme annotations described below.

## Inputs and outputs

Formal outputs:

- `predict/{date}/news.json` (`daily_news.v1`)
- `predict/{date}/news.md`
- `predict/{date}/themes.json` (`daily_themes.v2`)

Intermediate non-contract artifacts:

- `predict/{date}/.theme_evidence_input.json`
- `predict/{date}/.theme_annotations.json`

Observability:

- `predict/{date}/step1_timing.json`

## Execute in this exact order

1. Fetch news and prepare compact evidence in one command:

   ```bash
   uv run --frozen ashare-pilot themes daily prepare \
     --date {YYYY-MM-DD} \
     --fetch-news
   ```

   The command writes `news.json`, `news.md`, and
   `.theme_evidence_input.json`. Do not reorganize `news.md` with an LLM.

2. Read only `.theme_evidence_input.json` and
   [references/theme-semantics-rubric.md](references/theme-semantics-rubric.md).
   Do not reopen `news.json`, `news.md`, the Theme Library, stock artifacts,
   Mapper artifacts, strategy artifacts, or memory rules.

3. Write `.theme_annotations.json` with this shape:

   ```json
   {
     "schema_version": "daily_theme_annotations.v1",
     "date": "YYYY-MM-DD",
     "themes": [
       {
         "name": "AI算力",
         "accepted_refs": ["news#12"],
         "confidence": 82,
         "attention_direction": "bullish",
         "market_action": 65,
         "emotion_raw": 80,
         "capital": 45,
         "policy_tier": "none",
         "policy_polarity": "neutral",
         "policy_ref": null,
         "catalyst": null,
         "reason": "算力催化与正向市场表现一致"
       }
     ]
   }
   ```

   Emit exactly one annotation for every input theme. Select
   `accepted_refs` only from that theme's evidence rows. Do not emit `rank`,
   `status`, heat, density, coefficients, base, policy bonus, or
   `matched_concepts`.

4. Publish:

   ```bash
   uv run --frozen ashare-pilot themes daily publish --date {YYYY-MM-DD}
   ```

   This command validates annotations, assembles and validates the complete
   contract in memory, requires all three formal outputs, and atomically
   publishes `themes.json`. If it reports annotation field errors, correct only
   those fields and rerun `publish` once. Stop after a second annotation
   failure or immediately on any deterministic contract error. Never edit
   evidence input or ask the orchestrator to repair artifacts.

## Timing

`prepare` and `publish` automatically record `news_fetch`, `theme_prepare`,
`theme_llm`, and `theme_finalize`. Never estimate or supply durations, counts,
artifact paths, or validation retry counts. Timing diagnostics never replace
contract validation.
