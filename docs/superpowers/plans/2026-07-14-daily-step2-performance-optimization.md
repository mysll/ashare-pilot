# Daily Step 2 Performance Optimization Plan

**Date:** 2026-07-14

**Status:** Proposed

**Scope:** `daily-market-analysis` Step 2 / `daily-stock-mapping`

## Goal

Reduce daily Step 2 wall time from the current 8–10 minutes to a normal target
of 2–4 minutes without weakening:

- Candidate Pool coverage;
- per-stock `news_impact` quality;
- `major_event` / `anomaly` detection;
- JSON-first evidence and validation contracts;
- Step 3 Direction and ranking inputs.

The optimization is not “make JSON smaller at any cost”. The objective is to
keep scripts responsible for deterministic work, reserve LLM time for genuine
semantic decisions, and remove repeated LLM authoring and tool round trips.

---

## Measured Baseline

### 2026-07-14 Step 2 timeline

Artifact modification times give the following approximate breakdown. LLM
rows include model thinking, output generation, and the surrounding tool-call
overhead.

| Stage | Approx. time | Share / note |
|---|---:|---|
| LLM writes `themes.json` | 186s | Main bottleneck |
| Build extra/universe, fetch indicators, build base | 36s | Indicator fetch about 18s |
| LLM writes `theme_stocks.annotations.json` | 129s | Main bottleneck |
| Validate/merge theme stocks | 8s | Local script itself is under 0.2s |
| LLM writes `mapper.annotations.json` | 119s | Main bottleneck |
| Build/validate mapper and strategy view | 18s | Mostly tool-call round trips |
| **Total** | **495s / 8m15s** | |

The three LLM authoring stages account for approximately 434 seconds, or 88%
of Step 2.

### Local script benchmark

Using frozen `predict/2026-07-14` artifacts and writing rebuilt files under
`/tmp`, each validator/builder completed in about 0.07–0.20 seconds. Eleven
local validate/build/project commands took about 1.2 seconds of actual Python
runtime in total.

Therefore JSON parsing and merge computation are not the primary regression.
The main causes are:

1. three sequential LLM-authored files;
2. large and partly duplicated LLM context;
3. verbose repeated per-stock JSON objects;
4. many separate agent-to-script round trips;
5. sequential indicator fetching as a bounded external-API cost that is not
   optimized in this plan because concurrency may trigger provider rate limits
   or account/IP blocking.

### Current context and output size

On 2026-07-14:

| Input/output | Size |
|---|---:|
| `daily-stock-mapping/SKILL.md` | 47 KB / 929 lines |
| `news.json` | 69 KB / 239 items |
| `news.md` | 34 KB |
| `theme_stocks.base.json` | 46 KB |
| `theme_stocks.annotations.json` | 13 KB |
| `mapper.annotations.json` | 41 KB |

The model can therefore carry well over 190 KB of instructions and data across
the full Step 2 workflow before accounting for tool output and Theme Library
queries.

### Repetitive annotation evidence

For the 45 mapper annotations on 2026-07-14:

- 44/45 `major_event` values were `none`;
- 45/45 `pattern.auction` values were `NEUTRAL`;
- all 45 stocks received a verbose five-dimension pattern object;
- volume was 34 `SURGE` and 11 `NORMAL`, derivable from numeric inputs;
- all 45 theme-stock annotations contained `source_explanation`;
- most `news_relevance` values were sector-level R2/P1 or R2/P2.

This confirms that a large part of the output token budget is spent restating
defaults or deterministic classifications.

---

## Correctness Blocker: Candidate Pool Ownership

Performance work must not begin by simply omitting annotations.

The current `build_base_from_annotations()` iterates
`mapper.annotations.json.stocks[]` and creates Candidate Pool rows from that
list. A technically eligible stock missing from annotations can therefore
disappear from the mapper instead of remaining a candidate with a validation
error.

Observed historical state:

| Date | `theme_stocks.base` candidates | Mapper annotations | Final mapper candidates |
|---|---:|---:|---:|
| 2026-07-09 | 82 | 109 | 82 |
| 2026-07-13 | 63 | 22 | 19 |
| 2026-07-14 | 45 | 45 | 45 |

### Required ownership rule

- `theme_stocks.json.stocks[].filter.status == "candidate"` exclusively owns
  Candidate Pool membership.
- `mapper.annotations.json` may enrich candidates but may not create or remove
  them.
- Missing candidate annotations are a validation failure, not a membership
  decision.
- Extra annotations for missing, observation, removed, or scope-excluded codes
  remain warn-and-skip at merge time.

