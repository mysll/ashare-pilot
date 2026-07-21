# Code Review: JSON-first Mapper Theme Stocks Pipeline

**Date:** 2026-07-08
**Scope:** Commit `7cef981` + uncommitted working-tree changes

---

## Part 1: Committed Changes (`7cef981` — feat: add json-first mapper contract)

10 new scripts, 3 updated SKILL.md files. Introduces JSON-first pipeline: LLM writes `mapper.annotations.json` → scripts build/merge/validate `mapper.json` → project `mapper.strategy_view.json` → render `mapper.md`.

### Bug 1 (Medium): R0/P0 Validator/Matrix Mismatch

**Files:** `validate_mapper_annotations.py:17-18` ↔ `mapper_json_lib.py:20-33`

Validator accepts `"r": "R0"` and `"p": "P0"`:

```python
RELEVANCE = {"R0", "R1", "R2", "R3", "R4"}
PROMINENCE = {"P0", "P1", "P2", "P3"}
```

But `NEWS_IMPACT_MATRIX` has no R0 or P0 entries — it only covers R1-R4 × P1-P3. When LLM writes `{"r": "R0", "p": "P3"}`, validation passes but `calculate_news_impact()` (line 852) finds no matrix hit and falls back to `parse_float(news_relevance.get("value", fallback.get("value")))`, potentially zero-scoring silently.

**Fix:** Remove `"R0"` and `"P0"` from validator (match the matrix), or add R0/P0 entries to the matrix. R0 should be 0 regardless; P0 should be 0 regardless.

### Bug 2 (Low): Hardcoded Synthetic Auction Confidence in Legacy Bridge

**File:** `mapper_json_lib.py:369`

```python
"auction": score(50, 100, "from mapper phase 1 bridge"),
"money_flow": score(50, 50, "phase 1 default"),
```

`auction` has `confidence: 100` for synthetic data that is never null-or-missing. Should use `confidence: 50` (same as `money_flow`) for honesty about data quality.

### Observation 1 (Not a Bug): Legacy Column Names Depend on Exact Markdown Headers

**File:** `mapper_json_lib.py:350-392`

`parse_candidate_pool` expects exact dot-delimited column names (`"comp.value"`, `"tech.value"`, `"th_heat.value"`, `"maj_ev.pol"`). Slight format drift causes silent `None` defaults.

---

## Part 2: Uncommitted Changes

8 files with substantive changes (+5 new untracked scripts). ~537 insertions, 73 deletions (ignoring whitespace).

### Summary of Changes

| File | Nature |
|------|--------|
| `kline_cache.py` | Bug fix: cache path from 6 `.parent` (root fs) → 4 `.parent` (repo root) |
| `requirements.txt` | Removed version pins from `requests` and `websocket-client` |
| `mapper_json_lib.py` | +324 lines: `scope_decision`, `board_policy_from_scope`, `deterministic_filter_from_technical`, `merge_theme_stock_annotations`, theme_stocks JSON parsers, expanded `CODE_RE` |
| `build_mapper_base.py` | +`--theme-stocks-json`, `--scope` args; reads `theme_stocks.json` for observation/excluded stocks |
| `fetch_pool_indicators.py` | `--codes-file` arg (reads `theme_stocks.universe.json`), code dedup |
| `validate_mapper_json.py` | Scope-driven board exclusion, not hardcoded `sh688`/`bj` |
| `daily-market-analysis/SKILL.md` | Updated pipeline docs: theme_stocks JSON steps |
| `daily-stock-mapping/SKILL.md` | Updated: theme_stocks.base.json → annotations → json → md |
| 5 new scripts (untracked) | `build_theme_stocks_base.py` (718 lines), `build_theme_stocks_json.py`, `render_theme_stocks_md.py`, `validate_theme_stocks_annotations.py`, `validate_theme_stocks_json.py` |

---

### Bug 3 (Low): `kline_cache.py` Cache Path Fix — Correct

**File:** `.opencode/lib/datasources/kline_cache.py:13`

```diff
-DEFAULT_CACHE_DIR = Path(__file__).resolve().parent * 6 / ".cache" / "kline"
+DEFAULT_CACHE_DIR = Path(__file__).resolve().parent * 4 / ".cache" / "kline"
```

Old: 6 parents = `/.cache/kline` (root filesystem, wrong).
New: 4 parents = `<repo_root>/.cache/kline` (correct).
This is a valid bug fix.

---

