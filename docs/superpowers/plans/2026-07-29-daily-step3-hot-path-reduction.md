# Daily Step 3 Hot-Path Reduction — Modification Checklist

**Date:** 2026-07-29

**Status:** Proposed / Ready for implementation

**Scope:** Reduce Step 3 LLM input/output work without changing rule loading,
rule matching ownership, the candidate universe, or the formal
`daily_strategy.v3` output contract.

**Predecessor:** [2026-07-15 Step 3 Performance Optimization](2026-07-15-daily-step3-performance-optimization.md)

---

## 1. Current baseline

The 2026-07-29 run provides the implementation baseline:

| Metric | Current value |
|---|---:|
| Step 3 total recorded time | 200.116s |
| Prepare | 0.995s |
| Strategy LLM | 199.086s |
| Finalize | 0.035s |
| Candidates | 21 |
| Selected stocks | 5 |
| Compact input | 24,637 bytes |
| Minified draft | 10,816 bytes |
| Draft validation retries | 1 |

The retry was caused by an LLM-copied deterministic field:

```text
stocks[1].name: differs from compact candidate
```

The Python stages are already fast. This change targets LLM context parsing,
draft generation, and avoidable validation repair.

## 2. Locked non-goals

This phase MUST NOT:

- modify, summarize, filter, retrieve, index, or preselect
  `memory/RULES.md` or `memory/SHARED_RULES.md`;
- change rule matching or override ownership;
- change rule governance, lifecycle, evidence, or memory write paths;
- introduce a top-N shortlist or omit/reorder any Step 2 candidate;
- move final regime, selected codes/order, Direction, rating, position tier,
  RiskSeverity application, or rule application out of the LLM;
- weaken validation, source grounding, T+1 constraints, or manual execution;
- parallelize candidate reasoning across multiple LLM calls;
- change the formal `daily_strategy.v3` or `daily_report.html` contracts merely
  to improve performance.

The existing rule files remain mandatory hot-stage inputs exactly as they are.

## 3. Target

For a comparable 21-candidate run:

- eliminate retries caused by deterministic copied fields;
- reduce compact input from 24.6KB to at most 16KB;
- reduce a five-stock minified draft from 10.8KB to at most 6KB;
- reduce Strategy LLM time from approximately 199s toward 120–150s;
- retain every candidate in original order and preserve all final
  LLM-owned decisions.

Timing targets are provisional. Do not claim a stable improvement until at
least five artifact-linked live runs are available.

## 4. Contract boundary after the change

### 4.1 Python-owned draft materialization

Remove these deterministic or fixed values from LLM ownership:

- stock `name`;
- root `generated_at`;
- fixed `market.requires_open_confirmation`;
- fixed `market.stop_atr_multiplier`;
- fixed `portfolio_limits`;
- fixed stock `horizon`;
- fixed earliest/latest entry times;
- fixed first-bar, market-confirmation, and theme-confirmation booleans;
- deterministic Trade Profile trace and unchanged profile fields.

Python copies stock names from the candidate selected by `code`. This removes
the entire copied-name validation failure class, including differences in
spaces or aliases.

### 4.2 LLM-owned decision payload

The LLM continues to emit:

- final market regime and concise regime notes;
- selected stock codes and order;
- source theme when more than one source theme is available;
- final Direction, rating, and qualitative position tier;
- entry profile, anchor, and entry setup;
- applied rules;
- concise source basis, Direction path, and risk reasoning;
- justified profile or plan overrides;
- exceptional exclusion overrides.

The temporary decision schema must contain only these decisions. Bump the
non-contract draft schema rather than accepting both old and new shapes.

### 4.3 Python-generated execution baseline

Add a deterministic execution-plan materializer that derives the default:

- entry trigger;
- no-buy condition;
- pre-open plan;
- T+1 risk plan;
- profile trace;
- final Trade Profile.

Inputs include final regime, selected anchor/profile/tier, candidate
MA/ATR/price fields, risk flags, theme, and deterministic profile base.

