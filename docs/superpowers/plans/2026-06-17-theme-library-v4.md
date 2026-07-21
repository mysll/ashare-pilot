# Theme Library V4: Multi-Dimensional Ranking System Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the V3 single-score leader ranking with a V4 multi-dimensional system (purity_score, leader_score, candidate_score) with eligibility filters, configurable thresholds, and new query commands.

**Architecture:** Refactor `build_library.py` scoring pipeline from single `_compute_theme_leaders()` to three-pass computation (purity → leader → candidate). Add `theme_library_config.json` for all configurable values. Add min_coverage/min_concepts per theme in `theme_config.json`. Replace `leaders` list in theme output with three lists. Remove `core_theme` from stock files. Add `leaders`, `pure`, `candidates` subcommands to `query_theme.py`.

**Tech Stack:** Python 3, JSON, no new external dependencies

---

## File Structure

| File | Action | Responsibility |
|------|--------|---------------|
| `scripts/theme_library_config.json` | Create | Limits, thresholds, scoring weights |
| `scripts/theme_config.json` | Modify | Add `min_coverage`/`min_concepts` per theme |
| `scripts/build_library.py` | Modify | V4 scoring pipeline, new output structures |
| `scripts/query_theme.py` | Modify | New subcommands, updated display |
| `SKILL.md` | Modify | Updated docs for V4 |

---

### Task 1: Create theme_library_config.json

**Files:**
- Create: `.opencode/skills/theme-library/scripts/theme_library_config.json`

- [ ] **Step 1: Create the configuration file**

```json
{
  "pure_limit": 50,
  "leader_limit": 20,
  "candidate_limit": 30,
  "pure_threshold": 30,
  "leader_threshold": 50,
  "candidate_threshold": 60,
  "default_min_coverage": 15,
  "default_min_concepts": 2,
  "scoring": {
    "purity_coverage_weight": 0.60,
    "purity_rank_weight": 0.40,
    "leader_purity_weight": 0.40,
    "leader_liquidity_weight": 0.35,
    "leader_market_cap_weight": 0.25,
    "candidate_purity_weight": 0.30,
    "candidate_liquidity_weight": 0.30,
    "candidate_market_cap_weight": 0.20,
    "candidate_momentum_weight": 0.20
  }
}
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/skills/theme-library/scripts/theme_library_config.json
git commit -m "feat(theme-library): add V4 configuration file with scoring weights and thresholds"
```

---

### Task 2: Add min_coverage/min_concepts to theme_config.json

**Files:**
- Modify: `.opencode/skills/theme-library/scripts/theme_config.json`

Broad themes (>5 concepts, high stock count) get `min_coverage: 20`. Narrow themes (1-2 concepts) get `min_coverage: 10`. All others keep defaults.

- [ ] **Step 1: Add threshold fields to each theme**

Broad themes (min_coverage=20): AI算力, AI应用, 半导体, 华为产业链, 新能源车, 数字经济, 创新药, 新消费

Narrow themes (min_coverage=10): 脑机接口, 量子科技, 海南自贸, 云计算/大数据, 教育的中药, 生物疫苗, 中俄贸易, 5G/6G通信, 风电, 氢能源, 储能, 核电, Web3/区块链

All other themes: no override (defaults to 15).

For each theme entry, add `"min_coverage": <value>` and `"min_concepts": 2`. Example:

```json
"AI算力": {
  "concepts": ["算力概念", "东数西算", "液冷概念", "数据中心", "国资云概念", "边缘计算", "高带宽内存"],
  "aliases": ["AI算力", "算力", "AI基础设施", "智算中心", "IDC", "机房", "数据中心"],
  "concept_weights_override": {
    "算力概念": 1.0,
    "东数西算": 0.9,
    "数据中心": 0.8,
    "液冷概念": 0.7,
    "国资云概念": 0.6,
    "边缘计算": 0.4,
    "高带宽内存": 0.3
  },
  "anchors": ["sz000977", "sh603019", "sz000063", "sz000938"],
  "min_coverage": 20,
  "min_concepts": 2
}
```

Apply this pattern to every theme in `theme_config.json`:
- `min_coverage: 20` for broad themes (AI算力, AI应用, 半导体, 华为产业链, 新能源车, 数字经济, 创新药, 新消费)
- `min_coverage: 10` for narrow themes (脑机接口, 量子科技, 海南自贸, 云计算/大数据, 教育, 中药, 生物疫苗, 中俄贸易, 5G/6G通信, 风电, 氢能源, 储能, 核电, Web3/区块链)
- No min_coverage/min_concepts entry for other themes (will use defaults from theme_library_config.json)

- [ ] **Step 2: Verify JSON is valid**

