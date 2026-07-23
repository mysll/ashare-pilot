# Daily Step 3 Performance Optimization — Development Plan

**Date:** 2026-07-15

**Status:** Final / Ready for implementation

**Scope:** `daily-strategy` Step 3 preparation, LLM reasoning, strategy
publication, validation, and HTML rendering.

---

## 1. Goal

Reduce Step 3 wall time from the observed approximately 10 minutes to a normal
4–6 minute range without changing the candidate universe or transferring the
final stock-selection decision away from the Step 3 LLM.

The first implementation phase must preserve:

- all deterministic Step 2 candidates in the Step 3 decision input;
- final selected stock codes and order;
- final Direction and rating;
- regime-dependent 10/7/5 main-list limits;
- `reasoning.source_basis` grounded in actual role tags and news references;
- final Trade Profile, pre-open plan, and T+1 risk plan contracts; frozen-draft
  deterministic replay must preserve these fields exactly, while live LLM
  shadow runs report differences without treating nondeterminism as a hard
  failure;
- canonical `news#<id>` references;
- `daily_strategy.v2` validation and HTML behavior;
- manual execution rather than automatic trading.

The first phase must not:

- introduce a top-N candidate shortlist;
- omit low-ranked candidates before the LLM sees them;
- move final Direction or final RiskSeverity ownership into Python;
- pre-filter historical trading rules in a way that can hide a relevant rule;
- read the full `mapper.json`, `pool_indicators.json`, or `news.json` into the
  LLM context when a script can project the required fields;
- add network concurrency;
- regenerate historical strategy contracts.

---

## 2. Measured 2026-07-15 Baseline

### 2.1 Wall time

| Event | Time |
|---|---:|
| Step 2 finalize complete | 09:24:46 |
| Step 3 strategy view rebuilt | 09:26:15 |
| `strategy.json.generated_at` | 09:33:06 |
| Final `strategy.json` written | 09:34:49 |
| HTML written | 09:34:54 |
| **Approximate Step 3 total** | **10m08s** |

The intermediate split is approximate because `generated_at` is authored by
the LLM. The total from Step 2 finalize to final HTML is reliable.

### 2.2 Input and output volume

| Artifact/context | Size |
|---|---:|
| `daily-strategy/SKILL.md` | 28,780 bytes |
| `memory/RULES.md` | 15,180 bytes |
| `memory/SHARED_RULES.md` | 11,289 bytes |
| `mapper.strategy_view.json` | 102,484 bytes |
| **Minimum mandatory LLM context** | **157,733 bytes** |
| `mapper.json` if unnecessarily loaded | 159,030 bytes |
| `pool_indicators.json` if unnecessarily loaded | 434,240 bytes |
| Final `strategy.json` | 30,153 bytes |

The minimum mandatory context is roughly 39k tokens before conversation,
tool output, indices, or conditional news evidence.

### 2.3 Work volume

| Item | Count |
|---|---:|
| Candidate Pool | 60 |
| Selected strategy stocks | 10 |
| Generated observation rows | 50 |
| Themes | 8 |

Current instructions require the LLM to execute the full Direction, risk,
rule-matching, and profile reasoning flow for every one of the 60 candidates.

### 2.4 Local script cost

Measured on frozen 2026-07-15 inputs:

| Operation | Approximate runtime |
|---|---:|
| Build strategy view | 0.13s |
| Compute 60 Trade Profiles | under 0.01s |
| Validate strategy | 0.07s |
| Render HTML | 0.09s |

Python computation is not the bottleneck. LLM context processing, repeated
per-candidate reasoning, and Agent/tool round trips dominate.

---

## 3. Locked Ownership Decisions

### 3.1 Python owns

- mapper and strategy-input validation;
- freshness checks and input projection;
- current index fetching and raw regime inputs;
- deterministic DirectionBase hint;
- deterministic RiskSeverityBase hint;
- deterministic Trade Profile base, including recomputation from the LLM's
  final regime during finalization;
- conditional-news trigger detection;
- compact candidate serialization;
- creation of observation rows for candidates not selected by the LLM;
- normalization, final validation, timing, and HTML rendering.

Python hints are advisory inputs. They do not become final strategy decisions.

### 3.2 Step 3 LLM owns

- final `market.regime_prior`;
- final selected code set and order;
- final Direction;
- final RiskSeverity application;
- final rating;
- rule application and any justified override;
- final entry profile and execution conditions for selected stocks;
- readable `reasoning.source_basis` and other reasoning fields.

### 3.3 Step 2 continues to own