This change is Task 0 and is a prerequisite for annotation reduction.

---

## Target Architecture

Reduce Step 2 from three LLM authoring stages and many script calls to two LLM
stages and two orchestration commands:

```text
news.json
  |
  v
build_theme_evidence_input.py              # deterministic compact retrieval
  |
  v
LLM A: themes.json                         # semantic theme choice + heat
  |
  v
prepare_daily_mapping.py                   # one command
  - validate themes
  - build universe
  - fetch indicators
  - build theme_stocks base/final JSON
  - build compact mapper annotation input
  |
  v
LLM B: mapper.annotations.json             # sparse semantic overrides
  |
  v
finalize_daily_mapping.py                  # one command
  - validate annotation coverage/fields
  - build mapper base
  - merge annotations
  - validate mapper
  - build strategy view
  - emit timing report
```

### Contract principles

1. Keep `news.json`, `themes.json`, `theme_stocks.json`, `mapper.json`, and
   `mapper.strategy_view.json` as the formal JSON contracts.
2. Do not add sidecar artifacts when a deterministic value can be written
   directly into a script-owned base document.
3. Delete `theme_stocks.annotations.json` from the future daily workflow. Do
   not retain compatibility reads, overrides, or historical regeneration.
4. Keep `mapper.annotations.json` LLM-owned, but make it sparse and limited to
   semantic information.
5. Preserve full candidate-specific `news_relevance`; never blanket-fill R2/P2.
6. Missing source data produces `UNKNOWN`/null, not invented neutral facts.
7. Keep `fetch_pool_indicators.py` sequential in this plan; API safety takes
   precedence over saving tens of seconds.

---

## Task 0: Fix Candidate Pool Membership Before Optimizing

**Files:**

- Modify: `.agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/build_mapper_base.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/validate_mapper_annotations.py`
- Add mapper membership and coverage tests under the skill test directory

### Implementation

1. Replace annotation-driven candidate construction with a function that
   iterates candidate rows from `theme_stocks.json`.
2. Build deterministic candidate fields from `theme_stocks.json` and
   `pool_indicators.json` even when annotations are missing.
3. Apply `mapper.annotations.json` only in the merge stage.
4. Validator must compare annotation codes with the complete deterministic
   candidate set.
5. Fail validation for every missing candidate annotation.
6. Continue warning and skipping extra legal annotation rows during merge.

### Tests

- Candidate exists in theme stocks but is absent from annotations: candidate
  remains in mapper base; annotation validation fails.
- Observation stock appears in annotations: it is not promoted to candidate.
- Extra A-share annotation not in theme stocks: warn and skip.
- Candidate ordering is independent of annotation file order.
- Date and code-scope checks remain strict.

### Acceptance

For each regression date:

```text
set(mapper.base.candidate_pool.code)
==
set(theme_stocks.json stocks where filter.status == candidate)
```

---

## Task 1: Add Step 2 Timing and Volume Observability

**Files:**

- Create: `.agents/skills/daily-stock-mapping/scripts/build_step2_timing.py`
- Modify: `.agents/skills/daily-stock-mapping/SKILL.md`
- Modify: `.agents/skills/daily-market-analysis/SKILL.md`

### Output

Write report-only diagnostics to:

```text
predict/{date}/step2_timing.json
```

Suggested contract:

```json
{
  "schema_version": "daily_step2_timing.v1",
  "date": "YYYY-MM-DD",
  "stages": {
    "themes_llm": {"seconds": 0},
    "prepare_mapping": {"seconds": 0},
    "mapper_annotations_llm": {"seconds": 0},
    "finalize_mapping": {"seconds": 0}
  },
  "counts": {
    "news": 0,
    "themes": 0,
    "universe": 0,
    "base_candidates": 0,
    "mapper_annotations": 0,
    "final_candidates": 0
  },
  "bytes": {
    "theme_input": 0,
    "themes_json": 0,
    "mapper_annotation_input": 0,
    "mapper_annotations_json": 0
  }
}
```

Use runtime/model token metrics when the agent runtime exposes them. Otherwise
use stage start/end timestamps and artifact metadata. Timing collection must
not become another mandatory LLM-authored file.

### Acceptance

- Every live Step 2 run reports stage duration and row counts.
- A missing timing report does not invalidate trading contracts.
- Counts expose candidate loss immediately.

---

## Task 2: Delete `theme_stocks.annotations.json`

**Files:**

