# Code Review: Daily Step 3 Performance Optimization

**Date:** 2026-07-15  
**Plan:** `docs/superpowers/plans/2026-07-15-daily-step3-performance-optimization.md`  
**Scope:** Uncommitted working-tree changes implementing prepare → selected-only draft → finalize for `daily-strategy` Step 3

---

## 1. Review Method

| Check | Result |
|---|---|
| Plan vs. file inventory | Compared Tasks 0–7 and Commit 1–5 order |
| Static review of new/modified scripts & SKILLs | Completed |
| Unit tests | `daily-strategy` suite: **22 tests OK** |
| Live-input dry-run | `prepare_daily_strategy.py --date 2026-07-15` with frozen indices → **60 candidates, 0.031s, 79,215 bytes** |

Out-of-scope noise: `intraday-operation-guide` HTML cutover is present in the same working tree and should not be reviewed/merged as part of this plan.

---

## 2. Changed Surface

### Modified

| Path | Role |
|---|---|
| `.opencode/skills/daily-strategy/SKILL.md` | Slimmed to ownership + prepare/LLM/finalize sequence |
| `.opencode/skills/daily-market-analysis/SKILL.md` | Step 3 wired to prepare → draft → finalize |
| `.opencode/skills/daily-stock-mapping/scripts/build_strategy_view.py` | Adds `source.mapper_sha256` for view↔mapper linkage |
| `.opencode/skills/daily-strategy/scripts/compare_strategy_shadow.py` | Locks rating / budget / entry / anchor / rules / profile |
| `.opencode/skills/daily-strategy/scripts/render_daily_report_html.py` | Observation pool reads `strategy.observation_pool` |
| `.opencode/skills/daily-strategy/tests/test_compare_strategy_shadow.py` | Shadow field-lock tests |

### Added (in plan)

| Path | Role |
|---|---|
| `scripts/build_step3_timing.py` | Task 0 — `daily_step3_timing.v1` |
| `scripts/build_strategy_llm_input.py` | Task 1 — compact LLM input |
| `scripts/prepare_daily_strategy.py` | Task 2 — prepare orchestration |
| `scripts/validate_strategy_draft.py` | Task 4 — draft CLI wrapper |
| `scripts/finalize_daily_strategy.py` | Task 5–6 — draft validate, materialize, publish |
| `references/strategy-selection-rubric.md` | Task 3 — hot-phase selection rubric |
| `references/strategy-output-contract.md` | Task 3 — draft output contract |
| `tests/test_step3_performance_contract.py` | Task 7 — gates (partial) |
| `tests/fixtures/step3_frozen_gates.json` | Task 7 — frozen case metadata |

### Out of plan (same working tree)

| Path | Note |
|---|---|
| `.opencode/skills/intraday-operation-guide/SKILL.md` | HTML board cutover |
| `.opencode/skills/intraday-operation-guide/scripts/render_operation_guide_html.py` | New renderer |

---

## 3. Architecture Verdict

Target flow from the plan is implemented:

```text
mapper.json + mapper.strategy_view.json
        → prepare_daily_strategy.py
        → .strategy_llm_input.json
        → portfolio-manager (selected-only draft)
        → strategy.draft.json
        → finalize_daily_strategy.py
        → strategy.json + daily_report.html + step3_timing.json
```

Ownership split matches the plan:

- **Python:** validation, projection, index fetch, advisory bases, observation completion, normalize/publish/HTML/timing
- **LLM:** final regime, selected codes/order, Direction, RiskSeverity application, rating, rules, execution plans, justified profile overrides
- **Formal contracts:** `mapper.strategy_view.json`, `strategy.json`, `daily_report.html`
- **Non-contract artifacts:** `.strategy_llm_input.json`, `strategy.draft.json`, `step3_timing.json`

Morning memory mutation (`memory/daily/INDEX.md`) correctly removed from Step 3.

---

## 4. Plan Compliance Matrix