- Candidate Pool membership;
- theme membership and heat;
- composite and component scores;
- source role tags;
- Pattern defaults;
- canonical news links;
- technical strategy inputs.

Step 3 must never create a candidate absent from
`mapper.strategy_view.json.candidates[]`.

`RiskSeverity` remains an internal reasoning decision, not a new standalone
`strategy.json` field. Its externally visible effects land in
`reasoning.risk` and the final Direction cap.

Trade Profile ownership is split deliberately:

- prepare computes an advisory `profile_base` using an index-derived
  `regime_hint`;
- the LLM selects the final regime and emits only justified, whitelisted
  `profile_overrides` for selected stocks;
- finalize recomputes the deterministic base using the final regime, applies
  the overrides, and materializes the complete final profile;
- invalid or contradictory overrides fail validation; finalize never silently
  repairs them.

---

## 4. Target Architecture

```text
mapper.json + mapper.strategy_view.json
                 |
                 v
prepare_daily_strategy.py
  - validate/freshness check
  - fetch indices once
  - derive regime_hint and advisory profile bases
  - resolve conditional news items
  - write compact non-contract input
                 |
                 v
.strategy_llm_input.json
  - all candidates, compact rows
  - no full mapper/pool/news payload
                 |
                 v
Step 3 LLM
  - sees all candidates
  - shallow-scans every candidate for selection
  - deep-reasons only selected candidates
  - selects regime-limited main list
  - writes final regime, selected decisions, and profile overrides
                 |
                 v
strategy.draft.json
                 |
                 v
finalize_daily_strategy.py
  - verify selected membership
  - recompute profile bases from final regime
  - apply whitelisted profile overrides
  - fill deterministic observation rows
  - normalize + validate
  - publish strategy.json
  - render daily_report.html
  - record timing
```

Formal contracts remain:

- `mapper.strategy_view.json`;
- `strategy.json`;
- `daily_report.html`.

The following are non-contract workflow artifacts:

- `.strategy_llm_input.json`;
- `strategy.draft.json`;
- `step3_timing.json`.

---

## 5. Task 0 — Add Step 3 Observability

**Priority:** First

**Add:**

- `.agents/skills/daily-strategy/scripts/build_step3_timing.py`
- timing tests

Record these stages:

- `prepare`;
- `strategy_llm`;
- `finalize`.

The artifact schema is `daily_step3_timing.v1`. Reuse the Step 2 timing
semantics for artifact invalidation, fingerprints, and
`complete_same_run=true`.

For each stage record:

- start/end or measured duration;
- input/output artifact size and modification time;
- candidate count;
- selected count;
- observation count;
- conditional-news count;
- validation retry count;
- index-fetch duration/failure;
- LLM input and output bytes.

Requirements:

- diagnostic failures never invalidate strategy contracts;
- upstream reruns invalidate downstream timing entries;
- `total_recorded_seconds` is populated only when all stage artifacts are
  linked within the same run;
- the final LLM timing must point to the exact draft consumed by finalize;
- a validation correction must re-record `strategy_llm` rather than leaving a
  stale artifact fingerprint.

---

## 6. Task 1 — Define the Compact Strategy Input

**Add:**

- `.agents/skills/daily-strategy/scripts/build_strategy_llm_input.py`
- schema/coverage tests

### 6.1 Top-level fields

```json
{
  "schema_version": "strategy_llm_input.tmp.v1",
  "date": "YYYY-MM-DD",
  "non_contract": true,
  "source": {"strategy_view_sha256": "..."},
  "market_inputs": {},
  "themes": [],
  "news_evidence": [],
  "candidates": []
}
```

### 6.2 Candidate row

Each deterministic candidate appears exactly once with:

- `code`, `name`, and primary/source themes;
- `role_tags` and canonical `news_link`;
- composite, tech, theme heat, news impact, auction, and money-flow values;
- only confidence exceptions below the normal threshold, rather than repeated
  confidence=100 fields;
- `risk_type`;
- Pattern states without repetitive default traces;
- compact major event and anomaly;
- price source, price, MA5, MA20, ATR, ATR%, high20, and low20;
- `direction_base_hint`;
- `risk_severity_base_hint`;
- compact `profile_base`, explicitly tagged as derived from `regime_hint`;
- deterministic trigger flags.

### 6.3 Evidence projection

Python evaluates the existing Conditional Reread triggers using only fields
actually projected from `mapper.strategy_view.json`, such as scores and
auction state. The first release must not depend on `cross_rank` or another
field absent from the compact input. Only canonical news items referenced by a
triggered candidate are placed into top-level `news_evidence`. Candidate rows
contain references, not duplicated prose.

The LLM must not load the complete `news.json`.