- Modify: `.agents/skills/daily-stock-mapping/scripts/build_theme_stocks_json.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/build_theme_stocks_universe.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/build_theme_stocks_base.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py`
- Delete: `.agents/skills/daily-stock-mapping/scripts/validate_theme_stocks_annotations.py`
- Modify: `.agents/skills/daily-stock-mapping/SKILL.md`
- Modify: `.agents/skills/daily-market-analysis/SKILL.md`

### New rule

`theme_stocks.json` is built directly from deterministic universe, source,
Theme Library, market-view, news-direct, LHB, scope, and technical-filter data.
The future workflow does not create, read, validate, or merge
`theme_stocks.annotations.json`.

There is no compatibility mode, override file, feature flag, or historical
regeneration path. Previously generated strategies are final and are not in
scope for rebuilding.

### Field ownership

| Existing annotation field | Final handling |
|---|---|
| `source_flags` | Universe builder from actual source membership |
| `news_ref` | Deterministic news stock matching where needed to derive `NewsDirect` |
| `market_ref` | Market-view batch data where needed to derive `MarketActive` |
| theme `note` / `evidence` | Delete; `themes.json` already owns theme evidence |
| `source_explanation` / stock `note` | Delete with no replacement |
| candidate `anomaly` | `mapper.annotations.json` only |
| observation `anomaly` | Mapper annotation stage or deterministic observation rule only if Step 3 still consumes it |

The only annotation information that can affect Step 3 today is:

1. `source_flags`, because mapper projects them to `ThemeLibrary`,
   `MarketActive`, `NewsDirect`, and `LHB` role tags;
2. `anomaly`, because mapper projects candidate/observation anomalies to the
   Step 3 strategy view.

Both must be migrated before deletion. All other annotation fields are removed.

If market-view data is absent, keep `source_flags.market=false`. Do not ask the
LLM to guess market activity merely to preserve a populated field. Market flags
must be derived from actual `query_theme.py market` results such as
`cross_rank_highlights`, `market_attention`, and `top_gainers` according to the
existing skill rules.

Do not add `source_trace`, translated source text, or another intermediate
explanation field. Intermediate JSON keeps only the compact machine fields and
references needed to derive the same mapper role tags.

### Required code removal

- Remove the `--annotations` argument and annotations existence/schema checks
  from `build_theme_stocks_json.py`.
- Publish `daily_theme_stocks.v1` directly from `theme_stocks.base.json` after
  updating generated metadata.
- Remove `merge_theme_stock_annotations()`.
- Delete the annotation validator.
- Remove the artifact, authoring instructions, schema example, validation
  command, and merge command from both workflow skills.
- Remove `annotation_schema_version` and use a deterministic generation mode.

### Decision-equivalence gate

Deletion is allowed only when the old and new `mapper.strategy_view.json` are
deep-equal for every field visible to Step 3, excluding generated timestamps
and generation-mode metadata. In particular, candidate `role_tags` and all
candidate/observation anomalies must remain equal.

### Expected gain

Approximately 30–130 seconds per day based on recent runs, plus lower context
growth before mapper annotation generation.

---

## Task 3: Build a Compact Theme Evidence Input

**Files:**

- Create: `.agents/skills/daily-stock-mapping/scripts/build_theme_evidence_input.py`
- Add retrieval/deduplication tests
- Modify the theme extraction section of `daily-stock-mapping/SKILL.md`

### Purpose

Avoid making the theme LLM repeatedly scan full `news.json`, `news.md`, URLs,
and the full Theme Library search space.

### Input and output

Input:

- canonical `predict/{date}/news.json`;
- Theme Library names, aliases, keywords, and member concepts.

Output, as a script-owned intermediate input:

```json
{
  "schema_version": "daily_theme_evidence_input.v1",
  "date": "YYYY-MM-DD",
  "theme_candidates": [
    {
      "name": "AI算力",
      "matched_by": ["alias:算力", "keyword:数据中心"],
      "news_refs": ["news#12", "news#44"],
      "items": [
        {
          "ref": "news#12",
          "category": "flash",
          "source": "CLS",
          "title": "..."
        }
      ]
    }
  ],
  "unmatched_high_priority_items": []
}
```

### Rules

- Preserve canonical `news#<id>` references.
- Remove URL, `source_item_no`, and empty description fields from LLM input.
- Deduplicate repeated titles while retaining the complete source-ID list.
- Retrieval must be high recall; the LLM still makes the final theme decision.
- Include unmatched high-priority policy, flash, sentiment, and market-action
  items so keyword retrieval cannot silently hide new catalysts.