Run: `python -c "import json; json.load(open('.opencode/skills/theme-library/scripts/theme_config.json', encoding='utf-8')); print('OK')"`

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add .opencode/skills/theme-library/scripts/theme_config.json
git commit -m "feat(theme-library): add min_coverage/min_concepts thresholds per theme"
```

---

### Task 3: Refactor build_library.py scoring pipeline

**Files:**
- Modify: `.opencode/skills/theme-library/scripts/build_library.py`

This is the largest task. The changes are:

1. Replace hardcoded constants with config loading
2. Replace `_compute_theme_leaders()` with new V4 scoring functions
3. Update theme output structure (3 lists instead of `leaders`)
4. Update stock output structure (3 scores, no `core_theme`, sorted by purity_score)
5. Update concept output (remove `core_stocks`)
6. Add `qualified_stock_count` to theme output
7. Update `build_update_log()` version marker

- [ ] **Step 1: Replace module-level constants with config loading**

Replace lines 51-60:

```python
CONFIG_FILE = SCRIPT_DIR / "theme_config.json"

COVERAGE_WEIGHT = 0.45
RANK_WEIGHT = 0.30
LIQUIDITY_WEIGHT = 0.15
MARKET_CAP_WEIGHT = 0.10
LEADERS_TOP_N = 20
PURITY_COVERAGE_THRESHOLD = 15
PURITY_CONCEPT_MIN = 2
ANCHOR_BONUS = 5
```

With:

```python
CONFIG_FILE = SCRIPT_DIR / "theme_config.json"
LIBRARY_CONFIG_FILE = SCRIPT_DIR / "theme_library_config.json"