### 6.4 Coverage gate

Before the LLM phase:

```text
set(input candidate codes)
== set(mapper.strategy_view candidate codes)
```

Duplicate, missing, extra, or reordered rows fail prepare.

### 6.5 Size target

For approximately 60 candidates:

- `.strategy_llm_input.json` hard target: at most 80KB;
- `.strategy_llm_input.json` stretch target: at most 60KB;
- phase-specific instruction context target: at most 10KB;
- no full mapper or indicator payload in LLM context.

This is a target for measurement, not a reason to omit a required decision
field.

Apply these compression rules before considering any field removal:

- omit confidence values equal to the normal default of 100;
- omit repetitive default Pattern traces;
- reference, rather than duplicate, theme and news prose;
- use compact JSON serialization;
- keep `profile_base` to the fields required for final recomputation and
  override review.

### 6.6 Content fingerprint

All input/draft linkage uses a content hash, never a path, modification time,
or file size. Canonicalize parsed JSON as UTF-8 with equivalent Python
semantics:

```python
json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
```

Compute SHA-256 over those bytes. The draft stores the exact compact-input
hash as `source.strategy_input_sha256`.

---

## 7. Task 2 — Implement `prepare_daily_strategy.py`

**Add:**

- `.agents/skills/daily-strategy/scripts/prepare_daily_strategy.py`
- orchestration tests

Run:

```bash
python .agents/skills/daily-strategy/scripts/prepare_daily_strategy.py \
  --date YYYY-MM-DD
```

The command must:

1. validate `mapper.json`;
2. verify `mapper.strategy_view.json` is linked to the current mapper;
3. rebuild the view only when missing or stale;
4. fetch the required indices once;
5. compute base regime inputs and derive an advisory `regime_hint`;
6. compute DirectionBase and RiskSeverityBase hints for all candidates;
7. compute advisory Trade Profile bases for all candidates from `regime_hint`
   in one Python process;
8. resolve conditional-news triggers and referenced items;
9. write `.strategy_llm_input.json` with the canonical strategy-view content
   hash;
10. record prepare timing and counts.

The command may read full mapper, pool, and news contracts. The LLM may not.

Index requests remain sequential unless an existing batch endpoint already
supports the three codes in one request.

---

## 8. Task 3 — Split the Step 3 Skill by Phase

**Modify:**

- `.agents/skills/daily-strategy/SKILL.md`
- `.agents/skills/daily-market-analysis/SKILL.md`

**Add references:**

- `references/strategy-selection-rubric.md`
- `references/strategy-output-contract.md`

The main SKILL should contain only:

- ownership and invariants;
- prepare command;
- exact LLM input/output locations;
- finalization command;
- failure/retry behavior.

The rubric must make the reasoning budget explicit:

- scan every candidate at least once using the compact comparison fields;
- select only after considering the complete candidate set;
- run the full Direction, risk, rules, and execution-plan reasoning sequence
  only for the selected 5/7/10 stocks;
- do not generate hidden full reasoning records for unselected stocks.

Move out of the hot LLM phase:

- migration history;
- long explanatory examples;
- full field tables already enforced by validators;
- open questions;
- repeated V4/V5 comparisons;
- renderer documentation.

The first-release LLM phase loads only:

- `.strategy_llm_input.json`;
- `strategy-selection-rubric.md`;
- `strategy-output-contract.md`;
- `memory/RULES.md`;
- `memory/SHARED_RULES.md`.

`RULES.md` and `SHARED_RULES.md` remain available in the first phase to avoid
decision drift. Rule preselection is explicitly deferred.

The `daily-market-analysis` workflow must expose one unambiguous Step 3
sequence and exact `portfolio-manager` paths:

```bash
python .agents/skills/daily-strategy/scripts/prepare_daily_strategy.py \
  --date YYYY-MM-DD

# portfolio-manager reads:
#   predict/YYYY-MM-DD/.strategy_llm_input.json
#   .agents/skills/daily-strategy/references/strategy-selection-rubric.md
#   .agents/skills/daily-strategy/references/strategy-output-contract.md
#   memory/RULES.md
#   memory/SHARED_RULES.md
# and writes:
#   predict/YYYY-MM-DD/strategy.draft.json

python .agents/skills/daily-strategy/scripts/finalize_daily_strategy.py \
  --date YYYY-MM-DD
```

---

## 9. Task 4 — Reduce LLM Output to Selected Decisions

The LLM writes `strategy.draft.json` containing:

- `source.strategy_input_sha256`, the exact compact-input content hash;
- market and portfolio decisions;
- the final selected 5/7/10 stocks in order;
- complete LLM-owned strategy fields for selected stocks only;
- whitelisted `profile_overrides` rather than a second independently computed
  profile base;