- Theme names still come exclusively from Theme Library.
- `news.md` remains a readable report, not a mandatory Step 2 evidence input.

### Regression

For 2026-07-09, 2026-07-13, and 2026-07-14:

- every historically selected theme must appear in the retrieval candidate
  list, or its absence must be reviewed and explained;
- every emitted `news#id` must resolve in canonical `news.json`;
- input bytes and candidate count must be reported.

---

## Task 4: Compute Deterministic Pattern Fields in Mapper Base

**Files:**

- Modify: `.agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/build_mapper_base.py`
- Add deterministic pattern tests

Do not create a mandatory `pattern_defaults.json` sidecar. Write defaults
directly into the script-owned mapper base and overlay sparse LLM overrides.

### Ownership

| Dimension | Default owner | Rule |
|---|---|---|
| `volume` | Python | amount / volume ratio using verified units |
| `leader` | Python | Anchor, board streak, seal quality |
| `rotation` | Python where inputs exist | MultiTheme, purity, pool membership |
| `auction` | Python only with real auction input | Otherwise `UNKNOWN`, not previous-close change |
| `heat` | Python only with comparable history | Otherwise low-confidence `STABLE` or `UNKNOWN` |

### Safety rules

- Never turn absent data into high-confidence `NEUTRAL`.
- Never use yesterday's `change_pct` as call-auction change.
- Each script-generated state includes a concise trace naming its input fields.
- LLM overrides only supplied dimensions; missing override keys preserve base.
- Pattern object normalization must preserve `{state, confidence, trace,
  evidence}` rather than stringify nested dictionaries.

### Tests

- Exact amount boundaries for `DRY`, `NORMAL`, and `SURGE`.
- Missing auction data produces `UNKNOWN`.
- Valid auction data maps to the documented auction enum.
- Anchor/streak combinations map to expected leader states.
- Sparse LLM override changes only the named dimension.

---

## Task 5: Make Mapper Annotations Sparse and Candidate-Complete

**Files:**

- Modify: `.agents/skills/daily-stock-mapping/SKILL.md`
- Modify: `.agents/skills/daily-stock-mapping/scripts/validate_mapper_annotations.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py`
- Modify: `.agents/skills/daily-strategy/SKILL.md`
- Modify: `.agents/skills/daily-strategy/scripts/validate_strategy_json.py`
- Modify: `.agents/skills/daily-strategy/scripts/render_daily_report_html.py`
- Add sparse annotation contract tests

### Required per candidate

- `code`;
- complete candidate-specific `news_relevance` matrix decision;
- evidence or trace for `news_relevance`.

### Sparse optional fields

- `major_event` only when a named company-level discrete event exists;
- `anomaly` only when a mandatory trigger or genuine structural anomaly exists;
- `pattern` only for dimensions that override deterministic base values;
- `news_link` may be projected from `news_relevance.evidence`.

When absent, the builder supplies:

- `major_event.polarity = none` with script trace;
- `anomaly = null`;
- deterministic/unknown base pattern;
- no fabricated evidence.

### Validation

- Candidate code coverage must be exact before mapper publication.
- `news_relevance` is mandatory for every candidate.
- Missing optional fields are allowed only because the base owns their defaults.
- Extra annotation codes warn and skip at merge.
- Duplicate codes, invalid enums, invalid dates, and invalid evidence remain hard
  failures.
- Add a review check that detects suspicious blanket R2/P2 assignment.

### Compact authoring guidance

Keep machine values compact. Do not require repetitive prose such as “no
company-specific event” 40 times. Generate deterministic trace text in Python
when the value itself is a deterministic default.

Do not generate translated source explanations for all candidates in Step 2.
Step 2 retains only the existing compact machine inputs needed by Step 3, such
as `role_tags` and evidence links.

### Final source explanation belongs to Step 3

Only the final stocks selected into `strategy.json.stocks[]` need a readable
Chinese source/selection explanation. The current strategy contract selects 10
stocks, so Step 3 must add one concise field inside the existing reasoning
object:

```json
{
  "reasoning": {
    "source_basis": "AI算力主题候选，市场活跃，并被 news#87 直接提及",
    "direction_path": "comp=71.8→看多; final=看多",
    "risk": "—",
    "reread": "—",
    "override": "—"
  }
}
```

Rules:

- Generate `reasoning.source_basis` only for final strategy stocks, not for all
  Step 2 candidates.
- Base it only on the machine `role_tags` and evidence links supplied by Step 2.
- Do not invent a market/news source that is absent from the mapper input.
- `strategy.json.observation_pool[]` keeps only its existing compact exclusion
  `reason`; it does not need a translated source explanation.