### Issue 4 (Medium): `CODE_RE` Regex Significantly Broadened

**File:** `mapper_json_lib.py:17`

```python
# Old (A-share only):
r"\b(?:sh|sz)\d{6}\b"
# New (all markets):
r"\b(?:[a-z]{2}\d{6}|[a-z]{2,4}_[a-z0-9]+)\b"
```

The new regex now matches `hk00700`, `usr_nvda`, `nf_IF0`, `hf_OIL`, etc. Scope decisions catch non-A-share codes downstream (`scope_decision` returns `allowed: False` for unmatched board prefixes), but `CODE_RE` is also used as a standalone format validator in places without scope checks (`parse_removed_rows`, `load_extra_stocks`). If someone adds `hk00700` to `theme_stocks.extra.json`, it passes regex but fails later with a confusing error ("pool_indicators.json missing codes").

**Risk:** Low impact (scope catches it), but the regex now encodes a bogus validation contract. If scope config is misconfigured, non-A-share codes could silently enter the daily pipeline.

---

### Issue 5 (Medium): `build_doc_from_themes` — Redundant Computation Between `--universe-only` and Full Build

**File:** `build_theme_stocks_base.py:395-527`

The full build re-reads Theme Library JSON + `theme_stocks.extra.json` + scope config independently from the `--universe-only` run. If any input changes between steps, stock sets diverge:

- **Fork A:** full build has more codes than universe → `missing_pool_codes` error (recoverable, but requires re-running entire pipeline)
- **Fork B:** universe has more codes than full build → universe contains redundant codes not in base

**Suggested fix:** Full build should read `theme_stocks.universe.json` codes instead of re-collecting from Theme Library, ensuring steps 2.2a and 2.2c use identical stock sets.

---

### Issue 6 (Medium): `theme_stocks.json` Data Not Propagated to `mapper.base.json`

**File:** `mapper_json_lib.py:730-834` (`build_base_from_annotations`)

When `theme_stocks_doc` is provided, only cross-referencing and observation/excluded pools are consumed. The following rich data from `theme_stocks.json` is discarded:

- `source_themes` — per-stock theme membership and scores
- `source_flags` — candidate/market/news/LHB provenance
- `best_score` — cross-theme composite score
- `themes[].heat` — actual theme heat values

Instead, hardcoded defaults are used:

```python
# line 785-786
"theme_heat": score(50, 50, "base default; refine upstream when themes.json exists"),
"role_tags": [],  # line 782, always empty
```

`theme_heat` at score 50 with weight 30% materially affects composite ranking. The comment acknowledges the gap.

**Suggested fix:** Populate `theme_heat` from `theme_stocks.json.themes[].heat` matched by theme name, and populate `role_tags` from `source_flags` (e.g., "market_active", "news_direct", "lhb").

---

### Issue 7 (Low): `build_doc_from_themes` Overwrites Universe File on Every Run

**File:** `build_theme_stocks_base.py:481-482`

```python
if universe_output is not None:
    write_json(universe_output, universe_doc(date, stocks_by_code, board_excluded))
```

`universe_output` has a default value (line 668), so the full build also writes `theme_stocks.universe.json`. If the full build's stock collection diverges from the universe-only run, it silently overwrites the correct universe.

---

### Issue 8 (Low): `load_theme` Alias Resolution — No Cycle Guard

**File:** `build_theme_stocks_base.py:183-199`

The recursive `load_theme` function resolves Theme Library aliases by name lookup. If aliases form a cycle (e.g., `{A: [B], B: [A]}` and both JSON files are missing), infinite recursion occurs.

**Fix:** Add a `seen` set to detect cycles.

**Probability:** Very low — requires malformed Theme Library alias data.

---

### Issue 9 (Low): `safe_filename` Over-strips Characters

**File:** `build_theme_stocks_base.py:144-145`

```python
return re.sub(r'[<>:"/\\|?*()]', "_", name)
```

Parentheses are replaced with `_`, which can cause filename collisions: `"AI(5G)"` and `"AI 5G"` both become `"AI_5G_"`. Only `* ? < > : " / \ |` are problematic for path names on Windows.

**Risk:** Low — theme names rarely differ only by parentheses.

---

### Issue 10 (Low): `requirements.txt` Removed Version Pins

```diff
-requests>=2.25.0
-websocket-client>=1.0.0
+requests
+websocket-client
```

Allows installation of any version. If upstream releases breaking changes, the environment could break. Low risk for script repository, but loses reproducible guarantees.

