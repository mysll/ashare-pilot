---
name: theme-library
description: >
  Build and query an offline theme/concept knowledge base from East Money concept boards.
  Hierarchical structure: Theme → Concept → Stock (1:N:N).
  ~60 investment themes group ~330 East Money concept boards, with ~166 non-investment
  concepts (index/style/trading-state) excluded from themes but still queryable.
  V5 multi-dimensional ranking: purity/industry/candidate scores with eligibility filtering.
  Market observation view for dynamic rankings.
  Triggers on "概念板块", "主题库", "theme", "concept board", "主题查询",
  "新闻映射主题", "哪些股票属于XX概念".
---

# Theme Library

Offline knowledge base with a 3-tier hierarchy: **Theme → Concept → Stock**.

- **Theme** (~60): High-level investment themes mapped from news, e.g. "AI算力"
- **Concept** (~490): East Money concept boards, e.g. "算力概念", "液冷概念"
- **Stock** (~5200): Individual stocks with weights in both themes and concepts

## Data Model

```
Theme: AI算力
  ├── Concept: 算力概念 (weight: 1.0, 100 stocks)
  ├── Concept: 东数西算 (weight: 0.9, 67 stocks)
  ├── Concept: 数据中心 (weight: 0.8, ...)
  ├── Concept: 液冷概念 (weight: 0.7, 100 stocks)
  ├── Concept: 国资云概念 (weight: 0.6, ...)
  ├── Concept: 边缘计算 (weight: 0.4, ...)
  └── Concept: 高带宽内存 (weight: 0.3, ...)
      → Merged 403 unique stocks for theme "AI算力"
```

Stock theme weight = max(concept_weight * rank_weight) across all member concepts.

## Theme Ranking (v5)

Three-dimensional ranking system with eligibility filtering:

| Score | Formula | Purpose |
|-------|---------|---------|
| `purity_score` | `coverage * 0.60 + rank * 0.40` | Theme belonging strength |
| `industry_score` | `purity * 0.40 + liquidity * 0.35 + market_cap * 0.25` | Theme representative (产业代表) |
| `candidate_score` | `purity * 0.30 + liquidity * 0.30 + market_cap * 0.20 + momentum * 0.20` | Analysis watchlist (momentum=0 for now) |

**Eligibility Filter:** Before ranking, stocks must pass `coverage >= min_coverage OR matched_concepts >= min_concepts`. Exceptions: anchor stocks, or rank #1 in core concept (weight >= 0.8).

| Output | Meaning |
|--------|---------|
| `purity_score` | How strongly a stock belongs to this theme (0-100) |
| `industry_score` | Industry representative strength (0-100) |
| `candidate_score` | Worth further analysis (0-100) |
| `anchor` | Boolean label: market consensus leader |
| `qualified_stock_count` | Stocks passing eligibility filter / total |

**Thresholds** (configured in `theme_library_config.json`):
- pure_stocks: purity >= 30, max 50
- industry_leaders: industry >= 50, max 20
- candidate_stocks: candidate >= 60, max 30

## Quick Start

### Build / Refresh Library

```bash
# Step 1: Fetch concept board list
python scripts/fetch_concepts.py

# Step 2: Fetch stocks for all concepts (slow, ~500 concepts)
python scripts/fetch_concept_stocks.py

# Step 3: Build concept, theme, stock files and indexes
python scripts/build_library.py
```

### Query

```bash
# Query theme (shows concepts + weights + industry leaders)
python scripts/query_theme.py theme AI算力

# Query concept (shows stocks + parent theme)
python scripts/query_theme.py concept 算力概念

# Query stock (shows themes + concepts with weights)
python scripts/query_theme.py stock sz000977

# Map keyword to theme
python scripts/query_theme.py keyword GPU

# Ranking commands
python scripts/query_theme.py leaders AI算力      # Top industry leaders by industry_score
python scripts/query_theme.py pure AI算力         # Top pure stocks by purity_score
python scripts/query_theme.py candidates AI算力    # Top candidate stocks by candidate_score

# Market observation view (dynamic, from concept cache)
python scripts/query_theme.py market AI算力        # Full market view (7 sections)
python scripts/query_theme.py market AI算力 --top 20

# List all themes
python scripts/query_theme.py list

# Library statistics
python scripts/query_theme.py stats
```

## Scripts

| Script | Purpose |
|--------|---------|
| `fetch_concepts.py` | Fetch concept board list from East Money |
| `fetch_concept_stocks.py` | Fetch stocks for each concept board (supports resume) |
| `build_library.py` | Build concepts/themes/stocks JSON files and indexes (v5 ranking) |
| `query_theme.py` | Query interface for themes, concepts, stocks, keywords |

## Query Commands

| Command | Input | Output |
|---------|-------|--------|
| `theme <name>` | Theme name or alias | Theme details with concepts + weights + industry leaders |
| `concept <name>` | Concept name | Concept details + parent theme |
| `stock <code>` | Stock code (e.g., sz000977) | Themes and concepts with weights |
| `keyword <word>` | Keyword | Mapped theme or concept |
| `leaders <name>` | Theme name | Top industry leaders by industry_score |
| `pure <name>` | Theme name | Top pure stocks by purity_score |
| `candidates <name>` | Theme name | Top candidate stocks by candidate_score |
| `market <name>` | Theme name | 7-section market observation: cross-rank, reps, gainers, turnover, volume, attention |
| `list` | --top N | Top N themes by stock count |
| `stats` | - | Library statistics |

All query commands support `--json` for structured output.

## Market View (`market` command)

