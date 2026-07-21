# Concept Sector (概念板块) API — Design Spec

**Date:** 2026-06-16
**Status:** Draft
**Skill:** `stock-analysis`

## Goal

Add a new interface to the `stock-analysis` skill that fetches concept sector (概念板块) data from East Money, supporting two use cases that map to the user's "Theme Library" project:

1. **Theme Library (主题库)** — list all concept sectors
2. **Theme-to-Stock Mapping (主题 → 股票池映射库)** — list stocks belonging to a specific concept

Out of scope: theme scoring model (主题评分模型) — that will pull additional data (money flow, price changes) from existing scripts (`fetch_money_flow.py`, `fetch_stock.py`) as a separate concern. This spec only provides the data foundation.

## Scope

| Item | Decision |
|------|----------|
| Sector type | 概念板块 (concept sectors) only — `m:90+t:3` |
| Output detail | Basic info only: `code`, `name`, `source` |
| Markets | A stocks (concept sectors are A-share only) |
| Cookie required | No (concept API is public, no auth needed) |

## API Endpoints (East Money)

> **Pagination note:** East Money's `push2.clist/get` API caps responses at ~100 items per page. Both endpoints below are called with `pn={page}&pz=100` and paginated automatically by the implementation to fetch the full result set. The spec shows the base URL; pagination is handled in code.

### 1. List concept sectors

```
GET https://push2.eastmoney.com/api/qt/clist/get
    ?pn={page}
    &pz={page_size}
    &po=1
    &np=1
    &ut=fa5fd1943c747385f9554f5b7d918a9e
    &fltt=2
    &invt=2
    &fid=f3
    &fs=m:90+t:3
    &fields=f12,f14,f3
```

**Fields:**
- `f12` — concept code (e.g., `BK0486`)
- `f14` — concept name (e.g., `元宇宙`)
- `f3` — change percent (used for sorting)

**Response:** JSONP-wrapped JSON, `data.diff[]` array of concept records. ~500+ concepts total, fetched across multiple pages (`pn=1,2,3,...` until `len(diff) < pz`).

### 2. List stocks in a concept

```
GET https://push2.eastmoney.com/api/qt/clist/get
    ?pn=1
    &pz=500
    &po=1
    &np=1
    &ut=fa5fd1943c747385f9554f5b7d918a9e
    &fltt=2
    &invt=2
    &fid=f3
    &fs=b:{concept_code}+f:!2
    &fields=f12,f14
```

**Example:** `fs=b:BK0486+f:!2` — concept BK0486 (元宇宙), excluding ST stocks.

**Fields:**
- `f12` — stock code (e.g., `600519`)
- `f14` — stock name (e.g., `贵州茅台`)

**Stock code prefix mapping:**
- `6xx xxx` → `sh` prefix
- `0xx xxx` or `3xx xxx` → `sz` prefix
- `4xx xxx` or `8xx xxx` → `bj` prefix

**Pagination:** Concept sectors with a large number of constituent stocks are also paginated internally with `pn={page}&pz=100` to fetch the complete stock list.

## Script Design

### New file: `scripts/fetch_concept.py`

Follows the pattern of `fetch_money_flow.py`: module-level singleton, table/JSON/CSV output modes, `-o FILE` for file output.

**CLI:**

```bash
# Default: list all concept sectors
python scripts/fetch_concept.py
python scripts/fetch_concept.py --json
python scripts/fetch_concept.py --csv -o concepts.csv
python scripts/fetch_concept.py --search "新"   # Filter by substring
python scripts/fetch_concept.py --top 20        # Top 20 by change%

# Get stocks in a concept
python scripts/fetch_concept.py --code BK0486         # By East Money code
python scripts/fetch_concept.py --name "元宇宙"        # By Chinese name
python scripts/fetch_concept.py --code BK0486 --json
```

**Argument conflicts:** `--code` and `--name` are mutually exclusive. `--search` and `--name` are mutually exclusive.

**Output fields:**

| Mode | Fields |
|------|--------|
| Concept list (default) | `code`, `name`, `source` |
| Concept stocks (`--code`/`--name`) | `code`, `name`, `source` |

(Per user requirement: basic info only. Money flow / price data not included.)

## Data Source Changes

### File: `scripts/datasources/eastmoney.py`

Add two methods to `EastMoneyDataSource`:

```python
def fetch_concept_list(self, sort_desc: bool = True) -> list:
    """Fetch all concept sectors (概念板块). Returns basic info: code, name, source."""

def fetch_concept_stocks(self, concept_code: str) -> list:
    """Fetch stocks in a specific concept sector. Returns code, name, source."""
```

Reuse existing `_get_push2_headers()` and rate-limiting infrastructure. No cookie required.

### File: `scripts/datasources/__init__.py`

No changes — `EastMoneyDataSource` is already exported.

## Documentation Updates

### File: `SKILL.md`

Add new section "Concept Sectors (概念板块)" after the "Money Flow" section, with:
- Usage examples (list / search / by code / by name)
- Output fields
- Brief API source note (East Money, no auth)

Update the "Scripts" table to include `fetch_concept.py`.

### File: `AGENTS.md`

Add command examples for concept sector API, matching the style of existing entries.

## Error Handling

- Network failure → empty list, same pattern as existing scripts
- Invalid `--code` (e.g., `BK99999` doesn't exist) → empty list, print "No stocks found for concept: {code}"
- `--name` not found → empty list, print "Concept not found: {name}"
- JSONP parse failure → empty list, log nothing (existing pattern)

## Testing

Manual verification (no automated tests in this skill):
1. `python scripts/fetch_concept.py` returns ~500+ concepts
2. `python scripts/fetch_concept.py --code BK0486 --json` returns stocks with `sh`/`sz`/`bj` prefixes
3. `python scripts/fetch_concept.py --name "元宇宙"` finds and returns same stocks as `--code BK0486`
4. `python scripts/fetch_concept.py --search "新" --top 10` filters and limits

## Out of Scope

- 行业板块 (industry sectors) — not requested
- **主题评分模型 (Theme Scoring Model)** — handled by a separate system. This spec only provides the data foundation (theme list + theme-to-stock mapping); scoring logic lives elsewhere.
- Real-time concept price/change% — user wants basic info only. If the separate scoring system needs this, it should pull from existing scripts (`fetch_money_flow.py`, `fetch_stock.py`).
- Caching of concept list — not needed, API is fast enough
