# Theme Library V4: Multi-Dimensional Ranking System

**Version**: 4.0
**Date**: 2026-06-17
**Status**: Approved

## Problem

V3 uses a single `score` combining coverage, rank, liquidity, and market cap. One score cannot accurately represent theme belonging, market leadership, and trading candidacy simultaneously.

Example: In AI算力, 英维克 is the purest liquid-cooling stock but isn't a market leader. 浪潮信息 is a market leader but has low purity. A single score conflates these different concepts.

## V4 Model

Three separate scores, each serving a distinct purpose:

| Score | Purpose | Used By |
|-------|---------|---------|
| `purity_score` | Theme belonging strength | Theme analysis, stock mapping, news matching |
| `leader_score` | Market-recognized leaders | Leader identification, strategy reference |
| `candidate_score` | Analysis watchlist | stock-analysis, daily-market-analysis |

## Score Formulas

All formulas use **weighted addition**. Intermediate scores are normalized to 0-100 before combining, except `coverage_score` which is inherently 0-100.

### purity_score

```
purity_score = coverage_score * 0.60 + rank_score * 0.40
```

Where:
- `coverage_score` = `matched_concept_weight / total_theme_weight * 100` — already 0-100 range, **not re-normalized**
- `rank_score` = `rank_weighted_sum / max_rank_weighted_sum * 100` (same as V3 concept rank score, normalized)

### leader_score

```
leader_score = purity_score * 0.40 + liquidity_score * 0.35 + market_cap_score * 0.25
```

Where:
- `liquidity_score` = normalized log(amount) (same as V3)
- `market_cap_score` = normalized log(total_mv) (same as V3)
- Anchor is a **boolean label**, NOT a score factor. It marks market-recognized leaders for display only.

### candidate_score

```
candidate_score = purity_score * 0.30 + liquidity_score * 0.30 + market_cap_score * 0.20 + momentum_score * 0.20
```

Where:
- `momentum_score` = placeholder for V5 (currently normalized to 0 for all stocks). When V5 adds real momentum data, this slot is filled without changing the formula structure.
- **No circular dependency**: candidate_score does NOT reference leader_score.

## Anchor Stocks

Defined in `theme_config.json` per theme. Anchor stocks represent market consensus leaders.

Anchor is a **boolean label** (`true`/`false`) carried through to output. It does NOT affect any score calculation. Its purpose is informational: marking which stocks the market recognizes as leaders.

### Example (AI算力 anchors)

```json
"anchors": ["sz000977", "sh603019", "sz000063", "sz000938"]
```

## Eligibility Filter

Applied before ranking to define the qualified stock pool.

### Rule

```python
eligible = (
    coverage_score >= min_coverage
    OR matched_concepts >= min_concepts
)
```

### Exceptions