The LLM may provide sparse, reasoned overrides for exceptional conditions.
Python validates the override whitelist and never silently repairs an invalid
override.

## 5. Modification checklist

### Task 1 — Define the compact decision draft

- [x] Introduce one new temporary draft schema.
- [x] Remove `name` from each LLM-selected stock.
- [x] Remove root timestamps and fixed contract constants from LLM output.
- [x] Replace full plan text with compact decision fields plus sparse
      overrides.
- [x] Make no-op reasoning fields optional instead of requiring the literal
      `—`.
- [x] Add maximum lengths for remaining LLM prose fields.
- [x] Reject old temporary draft schemas; do not add a compatibility reader.

Expected primary files:

- `src/ashare_pilot/strategy/_commands/daily/finalize.py`
- `src/ashare_pilot/strategy/_commands/daily/validate_draft.py`
- `.agents/skills/daily-strategy/references/strategy-output-contract.md`

### Task 2 — Materialize deterministic strategy fields

- [x] Copy `name` from the compact candidate selected by `code`.
- [x] Generate `generated_at` in Python.
- [x] Fill fixed market and portfolio fields in Python.
- [x] Generate the standard pre-open and T+1 plans from structured inputs.
- [x] Generate deterministic profile trace text.
- [x] Apply only validated sparse LLM overrides.
- [x] Assemble the existing `daily_strategy.v3` shape before final validation.
- [x] Keep `daily_report.html` consuming only the formal strategy contract.

Prefer a focused helper module instead of adding more branching to
`finalize.py`, for example:

```text
src/ashare_pilot/strategy/_commands/daily/plan_baseline.py
```

### Task 3 — Compact every candidate without prefiltering

- [x] Preserve all candidate codes exactly once and in original order.
- [x] Add top-level candidate defaults for repeated neutral/default values.
- [x] Emit candidate fields only when they differ from those defaults.
- [x] Deduplicate repeated `profile_base` values.
- [x] Omit `major_event` when polarity is `none`.
- [x] Omit null anomaly, empty risk types, and zero severity.
- [x] Omit the base `ThemeLibrary` role and retain only additional role tags.
- [x] Omit `source_themes` when it equals the single primary theme.
- [x] Reference top-level evidence sets instead of repeating identical news
      refs on many candidates.
- [x] Round displayed technical floats to contract-safe precision.
- [x] Preserve every score, Pattern state, risk, role, evidence, and strategy
      input needed by the current rubric.

Expected primary files:

- `src/ashare_pilot/strategy/_commands/daily/llm_input.py`
- `src/ashare_pilot/strategy/_commands/daily/prepare.py`

The temporary compact-input schema must be bumped. Do not accept both layouts.

### Task 4 — Reduce repetitive selected-stock prose

- [x] Keep `source_basis`, Direction reasoning, and risk reasoning concise and
      auditable.
- [x] Replace repeated generic entry/risk prose with deterministic templates.
- [x] Require LLM prose only for actual exceptions, overrides, or
      stock-specific risks.
- [x] Preserve canonical `news#<id>`, role-tag, and source-theme grounding.
- [x] Keep the final HTML human-readable after template materialization.

Expected primary files:

- `.agents/skills/daily-strategy/SKILL.md`
- `.agents/skills/daily-strategy/references/strategy-selection-rubric.md`
- `.agents/skills/daily-strategy/references/strategy-output-contract.md`
- `src/ashare_pilot/strategy/_commands/daily/render_report.py` only if the
  existing formal fields are insufficient after materialization.

### Task 5 — Update validation and failure semantics

- [x] Validate selected membership and duplicate codes before materialization.
- [x] Validate optional source theme against candidate source themes.
- [x] Validate all LLM-owned enums and override structures.
- [x] Validate the fully materialized `daily_strategy.v3` with the existing
      formal validator.
- [x] Treat deterministic materialization errors as code/contract failures,
      not LLM-repairable errors.
- [x] Allow one repair only for LLM-owned decision fields.
- [x] Record retry count automatically; do not rely on copied deterministic
      fields or LLM-supplied timing metadata.