| Task / Gate | Status | Notes |
|---|---|---|
| Task 0 Timing | **Done** | Stages, fingerprints, downstream invalidation, `complete_same_run`, soft-fail on timing write |
| Task 1 Compact input | **Mostly done** | Full candidate set/order, content hash, hard 80KB gate; triggers incomplete (see bugs) |
| Task 2 Prepare | **Done** | Mapper validate, view rebuild-when-stale, indices, hints, timing |
| Task 3 Skill split | **Done** | SKILL slim + rubric + contract; market-analysis sequence unambiguous |
| Task 4 Selected draft | **Partial** | Schema/overrides present; draft validation too weak |
| Task 5 Observation completion | **Partial** | Covers non-selected once; reason priority incomplete |
| Task 6 Finalize | **Done** | Hash link, recompute profile, apply overrides, validate v2, atomic publish, HTML |
| Gate A Input equivalence | **Weak** | Synthetic candidates only; not real predict fixtures |
| Gate B Frozen draft replay | **Missing** | No golden `strategy.draft.json` → exact strategy equality |
| Gate C Contract validation | **Partial** | Covered via unit path + final validator; not full HTML golden |
| Gate D Live timing | **Not started** | No multi-run wall-time samples |
| Deferred shortlist / rule preselect | **Correctly deferred** | Not mixed into first release |
| Commit order (2–4 offline, 5 cutover) | **Violated** | Live SKILL already cut over while gates incomplete |

---

## 5. What Works Well

1. **Correct bottleneck attack:** Python work is negligible; LLM context and per-candidate deep reasoning were the target; architecture removes full mapper/pool/news from hot context and stops authoring 50 observation rows in the LLM.
2. **Content-hash linkage:** Draft stores `source.strategy_input_sha256`; finalize recomputes canonical JSON SHA-256 and rejects stale drafts.
3. **Profile ownership split:** Advisory `profile_base` from `regime_hint`; finalize recomputes from final regime and applies only whitelisted `{value, reason}` overrides; budget/horizon must match stock fields.
4. **HTML observation fix:** Renderer now uses `strategy.get("observation_pool")` instead of mapper observation pool — required once Step 3 owns non-selected reasons.
5. **Shadow comparator extension:** Locked fields now include rating, position_budget, entry_profile, anchor, rules_applied, profile; `--report-only` supports live nondeterministic review.
6. **View linkage primitive:** `mapper_sha256` on strategy view enables prepare to detect stale projections.
7. **Measured prepare on 2026-07-15:** 60 candidates, ~79KB compact input under the hard ceiling, local prepare ~30ms.

---

## 6. Findings

### Bug / Gap 1 — High: `validate_draft` does not enforce selected-stock completeness

**Files:** `finalize_daily_strategy.py` (`validate_draft`), `validate_strategy_draft.py`

**Plan requirement:** Draft must carry complete LLM-owned fields for selected stocks; finalize must not silently invent missing decisions.

**Observed:** A draft stock with only `code` / `name` / `sector` can pass `validate_draft`. Missing Direction, preopen/T+1 plans, reasoning, etc. are deferred to final `validate_strategy_json` after materialize, or fail mid-materialize on profile budget contradictions with opaque messages.

**Impact:** LLM retry loop gets late, low-quality errors; violates “stop on first contract failure without silent repair.”

**Fix:** Reuse or mirror `validate_strategy_json` v2 stock checks inside draft validation (except final `profile`, which finalize materializes). Require non-empty `reasoning.source_basis`, `preopen_plan`, `t1_risk_plan`, `rules_applied`, `profile_trace` before materialize.

---

### Bug / Gap 2 — High: Gate B frozen draft replay not implemented

**Files:** `tests/fixtures/step3_frozen_gates.json`, `tests/test_step3_performance_contract.py`

**Plan requirement:** Replay frozen `strategy.draft.json` through deterministic finalize with exact equality on regime, selected order, Direction, rating, budget, entry/anchor, rules. Fixtures must not depend on ignored live `predict/`.