Stock is always eligible if ANY:
1. `anchor == True`
2. `concept_weight >= 0.8 AND rank == 1` (rank #1 in a core concept)

### Theme-Specific Thresholds

Stored in `theme_config.json` per theme:

| Theme Type | `min_coverage` | `min_concepts` |
|------------|---------------|----------------|
| Default | 15 | 2 |
| Broad (AI算力, 半导体, etc.) | 20 | 2 |
| Narrow (脑机接口, 量子科技, etc.) | 10 | 2 |

If not specified, defaults to `min_coverage=15, min_concepts=2`.

### qualified_stock_count

Each theme file records how many stocks passed the filter vs total:

```json
{
  "stock_count": 403,
  "qualified_stock_count": 87
}
```

This provides immediate visibility into filter strictness when tuning thresholds.

## List Thresholds and Limits

Each output list uses a **score threshold first, count limit second** approach:

| List | Score Threshold | Max Count |
|------|----------------|-----------|
| `pure_stocks` | purity_score >= 30 | 50 |
| `leader_stocks` | leader_score >= 50 | 20 |
| `candidate_stocks` | candidate_score >= 60 | 30 |

Configuration stored in `theme_library_config.json`.

## Computation Order

```
1. Load concept stock data and theme config
2. Compute concept weights (same as V3)
3. For each stock, compute raw values:
   - weighted_coverage, rank_weighted_sum, amount, total_mv, matched_concepts
4. Compute coverage_score directly (0-100, no re-normalization)
5. Normalize rank, liquidity, market_cap to 0-100
6. Compute purity_score for each stock
7. Apply eligibility filter
8. Compute leader_score for eligible stocks (anchor as boolean label only)
9. Compute candidate_score for eligible stocks (momentum_score = 0 for now)
10. Sort by each score, apply thresholds and limits
11. Record qualified_stock_count
12. Output pure_stocks, leader_stocks, candidate_stocks lists
```

## Output Structures

### Theme File (`themes/AI算力.json`)

```json
{
  "name": "AI算力",
  "concepts": ["算力概念", "东数西算", "液冷概念", "数据中心", "国资云概念", "边缘计算", "高带宽内存"],
  "concept_weights": [
    {"name": "算力概念", "weight": 1.0},
    {"name": "东数西算", "weight": 0.9}
  ],
  "aliases": ["AI算力", "算力", "AI基础设施"],
  "keywords": ["AI算力", "算力", "AI基础设施"],
  "anchors": ["sz000977", "sh603019", "sz000063", "sz000938"],
  "stock_count": 403,
  "qualified_stock_count": 87,
  "pure_stocks": [
    {"code": "sz000977", "name": "浪潮信息", "purity_score": 92.1}
  ],
  "leader_stocks": [
    {"code": "sz000977", "name": "浪潮信息", "leader_score": 95.6, "purity_score": 92.1, "liquidity_score": 85.0, "market_cap_score": 80.5, "anchor": true}
  ],
  "candidate_stocks": [
    {"code": "sz000977", "name": "浪潮信息", "candidate_score": 94.2, "purity_score": 92.1, "liquidity_score": 85.0, "market_cap_score": 80.5}
  ],
  "stocks": ["sz300502", "sz002371", "..."],
  "last_update": "2026-06-17"
}
```

### Stock File (`stocks/sz000977.json`)

```json
{
  "code": "sz000977",
  "name": "浪潮信息",
  "market": "SZ",
  "themes": [
    {
      "name": "AI算力",
      "weight": 6.3,
      "purity_score": 92.1,
      "leader_score": 95.6,
      "candidate_score": 94.2,
      "anchor": true
    }
  ],
  "concepts": [
    {"name": "国资云概念", "weight": 10},
    {"name": "东数西算", "weight": 7}
  ],
  "core_concept": "国资云概念",
  "theme_count": 3,
  "concept_count": 7,
  "last_update": "2026-06-17"
}
```

Note: `core_theme` removed. Themes are sorted by `purity_score` descending — the first theme is implicitly the "core" theme.

## Query API

### New Subcommands

```bash
python query_theme.py leaders AI算力     # Top 20 by leader_score
python query_theme.py pure AI算力         # Top 50 by purity_score
python query_theme.py candidates AI算力    # Top 30 by candidate_score
```

### Updated Display

- `theme` command shows all three list summaries
- `stock` command shows three scores per theme
- `stats` shows V4 version marker

## Configuration Files

### theme_config.json (per-theme additions)

```json
{
  "themes": {
    "AI算力": {
      "concepts": [...],
      "aliases": [...],
      "concept_weights_override": {...},
      "anchors": ["sz000977", "sh603019", "sz000063", "sz000938"],
      "min_coverage": 20,
      "min_concepts": 2
    }
  }
}
```

### theme_library_config.json (new file)

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

## Removed from V3

- `core_stocks` field in concept files
- `core_theme` field in stock files (replaced by purity_score sorting)
- Single `score` field in leaders
- Single `leaders` list (replaced by 3 lists)
- Hardcoded `LEADERS_TOP_N`, `PURITY_COVERAGE_THRESHOLD`, `PURITY_CONCEPT_MIN`
- Hardcoded weight constants
- `anchor_score` as a score factor (anchor is now a boolean label only)

## Files to Modify

| File | Change |
|------|--------|
| `scripts/build_library.py` | Replace v3 scoring with v4 pipeline. New output structures. Load config for thresholds/weights. |
| `scripts/theme_config.json` | Add `min_coverage`/`min_concepts` per theme with defaults. |
| `scripts/theme_library_config.json` | New file. Limits, thresholds, scoring weights. |
| `scripts/query_theme.py` | Add `leaders`, `pure`, `candidates` subcommands. Update display functions. |
| `SKILL.md` | Update docs for V4 scoring model and query commands. |

## V5 Future

Additional factors can be added without changing purity_score or the overall architecture:

- `momentum_score` — fills the 0.20 slot in candidate_score (currently zero for all stocks)
- `institution_score`
- `fund_flow_score`
- `news_score`
- `heat_score`

Leader_score and candidate_score formulas can evolve while purity_score remains stable.