def _load_library_config():
    defaults = {
        "pure_limit": 50,
        "leader_limit": 20,
        "candidate_limit": 30,
        "pure_threshold": 30,
        "leader_threshold": 50,
        "candidate_threshold": 60,
        "default_min_coverage": 15,
        "default_min_concepts": 2,
        "scoring": {
            "purity_coverage_weight": 0.60,
            "purity_rank_weight": 0.40,
            "leader_purity_weight": 0.40,
            "leader_liquidity_weight": 0.35,
            "leader_market_cap_weight": 0.25,
            "candidate_purity_weight": 0.30,
            "candidate_liquidity_weight": 0.30,
            "candidate_market_cap_weight": 0.20,
            "candidate_momentum_weight": 0.20,
        },
    }
    if not LIBRARY_CONFIG_FILE.exists():
        return defaults
    with open(LIBRARY_CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    for key, val in defaults.items():
        if key not in cfg:
            cfg[key] = val
        elif isinstance(val, dict) and isinstance(cfg.get(key), dict):
            for dk, dv in val.items():
                if dk not in cfg[key]:
                    cfg[key][dk] = dv
    return cfg


LIBRARY_CONFIG = _load_library_config()
```

- [ ] **Step 2: Update `_load_config()` to return min_coverage/min_concepts**

Replace the `_load_config()` function (lines 79-88) with:

```python
def _load_config():
    if not CONFIG_FILE.exists():
        return {}, {}, {}
    with open(CONFIG_FILE, "r", encoding="utf-8") as f:
        cfg = json.load(f)
    return (
        cfg.get("themes", {}),
        cfg.get("concept_aliases", {}),
        cfg.get("related_themes", {}),
    )


THEMES_CONFIG, CONCEPT_ALIASES, RELATED_THEMES_MAP = _load_config()
```

This is unchanged — theme-specific `min_coverage`/`min_concepts` are read from `THEMES_CONFIG` entries directly in the scoring function.

- [ ] **Step 3: Add eligibility filter function**

After the `_normalize_scores()` function (around line 226), add:

```python
def _is_eligible(stock_data, anchor_codes, concept_weights, theme_cfg):
    coverage_pct = stock_data.get("coverage_pct", 0)
    matched = stock_data.get("matched_concepts", 0)
    code = stock_data["code"]

    min_cov = theme_cfg.get("min_coverage", LIBRARY_CONFIG["default_min_coverage"])
    min_con = theme_cfg.get("min_concepts", LIBRARY_CONFIG["default_min_concepts"])

    if coverage_pct >= min_cov or matched >= min_con:
        return True

    if code in anchor_codes:
        return True

    concept_ranks = stock_data.get("concept_ranks", {})
    for cn, rank in concept_ranks.items():
        cw = concept_weights.get(cn, 0.5)
        if cw >= 0.8 and rank == 1:
            return True

    return False
```

- [ ] **Step 4: Replace `_compute_theme_leaders()` with V4 scoring pipeline**

Replace the entire `_compute_theme_leaders()` function (lines 284-423) with:

```python
def _compute_theme_scores(theme_name, theme_cfg, child_concepts, all_concept_stocks, concept_info):
    """Compute V4 multi-dimensional ranking: purity, leader, candidate.

    Returns (pure_stocks, leader_stocks, candidate_stocks, concept_weights, qualified_count)
    """
    scoring = LIBRARY_CONFIG["scoring"]

    all_stock_counts = [
        concept_info.get(cn, {}).get("stock_count", 50)
        for cn in child_concepts
        if cn in concept_info
    ]
    concept_weights = _get_concept_weights(theme_name, theme_cfg, child_concepts, concept_info, all_stock_counts)

    total_theme_weight = sum(concept_weights.get(cn, 0.5) for cn in child_concepts)

    anchor_codes = set(theme_cfg.get("anchors", []))

    stock_data = {}

    for cn in child_concepts:
        if cn not in all_concept_stocks:
            continue
        cw = concept_weights.get(cn, 0.5)
        sorted_stocks = all_concept_stocks[cn]
        total = len(sorted_stocks)
        for rank_0, s in enumerate(sorted_stocks):
            rank = rank_0 + 1
            code = s["code"]
            if code not in stock_data:
                stock_data[code] = {
                    "code": code,
                    "name": s["name"],
                    "total_mv": _safe_float(s.get("total_mv", 0)),
                    "turnover": _safe_float(s.get("turnover", 0)),
                    "amount": _safe_float(s.get("amount", 0)),
                    "concept_ranks": {},
                    "weighted_coverage": 0.0,
                    "rank_weighted_sum": 0.0,
                    "matched_concepts": 0,
                }
            stock_data[code]["concept_ranks"][cn] = rank
            stock_data[code]["weighted_coverage"] += cw
            stock_data[code]["rank_weighted_sum"] += cw * _rank_factor(rank)
            stock_data[code]["matched_concepts"] += 1

    if not stock_data or total_theme_weight <= 0:
        return [], [], [], concept_weights, 0

    for code, sd in stock_data.items():
        sd["coverage_pct"] = (sd["weighted_coverage"] / total_theme_weight) * 100

    raw_rank_scores = [sd["rank_weighted_sum"] for sd in stock_data.values()]
    max_rank_ws = max(raw_rank_scores) if raw_rank_scores else 1
    for sd in stock_data.values():
        sd["rank_score"] = (sd["rank_weighted_sum"] / max_rank_ws) * 100 if max_rank_ws > 0 else 0

    liq_vals = [sd["amount"] for sd in stock_data.values()]
    mcap_vals = [sd["total_mv"] for sd in stock_data.values()]

    liquidity_scores = _normalize_log_scores(liq_vals)
    mcap_scores = _normalize_log_scores(mcap_vals)

    for i, (code, sd) in enumerate(stock_data.items()):
        sd["liquidity_score"] = round(liquidity_scores[i], 1)
        sd["market_cap_score"] = round(mcap_scores[i], 1)

    for sd in stock_data.values():
        sd["purity_score"] = round(
            sd["coverage_pct"] * scoring["purity_coverage_weight"]
            + sd["rank_score"] * scoring["purity_rank_weight"],
            1
        )

    eligible_data = {}
    for code, sd in stock_data.items():
        if _is_eligible(sd, anchor_codes, concept_weights, theme_cfg):
            eligible_data[code] = sd

    qualified_count = len(eligible_data)

    for sd in eligible_data.values():
        sd["leader_score"] = round(
            sd["purity_score"] * scoring["leader_purity_weight"]
            + sd["liquidity_score"] * scoring["leader_liquidity_weight"]
            + sd["market_cap_score"] * scoring["leader_market_cap_weight"],
            1
        )

    momentum_weight = scoring.get("candidate_momentum_weight", 0.20)
    for sd in eligible_data.values():
        sd["candidate_score"] = round(
            sd["purity_score"] * scoring["candidate_purity_weight"]
            + sd["liquidity_score"] * scoring["candidate_liquidity_weight"]
            + sd["market_cap_score"] * scoring["candidate_market_cap_weight"]
            + 0 * momentum_weight,
            1
        )

    all_sorted = sorted(stock_data.values(), key=lambda x: x.get("purity_score", 0), reverse=True)
    pure_list = [
        {"code": s["code"], "name": s["name"], "purity_score": s["purity_score"]}
        for s in all_sorted
        if s["code"] in eligible_data and s["purity_score"] >= LIBRARY_CONFIG["pure_threshold"]
    ][:LIBRARY_CONFIG["pure_limit"]]

    leader_sorted = sorted(eligible_data.values(), key=lambda x: x["leader_score"], reverse=True)
    leader_list = [
        {
            "code": s["code"], "name": s["name"],
            "leader_score": s["leader_score"],
            "purity_score": s["purity_score"],
            "liquidity_score": s["liquidity_score"],
            "market_cap_score": s["market_cap_score"],
            "anchor": s["code"] in anchor_codes,
        }
        for s in leader_sorted
        if s["leader_score"] >= LIBRARY_CONFIG["leader_threshold"]
    ][:LIBRARY_CONFIG["leader_limit"]]

    candidate_sorted = sorted(eligible_data.values(), key=lambda x: x["candidate_score"], reverse=True)
    candidate_list = [
        {
            "code": s["code"], "name": s["name"],
            "candidate_score": s["candidate_score"],
            "purity_score": s["purity_score"],
            "liquidity_score": s["liquidity_score"],
            "market_cap_score": s["market_cap_score"],
        }
        for s in candidate_sorted
        if s["candidate_score"] >= LIBRARY_CONFIG["candidate_threshold"]
    ][:LIBRARY_CONFIG["candidate_limit"]]

    return pure_list, leader_list, candidate_list, concept_weights, qualified_count
```

Also add the `_normalize_log_scores` helper after `_normalize_scores`:

```python
def _normalize_log_scores(values, floor=0):
    if not values:
        return []
    positive = [v for v in values if v > 0]
    if not positive:
        return [0.0] * len(values)
    log_min = math.log(max(min(positive), 1))
    log_max = math.log(max(max(positive), 2))
    if log_max <= log_min:
        return [50.0] * len(values)
    result = []
    for v in values:
        if v > 0:
            result.append(((math.log(max(v, 1)) - log_min) / (log_max - log_min)) * 100)
        else:
            result.append(float(floor))
    return result
```

- [ ] **Step 5: Update `build_themes()` to use new scoring function**

In `build_themes()` (around line 457), change the call from `_compute_theme_leaders()` to `_compute_theme_scores()` and update the theme_data output.

Replace:
```python
        leaders, concept_weights = _compute_theme_leaders(
            theme_name, theme_cfg, child_concepts, all_concept_stocks, concept_info
        )
```

With:
```python
        pure_stocks, leader_stocks, candidate_stocks, concept_weights, qualified_count = _compute_theme_scores(
            theme_name, theme_cfg, child_concepts, all_concept_stocks, concept_info
        )
```

Replace the `theme_data` dict (around lines 471-487) with:

```python
        theme_data = {
            "name": theme_name,
            "concepts": child_concepts,
            "concept_weights": weighted_concepts,
            "aliases": theme_aliases,
            "keywords": keywords,
            "anchors": list(anchor_codes),
            "stock_count": len(stock_codes),
            "qualified_stock_count": qualified_count,
            "pure_stocks": pure_stocks,
            "leader_stocks": leader_stocks,
            "candidate_stocks": candidate_stocks,
            "stocks": stock_codes,
            "last_update": time.strftime('%Y-%m-%d'),
        }
```

And update `theme_info` dict (around line 493):

```python
        theme_info[theme_name] = {
            "concepts": child_concepts,
            "concept_weights": concept_weights,
            "aliases": theme_aliases,
            "keywords": keywords,
            "stock_count": len(stock_codes),
            "qualified_stock_count": qualified_count,
            "stocks": stock_codes,
            "pure_stocks": pure_stocks,
            "leader_stocks": leader_stocks,
            "candidate_stocks": candidate_stocks,
            "file": f"{safe_name}.json",
        }
```

- [ ] **Step 6: Update `build_stocks()` for V4 output**

In `build_stocks()` (around lines 507-622), replace the `leader_scores` dict construction (lines 544-559) with:

```python
    theme_scores = {}
    for theme_name, info in theme_info.items():
        for entry in info.get("leader_stocks", []):
            code = entry["code"]
            if code not in theme_scores:
                theme_scores[code] = {}
            theme_scores[code][theme_name] = {
                "leader_score": entry.get("leader_score"),
                "purity_score": None,
                "candidate_score": None,
                "liquidity_score": entry.get("liquidity_score"),
                "market_cap_score": entry.get("market_cap_score"),
                "anchor": entry.get("anchor", False),
            }
        for entry in info.get("pure_stocks", []):
            code = entry["code"]
            if code in theme_scores and theme_name in theme_scores[code]:
                theme_scores[code][theme_name]["purity_score"] = entry.get("purity_score")
            elif code not in theme_scores:
                theme_scores[code] = {}
                theme_scores[code][theme_name] = {
                    "leader_score": None,
                    "purity_score": entry.get("purity_score"),
                    "candidate_score": None,
                    "liquidity_score": None,
                    "market_cap_score": None,
                    "anchor": False,
                }
            else:
                theme_scores[code][theme_name] = {
                    "leader_score": None,
                    "purity_score": entry.get("purity_score"),
                    "candidate_score": None,
                    "liquidity_score": None,
                    "market_cap_score": None,
                    "anchor": False,
                }
        for entry in info.get("candidate_stocks", []):
            code = entry["code"]
            if code in theme_scores and theme_name in theme_scores[code]:
                theme_scores[code][theme_name]["candidate_score"] = entry.get("candidate_score")
                if theme_scores[code][theme_name].get("purity_score") is None:
                    theme_scores[code][theme_name]["purity_score"] = entry.get("purity_score")
                if theme_scores[code][theme_name].get("liquidity_score") is None:
                    theme_scores[code][theme_name]["liquidity_score"] = entry.get("liquidity_score")
                if theme_scores[code][theme_name].get("market_cap_score") is None:
                    theme_scores[code][theme_name]["market_cap_score"] = entry.get("market_cap_score")
            elif code not in theme_scores:
                theme_scores[code] = {}
                theme_scores[code][theme_name] = {
                    "leader_score": None,
                    "purity_score": entry.get("purity_score"),
                    "candidate_score": entry.get("candidate_score"),
                    "liquidity_score": entry.get("liquidity_score"),
                    "market_cap_score": entry.get("market_cap_score"),
                    "anchor": False,
                }
            else:
                theme_scores[code][theme_name] = {
                    "leader_score": None,
                    "purity_score": entry.get("purity_score"),
                    "candidate_score": entry.get("candidate_score"),
                    "liquidity_score": entry.get("liquidity_score"),
                    "market_cap_score": entry.get("market_cap_score"),
                    "anchor": False,
                }
```

Then in the stock theme entry construction (around line 584), replace:

```python
        theme_entries = []
        for t in themes_sorted:
            entry = {"name": t["name"], "weight": t["weight"]}
            scores = leader_scores.get(stock_code, {}).get(t["name"])
            if scores:
                entry["score"] = scores["score"]
                entry["coverage_score"] = scores["coverage_score"]
                entry["rank_score"] = scores["rank_score"]
                entry["liquidity_score"] = scores["liquidity_score"]
                entry["market_cap_score"] = scores["market_cap_score"]
                entry["matched_concepts"] = scores["matched_concepts"]
                entry["anchor"] = scores["anchor"]
            theme_entries.append(entry)
```

With:

```python
        theme_entries = []
        for t in themes_sorted:
            entry = {"name": t["name"], "weight": t["weight"]}
            scores = theme_scores.get(stock_code, {}).get(t["name"])
            if scores:
                if scores.get("purity_score") is not None:
                    entry["purity_score"] = scores["purity_score"]
                if scores.get("leader_score") is not None:
                    entry["leader_score"] = scores["leader_score"]
                if scores.get("candidate_score") is not None:
                    entry["candidate_score"] = scores["candidate_score"]
                if scores.get("liquidity_score") is not None:
                    entry["liquidity_score"] = scores["liquidity_score"]
                if scores.get("market_cap_score") is not None:
                    entry["market_cap_score"] = scores["market_cap_score"]
                entry["anchor"] = scores.get("anchor", False)
            theme_entries.append(entry)
```

Then sort themes by purity_score descending (instead of weight) and remove `core_theme`:

Replace:
```python
        market = "SH" if stock_code.startswith("sh") else "SZ" if stock_code.startswith("sz") else "BJ"

        core_theme = themes_sorted[0]["name"] if themes_sorted else ""
        core_concept = concepts_sorted[0]["name"] if concepts_sorted else ""
```

With:
```python
        market = "SH" if stock_code.startswith("sh") else "SZ" if stock_code.startswith("sz") else "BJ"

        core_concept = concepts_sorted[0]["name"] if concepts_sorted else ""
```

And update the `stock_data` dict (removing `core_theme`, sorting themes by purity_score):

```python
        stock_data = {
            "code": stock_code,
            "name": stock_name,
            "market": market,
            "themes": theme_entries,
            "concepts": [{"name": c["name"], "weight": c["weight"]} for c in concepts_sorted],
            "core_concept": core_concept,
            "theme_count": len(themes_sorted),
            "concept_count": len(concepts_sorted),
            "last_update": time.strftime('%Y-%m-%d'),
        }
```

Also update `stock_files` dict (around line 612):

```python
        stock_files[stock_code] = {
            "name": stock_name,
            "core_concept": core_concept,
            "theme_count": len(themes_sorted),
            "concept_count": len(concepts_sorted),
            "themes": themes_sorted,
            "concepts": concepts_sorted,
        }
```

- [ ] **Step 7: Remove `core_stocks` from concept output**

In `build_concepts()` (around line 250-256), remove `core_stocks` from `concept_data`:

```python
        concept_data = {
            "id": concept_code,
            "name": name,
            "source": {
                "provider": "eastmoney",
                "concept_code": concept_code,
            },
            "aliases": aliases,
            "stock_count": stock_count,
            "stocks": stock_codes,
            "last_update": time.strftime('%Y-%m-%d'),
        }
```

And remove `core_stocks` from `concept_info`:

```python
        concept_info[name] = {
            "code": concept_code,
            "file": f"{safe_name}.json",
            "stock_count": stock_count,
            "stocks": stock_codes,
            "aliases": aliases,
        }
```

- [ ] **Step 8: Update `build_update_log()` version marker**

Change `"leader_ranking_version": "v3"` to `"leader_ranking_version": "v4"`.

- [ ] **Step 9: Verify the script runs without errors**

Run: `python .opencode/skills/theme-library/scripts/build_library.py`

Expected: Script executes, builds theme/stock/concept/index files. Check output for errors.

- [ ] **Step 10: Commit**

```bash
git add .opencode/skills/theme-library/scripts/build_library.py
git commit -m "feat(theme-library): implement V4 multi-dimensional scoring pipeline

- Replace single leader score with purity_score, leader_score, candidate_score
- Add eligibility filter with configurable thresholds per theme
- Add theme_library_config.json for scoring weights and limits
- Remove core_stocks from concepts, core_theme from stocks
- Add qualified_stock_count to theme files
- Coverage_score no longer double-normalized
- Anchor is boolean label, not score factor
"
```

---

### Task 4: Update query_theme.py for V4 subcommands

**Files:**
- Modify: `.opencode/skills/theme-library/scripts/query_theme.py`

- [ ] **Step 1: Add `leaders`, `pure`, `candidates` subcommands**

After the existing `stats_p` subcommand (around line 326), add:

```python
    leaders_p = subparsers.add_parser("leaders", help="Top leader stocks for a theme")
    leaders_p.add_argument("name", help="Theme name")
    leaders_p.add_argument("--top", type=int, default=0, help="Limit results")
    leaders_p.add_argument("--json", action="store_true")

    pure_p = subparsers.add_parser("pure", help="Top pure stocks for a theme")
    pure_p.add_argument("name", help="Theme name")
    pure_p.add_argument("--top", type=int, default=0, help="Limit results")
    pure_p.add_argument("--json", action="store_true")

    candidates_p = subparsers.add_parser("candidates", help="Top candidate stocks for a theme")
    candidates_p.add_argument("name", help="Theme name")
    candidates_p.add_argument("--top", type=int, default=0, help="Limit results")
    candidates_p.add_argument("--json", action="store_true")
```

- [ ] **Step 2: Add display function for leader/pure/candidate lists**

Add these display functions after the existing `_print_theme()` function:

```python
def _print_leaders(data):
    theme_name = data.get("name", "-")
    leaders = data.get("leader_stocks", []) or []
    qualified = data.get("qualified_stock_count", "?")
    total = data.get("stock_count", "?")
    anchors = data.get("anchors", []) or []

    print(f"Theme: {theme_name}")
    print(f"Qualified: {qualified}/{total} stocks")
    if anchors:
        print(f"Anchors: {', '.join(anchors)}")

    if not leaders:
        print("No leader stocks above threshold.")
        return

    print(f"\nLeader Stocks (Top {len(leaders)}):")
    print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Leader':>7} {'Purity':>7} {'Liq':>5} {'MCap':>5} {'Anc':>3}")
    print(f"  {'--':>2}  {'----':<10} {'----':<12} {'------':>7} {'-------':>7} {'---':>5} {'----':>5} {'---':>3}")
    for i, l in enumerate(leaders, 1):
        anchor_mark = " *" if l.get("anchor") else ""
        print(f"  {i:>2}  {l.get('code',''):<10} {l.get('name',''):<12} {l.get('leader_score',0):>7.1f} {l.get('purity_score',0):>7.1f} {l.get('liquidity_score',0):>5.1f} {l.get('market_cap_score',0):>5.1f}{anchor_mark}")


def _print_pure(data):
    theme_name = data.get("name", "-")
    pure = data.get("pure_stocks", []) or []
    qualified = data.get("qualified_stock_count", "?")
    total = data.get("stock_count", "?")

    print(f"Theme: {theme_name}")
    print(f"Qualified: {qualified}/{total} stocks")

    if not pure:
        print("No pure stocks above threshold.")
        return

    print(f"\nPure Stocks (Top {len(pure)}):")
    print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Purity':>7}")
    print(f"  {'--':>2}  {'----':<10} {'----':<12} {'-------':>7}")
    for i, p in enumerate(pure, 1):
        print(f"  {i:>2}  {p.get('code',''):<10} {p.get('name',''):<12} {p.get('purity_score',0):>7.1f}")


def _print_candidates(data):
    theme_name = data.get("name", "-")
    candidates = data.get("candidate_stocks", []) or []
    qualified = data.get("qualified_stock_count", "?")
    total = data.get("stock_count", "?")

    print(f"Theme: {theme_name}")
    print(f"Qualified: {qualified}/{total} stocks")

    if not candidates:
        print("No candidate stocks above threshold.")
        return

    print(f"\nCandidate Stocks (Top {len(candidates)}):")
    print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Cand':>7} {'Purity':>7} {'Liq':>5} {'MCap':>5}")
    print(f"  {'--':>2}  {'----':<10} {'----':<12} {'----':>7} {'-------':>7} {'---':>5} {'----':>5}")
    for i, c in enumerate(candidates, 1):
        print(f"  {i:>2}  {c.get('code',''):<10} {c.get('name',''):<12} {c.get('candidate_score',0):>7.1f} {c.get('purity_score',0):>7.1f} {c.get('liquidity_score',0):>5.1f} {c.get('market_cap_score',0):>5.1f}")
```

- [ ] **Step 3: Update `_print_theme()` for V4 output**

Replace the leader display section in `_print_theme()` (around lines 221-231):

```python
    leaders = data.get('leaders', []) or []
    if leaders:
        has_anchor = any(l.get('anchor') for l in leaders)
        anchor_hdr = " Anc" if has_anchor else ""
        print(f"\nLeaders v3 (Top {len(leaders)}):")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Score':>6} {'Cov':>5} {'Rank':>5} {'Liq':>5} {'MCap':>5} {'MCpts':>5}{anchor_hdr}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'-----':>6} {'---':>5} {'----':>5} {'---':>5} {'----':>5} {'-----':>5}{'-' * len(anchor_hdr)}")
        for i, l in enumerate(leaders, 1):
            anchor_mark = " *" if l.get('anchor') else ""
            print(f"  {i:>2}  {l.get('code',''):<10} {l.get('name',''):<12} {l.get('score',0):>6.1f} {l.get('coverage_score',0):>5.1f} {l.get('rank_score',0):>5.1f} {l.get('liquidity_score',0):>5.1f} {l.get('market_cap_score',0):>5.1f} {l.get('matched_concepts',0):>5}{anchor_mark}")
```

With:

```python
    anchors = data.get('anchors', []) or []
    qualified = data.get('qualified_stock_count', '?')
    total_stocks = data.get('stock_count', '?')
    print(f"\nQualified: {qualified}/{total_stocks} stocks")
    if anchors:
        print(f"Anchors: {', '.join(anchors)}")

    pure = data.get('pure_stocks', []) or []
    if pure:
        print(f"\nPure Stocks (Top {len(pure)}):")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Purity':>7}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'-------':>7}")
        for i, p in enumerate(pure[:10], 1):
            print(f"  {i:>2}  {p.get('code',''):<10} {p.get('name',''):<12} {p.get('purity_score',0):>7.1f}")
        if len(pure) > 10:
            print(f"  ... and {len(pure) - 10} more")

    leaders = data.get('leader_stocks', []) or []
    if leaders:
        print(f"\nLeader Stocks (Top {len(leaders)}):")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Leader':>7} {'Purity':>7} {'Liq':>5} {'MCap':>5} {'Anc':>3}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'------':>7} {'-------':>7} {'---':>5} {'----':>5} {'---':>3}")
        for i, l in enumerate(leaders, 1):
            anchor_mark = " *" if l.get('anchor') else ""
            print(f"  {i:>2}  {l.get('code',''):<10} {l.get('name',''):<12} {l.get('leader_score',0):>7.1f} {l.get('purity_score',0):>7.1f} {l.get('liquidity_score',0):>5.1f} {l.get('market_cap_score',0):>5.1f}{anchor_mark}")

    candidates = data.get('candidate_stocks', []) or []
    if candidates:
        print(f"\nCandidate Stocks (Top {len(candidates)}):")
        print(f"  {'#':>2}  {'Code':<10} {'Name':<12} {'Cand':>7} {'Purity':>7} {'Liq':>5} {'MCap':>5}")
        print(f"  {'--':>2}  {'----':<10} {'----':<12} {'----':>7} {'-------':>7} {'---':>5} {'----':>5}")
        for i, c in enumerate(candidates, 1):
            print(f"  {i:>2}  {c.get('code',''):<10} {c.get('name',''):<12} {c.get('candidate_score',0):>7.1f} {c.get('purity_score',0):>7.1f} {c.get('liquidity_score',0):>5.1f} {c.get('market_cap_score',0):>5.1f}")
```

- [ ] **Step 4: Update `_print_stock()` for V4 scores**

Replace the theme display section in `_print_stock()` (around lines 274-286):

```python
    themes = data.get('themes', []) or []
    if themes:
        print("\nThemes:")
        for t in themes:
            name = t.get('name', '') if isinstance(t, dict) else str(t)
            weight = t.get('weight', 0) if isinstance(t, dict) else 0
            score = t.get('score') if isinstance(t, dict) else None
            cov = t.get('coverage_score') if isinstance(t, dict) else None
            rank = t.get('rank_score') if isinstance(t, dict) else None
            liq = t.get('liquidity_score') if isinstance(t, dict) else None
            anchor = t.get('anchor') if isinstance(t, dict) else None
            bar = "█" * max(1, int(weight))
            score_str = f"score:{score:.1f}" if score is not None else ""
            cov_str = f"cov:{cov:.1f}" if cov is not None else ""
            anchor_str = " [ANCHOR]" if anchor else ""
            print(f"  {name:<20} weight:{weight:>5.1f} {bar} {score_str} {cov_str}{anchor_str}")
```

With:

```python
    themes = data.get('themes', []) or []
    if themes:
        print("\nThemes:")
        for t in themes:
            name = t.get('name', '') if isinstance(t, dict) else str(t)
            weight = t.get('weight', 0) if isinstance(t, dict) else 0
            purity = t.get('purity_score') if isinstance(t, dict) else None
            leader = t.get('leader_score') if isinstance(t, dict) else None
            candidate = t.get('candidate_score') if isinstance(t, dict) else None
            anchor = t.get('anchor') if isinstance(t, dict) else None
            anchor_str = " [ANCHOR]" if anchor else ""
            parts = [f"weight:{weight:.1f}"]
            if purity is not None:
                parts.append(f"pur:{purity:.1f}")
            if leader is not None:
                parts.append(f"ldr:{leader:.1f}")
            if candidate is not None:
                parts.append(f"cnd:{candidate:.1f}")
            parts_str = " ".join(parts)
            print(f"  {name:<20} {parts_str}{anchor_str}")
```

- [ ] **Step 5: Add command handlers for new subcommands**

In the `main()` function, after the `stats` handler (around line 386), add:

```python
    elif args.command == "leaders":
        data = query_theme(args.name)
        if data:
            leaders = data.get("leader_stocks", []) or []
            if args.top > 0:
                leaders = leaders[:args.top]
                data = dict(data)
                data["leader_stocks"] = leaders
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_leaders(data)

    elif args.command == "pure":
        data = query_theme(args.name)
        if data:
            pure = data.get("pure_stocks", []) or []
            if args.top > 0:
                pure = pure[:args.top]
                data = dict(data)
                data["pure_stocks"] = pure
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_pure(data)

    elif args.command == "candidates":
        data = query_theme(args.name)
        if data:
            candidates = data.get("candidate_stocks", []) or []
            if args.top > 0:
                candidates = candidates[:args.top]
                data = dict(data)
                data["candidate_stocks"] = candidates
            if args.json:
                print(json.dumps(data, ensure_ascii=False, indent=2))
            else:
                _print_candidates(data)
```

- [ ] **Step 6: Test the new subcommands**

Run: `python .opencode/skills/theme-library/scripts/query_theme.py leaders AI算力`

Expected: Shows leader stocks table with leader_score, purity_score, liquidity_score, market_cap_score, anchor.

Run: `python .opencode/skills/theme-library/scripts/query_theme.py pure AI算力`

Expected: Shows pure stocks table with purity_score.

Run: `python .opencode/skills/theme-library/scripts/query_theme.py candidates AI算力`

Expected: Shows candidate stocks table with candidate_score, purity_score, liquidity_score, market_cap_score.

- [ ] **Step 7: Test existing commands still work**

Run: `python .opencode/skills/theme-library/scripts/query_theme.py theme AI算力`

Expected: Shows theme with pure_stocks, leader_stocks, candidate_stocks sections.

Run: `python .opencode/skills/theme-library/scripts/query_theme.py stock sz000977`

Expected: Shows stock with purity_score, leader_score, candidate_score per theme, no core_theme.

- [ ] **Step 8: Commit**

```bash
git add .opencode/skills/theme-library/scripts/query_theme.py
git commit -m "feat(theme-library): add leaders/pure/candidates subcommands and V4 display"
```

---

### Task 5: Update SKILL.md documentation

**Files:**
- Modify: `.opencode/skills/theme-library/SKILL.md`

- [ ] **Step 1: Update SKILL.md with V4 scoring documentation**

Replace the "Theme Leader Ranking (v2)" section with V4 documentation covering:
- Three scores: purity_score, leader_score, candidate_score
- Formulas
- Eligibility filter
- Output structure changes
- New query commands

Key additions to SKILL.md:

```markdown
## Theme Ranking (v4)

Three-dimensional ranking replacing the single v3 score:

| Score | Formula | Purpose |
|-------|---------|---------|
| `purity_score` | `coverage * 0.60 + rank * 0.40` | Theme belonging strength |
| `leader_score` | `purity * 0.40 + liquidity * 0.35 + mcap * 0.25` | Market leaders |
| `candidate_score` | `purity * 0.30 + liquidity * 0.30 + mcap * 0.20 + momentum * 0.20` | Analysis watchlist |

### Eligibility Filter

Before ranking, stocks must pass: `coverage >= min_coverage OR matched_concepts >= min_concepts`
Exception: anchor stocks or rank #1 in core concept (weight >= 0.8).

### Query Commands

```bash
python query_theme.py leaders AI算力      # Top leader stocks
python query_theme.py pure AI算力          # Top pure stocks  
python query_theme.py candidates AI算力     # Top candidate stocks
```
```

- [ ] **Step 2: Commit**

```bash
git add .opencode/skills/theme-library/SKILL.md
git commit -m "docs(theme-library): update SKILL.md for V4 ranking system"
```

---

### Task 6: End-to-end verification

- [ ] **Step 1: Rebuild the entire library**

Run: `python .opencode/skills/theme-library/scripts/build_library.py --clean`

Expected: All files regenerated successfully with V4 structure.

- [ ] **Step 2: Verify theme file structure**

Run: `python -c "import json; d=json.load(open('.opencode/skills/theme-library/themes/AI算力.json','r',encoding='utf-8')); print('pure_stocks' in d, 'leader_stocks' in d, 'candidate_stocks' in d, 'qualified_stock_count' in d, 'anchors' in d, 'leaders' not in d)"`

Expected: `True True True True True True`

- [ ] **Step 3: Verify stock file structure**

Run: `python -c "import json; d=json.load(open('.opencode/skills/theme-library/stocks/sz000977.json','r',encoding='utf-8')); t=d['themes'][0]; print('purity_score' in t, 'leader_score' in t, 'candidate_score' in t, 'core_theme' not in d)"`

Expected: `True True True True`

- [ ] **Step 4: Verify query commands**

```bash
python .opencode/skills/theme-library/scripts/query_theme.py stats
python .opencode/skills/theme-library/scripts/query_theme.py leaders 半导体
python .opencode/skills/theme-library/scripts/query_theme.py pure 半导体 --top 10
python .opencode/skills/theme-library/scripts/query_theme.py candidates 半导体 --top 10 --json
```

Expected: All commands return valid data without errors.

- [ ] **Step 5: Final commit**

```bash
git add -A
git commit -m "chore(theme-library): V4 complete verification"
```