**Observed:** Fixture only stores `{date, candidate_count, ...}` metadata. Tests synthesize candidates and a minimal draft. No golden compact+draft→strategy triples for 2026-07-09/13/14/15.

**Impact:** Cannot prove decision-preserving finalize; cutover risk is unmeasured.

**Fix:** Check in compact frozen fixtures (or minimal real projections) plus frozen drafts and expected final strategy slices for at least one weak-regime and one neutral 45/60-candidate case.

---

### Bug / Gap 3 — High: Conditional reread trigger semantics drifted

**File:** `build_strategy_llm_input.py` (`reread_triggers`)

**Plan / legacy SKILL:**

1. anomaly present  
2. any of composite/tech/theme_heat/news_impact confidence &lt; 60  
3. hard contradictions including `auc_change_pct > +3% AND news_imp < 40`

**Observed:**

- Auction hard contradiction **not implemented** (`auction_change_pct` is not projected into compact rows).
- On live 2026-07-15 data, **60/60** candidates fire `low_confidence` because `composite.confidence` is commonly 50. Conditional news becomes near-universal rather than selective.

**Impact:**

- Evidence projection no longer matches Conditional Reread intent.
- Input size and LLM reread work inflate; 79KB leaves only ~2.7KB under the hard 80KB cap.
- Decision behavior may change vs. prior Step 3 instructions.

**Fix options (pick explicitly):**

1. Project `auction_change_pct` (or document permanent removal of that hard contradiction).  
2. Revisit whether Step 2 composite confidence=50 should trigger reread for every name; consider only non-default exceptions that are decision-relevant, or a higher bar for composite-only lows.

---

### Bug / Gap 4 — High: Live workflow cutover before gates complete

**Files:** `daily-strategy/SKILL.md`, `daily-market-analysis/SKILL.md`

**Plan:** Commits 2–4 leave live Step 3 functional; Commit 5 switches instructions only when prepare, draft validation, finalize, tests, and rollback are ready.

**Observed:** Skills already mandate prepare → draft → finalize. Gate B/D incomplete; draft validation weak; no parallel old-path skill retained.

**Impact:** Next weekday 9:20 run will use the new path with incomplete safety nets.

**Fix:** Either (a) finish draft validation + Gate B before relying on the path, or (b) temporarily keep an explicit rollback skill/path and mark the new sequence experimental until Gate B passes.

---

### Bug / Gap 5 — Medium-High: Out-of-scope intraday operation guide changes

**Files:** `intraday-operation-guide/SKILL.md`, `scripts/render_operation_guide_html.py`

Unrelated HTML board migration is mixed into the same uncommitted tree as Step 3 performance work.

**Fix:** Split into a separate commit/PR. Do not review or ship as part of this plan’s success criteria.

---

### Bug / Gap 6 — Medium: `regime_hint` derivation differs from legacy RegimeHint table

**File:** `build_strategy_llm_input.py` (`derive_regime`)

**Legacy table (old SKILL):**

| Regime | Condition |
|---|---|
| panic | 上证 &lt; -1.5% |
| weak | -1.5% ~ -0.5% |
| neutral | ±0.5% |
| strong-sector | **neutral index** BUT dominant heat ≥ 85 OR 科创50 &gt; +2% |

**Current code:** `sh_pct > 0.5` **OR** heat ≥ 85 **OR** kcb &gt; 2 → `strong-sector`.

**Impact:** Index-up days may be labeled `strong-sector` instead of a stronger-but-not-structural regime, changing the 10/7/5 main-list budget via advisory path and any consumer that treats the hint as near-final.

**Fix:** Restore structural strong-sector semantics; keep index strength as separate market_inputs signal if needed.

---

### Bug / Gap 7 — Medium: Observation reason priority incomplete

**File:** `finalize_daily_strategy.py` (`materialize`)