### Task 6 — Preserve ownership and equivalence

- [x] Keep final regime LLM-owned.
- [x] Keep selected codes and order LLM-owned.
- [x] Keep Direction, rating, position tier, rule application, and
      RiskSeverity effects LLM-owned.
- [x] Keep all candidates visible to the LLM.
- [x] Keep Python profile hints advisory.
- [x] Preserve selected-stock source grounding.
- [x] Preserve formal observation-pool completion in Python.
- [x] Preserve the `daily_strategy.v3` and HTML output interfaces.

## 6. Tests

### 6.1 Unit tests

- [x] Candidate-default compression round-trips to the same semantic rows.
- [x] Candidate count, code set, and order remain identical.
- [x] Candidate defaults never hide a non-default risk, event, role, Pattern,
      score, or evidence ref.
- [x] Selecting by code always materializes the canonical stock name.
- [x] Spacing or alias differences can no longer cause a name retry.
- [x] Fixed root/market/portfolio/T+1 fields are generated by Python.
- [x] Plan baselines are deterministic for each entry setup and anchor.
- [x] Sparse overrides are whitelist-validated and reason-required.
- [x] Old temporary input and draft schemas fail closed.
- [x] Zero selected stocks, duplicate codes, unknown codes, unsupported refs,
      and invalid overrides fail closed.

### 6.2 Frozen replay

Use at least:

- the 2026-07-29 21-candidate/5-selected run;
- the 2026-07-10 normal pool;
- the 2026-07-09 legacy large-pool coverage fixture;
- one panic/weak regime fixture;
- one multi-theme candidate fixture;
- one candidate with major event, anomaly, risk flags, conditional evidence,
  and profile override.

Compare:

- candidate set and order;
- regime;
- selected codes and order;
- Direction, rating, position tier, and applied rules;
- source refs and role grounding;
- final profile and T+1 plan semantics;
- observation pool;
- final validator and HTML output.

Text generated from deterministic templates may change wording. Decision
semantics and safety conditions must not weaken.

### 6.3 Performance checks

For every live run record:

- candidate count;
- selected count;
- compact input bytes;
- minified draft bytes;
- Strategy LLM duration;
- validation retry count;
- total Step 3 duration.

Do not attribute gains to this change when candidate counts or execution
environments are materially different.

## 7. Implementation order

1. Add frozen decision fixtures and failing tests for the new temporary
   schemas.
2. Implement deterministic plan/name/root materialization.
3. Switch the LLM draft contract to decision-only output.
4. Compact candidate defaults and bump the compact-input schema.
5. Update `daily-strategy` instructions and references.
6. Run unit, equivalence, renderer, and full-suite tests.
7. Run live shadow comparison without publishing changed decisions.
8. Enable the new hot path only after candidate and decision invariants pass.

## 8. Acceptance criteria

- All candidates remain present and ordered.
- No rule-related file or behavior changes.
- No deterministic copied field can trigger an LLM repair.
- `daily_strategy.v3` and report consumers remain compatible.
- Frozen decision invariants pass.
- Full test suite passes.
- Comparable live runs show lower input bytes, draft bytes, retry rate, and
  Strategy LLM duration.

## 9. Implementation status — 2026-07-29

Implemented Tasks 1–6. The current temporary contracts are
`strategy_llm_input.tmp.v3` and `daily_strategy_draft.tmp.v3`; the formal
`daily_strategy.v3` contract is unchanged.

Verification completed:

- full suite: 392 passed, 184 skipped, 10 subtests passed;
- 2026-07-29 replay retained all 21 candidates in order;
- compact input: 15,319 bytes, down from 24,637 bytes;
- equivalent five-stock decision draft estimate: 3,865 bytes, down from the
  previous 10,816-byte minified draft;
- candidate profile bases deduplicated to 2 rows and candidate evidence sets
  deduplicated to 3 rows.

Still pending:

- live shadow publication check;
- at least five comparable live runs before claiming a stable LLM-duration or
  retry-rate improvement.