Computed at query time from concept cache snapshots. No dynamic data is persisted to JSON files. ST stocks (ST/*ST prefix) are excluded from all sections.

7 output sections, in display order:

| # | Section | Source | Filter |
|---|---------|--------|--------|
| 1 | **热点交集** (Cross-Rank Highlights) | Stocks appearing in ≥2 top-N lists | Hit count descending |
| 2 | **主题代表股** (Theme Representatives) | `industry_leaders` from theme JSON | Top 20 by industry_score |
| 3 | **今日强势股** (Today's Strongest) | Cache `change_pct` | All theme stocks, descending |
| 4 | **成交额龙头** (Turnover Leaders) | Cache `amount` | Descending |
| 5 | **换手龙头** (Turnover Rate Leaders) | Cache `turnover` | Descending |
| 6 | **放量观察** (Volume Expansion) | Cache `volume_ratio` | Descending |
| 7 | **市场关注股** (Market Attention) | Composite score | Descending |

### 1. 热点交集 (Cross-Rank Highlights)

Simultaneously in ≥2 top-N lists. Columns: `涨幅`, `Atn` (attention_score), `Ind` (industry_score), `Hits`, `Tags`.

Stocks fall into three categories based on Atn + Ind:

| Category | Atn | Ind | Signal |
|----------|:---:|:---:|--------|
| **边缘扩散** | High | `--` or low | Capital-driven, no representative status |
| **中军启动** | High | Has value (≥50) | Established player receiving fresh capital |
| **主题主线** | Present | High | Core representative with active attention |

### 2. 主题代表股 (Theme Representatives)

Top `industry_leaders` by `industry_score`. Static ranking — these are the long-term theme representative stocks (老龙头).

### 3. 今日强势股 (Today's Strongest)

ALL theme stocks sorted by `change_pct` (no qualified filter). Includes `Ind` column so users can cross-reference representative score with price action.

### 4-6. 成交额/换手/量比

Single-dimension rankings. 放量观察 has a disclaimer: `量比仅作观察指标`.

### 7. 市场关注股 (Market Attention)

Composite ranking. Columns: `Atn`, `Ind`, `AmtRk`, `TrnRk`, `VRRk`.

Formula:
```
attention_score = 0.60 * amount_pctile + 0.25 * turnover_pctile + 0.15 * volume_ratio_pctile
```
All inputs are percentile ranks (排名百分位), not raw values.

`Ind` column: actual `industry_score` when computable (from `industry_leaders` or `candidate_stocks` component scores). `--` when the stock is not in any ranked pool.

### Design Notes

- **Static vs Dynamic**: `industry_score` lives in JSON, `attention_score` computed at query time
- **Data freshness**: Depends on `fetch_concept_stocks.py` last run time — shown as `Data Time` in output
- **No auto-refresh**: `market` command reads cache only, never triggers API calls
- **ST exclusion**: Applied at cache snapshot load time

## Directory Structure

```
theme-library/
├── themes/          # One JSON per Theme (high-level, ~60 files)
├── concepts/        # One JSON per East Money Concept (~490 files)
├── stocks/          # One JSON per stock (~5200 files)
├── aliases/         # Theme alias mapping (theme_aliases.json)
├── metadata/        # concept_list.json, update_log.json
├── index/           # Fast lookup indexes (JSON)
│   ├── theme_to_concept.json
│   ├── theme_to_stock.json
│   ├── concept_to_stock.json
│   ├── stock_to_theme.json
│   ├── stock_to_concept.json
│   └── keyword_to_theme.json
├── cache/           # Raw East Money data
│   ├── concepts.json
│   └── stocks/      # One JSON per concept (BK0917.json)
└── scripts/         # Data fetching and query scripts
```

## Theme Configuration

Themes are defined in `scripts/theme_config.json`:

- **`themes`**: Theme name → {concepts, aliases, concept_weights_override, anchors} mapping (~60 themes)
- **`concept_aliases`**: Concept-level aliases (for keyword matching)
- **`concept_weights_override`**: Manual concept weight overrides (auto-generated if not specified)
- **`anchors`**: Known theme representative stock codes (used as eligibility exceptions and anchor labels)
- Concepts not mapped to any theme remain queryable via `concept` command

## Integration

Theme Library provides data for:
- **daily-market-analysis**: Maps news to themes to stock pools
- **financial-news-mapper**: Resolves news keywords to themes/concepts
- **trading-strategist**: Identifies theme-level stock relationships

## Stock Weight System (Concept Rank)

| Weight | Meaning |
|--------|---------|
| 10 | 绝对龙头 (absolute leader) |
| 8-9 | 核心受益 (core beneficiary) |
| 5-7 | 重要成分 (important component) |
| 1-4 | 边缘概念 (peripheral) |

Stock theme weight = max(concept_weight × rank_weight) across all member concepts.

## Notes

- Data source: East Money push2 API (concept boards)
- Library must be built before querying (run fetch + build)
- `fetch_concept_stocks.py` supports resume — interrupt and re-run to continue
  - `--retry-failed` to retry previously failed concepts
  - `--reset` to clear cache and start fresh
- Use `--top N` to limit concept boards during development
- Theme definitions are in `scripts/theme_config.json`
- ~166 non-investment concepts (index/style/trading-state) are excluded from themes but still queryable via `concept` command
- All data files use JSON format
- **V5 Design Principle**: Static data (theme membership, purity, industry_score) lives in JSON files. Dynamic data (price action, turnover, volume ratio) lives in cache and is read at query time via `market` command. The two are never mixed.
- **industry_score** is stored in `industry_leaders` (top 20). For stocks in `candidate_stocks`, it is computed on-the-fly from purity/liquidity/market_cap components. For others, shown as `--`.
- **ST filter**: Stocks with names starting with `ST` or `*ST` are excluded from market view (filtered at cache load time)