---

### Observation: `.claude/settings.local.json` Should Be Gitignored

**File:** `.claude/settings.local.json` (untracked, `??`)

Local Claude permission configuration. If `git add .` captures it, developer-local settings would be committed.

---

### Observation: Massive Line-Ending Normalization Inflates Diff

Multiple files (`.opencode/lib/fetch/*.py`, `build_scan_pool.py`, `build_operation_snapshot.py`, `README.md`) show only CRLF → LF changes. This inflates the diff and risks merge conflicts. Should be done as a separate pre-commit.

---

## Part 3: JSON Pipeline Architecture Review

### Full Flow

```
themes.md (LLM)
    │
    ▼  LLM selects tradeable theme names → CLI --theme args
build_theme_stocks_base.py --universe-only    [Step 2.2a]
    ├─ Theme Library JSON (per theme)
    ├─ theme_stocks.extra.json (optional)
    ├─ scope filter → board_excluded[]
    └─ → theme_stocks.universe.json
    │
    ▼
fetch_pool_indicators.py --codes-file universe.json  [Step 2.2b]
    └─ → pool_indicators.json
    │
    ▼
build_theme_stocks_base.py (full build)       [Step 2.2c]
    ├─ [re-collects from sources — Issue 5]
    ├─ pool_indicators.json → technical data
    ├─ deterministic filter (hard/soft)
    └─ → theme_stocks.base.json
    │
    ▼
LLM writes theme_stocks.annotations.json      [Step 2.3]
    │
    ▼
validate → build_theme_stocks_json.py (merge) → validate → render .md
    │
    ▼
LLM writes mapper.annotations.json            [Step 2.4]
    │
    ▼
validate_mapper_annotations.py
    │
    ▼
build_mapper_base.py                          [Step 2.4]
    ├─ mapper.annotations.json
    ├─ theme_stocks.json → observation_pool + excluded_stocks ✓
    ├─ pool_indicators.json → candidate scoring ✓
    ├─ cross-ref: mapper candidates must exist in theme_stocks with status=candidate ✓
    └─ → mapper.base.json
    │
    ▼
build_mapper_json.py → validate_mapper_json.py → build_strategy_view.py → render_mapper_md.py
```

### What Is Correct

- **Data format match:** `load_pool` → `raw_value`/`computed_value` extraction paths exactly match `fetch_pool_indicators.py` V5 nested output format (`{code, raw_observation: {field: {value, confidence}}, computed_perception: {...}}`)
- **Filter consistency:** `deterministic_filter_from_technical` hard filters (amount < 3亿, atr > 8%) are cross-validated in `validate_theme_stocks_json.py`
- **Clean contract boundary:** Scripts own deterministic fields; LLM owns semantic annotations only; scripts own merge + validation + rendering
- **Cross-reference guard:** `build_base_from_annotations` (lines 769-773) verifies mapper candidate stocks exist in `theme_stocks.json` with `filter.status == "candidate"`
- **Observation pool routing:** `observation_pool_from_theme_stocks` correctly filters `status == "observation"` AND excludes codes already in the candidate pool
- **Excluded stocks aggregation:** `excluded_stocks_from_theme_stocks` collects from `removed_stocks[]`, `board_excluded[]`, and stocks with inline `status == "removed"`

### What Needs Work

| # | Severity | Issue | Location |
|---|----------|-------|----------|
| 1 | Medium | R0/P0 validator/matrix mismatch | `validate_mapper_annotations.py` vs `mapper_json_lib.py` |
| 2 | Medium | `--universe-only` / full build double-collect | `build_theme_stocks_base.py:395-527` |
| 3 | Medium | theme_stocks.json data not propagated to mapper | `mapper_json_lib.py:730-834` |
| 4 | Medium | `CODE_RE` too permissive (matches non-A-shares) | `mapper_json_lib.py:17` |
| 5 | Low | Universe file overwrite on every run | `build_theme_stocks_base.py:481-482` |
| 6 | Low | `load_theme` alias cycle risk | `build_theme_stocks_base.py:183-199` |
| 7 | Low | `safe_filename` over-strips parentheses | `build_theme_stocks_base.py:144-145` |
| 8 | Low | Auction synthetic confidence=100 | `mapper_json_lib.py:369` |
| 9 | Low | `requirements.txt` version pins removed | `requirements.txt` |
| 10 | Info | `.claude/` should be gitignored | root |
