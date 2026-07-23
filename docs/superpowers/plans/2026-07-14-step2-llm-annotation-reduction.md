# Step 2 LLM Annotation Reduction Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Cut daily Step 2 wall time by reducing LLM stock-level annotation volume, without changing final candidate strategy quality (Direction / ranking driven by composite + news_impact + major_event + anomaly).

**Architecture:** Keep V5 Compute → Perception → Reasoning boundaries. Scripts still own universe build, hard/soft filters, composite math, and mapper assembly. LLM still owns `themes.json` and **candidate-only** `mapper.annotations.json` semantic fields that affect strategy (`news_relevance`, sparse `major_event` / `anomaly`). Move deterministic pattern sub-dimensions to Python where possible; slim or optionalize `theme_stocks.annotations.json` semantic fluff. Do **not** default-downgrade candidate `news_impact`.

**Tech Stack:** Python 3 scripts under `.agents/skills/daily-stock-mapping/scripts/`, skill markdown contracts, existing validate/build pipeline, optional pytest under skill tests.

---

## Background / Why

Observed Step 2 cost ~8–10 minutes is dominated by:

1. LLM multi-file perception writes (`themes.json`, `theme_stocks.annotations.json`, `mapper.annotations.json`)
2. Oversized pre-filter universe (often 77–219 codes vs target 30–50)
3. Secondary: cold sequential `fetch_pool_indicators` (not the main 8–10m when cache is warm)

Strategy impact analysis (do not reverse these conclusions during implementation):

| Change | Strategy impact |
|--------|-----------------|
| Annotate only soft-filter **candidates** for mapper | Near-zero on final trades |
| Slim `theme_stocks.annotations` | Low (semantic/report only) |
| Script-fill `pattern.auction` / `pattern.volume` (+ partial leader) | Low–medium; protect anomaly path |
| Sparse `major_event` / `anomaly` with force triggers | Low for most names; keep force list |
| Default all `news_impact` to sector R2 | **High — forbidden** |
| Blind universe shrink without ranking rules | Medium–high leakage risk |

Recent pool sizes (for regression baselines):

| Date | Universe | theme_stocks | mapper.annotations | candidates |
|------|----------|--------------|--------------------|------------|
| 2026-07-14 | 77 | 49 | 45 | 45 |
| 2026-07-13 | 96 | 67 | 22 | 19 |
| 2026-07-09 | 219 | 109 | 109 | 82 |

---

## File Map

| File | Responsibility after change |
|------|-----------------------------|
| `.agents/skills/daily-stock-mapping/SKILL.md` | Perception contract: candidate-only mapper annotations; sparse event rules; pattern ownership split |
| `.agents/skills/daily-market-analysis/SKILL.md` | Step 2 prompt/IO notes aligned with reduced annotation surface |
| `.agents/skills/daily-stock-mapping/scripts/build_theme_stocks_universe.py` | Optional tighter defaults for top-N expansion (P1) |
| `.agents/skills/daily-stock-mapping/scripts/build_theme_stocks_base.py` | Unchanged filter ownership; may emit `annotation_targets[]` helper field or sidecar |
| `.agents/skills/daily-stock-mapping/scripts/build_annotation_targets.py` (**create**) | Deterministic list of codes that **must** receive full LLM mapper annotations |
| `.agents/skills/daily-stock-mapping/scripts/compute_pattern_defaults.py` (**create**) | Deterministic `pattern.auction` / `pattern.volume` (+ optional leader) from pool + theme_stocks |
| `.agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py` | Merge defaults + annotations; preserve news_impact recalculation; never invent news_impact |
| `.agents/skills/daily-stock-mapping/scripts/build_mapper_base.py` / `build_mapper_json.py` | Wire pattern defaults before/while merge |
| `.agents/skills/daily-stock-mapping/scripts/validate_mapper_annotations.py` | Allow partial stock list (candidates subset); still require full fields **for listed stocks** |
| `.agents/skills/daily-stock-mapping/scripts/validate_theme_stocks_annotations.py` | Allow minimal / empty stocks[] when generation_mode = slim |
| Tests under `.agents/skills/daily-stock-mapping/scripts/tests/` or existing test dirs | Contract tests for targets, defaults, merge, validation |