**Plan priority:**

1. explicit LLM exclusion override  
2. deterministic hard-unbuyable reason (only when contract proves unbuyable)  
3. regime main-list limit + primary theme  
4. generic not-selected  

**Observed:** override **or** `"{regime}主策略名额限制；主主题：{primary}"`.

Soft risk/score is correctly not used as causal reason, but hard-unbuyable branch is absent.

**Fix:** Add explicit hard-unbuyable predicates only where existing validators already prove non-buyable; otherwise keep regime-limit wording.

---

### Bug / Gap 8 — Medium: Prepare rewrites strategy view when `mapper_sha256` missing

**Files:** `prepare_daily_strategy.py`, live `predict/2026-07-15/mapper.strategy_view.json`

Live view currently has no `source.mapper_sha256`, so prepare treats it as unlinked and rebuilds/writes view.

**Impact:** First prepare mutates a Step 2 artifact. Correct for linkage, but surprising if operators expect view immutability after Step 2 finalize.

**Fix:** Ensure Step 2 `build_strategy_view.py` always writes `mapper_sha256` in production runs (code is present; regenerate views), and document that prepare may rebuild only on hash mismatch.

---

### Bug / Gap 9 — Medium: Compact input sits on the hard ceiling

**Measurement (2026-07-15, 60 candidates):** 79,215 / 81,920 bytes (~96.6% of hard target). Stretch 60KB not met (allowed by plan).

**Drivers:** per-candidate `profile_base`, near-universal triggers/confidence_exceptions, full strategy_inputs.

**Impact:** Small field growth or more conditional news items can fail prepare with hard error.

**Fix:** Further compress `profile_base` to recompute-critical fields only; avoid emitting default-ish trigger noise; keep hard fail but add a warn threshold (e.g. 70KB).

---

### Bug / Gap 10 — Medium: Shadow lock on full `profile` may noise live reports

**File:** `compare_strategy_shadow.py`

Finalize always recomputes profile from final regime. Comparing against historical LLM-authored full profiles will often flag `profile` diffs even when selection/Direction match.

**Impact:** Live shadow (Gate D / review) may look red for structural reasons.

**Fix:** For live report mode, compare profile enums/budget/anchor fields rather than full object equality; keep strict equality only for frozen finalize replay of identical drafts.

---

### Bug / Gap 11 — Low: LLM stage duration uses mtime delta

**File:** `finalize_daily_strategy.py`

`llm_duration = draft.mtime - compact.mtime` is best-effort only.

**Impact:** Timing KPI can be wrong after retries, touches, or clock skew.

**Fix:** Optional explicit `--llm-duration` or record start/end in draft metadata when available.

---

### Bug / Gap 12 — Low: Minor cleanliness

- `compact_atomic` in finalize is unused  
- Role-tag grounding uses substring `tag in source_basis` (possible false positive)  
- `normalize_strategy_selection.py` is no longer on the happy path (acceptable if draft is strict)

---

## 7. Dry-Run Evidence (2026-07-15)

Command shape:

```bash
python .opencode/skills/daily-strategy/scripts/prepare_daily_strategy.py \
  --date 2026-07-15 \
  --indices /tmp/opencode/indices_2026-07-15.json \
  --output-dir /tmp/opencode/step3_prep_2026-07-15
```

| Metric | Value |
|---|---:|
| Candidates | 60 |
| Prepare wall time | 0.031s |
| `.strategy_llm_input.json` | 79,215 bytes |
| Hard target | ≤ 81,920 bytes |
| Stretch target | ≤ 61,440 bytes |
| `regime_hint` (frozen indices ~flat) | neutral |
| Candidates with triggers | 60 |
| `low_confidence` flags | 60 |
| `anomaly` flags | 4 |
| Conditional `news_evidence` items | 3 |
| Live view had `mapper_sha256` | No (would rebuild) |