- The HTML renderer displays Step 3's text and does not reinterpret strategy
  meaning.
- The strategy validator requires a non-empty `reasoning.source_basis` for
  every final `stocks[]` row.

### Expected gain

Reduce mapper annotation output from five pattern objects plus event defaults
per candidate to one required news matrix decision and exceptional overrides.
Expected LLM stage reduction: roughly 40–70% depending on candidate count.

---

## Task 6: Add Prepare and Finalize Orchestration Commands

**Files:**

- Create: `.agents/skills/daily-stock-mapping/scripts/prepare_daily_mapping.py`
- Create: `.agents/skills/daily-stock-mapping/scripts/finalize_daily_mapping.py`
- Modify both workflow skill documents
- Add orchestration smoke tests

### Prepare command

```bash
python .agents/skills/daily-stock-mapping/scripts/prepare_daily_mapping.py \
  --date YYYY-MM-DD
```

Runs, with explicit stage error reporting:

1. validate `themes.json`;
2. build `theme_stocks.universe.json`;
3. fetch `pool_indicators.json`;
4. build filtered `theme_stocks.json`;
5. build compact mapper annotation input/target list;
6. record counts and elapsed time.

### Finalize command

```bash
python .agents/skills/daily-stock-mapping/scripts/finalize_daily_mapping.py \
  --date YYYY-MM-DD
```

Runs:

1. validate candidate coverage and mapper annotations;
2. build mapper base from deterministic candidate membership;
3. merge sparse annotations;
4. validate mapper;
5. build strategy view;
6. emit timing/count diagnostics.

### Requirements

- Reuse Python functions rather than launching many subprocesses when practical.
- Stop on the first correctness failure and name the failed stage.
- Preserve individual scripts as supported debugging entrypoints.
- Do not hide validation warnings or silently regenerate LLM artifacts.

### Expected gain

Reduce agent/tool orchestration overhead by approximately 30–60 seconds on
normal runs without changing scoring semantics.

---

## Task 7: Refactor Skill Context by Phase

**Files:**

- Modify: `.agents/skills/daily-stock-mapping/SKILL.md`
- Create small phase-specific references only where necessary

### Goal

Reduce the 929-line main skill while retaining all correctness rules.

### Structure

Keep the main skill focused on:

- pipeline sequence;
- artifact ownership;
- required gates;
- scope and evidence rules;
- failure handling;
- compact output contracts.

Move detailed material into phase references:

- theme heat and policy rubric;
- mapper news relevance/event/anomaly rubric;
- schema examples that duplicate validator behavior.

Each LLM phase loads only its relevant reference. Do not remove rules merely to
reduce prompt size; validators and scripts should own rules that can be
expressed deterministically.

---

## Task 8: Regression and Performance Harness

Use frozen same-day inputs from:

- 2026-07-09: oversized universe and over-annotation case;
- 2026-07-13: missing-candidate annotation case;
- 2026-07-14: normal candidate-complete baseline.

These dates are regression fixtures only. The production workflow does not
support historical strategy regeneration. All comparisons use temporary output
paths or fixture directories and never overwrite `predict/{date}` artifacts.

### Correctness checks

| Check | Requirement |
|---|---|
| Candidate membership | Exactly equals deterministic theme-stock candidates |
| Candidate coverage | 100% have valid news relevance before publication |
| Observation/excluded membership | Unchanged unless an intentional filter fix is documented |
| Composite values | Exact when semantic inputs are unchanged |
| Top-10 mapper ranking | 10/10 when semantic inputs are unchanged |
| Major-event non-none set | Identical for frozen annotations |
| Anomaly set | Identical unless reviewed migration changes it |
| Evidence refs | Every `news#id` resolves in canonical `news.json` |
| Strategy inputs | Exact projection from pool indicators |

The primary deletion gate is decision-input equivalence:

```text
old mapper.strategy_view.json
==
new mapper.strategy_view.json
```

Compare `market_state`, `themes`, candidate codes/order, `role_tags`, all
scores, major events, risk types, patterns, anomalies, news links, strategy
inputs, and the observation pool. Ignore only generated timestamps and
generation-mode metadata.

### Strategy safety check

Run a shadow Step 3 comparison after mapper regression passes:

- compare candidate coverage;
- compare Direction distribution and actionable top names;
- inspect every Direction change;
- verify that no change comes from missing annotation or invented defaults;
- preserve the existing strategy validator and review pipeline.

### Performance checks

Record for every sample/live run:

- total Step 2 wall time;
- theme LLM time and input/output size;
- stock annotation LLM time and input/output size;
- prepare/finalize runtime;
- universe and candidate count;
- sequential indicator fetch duration and failures;
- annotation rows and bytes.

---

## Rollout Order

```text
Phase A — correctness and measurement
  Task 0 candidate membership ownership
  Task 1 timing/count diagnostics

Phase B — low-risk round-trip reduction
  Task 2 delete theme_stocks annotations
  Task 6 prepare/finalize orchestration

Phase C — annotation output reduction
  Task 4 deterministic pattern base
  Task 5 sparse candidate-complete mapper annotations

Phase D — input and context reduction
  Task 3 compact theme evidence retrieval
  Task 7 phase-specific skill context

Phase E — shadow validation and live rollout
  Task 8 three-date regression
  one or more live shadow runs
  enable optimized workflow by default
```

Do not start by tightening universe top-N defaults. Universe reduction changes
recall and currently saves much less time than eliminating redundant LLM work.
Consider it only after the optimized pipeline is measured and candidate counts
still materially exceed the intended range.

---

## Success Metrics

### Performance

| Metric | Target |
|---|---|
| Normal Step 2 wall time | 2–4 minutes |
| Step 2 P95 after sufficient live samples | Under 5 minutes |
| LLM authoring stages | 2 instead of 3 |
| Mandatory script orchestration calls | 2 after themes instead of 10+ |
| Mapper annotation bytes | At least 40% lower on comparable candidate count |

### Correctness

| Metric | Target |
|---|---|
| Candidate membership coverage | 100% |
| Candidate annotation coverage | 100% before mapper publication |
| Missing candidate silently dropped | 0 |
| Invalid/unresolved news evidence | 0 |
| Blanket R2/P2 shortcut | 0 reviewed occurrences |
| Deterministic fields authored by LLM | Only explicit overrides |
| Old/new Step 3 decision-input diff after annotation deletion | 0 fields |
| Final strategy stocks with `reasoning.source_basis` | 100% (normally 10/10) |

### Rollback

- Use temporary shadow outputs before merging the deletion.
- Once the decision-equivalence gate passes, delete the annotation stage and
  its validator/merge code in the same change; do not ship dual production
  paths.
- Revert the change as a whole if candidate membership, role tags, anomalies,
  composite values, evidence resolution, or strategy validation regresses.

---

## Explicit Non-Goals

- Do not change composite weights in this optimization.
- Do not move Direction or RiskSeverity into Step 2.
- Do not default every candidate to sector-level R2/P2.
- Do not remove candidate-specific news relevance analysis.
- Do not replace absent auction data with previous-close movement.
- Do not use full-market stock fetching.
- Do not add concurrency to `fetch_pool_indicators.py`; concurrent requests may
  trigger API rate limiting or blocking. Keep the current sequential behavior.
- Do not treat Markdown as a downstream machine contract.
- Do not commit regenerated `predict/` artifacts unless explicitly requested.

---

## Expected Outcome

For a day similar to 2026-07-14, the target budget is:

| Optimized stage | Expected time |
|---|---:|
| Compact retrieval + theme LLM | 60–120s |
| Prepare mapping and sequential indicators | 20–60s |
| Sparse mapper annotation LLM | 40–90s |
| Finalize mapping | 2–10s |
| **Total** | **Approximately 2–4 minutes** |

The primary performance win comes from removing one full LLM authoring stage,
reducing theme and stock annotation context/output, and collapsing script tool
round trips. Indicator fetching remains sequential for API safety.

---

## Review Amendments (2026-07-14, second-pass code-aligned review)

**Reviewer role:** Independent review against current repo contracts
(`mapper_json_lib.build_base_from_annotations`, theme-stock merge path,
`predict/2026-07-09|13|14` artifacts, Step 3 read surface).

**Overall verdict:** Direction is sound and stronger than the earlier
annotation-reduction-only plan. Task 0, hard-delete of
`theme_stocks.annotations.json`, pattern defaults in mapper base, sparse
mapper annotations, prepare/finalize, and sequential indicator fetch are
reasonable. **Do not implement as written until the four must-fix items
below are accepted or explicitly rejected with rationale.**

### What is correct and should stay