- optional explicit exclusion overrides only when the deterministic reason
  would be misleading.

The LLM does not write 50 repetitive observation rows.

Every selected stock must still include:

- Direction and rating;
- entry profile, anchor, trigger, and no-buy condition;
- position budget and T+1 horizon;
- pre-open and T+1 risk plans;
- applied rule IDs;
- `reasoning.source_basis`;
- direction/risk/reread reasoning;
- all LLM-owned profile choices required for finalize to materialize the final
  profile.

The LLM must shallow-scan all input candidates before selection, but performs
deep Step 3 reasoning only for selected stocks. `RiskSeverity` is kept inside
that reasoning: its explanation is written to `reasoning.risk`, and any cap is
reflected in final Direction. No new standalone severity field is added.

Draft validation must require:

- every selected code exists in the input candidate set;
- no duplicate selected code;
- selected count respects the final regime;
- selected order is preserved through finalization;
- no unsupported source tag or news reference is introduced.

---

## 10. Task 5 — Deterministic Observation Completion

**Modify or add:**

- `normalize_strategy_selection.py`, or
- a dedicated `complete_strategy_observations.py` used by finalization.

For every input candidate not selected by the LLM, Python emits exactly one
compact observation row:

```json
{"code": "sh600000", "name": "example", "reason": "regime limit"}
```

Deterministic reason priority:

1. explicit LLM exclusion override;
2. deterministic hard-unbuyable reason, but only when an existing explicit
   contract rule proves the candidate cannot be bought;
3. regime main-list limit with primary theme;
4. generic not-selected reason.

Requirements:

- selected codes never appear in observations;
- all non-selected candidate codes appear once;
- observations remain `{code,name,reason}` only;
- Python does not invent a final Direction for an unselected stock;
- soft risk, score, or setup signals must not be presented as the causal
  exclusion reason;
- observation wording is presentation/support data and must not influence
  selection retroactively.

---

## 11. Task 6 — Implement `finalize_daily_strategy.py`

**Add:**

- `.agents/skills/daily-strategy/scripts/finalize_daily_strategy.py`
- finalization tests

Run:

```bash
python .agents/skills/daily-strategy/scripts/finalize_daily_strategy.py \
  --date YYYY-MM-DD
```

The command must:

1. verify dates and schema versions;
2. recompute the canonical compact-input SHA-256 and verify the draft source
   hash;
3. validate selected candidate membership and source references;
4. recompute each selected stock's deterministic Trade Profile base using the
   LLM's final regime;
5. validate and apply only whitelisted `profile_overrides`;
6. complete deterministic `observation_pool` rows;
7. enforce regime limits without reordering valid selected rows;
8. validate `daily_strategy.v2`;
9. atomically publish `strategy.json`;
10. render `daily_report.html`;
11. record finalize timing and linked artifacts.

The command stops on the first contract failure and never silently repairs a
missing selected-stock decision field.

The stale instruction to append a morning strategy entry directly to
`memory/daily/INDEX.md` must be removed unless a separate verified memory
workflow explicitly owns that mutation. Morning verification remains the
owner of daily memory updates.

---

## 12. Task 7 — Regression and Shadow Gates

### 12.1 Frozen dates

Use compact frozen fixtures for:

- 2026-07-09: oversized Candidate Pool;
- 2026-07-13: candidate-loss regression case;
- 2026-07-14: 45-candidate normal baseline;
- 2026-07-15: 60-candidate performance baseline.

Fixtures must not depend on ignored live `predict/` files during tests.

### 12.2 Gate A — Input equivalence

Require:

- identical candidate code set and order;
- identical themes and market-state inputs;
- identical score values;
- identical risk types, Pattern states, major events, anomaly, and news links;
- no unresolved news reference;
- every conditional reread trigger has its referenced evidence.

### 12.3 Gate B — Deterministic fixture replay

Gate B replays a frozen `strategy.draft.json` through deterministic finalize.
It is not a fresh live LLM generation. Require exact equality for:

- final regime;
- selected code set and order;
- Direction by selected code;
- rating by selected code;
- position budget by selected code;
- entry profile and anchor;
- applied rule IDs.

Allow only:

- equivalent observation wording changes;
- generated timestamps;
- deterministic metadata;
- formatting-only source-basis wording when the cited sources are unchanged.

Every non-allowlisted difference fails.

Extend `compare_strategy_shadow.py`, or add an equivalent comparator, so the
gate actually checks rating, position budget, entry profile, anchor, and
applied rules in addition to regime, code order, and Direction.