---

## Non-Goals (this plan)

- Concurrent `fetch_pool_indicators` (separate perf plan)
- Changing composite weights
- Letting Step 2 emit Direction / RiskSeverity
- Replacing Step 3 Reasoning with more Step 2 inference

---

## Target Contracts

### A. `predict/{date}/annotation_targets.json` (new, script-owned)

```json
{
  "schema_version": "daily_annotation_targets.v1",
  "date": "YYYY-MM-DD",
  "candidates": ["sz000001", "sh600519"],
  "force_full": ["sz000001"],
  "rules": {
    "include_all_candidates": true,
    "force_triggers": [
      "news_direct",
      "lhb",
      "board_streak>=2",
      "cross_rank_or_market_active",
      "tech_score 50-59",
      "hard_contradiction_precheck"
    ]
  }
}
```

- **candidates**: every `theme_stocks.json` / base stock with `filter.status == "candidate"` after technical filters.
- **force_full**: subset that must include non-default `major_event` review + `anomaly` consideration + high-attention `news_relevance` (not optional skip).
- Observation / removed / board_excluded codes are **never** required in `mapper.annotations.json.stocks[]`.

### B. `mapper.annotations.json` (LLM-owned, reduced membership)

- `stocks[]` **MAY** contain only `annotation_targets.candidates` (ideally exactly that set, or a superset that scripts will soft-skip).
- Missing candidate annotation is a **warning** in build (existing behavior), but Step 2 skill will treat missing candidate annotation as a **hard agent failure** after this plan (agent must cover all targets).
- Per stock still requires: `news_relevance`, `major_event`, `pattern` (may be partial if defaults filled by script), `anomaly`, `news_link`.

### C. Pattern ownership split

| Dimension | Owner after plan |
|-----------|------------------|
| `auction` | Python default from auction/change fields; LLM override only if anomaly-related |
| `volume` | Python default from amount / vol_ratio |
| `leader` | Python default from role_tags + board_streak/seal; LLM may override |
| `heat` | LLM preferred (theme heat trajectory); Python fallback `STABLE` conf=50 |
| `rotation` | LLM preferred; Python fallback `TERTIARY`/`NONE` from MultiTheme/purity if available |

### D. Sparse events

- Default `major_event.polarity = "none"`, conf=90, unless force trigger evidence.
- Default `anomaly = null` unless mandatory trigger (existing skill mandatory anomaly list).
- **Never** invent Positive/Negative without company-named discrete event.

### E. Forbidden

- Filling `news_relevance` as blanket `R2/P2` for all candidates.
- Dropping candidates from annotation targets to save tokens without removing them from candidate_pool.

---

### Task 1: Spec lock in skill docs (contract first)

**Files:**
- Modify: `.agents/skills/daily-stock-mapping/SKILL.md`
- Modify: `.agents/skills/daily-market-analysis/SKILL.md`

- [ ] **Step 1: Edit daily-stock-mapping skill — Technical Enrichment / Structured Dataset sections**

Add an explicit subsection **“Annotation Budget (P0)”** after Technical Enrichment output contract:

```markdown
## Annotation Budget (P0)

1. Run deterministic filters first:
   `validate_themes_json` → `build_theme_stocks_universe` → `fetch_pool_indicators`
   → `build_theme_stocks_base` → `build_annotation_targets.py`.
2. LLM writes `theme_stocks.annotations.json` in **slim mode** (optional per-stock
   fields; empty `stocks[]` allowed if no semantic overrides).
3. LLM writes `mapper.annotations.json` **only for codes listed in**
   `predict/{date}/annotation_targets.json` → `candidates[]`.
4. Do **not** author mapper stock annotations for universe-only, removed,
   observation, or board_excluded names.
5. Preserve full `news_relevance` matrix discipline for every annotation target.
6. Use sparse `major_event` / `anomaly` with force triggers from annotation_targets.
7. Prefer script pattern defaults; LLM may omit pattern.auction/volume or set them
   only when overriding.
```

Update the long script sequence block to insert:

```bash
python .agents/skills/daily-stock-mapping/scripts/build_annotation_targets.py --date {YYYY-MM-DD}
python .agents/skills/daily-stock-mapping/scripts/compute_pattern_defaults.py --date {YYYY-MM-DD}
```

after `build_theme_stocks_base.py` / validated `theme_stocks.json` as appropriate (targets from base or final theme_stocks — prefer **base candidate set** so annotations can be written before theme_stocks merge if needed).

**Decision locked for implementers:**  
`build_annotation_targets.py` reads `theme_stocks.base.json` (status candidate) so mapper annotations can be authored immediately after base; if annotations already exist for a code later removed, soft-skip remains.

- [ ] **Step 2: Edit daily-market-analysis Step 2 outputs list**

Add outputs:

- `predict/{date}/annotation_targets.json`
- `predict/{date}/pattern_defaults.json` (script)

Keep existing outputs; note Step 2 agent must load annotation_targets before writing mapper.annotations.

- [ ] **Step 3: Commit docs-only contract**

```bash
git add .agents/skills/daily-stock-mapping/SKILL.md .agents/skills/daily-market-analysis/SKILL.md
git commit -m "docs(daily-step2): lock candidate-only annotation budget contract"
```

---

### Task 2: `build_annotation_targets.py` + tests

**Files:**
- Create: `.agents/skills/daily-stock-mapping/scripts/build_annotation_targets.py`
- Create: `.agents/skills/daily-stock-mapping/scripts/tests/test_build_annotation_targets.py`

- [ ] **Step 1: Write failing tests**

```python
# test_build_annotation_targets.py
from pathlib import Path
import json
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from build_annotation_targets import build_targets_doc


def test_only_candidates_become_targets():
    base = {
        "schema_version": "daily_theme_stocks_base.v1",
        "date": "2026-07-14",
        "stocks": [
            {"code": "sz000001", "name": "A", "filter": {"status": "candidate"}, "source": "candidate", "source_flags": {}, "technical": {"tech_score": 70, "board_streak": 0}},
            {"code": "sz000002", "name": "B", "filter": {"status": "observation"}, "source": "candidate", "source_flags": {}, "technical": {"tech_score": 40, "board_streak": 0}},
            {"code": "sh600000", "name": "C", "filter": {"status": "candidate"}, "source": "news_direct", "source_flags": {"news": True}, "technical": {"tech_score": 55, "board_streak": 2}},
        ],
    }
    doc = build_targets_doc(base, date="2026-07-14")
    assert doc["schema_version"] == "daily_annotation_targets.v1"
    assert set(doc["candidates"]) == {"sz000001", "sh600000"}
    assert "sz000002" not in doc["candidates"]
    assert "sh600000" in doc["force_full"]  # news_direct + board_streak>=2


def test_empty_candidates_ok():
    base = {
        "schema_version": "daily_theme_stocks_base.v1",
        "date": "2026-07-14",
        "stocks": [],
    }
    doc = build_targets_doc(base, date="2026-07-14")
    assert doc["candidates"] == []
    assert doc["force_full"] == []
```

- [ ] **Step 2: Run tests — expect fail (module missing)**

```bash
python -m pytest .agents/skills/daily-stock-mapping/scripts/tests/test_build_annotation_targets.py -v
```

Expected: import / collection failure.

- [ ] **Step 3: Implement `build_annotation_targets.py`**

Minimal behavior:

```python
#!/usr/bin/env python3
"""Build predict/{date}/annotation_targets.json from theme_stocks.base.json."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any

from mapper_json_lib import clean_text, default_predict_dir, ensure_doc_date, parse_float, read_json, write_json


def _force_reasons(stock: dict[str, Any]) -> list[str]:
    reasons: list[str] = []
    source = clean_text(stock.get("source")) or ""
    flags = stock.get("source_flags") if isinstance(stock.get("source_flags"), dict) else {}
    tech = stock.get("technical") if isinstance(stock.get("technical"), dict) else {}
    score = parse_float(tech.get("tech_score"))
    streak = parse_float(tech.get("board_streak")) or 0

    if source in {"news_direct", "lhb", "market_active"} or flags.get("news") or flags.get("lhb") or flags.get("market"):
        reasons.append(source or "source_flag")
    if streak >= 2:
        reasons.append("board_streak>=2")
    if score is not None and 50 <= score < 60:
        reasons.append("tech_borderline")
    return reasons


def build_targets_doc(base: dict[str, Any], date: str) -> dict[str, Any]:
    candidates: list[str] = []
    force_full: list[str] = []
    force_detail: dict[str, list[str]] = {}
    for stock in base.get("stocks", []):
        if not isinstance(stock, dict):
            continue
        code = clean_text(stock.get("code"))
        if not code:
            continue
        status = clean_text((stock.get("filter") or {}).get("status")) if isinstance(stock.get("filter"), dict) else None
        if status != "candidate":
            continue
        candidates.append(code)
        reasons = _force_reasons(stock)
        if reasons:
            force_full.append(code)
            force_detail[code] = reasons
    # stable unique order
    seen = set()
    candidates = [c for c in candidates if not (c in seen or seen.add(c))]
    seen_f = set()
    force_full = [c for c in force_full if not (c in seen_f or seen_f.add(c))]
    return {
        "schema_version": "daily_annotation_targets.v1",
        "date": date,
        "candidates": candidates,
        "force_full": force_full,
        "force_detail": force_detail,
        "rules": {
            "include_all_candidates": True,
            "force_triggers": [
                "news_direct",
                "lhb",
                "market_active",
                "board_streak>=2",
                "tech_borderline_50_59",
            ],
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build annotation_targets.json")
    parser.add_argument("--date", required=True)
    parser.add_argument("--base", help="theme_stocks.base.json path")
    parser.add_argument("--output", help="output path")
    args = parser.parse_args()
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")
    predict_dir = default_predict_dir(args.date)
    base_path = Path(args.base) if args.base else predict_dir / "theme_stocks.base.json"
    out_path = Path(args.output) if args.output else predict_dir / "annotation_targets.json"
    base = read_json(base_path)
    if not isinstance(base, dict):
        print("[ERROR] base must be object", file=sys.stderr)
        return 1
    try:
        ensure_doc_date(base, args.date, str(base_path))
    except ValueError as exc:
        print(f"[ERROR] {exc}", file=sys.stderr)
        return 1
    doc = build_targets_doc(base, args.date)
    write_json(out_path, doc)
    print(f"OK: wrote {out_path} candidates={len(doc['candidates'])} force_full={len(doc['force_full'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

Adjust field paths (`filter.status`, `technical.*`, `source`) to match **actual** `theme_stocks.base.json` shape in repo when implementing — read one real file under `predict/` first and align.

- [ ] **Step 4: Run tests — expect pass**

```bash
python -m pytest .agents/skills/daily-stock-mapping/scripts/tests/test_build_annotation_targets.py -v
```

- [ ] **Step 5: Smoke on real day**

```bash
python .agents/skills/daily-stock-mapping/scripts/build_annotation_targets.py --date 2026-07-14
```

Expected: `candidates` count ≈ current candidate count for that date; `force_full` ≤ candidates.

- [ ] **Step 6: Commit**

```bash
git add .agents/skills/daily-stock-mapping/scripts/build_annotation_targets.py .agents/skills/daily-stock-mapping/scripts/tests/test_build_annotation_targets.py
git commit -m "feat(daily-step2): build candidate-only annotation targets"
```

---

### Task 3: Pattern defaults script + merge wiring

**Files:**
- Create: `.agents/skills/daily-stock-mapping/scripts/compute_pattern_defaults.py`
- Create: `.agents/skills/daily-stock-mapping/scripts/tests/test_compute_pattern_defaults.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/build_mapper_base.py` and/or `build_mapper_json.py`

- [ ] **Step 1: Write failing tests for auction/volume defaults**

```python
from compute_pattern_defaults import pattern_defaults_for_stock