Incomplete draft smoke check: `validate_draft` returned **no errors** for a stock missing required decision fields; materialize then failed on profile budget contradiction. Confirms Gap 1.

---

## 8. Success Criteria Scorecard

### Correctness (plan §16)

| Metric | Requirement | Status |
|---|---|---|
| Candidate visibility | 100% Step 2 candidates | **Pass** (prepare coverage gate) |
| Missing/duplicate compact candidates | 0 | **Pass** |
| Frozen replay code/order diff | 0 | **Not proven** |
| Frozen replay Direction/rating/profile/rules | 0 | **Not proven** |
| Live LLM shadow | Report, not hard CI | **Tool ready; no sample run** |
| Invalid/unresolved evidence | 0 | **Pass on prepare path** (theme/news refs checked) |
| Source-basis coverage | 100% selected | **Final validator only; draft weak** |
| Observation coverage | 100% non-selected | **Pass in unit materialize** |
| Strategy/HTML validation failure | 0 | **Unit path pass; no full live publish sample in review** |

### Performance (plan §16)

| Metric | Requirement | Status |
|---|---|---|
| Compact input @ ~60 names | hard ≤80KB; stretch ≤60KB | **Hard pass / stretch fail** |
| Hot-phase instruction context | ≤10KB target | **Pass** (rubric+contract ~6KB; rules still full by design) |
| Local prepare/finalize excl. network | &lt;1s each | **Prepare pass; finalize not timed on live draft** |
| Normal Step 3 wall time | ~4–6 min | **Not measured (Gate D)** |
| Timing linkage | `complete_same_run=true` | **Unit pass** |

---

## 9. Recommended Fix Order

1. **Harden `validate_draft`** — full selected-stock contract before materialize.  
2. **Add Gate B goldens** — at least one weak and one neutral frozen draft replay.  
3. **Fix trigger/regime semantics** — auction contradiction decision + low_confidence flood + `derive_regime` table.  
4. **Compress compact input** — leave headroom under 80KB.  
5. **Ensure Step 2 emits `mapper_sha256`** on all produced views.  
6. **Split intraday-operation-guide** changes out of this branch.  
7. **Collect ≥5 live Gate D timings** before declaring 4–6 minute success.  
8. Only then treat workflow cutover as production-ready (or keep explicit rollback until then).

---

## 10. Merge Recommendation

**Not ready to call the plan Done.**

Acceptable as an **implementation skeleton + wired workflow** with strong directional correctness on ownership and orchestration.

Blockers before trusting the next live morning run:

1. Draft validation completeness  
2. Real Gate B frozen replay  
3. Explicit decision on reread triggers / regime_hint semantics  
4. Separation of unrelated intraday HTML work  

Performance trajectory is plausible (local prepare is free; input under hard cap), but wall-clock success remains unproven until Gate D samples exist.

---

## 11. File-Level Checklist for Follow-up PRs

| Follow-up | Primary files |
|---|---|
| Draft contract hardening | `finalize_daily_strategy.py`, `validate_strategy_draft.py`, new tests |
| Gate B goldens | `tests/fixtures/*`, `test_step3_performance_contract.py` |
| Triggers / regime | `build_strategy_llm_input.py`, prepare tests |
| Size compression | `build_strategy_llm_input.py` |
| View hash always present | `build_strategy_view.py` + Step 2 finalize path |
| Shadow noise | `compare_strategy_shadow.py` report mode field subset |
| Scope split | revert/move `intraday-operation-guide/*` |
| Live timing samples | `predict/*/step3_timing.json` collection notes |

---

## 12. Conclusion

The Step 3 performance plan’s **architecture is correctly realized**: all candidates remain visible, deterministic work moves to Python, LLM output shrinks to selected decisions, and formal contracts stay `strategy.json` + HTML.

The remaining gap is not “missing scripts,” but **contract strictness, semantic fidelity to the prior reasoning rules, and regression gates**. Until those land, treat the cutover as **provisional** rather than production-complete.