### 12.4 Gate C — Contract validation

- strategy validator passes;
- selected count respects 10/7/5 limits;
- source-basis coverage is 100%;
- observation coverage equals all non-selected candidates;
- HTML renders successfully;
- no full source JSON is copied into the LLM input.

### 12.5 Gate D — Live timing

Collect at least five comparable live runs before setting a P95 target.

Report:

- candidates and selected count;
- input/output bytes;
- prepare, LLM, and finalize wall time;
- validation retries;
- complete-same-run status;
- total Step 3 wall time.

### 12.6 Live LLM shadow report

A live re-run of the LLM is intentionally nondeterministic. Compare regime,
selection/order, Direction, rating, position budget, anchor, profiles, rules,
and source grounding, but publish the differences as a review report rather
than an exact-equality CI gate. Any material drift must be investigated before
workflow cutover, but wording or sampling variance does not make the
deterministic implementation flaky.

---

## 13. Phased Performance Targets

| Phase | Target |
|---|---:|
| Instrumentation only | Accurate 10-minute baseline |
| Prepare/finalize orchestration | Under approximately 7–8 minutes |
| Compact input + phase-specific skill | Normal approximately 5–7 minutes |
| Selected-only draft + observation completion | Normal approximately 4–6 minutes |
| Later validated rule/shortlist optimization | 3–5 minute stretch goal |

The first release must not be blocked solely because it misses the stretch
goal. Correctness and same-run timing take priority.

---

## 14. Deferred Optimization — Not in First Release

### 14.1 High-recall shortlist

A future phase may send detailed fields only for a high-recall shortlist while
keeping compact summaries for all candidates. It may be enabled only after
multi-day shadow proves every historically selected stock remains eligible.

### 14.2 Rule candidate preselection

Python may later map structured triggers to a high-recall set of rule IDs. The
LLM would read only those rule texts. This requires dedicated recall tests and
must not be bundled with the initial context refactor.

### 14.3 Deterministic final Direction

Not planned. Python may compute an advisory base, but final Direction remains
an LLM-owned Step 3 decision.

---

## 15. Implementation Order

```text
Commit 1 — Step 3 timing and baseline tests

Commit 2 — compact input builder, fingerprint, prepare script, and tests
           (not wired into the live workflow)

Commit 3 — draft validator, observation completion, finalize script, and tests
           (not wired into the live workflow)

Commit 4 — frozen fixtures, extended shadow comparator, and contract gates

Commit 5 — atomic workflow cutover: phase references, daily-strategy SKILL,
           daily-market-analysis SKILL, portfolio-manager paths, and the
           prepare -> LLM -> finalize sequence
```

Do not mix an optional shortlist or rule-filtering experiment into these
commits. Commits 2–4 must leave the existing live Step 3 path functional;
workflow instructions switch only when prepare, draft validation, finalize,
tests, and rollback instructions are all present in Commit 5.

---

## 16. Success Criteria

### Correctness

| Metric | Requirement |
|---|---|
| Candidate visibility | 100% of Step 2 candidates |
| Missing/duplicate compact candidates | 0 |
| Frozen replay selected code/order diff | 0 |
| Frozen replay Direction/rating/profile/rules diff | 0 |
| Live LLM shadow diff | Report and review; not exact-equality CI |
| Invalid/unresolved evidence | 0 |
| Source-basis coverage | 100% selected stocks |
| Observation coverage | 100% non-selected candidates |
| Strategy/HTML validation failure | 0 |

### Performance

| Metric | Requirement |
|---|---|
| Compact LLM input at ~60 candidates | Hard <= 80KB; stretch <= 60KB |
| Hot-phase instruction context | Target <= 10KB |
| Local prepare/finalize excluding network | Under 1s each on frozen inputs |
| Normal Step 3 wall time | Approximately 4–6 minutes |
| Timing artifact linkage | `complete_same_run=true` |

---

## 17. Final Expected Result

The optimized Step 3 keeps all 60 candidates visible to the LLM and requires a
shallow comparison across the complete set, but stops forcing it to ingest
full source contracts, repeat deterministic computation, deep-reason every
unselected candidate, and author 50 repetitive observation rows.

Python prepares compact evidence and advisory bases, then recomputes profiles
from the final regime and atomically validates and publishes the result. The
LLM retains final regime, selection, Direction, risk application, rule use,
profile overrides, and trade-plan ownership.

This should move the workflow from approximately 10 minutes toward a normal
4–6 minute range while preserving current trading decisions and leaving more
aggressive shortlist/rule-filtering work behind explicit shadow gates.