def test_volume_surge():
    pool_entry = {
        "raw_observation": {
            "amount": {"value": 90000},  # 万 → 9亿 if pipeline uses 万
            "vol_ratio_5d": {"value": 2.5},
        }
    }
    # Align units with real pool_indicators.json before asserting thresholds
    p = pattern_defaults_for_stock("sz000001", pool_entry, stock_meta={})
    assert p["volume"]["state"] in {"SURGE", "NORMAL", "DRY"}
    assert p["auction"]["state"] in {"LEADING", "LAGGING", "MATCH", "NEUTRAL"}
```

Use **real field units** from `predict/2026-07-14/pool_indicators.json` when coding thresholds (skill text: amount in 亿 ≥8 SURGE; 3–8 NORMAL; <3 DRY — confirm whether stored amount is 万 or 元).

- [ ] **Step 2: Implement `compute_pattern_defaults.py`**

Write `pattern_defaults.json`:

```json
{
  "schema_version": "daily_pattern_defaults.v1",
  "date": "YYYY-MM-DD",
  "stocks": {
    "sz000001": {
      "auction": {"state": "NEUTRAL", "confidence": 80, "trace": "script"},
      "volume": {"state": "NORMAL", "confidence": 80, "trace": "script"},
      "leader": {"state": "ABSENT", "confidence": 60, "trace": "script"},
      "heat": {"state": "STABLE", "confidence": 50, "trace": "script-fallback"},
      "rotation": {"state": "TERTIARY", "confidence": 50, "trace": "script-fallback"}
    }
  }
}
```

- [ ] **Step 3: Merge rules in `mapper_json_lib.py`**

When merging annotations:

1. Start pattern from defaults for code.
2. Overlay LLM pattern dims **only where present**.
3. Recalculate composite only after `news_impact` from annotations (unchanged).

Add helper:

```python
def merge_pattern_with_defaults(defaults: dict | None, annotation_pattern: Any) -> dict[str, Any]:
    base = defaults or {}
    result = {
        key: pattern_state(base.get(key))
        for key in ("heat", "leader", "auction", "rotation", "volume")
    }
    return merge_pattern(result, annotation_pattern)
```

Wire load of `pattern_defaults.json` in `build_mapper_base.py` / `build_mapper_json.py`.

- [ ] **Step 4: Tests green + dry-run merge on 2026-07-14**

```bash
python -m pytest .agents/skills/daily-stock-mapping/scripts/tests/test_compute_pattern_defaults.py -v
python .agents/skills/daily-stock-mapping/scripts/compute_pattern_defaults.py --date 2026-07-14
```

- [ ] **Step 5: Commit**

```bash
git add .agents/skills/daily-stock-mapping/scripts/compute_pattern_defaults.py .agents/skills/daily-stock-mapping/scripts/mapper_json_lib.py .agents/skills/daily-stock-mapping/scripts/build_mapper_base.py .agents/skills/daily-stock-mapping/scripts/build_mapper_json.py .agents/skills/daily-stock-mapping/scripts/tests/test_compute_pattern_defaults.py
git commit -m "feat(daily-step2): script pattern defaults with LLM overlay"
```

---

### Task 4: Validation updates for partial / slim annotations

**Files:**
- Modify: `.agents/skills/daily-stock-mapping/scripts/validate_mapper_annotations.py`
- Modify: `.agents/skills/daily-stock-mapping/scripts/validate_theme_stocks_annotations.py`
- Create tests if missing

- [ ] **Step 1: Mapper annotations validation**

Rules after change:

- If `annotation_targets.json` exists: every `candidates[]` code **must** appear in `mapper.annotations.stocks[]` (hard error for agent gate).
- Extra annotation codes still soft-skip at build (warn only).
- Enum/schema checks unchanged for present stocks.
- Pattern dims may be partial **if** `pattern_defaults.json` covers missing dims (validator may allow omit auction/volume when defaults file present).

Implement check:

```python
def check_targets_coverage(annotations: dict, targets: dict | None) -> list[str]:
    if not targets:
        return []
    have = {s.get("code") for s in annotations.get("stocks", []) if isinstance(s, dict)}
    missing = [c for c in targets.get("candidates", []) if c not in have]
    return [f"mapper.annotations missing candidate {c}" for c in missing]