| Item | Why it holds under current code |
|------|----------------------------------|
| Task 0 candidate membership | `build_base_from_annotations()` still iterates `mapper.annotations.json.stocks[]` to *create* candidate rows; missing annotation can drop an eligible stock (e.g. 2026-07-13: 63 base candidates → 22 annotations → 19 mapper candidates). |
| Delete daily `theme_stocks.annotations.json` | Merge only patches semantic fields; does not own `filter.status` / technicals / membership. Historical files mostly restate `source_flags` and verbose `source_explanation`. Large wall-time win (~129s on 2026-07-14). |
| Migrate only Step-3-visible effects | `source_flags` → `role_tags`; `anomaly` → strategy view. Other annotation fields are display/audit only. |
| Pattern defaults in mapper base (no sidecar) | Cleaner than a mandatory `pattern_defaults.json`. |
| No indicator concurrency in this plan | Secondary cost; rate-limit risk is real. |
| No early universe top-N tighten | Saves less than LLM stages; changes recall. |
| Phase order A → B → C → D → E | Correctness before sparse annotations before input compression. |
| Forbidden blanket R2/P2; no fake auction/NEUTRAL | Strategy-safe. |

### Must-fix before coding

#### A1. Replace “full strategy_view deep-equal” with layered gates

**Problem:** Task 2 and Task 8 require old/new `mapper.strategy_view.json`
deep-equal (ignoring timestamps). That conflicts with later intentional
fixes:

- Task 4: missing auction must become `UNKNOWN`, not high-confidence
  `NEUTRAL`. On 2026-07-14, 45/45 `pattern.auction` were `NEUTRAL` — a
  correct Task 4 will *fail* full deep-equal.
- Task 5: sparse defaults change `major_event` traces / omitted pattern
  dims even when semantics are equivalent.

**Required amendment:**

| Stage | Gate |
|-------|------|
| Task 2 only | Candidate code set equal; observation/excluded sets equal; `role_tags` equal (or a documented, reviewed flag-migration diff); **do not** require pattern / major_event / full scores deep-equal |
| After Task 4/5 | Maintain an **intentional-diff allowlist** (e.g. auction NEUTRAL→UNKNOWN when no auction input); composite exact when `news_impact` and other semantic inputs unchanged |
| End-to-end | Shadow Step 3: every Direction / top-name change must be explained; no silent drops |

#### A2. Task 0 must also fix theme ownership, not only stock membership

**Problem:** Mapper base themes / `market_state.dominant_themes` are still
seeded from `mapper.annotations.json.themes[]`, and heat is partially
derived from annotation emotion placeholders — not solely from
`themes.json` / `theme_stocks.json`.

**Required amendment:** Deterministic theme list + heat come from
`themes.json` (or already-resolved `theme_stocks.json.themes`). Mapper
annotations may overlay theme-level semantic fields only (emotion /
policy / catalyst), and must not create or drop themes from the pool
used by Step 3.

#### A3. Deleting theme-stock annotations requires forced deterministic market/news/LHB flagging in prepare

**Problem:** Today `source_flags.market` / news / lhb are often completed
or restated by the LLM in `theme_stocks.annotations.json`. Market view is
optional agent work, not a guaranteed script stage. If annotations are
deleted without a mandatory batch path, `MarketActive` / `NewsDirect` /
`LHB` role tags will systematically shrink and Task 2 role-tag gates will
fail for the wrong reason.

**Required amendment:**

- `prepare_daily_mapping.py` (or an earlier deterministic step it calls)
  must batch market-view selection and write `source_flags` /
  membership into universe/base **before** publishing
  `theme_stocks.json`.
- Same for news-direct and LHB when those extras are in scope for the day.
- If market data is unavailable: keep `market=false` (as written); do not
  invent flags — but then role-tag diffs vs historical LLM days are
  expected and must be classified as **data-availability diffs**, not
  silent regressions.

#### A4. `reasoning.source_basis` is scope creep; demote or script it

**Problem:** Task 5 requires Step 3 `strategy.json.stocks[].reasoning.source_basis`
and validator/HTML changes. That:

- does not reduce Step 2 wall time;
- expands scope beyond `daily-stock-mapping` into `daily-strategy` contracts;
- breaks historical strategy validation if the field becomes mandatory;
- risks LLM inventing sources unless tightly bound to machine tags.

**Required amendment (pick one, document choice):**

1. **Preferred:** Script-generate a one-line `source_basis` from
   `role_tags` + `news_link` for final strategy stocks; LLM optional polish;
   or
2. Move to a separate “report readability” task after Step 2 perf ships; or
3. Keep optional (non-failing) for one release, then tighten.

Do not block Step 2 performance merge on a mandatory new Step 3 prose field
unless product explicitly prioritizes it.

### Should-fix (important, not blockers)

#### B1. Time target 2–4 minutes is a stretch, not Task-2 acceptance