```

- [ ] **Step 2: Theme stocks annotations slim mode**

Allow:

```json
{
  "schema_version": "daily_theme_stocks_annotations.v1",
  "date": "YYYY-MM-DD",
  "themes": [],
  "stocks": []
}
```

Still require schema_version + date. Theme notes optional.

- [ ] **Step 3: Tests + commit**

```bash
python -m pytest .agents/skills/daily-stock-mapping/scripts/tests/ -k "annotation" -v
git add .agents/skills/daily-stock-mapping/scripts/validate_mapper_annotations.py .agents/skills/daily-stock-mapping/scripts/validate_theme_stocks_annotations.py
git commit -m "fix(daily-step2): validate candidate coverage and slim theme-stock annotations"
```

---

### Task 5: Skill agent procedure rewrite (token budget)

**Files:**
- Modify: `.agents/skills/daily-stock-mapping/SKILL.md` (mapper annotation authoring section)
- Optionally: `.opencode/agents/*` if sector-analyst embeds step2 instructions

- [ ] **Step 1: Replace “annotate every pool stock” language**

Authoring checklist for agent:

1. Read `annotation_targets.json` only (not full universe) for stock loop.
2. For each target code: write `news_relevance` carefully (matrix).
3. If code in `force_full`: spend tokens on `major_event` / `anomaly` / richer pattern.
4. Else: `major_event=none`, `anomaly=null`, omit auction/volume pattern (script fills).
5. Themes still fully annotated in `themes.json` (not reduced in this plan).

- [ ] **Step 2: Add anti-patterns red flag table rows**

| Symptom | Fix |
|---------|-----|
| Annotated universe codes not in candidates | Drop; only targets |
| All news_relevance R2/P2 identical | Illegal shortcut; redo matrix |
| Missing candidate in mapper.annotations | Fail validation; fill gaps |
| Pattern walls of prose for every stock | Use defaults; only override force_full |

- [ ] **Step 3: Commit**

```bash
git add .agents/skills/daily-stock-mapping/SKILL.md
git commit -m "docs(daily-step2): agent procedure for reduced annotation budget"
```

---

### Task 6: Optional P1 universe top-N tighten (separate commit)

**Files:**
- Modify: `.agents/skills/daily-stock-mapping/scripts/build_theme_stocks_universe.py` defaults
- Modify: skill docs defaults text

**Only if** candidate counts still >> 50 after Task 1–5.

Proposed defaults (tune with backtest):

| Flag | Old | New |
|------|-----|-----|
| `--top-candidates` | 15 | 10 |
| `--top-leaders` | 10 | 8 |
| `--top-pure` | 15 | 8 |

Hard cap optional: after merge, keep top K by library score per theme — **do not implement hard global drop without score field audit**.

- [ ] **Step 1: Measure before/after on 2026-07-09 and 2026-07-14**

```bash
python .agents/skills/daily-stock-mapping/scripts/build_theme_stocks_universe.py --date 2026-07-14 --top-candidates 10 --top-leaders 8 --top-pure 8
# compare len(stocks) vs previous universe
```

- [ ] **Step 2: If leakage risk low (same top candidates by purity/score), change defaults + commit**

```bash
git commit -m "perf(daily-step2): tighten theme universe top-N defaults"
```

If top names churn >20% vs old universe for 3 sample days, **abort defaults change** and leave flags manual.

---

### Task 7: Regression harness (strategy-safe check)

**Files:**
- Create: `.agents/skills/daily-stock-mapping/scripts/tests/test_annotation_budget_regression.py` (optional offline)
- Or a small shell/python compare script under `docs/superpowers/plans/` tools — prefer skill tests using frozen fixtures.

- [ ] **Step 1: Offline compare using existing predict artifacts**

For date `2026-07-14`:

1. Build targets from base.
2. Assert `set(targets.candidates) == set(mapper.candidate codes)` (or ⊆ historical candidates).
3. Simulate “reduced annotations” by filtering historical `mapper.annotations.json` to targets only; rebuild mapper; compare:

| Metric | Tolerance |
|--------|-----------|
| candidate set | identical |
| composite rank top 10 codes | ≥8/10 same |
| composite value delta per shared code | ≤ 1e-6 if news_impact kept identical |
| major_event non-none codes | identical set |

```bash
python .agents/skills/daily-stock-mapping/scripts/build_annotation_targets.py --date 2026-07-14
# filter annotations to targets, rebuild mapper, diff composites
```

- [ ] **Step 2: Document results in plan appendix or PR body**

- [ ] **Step 3: Commit harness if automated**

```bash
git commit -m "test(daily-step2): regression checks for annotation budget"
```

---

### Task 8: End-to-end dry run (manual)

- [ ] **Step 1: Pick a past date with full artifacts (e.g. 2026-07-14)**

Run:

```bash
set PYTHONIOENCODING=utf-8
python .agents/skills/daily-stock-mapping/scripts/validate_themes_json.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/build_theme_stocks_universe.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/fetch_pool_indicators.py --codes-file predict/2026-07-14/theme_stocks.universe.json --json -o predict/2026-07-14/pool_indicators.json
python .agents/skills/daily-stock-mapping/scripts/build_theme_stocks_base.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/build_annotation_targets.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/compute_pattern_defaults.py --date 2026-07-14
# use existing annotations filtered to targets OR re-author slim file
python .agents/skills/daily-stock-mapping/scripts/validate_theme_stocks_annotations.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/build_theme_stocks_json.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/validate_theme_stocks_json.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/validate_mapper_annotations.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/build_mapper_base.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/build_mapper_json.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/validate_mapper_json.py --date 2026-07-14
python .agents/skills/daily-stock-mapping/scripts/build_strategy_view.py --date 2026-07-14
```

- [ ] **Step 2: Confirm**

- `annotation_targets.json` exists and candidate count << universe when universe bloated  
- validate passes  
- strategy_view candidates unchanged when annotations preserved for those codes  

- [ ] **Step 3: No commit of regenerated predict artifacts unless user asks**

---

## Implementation Order Summary

```text
Task 1 docs contract
  → Task 2 annotation_targets
  → Task 3 pattern defaults + merge
  → Task 4 validators
  → Task 5 agent procedure
  → Task 7 regression
  → Task 8 dry run
  → Task 6 universe tighten only if still needed
```

---

## Success Metrics

| Metric | Target |
|--------|--------|
| Mapper annotation stock count | = candidate count (not universe) |
| Step 2 LLM token/time on stock annotations | −40% to −70% vs current full-universe habit |
| Top-10 composite membership (same news_impact) | ≥80% stable |
| Direction-affecting fields preserved for candidates | news_impact / major_event / anomaly / theme_heat |
| `news_impact` blanket R2 | 0 occurrences in review |

---

## Risks & Mitigations

| Risk | Mitigation |
|------|------------|
| Agent still annotates universe | Hard coverage check vs targets; skill red flags |
| Pattern defaults wrong units | Unit test against real pool_indicators sample |
| force_full too small → miss anomaly pivots | Include news_direct/lhb/streak/borderline tech |
| force_full too large → no speedup | Cap force heuristics; measure ratio force/candidates |
| Validator too strict before defaults exist | Feature-detect pattern_defaults.json |

---

## Out-of-scope follow-ups (next plans)

1. Concurrent `fetch_pool_indicators` + cache warmup  
2. Batch-only enforcement for `query_theme` / money flow  
3. Step 2 stage timing logs (`step2_timing.json`)  
4. Auto-derive more of `news_relevance` from structured news stock tags if Step 1 gains NER

---

## Self-Review Checklist

- [x] Spec coverage: candidate-only annotations, sparse events, pattern split, forbidden news_impact shortcut, optional universe tighten, regression, skill docs  
- [x] No TBD placeholders for core path  
- [x] Types/schema names consistent: `daily_annotation_targets.v1`, `daily_pattern_defaults.v1`  
- [x] Strategy-safe constraints explicit  

---

## Appendix: Suggested agent prompt delta (Step 2)

After scripts produce targets:

```text
Read predict/{date}/annotation_targets.json.
Write mapper.annotations.json stocks[] covering ALL candidates[] only.
For force_full codes: full major_event/anomaly/pattern care.
For other candidates: news_relevance required; major_event=none; anomaly=null;
pattern may omit auction/volume.
Do not annotate non-candidate codes.
```