Rough re-budget for a 2026-07-14-like day if themes LLM stays ~186s:

```text
~495s baseline
- ~129s remove theme_stocks.annotations
- ~30–60s prepare/finalize less tool thrash
- ~40–80s sparse mapper annotations
≈ 4–5+ minutes without a large themes-stage win
```

Hitting 2–4 minutes needs Task 3 (and possibly skill-phase split) to cut
theme LLM time substantially. If the bottleneck is multi-factor heat
reasoning rather than news bytes, evidence compression alone may under-deliver.

**Amendment:** Split success metrics:

- P0 after Task 0+2+6: stable Step 2 under ~6–7 minutes on comparable days
- P1 after Task 4+5+3: normal 3–5 minutes
- 2–4 minutes: stretch / P95 goal after live samples

#### B2. Zero historical regeneration is OK; fixtures must not assume old rebuild paths

Hard-delete with no ann read path is acceptable if old strategies are final.
Task 8 fixtures must freeze the **decision inputs** needed for comparison
(e.g. published `theme_stocks.json` / expected role tags / mapper ann), not
assume new code can recreate old `theme_stocks.json` from deleted
annotations.

#### B3. Clarify observation `anomaly`

Replace “if Step 3 still consumes it” with a measured decision:

- If strategy_view / Step 3 / HTML ignore observation anomalies → delete
  the field from the migration plan; keep compact `reason` only.
- If consumed → single owner (mapper annotation optional row, or
  deterministic rule), no dual paths.

#### B4. Task 3 recall guard

Keep high-recall retrieval + unmatched high-priority items. Add: every
`news#id` cited by a historical tradeable theme’s evidence must appear in
that theme’s retrieved items or in unmatched high-priority, or be filed
as a reviewed miss.

#### B5. Compact mapper annotation input vs “no sidecar” principle

Prepare may emit a compact LLM input file for agent convenience. Treat it
as **intermediate / non-contract** (or stdout-only). Do not add a new
formal long-lived schema unless validators depend on it. Formal contracts
remain themes / theme_stocks / mapper / strategy_view.

#### B6. Scope line for strategy-skill edits

If A4 option 1/3 still touches `daily-strategy`, widen the plan Scope line
to “Step 2 + minimal Step 3 contract for source_basis”, or split PRs:
Step 2 perf first, strategy prose second.

### Task-by-task reasonableness

| Task | Verdict | Note |
|------|---------|------|
| 0 Membership | Must-do, correct | Extend with A2 themes ownership |
| 1 Timing | Reasonable | Non-trading diagnostic OK |
| 2 Delete theme_stocks.ann | High value | Apply A1 + A3 |
| 3 Theme evidence input | Reasonable, medium risk | Needs recall metrics (B4); largest uncertainty for 2–4m |
| 4 Pattern in base | Reasonable | Intentional UNKNOWN diffs (A1) |
| 5 Sparse mapper | Reasonable | Demote source_basis (A4) |
| 6 prepare/finalize | Reasonable | Host A3 flagging |
| 7 Skill phase split | Reasonable, later | Hard to quantify alone |
| 8 Regression | Reasonable | Layered gates, not full deep-equal forever |
| No fetch concurrency | Reasonable | Keep |
| No universe tighten first | Reasonable | Keep |

### Suggested text patches (for plan author)

1. **Contract principle / Task 2 gate:** replace “strategy_view deep-equal”
   with layered gates in A1.
2. **Task 0:** add themes ownership paragraph from A2.
3. **Task 2 / Task 6:** add mandatory deterministic market/news/LHB →
   `source_flags` in prepare (A3).
4. **Task 5:** demote `reasoning.source_basis` per A4.
5. **Success metrics:** add P0/P1/stretch time bands (B1).
6. **Task 8:** fixture language for frozen decision inputs (B2); drop
   permanent full-view equality as the sole primary gate.

### Non-blocking agreement with plan non-goals

Agree: no composite weight change; no Step 2 Direction/RiskSeverity; no
blanket R2/P2; no fake auction; no full-market fetch; no Markdown machine
contracts; no committing regenerated `predict/` unless requested.

### Bottom line for the other author

The plan is **good enough to be the master plan** after incorporating
**A1–A4**. Without those, Task 2’s equivalence gate will fight Task 4’s
correctness rules, role tags may regress when annotations disappear, and
Step 3 scope may expand for little Step 2 speedup.

Please reply with accept/reject on A1–A4 (and optional B1–B6). After that,
implementation should start at Phase A Task 0 only.
