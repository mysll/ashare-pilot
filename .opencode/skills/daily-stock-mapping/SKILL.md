---
name: daily-stock-mapping
description: Use when dispatched as Step 2 of daily-market-analysis pipeline. Consumes news.md, produces themes.md, theme_stocks.md, mapper.md with theme-heat and composite-scored stock pool
---

# Daily Stock Mapping

Loaded by financial-news-mapper subagent when dispatched for pipeline stock-data mapping.

## Stage I/O

| Stage | Input | Output |
|-------|-------|--------|
| Theme Extraction | news.md | themes.md |
| Stock Pool Build | themes.md | theme_stocks.md |
| Technical Enrichment | theme_stocks.md | theme_stocks.md (enriched in-place) |
| Structured Dataset Generation | theme_stocks.md (enriched) | mapper.md (6-section structured dataset: Market State, Theme Ranking, Candidate Pool, Strategy Inputs, Observation Pool, Excluded Stocks) |

## Scope

A-shares only (sh/sz prefix). Ignore HK/US and other markets.

**Core Rule:** Theme Library is the ONLY valid source of themes and theme-stock mappings. Never invent themes, concepts, or stocks.

**Format Rule:** All intermediate files are markdown. Write them directly — do NOT write scripts to generate JSON. The LLM is the author, not a code generator.

**Layer Boundary:** Script outputs data + features + formula-based scores (25 fields from `fetch_pool_indicators.py`). Skill layer reads these directly — composite weighting, direction, hard/soft filter decisions, and table population are LLM territory. Do NOT write ad-hoc scoring scripts.

## Red Flags — STOP and Restart the Stage

| Symptom | Fix |
|---------|-----|
| Theme name not found in Theme Library | Discard. Theme Library is the only source. |
| Stock entered pool but source not in {candidates, market, news_direct, lhb} | Remove. All stocks must be traceable to one of 4 sources. |
| `sh688*` (科创板 STAR board) or `bj*` (北交所 BSE) stock entered the pool | Remove. Hard exclude — cannot trade. |
| Wrote a Python/JS script to generate JSON intermediate file | Delete script. Write markdown directly. |
| theme_stocks.md row missing `source_themes` column | Re-add. Downstream needs WHY a stock is in pool. |
| mapper.md contains buy/stop/target recommendations | Remove strategy clauses. Strategy is Step 3 territory. |
| Composite score or tech_score filled without showing calculation trace | Recompute with weights shown. |
| Auto-removed a stock solely because of RSI>75 / RSI<30 / MA双熊 / 炸板 | Restore to pool. These are risk flags, not hard filters. |

**Violating these is violating the spirit of the rules.**

---

## Theme Extraction

**Objective:** Match news items to themes from Theme Library via retrieval, not generation.

### Load Theme Universe

```bash
python .opencode/skills/theme-library/scripts/query_theme.py list --json
```

Retrieve all available themes. Theme Library is the ONLY valid theme source.

### Match News to Themes

Read every news item in `news.md`. Match against available themes using:

1. Theme name (exact)
2. Aliases (exact)
3. Keywords (exact)
4. Member concepts (e.g., news mentions "东数西算" → matches theme "AI算力")
5. Semantic alignment (weakest priority)

Matching priority: `Name > Alias > Keyword > Concept > Semantic`

One news item may match multiple themes.

### Theme Confidence

For each matched theme, calculate `confidence` (0-100):

| Confidence | Meaning |
|------------|---------|
| 90-100 | Explicit theme/concept name in news text |
| 75-89 | Strong keyword or alias match |
| 60-74 | Semantic match with supporting evidence |
| <60 | Weak, discard |

Discard `confidence < 60`.

### Theme Heat

Merge all news mapped to the same theme. Calculate `theme_heat` (0-100):

```
theme_heat = policy × 0.40 + capital × 0.15 + emotion × 0.25 + news_count × 0.20
```

| Component | Weight | Meaning |
|-----------|--------|---------|
| policy | 40% | National/industrial policy, regulatory support |
| capital | 15% | Capital activity, financing, institutional participation |
| emotion | 25% | Market attention, media discussion, sentiment |
| news_count | 20% | Number and density of related news |

### Rank & Filter

Sort by `theme_heat DESC`. Keep `theme_heat >= 60`. Max 20 themes.

### Output Format

Write as structured markdown table. One row per theme, sorted by `theme_heat DESC`.

```markdown
# Theme Extraction Results

Date: 2026-06-17

| # | Theme | Heat | Confidence | Policy | Capital | Emotion | News# | Matched Concepts | Reason |
|---|-------|------|------------|--------|---------|---------|-------|-------------------|--------|
| 1 | AI算力 | 92 | 95 | 85 | 70 | 95 | 8 | 东数西算, 数据中心 | Multiple AI infra news, strong market attention |
| 2 | 半导体 | 78 | 88 | 80 | 65 | 85 | 6 | 国产芯片, 先进封装 | Policy support for domestic chips |
| ... |

Themes with heat < 60 are excluded. Max 20 themes.
```

### Constraints

- Theme names MUST come from Theme Library
- Never invent themes
- Concepts are matching signals only, not output
- Confidence must be calculated, not guessed

---

## Stock Pool Build

**Objective:** Convert themes into deduplicated stock pools with source-theme tracking.

### Retrieve Candidate Stocks

For each theme in `themes.md`:

```bash
python .opencode/skills/theme-library/scripts/query_theme.py candidates <theme_name> --json
```

Use `candidate_stocks` as the primary pool. These are specifically designed for downstream analysis (purity + liquidity + market_cap combined).

**Optionally** supplement with `market` view to catch stocks showing active signals that may rank outside the static candidate list:

```bash
python .opencode/skills/theme-library/scripts/query_theme.py market <theme_name> --top 10 --json
```

The `market` view provides the following fields in JSON output (`market_view` key):

| Field | Content | Use in pool building |
|-------|---------|---------------------|
| `cross_rank_highlights` | Stocks in ≥2 top-N lists, with `attention_score` + `industry_score` | **Primary source** — reveals edge diffusion (边缘扩散 Atn↑Ind--), bellwether launch (中军启动 Atn↑Ind≥50), and theme mainline (主题主线) signals |
| `market_attention` | Composite: 0.6×成交额 + 0.25×换手率 + 0.15×量比 (all percentile ranks) | Stocks with `attention_score >= 80` not in pool → add with `source = "market_active"` |
| `top_gainers` | Today's strongest by `change_pct`, with `industry_score` column | Stocks with `change_pct >= 3%` not in pool → add with `source = "market_active"` |

**Priority:** `cross_rank_highlights` stocks should be added FIRST, as they represent the strongest multi-dimensional signals. A stock appearing in 3+ top-N lists with `industry_score: --` is a classic "边缘扩散 → 新龙头" (edge diffusion → new leader) pattern — the most valuable trading signal the market view provides.

### Inject News-mentioned Stocks

Scan `news.md` for **explicitly mentioned A-share stocks** (codes or names). For each:

1. Resolve stock name → code via `fetch_stock.py --search "名称"` or LLM knowledge of common codes
2. Add to pool with `source = "news_mentioned"`, `score = News_Impact` (estimated from mention prominence: headline=100, body=80, listed-only=60)
3. Mark as `news_direct: true` to indicate this stock was directly named in news

**Rationale:** A stock named in news may not appear in theme library TOP 30 candidates (e.g., small-cap 盛美上海 or non-core-concept 金博股份), but direct news mention is the strongest possible signal. These stocks skip theme-library constraints.

**Resolve codes in batch:**

```bash
# Batch resolve multiple stock names — use ; separator within quotes for multiple searches
python .opencode/skills/stock-analysis/scripts/fetch_stock.py --search "盛美上海" --json
python .opencode/skills/stock-analysis/scripts/fetch_stock.py --search "赛腾股份" --json
```

Run searches in parallel. Alternatively, use LLM knowledge for well-known codes (sh688012=中微公司, sh603986=兆易创新, etc.).

### Dragon & Tiger List Injection

The Dragon & Tiger List (龙虎榜) captures stocks with abnormal price/volume moves (limit-up, limit-down, amplitude swing, turnover surge) — exactly the type of stock that may rank outside theme library top 30 but suddenly broke out.

```bash
python .opencode/skills/stock-analysis/scripts/fetch_special.py lhb --json
```

For each stock in the LHB list (~50 records):

1. Look up theme membership: `python .opencode/skills/theme-library/scripts/query_theme.py stock <code> --json` (parallel calls, local JSON reads, ~1-2s total)
2. If the stock belongs to ANY theme in `themes.md` (Heat ≥ 60) → add to pool
3. Mark with `source: lhb` + score based on list reason (净买入 net buy > 0 = 85; 涨停 limit-up = 90; 跌停 limit-down = skip)
4. If already in pool (from news or library), merge labels, keep the higher score

**Theme gate prevents pool inflation:** ~50 LHB records → theme filter → typically 3-8 net new stocks added. Stocks in unrelated sectors (食品饮料, ST, etc.) are silently dropped.

**Run in parallel** with candidate retrieval and news injection — LHB fetch + stock lookups don't depend on previous results.

### Supplement with Pure Stocks

`query_theme.py pure` reads local JSON files — no network cost. Always fetch for all themes to compensate for downstream STAR/BSE board filtering.

```bash
python .opencode/skills/theme-library/scripts/query_theme.py pure <theme_name> --top 15 --json
```

Add all `pure_stocks` to the pool. This catches highly relevant stocks that didn't enter the candidate list (e.g., deeply pure to one concept but with low liquidity).

**Merge rule:** If a stock already exists in the pool (from candidates), keep the higher score. If new (from pure supplement), add with `purity_score` as the score.

### Deduplicate & Board Filter

The same stock may appear under multiple themes. Deduplicate by stock code:

1. Merge `source_themes` list, keep the highest score across themes, record all theme associations

2. **Board filter — hard exclude (no exceptions):**
   - `sh688*` — 科创板 (STAR Board)
   - `bj*` — 北交所 (Beijing Stock Exchange)

3. News-mentioned stocks (`news_direct: true`) and LHB stocks (`source: lhb`) bypass score-based dedup but NOT the board filter. A stock you cannot trade should never enter the pool.

### Output Format

Write as structured markdown. Two sections: theme summary table + stock detail table.

```markdown
# Stock Pool

Date: 2026-06-17

## Themes Summary

| # | Theme | Heat | Confidence | Stocks in Pool |
|---|-------|------|------------|----------------|
| 1 | AI算力 | 92 | 95 | 28 |
| 2 | 半导体 | 78 | 88 | 22 |
| ... |

Total unique stocks: 156 (deduplicated across themes)

## Stock Pool (Deduplicated)

| # | Code | Name | Best Score | Source Themes | Anch? | News? | LHB? | Mkt? |
|---|------|------|-----------|---------------|------|-------|------|------|
| 1 | sz000977 | 浪潮信息 | 94.2 | AI算力(94.2), 英伟达产业链(47.3) | Yes | ✓ | — | — |
| 2 | sh603019 | 中科曙光 | 88.5 | AI算力(88.5) | Yes | — | ✓ | — |
| 3 | sh600522 | 中天科技 | 81.8 | AI算力(81.8) | No | — | — | ✓ |
| ... |

Source Themes format: ThemeName(score). News?/LHB?/Mkt? = ✓ marks source channels. Mkt? = from market_active query. Board filter: sh688* and bj* stocks are excluded (cannot trade).
```

### Constraints

- Stocks come from four sources: Theme Library queries, `news.md` mentions, LHB list (post theme-filter), **and** `market` active signals
- Never generate stocks manually — must be traceable to one of the four sources
- `source_themes` must be preserved — downstream stages need to know WHY a stock is in the pool
- LHB and news-mentioned stocks are always kept; if they fail technical hard filters, flag for manual review instead of removal
- Market-active stocks (`source: market_active`) are supplemental — they bypass theme library candidate ranking but NOT board/technical filters
- Deduplication is mandatory before Technical Enrichment to avoid redundant API calls
- Board filter (`sh688*` / `bj*`) is applied BEFORE Technical Enrichment — never fetch indicators for untradeable stocks
- If a theme's post-filter candidate count drops below 8, re-run pure stock supplement with `--top 20` for that theme

---

## Technical Enrichment

**Objective:** Enrich each stock with market data and technical indicators, then filter out technically disqualified stocks. Enriches the existing markdown table with new columns.

### Fetch Data

Execute in 2 phases. Data reflects the **previous trading day** when running pre-market; use live data if running intraday.

**Phase 1: Auction Snapshot & Call Auction Metrics (single batch call)**

```bash
python .opencode/skills/stock-analysis/scripts/fetch_stock.py <code_1>,<code_2>,...,<code_N> --json
```

`fetch_stock.py` supports comma-separated multi-code queries. During call auction (9:15-9:25), returns live auction data. Combine ALL stocks from `theme_stocks.md` into ONE call.

Extract these auction metrics from the JSON output:

| Auction Metric | JSON Field | Formula / Note |
|---------------|-----------|----------------|
| **Auction Change%** (竞价涨幅) | `percent` | Computed by API: `(price - yestclose) / yestclose × 100` |
| **Auction Amount** (竞价金额) | `amount_10000` | Cumulative auction turnover, divided by 10000. Unit: **万** (e.g., CNY/10000 for A stocks). Use directly without further conversion. |
| **Auction Turnover Rate** (竞价换手) | `volume` / float_shares | `auction_volume / float_shares`. `float_shares` from `fetch_stock.py --json` output field (流通股本, 股). Returns `null` if unavailable. |

Usage in pipeline:
- Auction Change%: flag stocks with `abs(percent) > 3%` as auction anomaly → passed to Step 3 for opening gap strategy
- Auction Amount: `amount_10000 > 5000万` = auction with volume (conviction signal); `< 1000万` = auction without volume (weak signal)
- Auction Turnover Rate (optional): `> 0.3%` = active auction participation, strengthens the above signals

Enrich `theme_stocks.md` with these columns: `Auction%` (竞价涨幅), `AuctionAmt` (竞价金额/万), `AuctionTO` (竞价换手%, optional).

**Phase 2: Technical Indicators, Features & Scoring (single batch call)**

> **Timeout:** This command fetches history + computes indicators for every stock in the pool. With Sina source (~30s for 80 stocks), set bash timeout to **5 minutes** (`timeout: 300000`).

```bash
python .opencode/skills/daily-stock-mapping/scripts/fetch_pool_indicators.py <code_1>,<code_2>,...,<code_N> --json -o <output_file>
```

Output is a flat JSON array — same structure as Phase 1 `fetch_stock.py`. Each element is a single record per stock with 25 fields covering 3 layers. All numeric values are float/int (no `"14.38%"` string formatting). One tool call covers the entire pool.

Example output (one element per stock):

```json
[{
  "code": "sh600584",      "price": 94.70,       "close": 94.70,
  "turnover": 14.38,        "change_pct": 10.0,    "amount": 12345678,
  "rsi": 68.9,              "macd": 7.2,           "macdh": 1.5,
  "ma20": 79.42,            "ma50": 62.50,
  "boll_ub": 94.70,         "boll_lb": 64.14,      "atr": 6.14,
  "high20": 94.70,          "low20": 65.72,
  "atr_pct": 6.50,          "percent_b": 0.82,
  "board_streak": 2,        "seal_quality": "封死",
  "limit_up_freq": 3,       "traditional": 73.2,   "sentiment": 92.5,
  "tech_score": 79.0,       "risk_flags": ["RSI>75"]
}]
```

Field reference:

| Field | Layer | Purpose |
|-------|-------|---------|
| `code` | ID | Stock code |
| **Raw indicators (15)** | Data | |
| `price`, `close` | K-line | Current price (last close), yesterday's close |
| `turnover`, `change_pct`, `amount` | K-line | 换手率, 涨跌幅, 成交额/万元 (all float, no `%` suffix). `amount` unit: **万元** |
| `rsi` | Indicator | RSI(14) — momentum / overbought |
| `macd`, `macdh` | Indicator | MACD line & histogram — momentum |
| `ma20` | Indicator | Bollinger middle = 20-SMA — medium-term trend |
| `ma50` | Indicator | 50-SMA — medium-term trend |
| `boll_ub`, `boll_lb` | Indicator | Bollinger upper/lower bands |
| `atr` | Indicator | ATR(14) — volatility |
| **Feature engineering (6)** | Formula | |
| `high20`, `low20` | `max(high[-20:])`, `min(low[-20:])` | Strategy Inputs |
| `atr_pct` | `atr / close × 100` | ATR Risk scoring |
| `percent_b` | `(close - boll_lb) / (boll_ub - boll_lb)` | BB Position scoring |
| `board_streak` | Consecutive limit-up days (int 0/1/2/3...) | Sentiment input |
| `seal_quality` | 封板质量: `"封死"` / `"未封板"` / `"炸板"` / `"—"` | Sentiment input |
| **Scoring (5)** | Weighted formula | |
| `limit_up_freq` | Total limit-up days in last 10 records (int) | Sentiment input |
| `traditional` | 7-factor weighted sub-score (0-100) | Tech score input |
| `sentiment` | 3-factor weighted sub-score (0-100) | Tech score input |
| `tech_score` | `traditional × 0.70 + sentiment × 0.30` (0-100) | Composite input |
| `risk_flags` | `["RSI>75","RSI<30","ATR>8%","MA双熊","流动性<3亿","炸板"]` — risk markers for Step 3 | Risk column |

**Skill layer uses these directly** — no need to re-derive %B, ATR%, board streak, seal quality, or tech_score from raw K-line data. Skill's job: composite, direction, hard/soft filter decisions, table population.

No further API calls needed. Read the JSON directly — do NOT write scripts to parse it.

### Scoring

`tech_score` (0-100) is **pre-computed by `fetch_pool_indicators.py`** and available in the output as `traditional`, `sentiment`, and `tech_score`. Formulas are documented here for transparency — the Skill layer reads the pre-computed values directly, no recalculation needed.

```
tech_score = Traditional × 0.70 + Sentiment × 0.30
```

**Traditional Technical sub-score (0-100):** MA_Trend × 0.22 + MACD_Mom × 0.19 + RSI × 0.13 + Liquidity × 0.22 + BB_Position × 0.16 + ATR_Risk × 0.09

| # | Factor | Weight | Scoring |
|---|--------|--------|---------|
| 1 | **MA Trend** | 22% | Price > ma20 > ma50 = 100; Price > ma20, ma20 < ma50 = 60; Price < ma20, ma20 < ma50 = 0 |
| 2 | **MACD Mom** | 19% | macdh > 0 AND accelerating = 100; macdh > 0 = 75; crossing 0 = 50; macdh < 0 = 25; deepening = 0 |
| 3 | **RSI** | 13% | 45-60 = 100; 60-70 = 80; 30-45 = 70; 70-75 = 40; >75 or <30 = 0 |
| 4 | **Liquidity** | 22% | `amount / 10000` → 亿: ≥5亿 = 100; 3-5亿 = 70; 1-3亿 = 40; <1亿 = 0. Note: `amount` unit is 万元 |
| 5 | **BB Position** | 16% | Use pre-computed `percent_b`. 0.4-0.6 = 100; 0.6-0.8 = 80; 0.2-0.4 = 70; >0.8 = 60; <0.2 = 20 |
| 6 | **ATR Risk** | 9% | Use pre-computed `atr_pct`. 1.5-3% = 100; 3-5% = 70; <1.5% = 60; >5% = 30 |

**Sentiment sub-score (0-100):** Board Streak × 0.50 + Limit-up Frequency × 0.25 + Seal Quality × 0.25

Scored from pre-computed `board_streak` (int) and `seal_quality` (str) fields in Phase 2 output:

| # | Factor | Weight | Scoring |
|---|--------|--------|---------|
| 8a | **Board Streak** (连板强度) | 50% | `board_streak >= 3` = 100; `board_streak = 2` = 85; `board_streak = 1` = 65; `board_streak = 0` = 0 |
| 8b | **Limit-up Frequency** (涨停频率) | 25% | Use pre-computed `limit_up_freq`: ≥3=100; 2=80; 1=60; 0=0 |
| 8c | **Seal Quality** (封板质量) | 25% | `seal_quality = "封死"` = 100; `seal_quality = "未封板"` = 60; `seal_quality = "炸板"` = 15; `seal_quality = "—"` = 0 |

Note: "Price" = auction price from Phase 1. A-share limit-up boards: Main Board 10%, STAR/ChiNext 20%, BSE 30%. Both `board_streak` and `seal_quality` are pre-computed by `fetch_pool_indicators.py` — no need to re-derive from K-line history.

**Stop-loss reference:** ATR passed to Step 3 for stop-loss: stop_distance = `2 × atr`. Sentiment also informs stop placement — widen stop for streak stocks (avoid shakeout), tighten stop for broken-board stocks.

### Hard Filters

Remove stocks that fail ANY hard filter (based on yesterday's data):

| Filter | Reject Condition | Data Source |
|--------|-----------------|-------------|
| Liquidity | `amount` < 30000 (万元) = 3亿 (300M CNY). Note: `amount` field unit is 万元 | fetch_pool_indicators (`amount` field) |
| Extreme Volatility | atr_pct > 8% (abnormal volatility) | fetch_pool_indicators (`atr_pct` field) |

### Technical Risk Flags

The following conditions are **risk markers only**, not auto-reject triggers. They are written to the `Risk?` column and passed to Step 3, where `memory/RULES.md` decides whether to trade, override, or downgrade:

| Flag | Condition | Relevant RULES.md Reference |
|------|-----------|----------------------------|
| MA双熊 | Price < ma20 AND ma20 < ma50 | R73 / R74 (weak-market MA20 buffer) |
| RSI>75 | RSI > 75 | R37 (strong-market RSI overbought exemption) |
| RSI<30 | RSI < 30 | R61 (deep-oversold tiered handling) |
| 炸板 | seal_quality = "炸板" | R39-v3 / R35-v3 (limit-up broken-board review) |

Do **not** remove these stocks in Step 2. Anchor stocks and theme core stocks (theme_heat >= 80) keep their pool status and carry the flag.

### Soft Filter

- Keep stocks with `tech_score >= 50`.
- Stocks with `tech_score 50-59` are flagged as `tech_risk: true` in output.
- Stocks carrying `MA双熊`, `RSI>75`, `RSI<30`, or `炸板` flags are **not removed** for those reasons alone. They remain in the pool but their `Direction` in `mapper.md` must not be higher than `neutral-bull`, and the `Risk` column must show all flags.

### Enrich theme_stocks.md

Add technical columns to the stock table. Only remove rows that failed **hard filters** (liquidity < 3亿 or atr_pct > 8%). Stocks with technical risk flags (`MA双熊`, `RSI>75`, `RSI<30`, `炸板`) remain in the table with their flags shown in the `Risk?` column.

```markdown
## Stock Pool (After Technical Enrichment)

| # | Code | Name | Best Score | Source Themes | Anch | Auc% | AucAmt | 情绪 | 连板 | 封板 | Tech | RSI | %B | MA50 | 换手% | Risk? |
|---|------|------|-----------|---------------|------|------|--------|------|------|------|------|-----|----|----------|-------|-------|
| 1 | sz000977 | 浪潮信息 | 94.2 | AI算力 | Yes | +1.2 | 3200万 | 75 | 1板 | 封死 | 78.5 | 55.3 | 0.62 | >ma50 | 6.8% | No |
| 2 | sh600522 | 中天科技 | 88.5 | AI算力 | — | -0.5 | 800万 | 30 | 0 | — | 68.0 | 48.2 | 0.45 | >ma50 | 2.1% | No |
| 3 | sh603986 | 兆易创新 | 92.0 | 半导体 | — | +3.5 | 8500万 | 85 | 2连板 | 封死 | 65.0 | 72.0 | 0.85 | >ma50 | 15.2% | RSI>75 |
| 4 | sh600XXX | 某股 | 70.0 | AI算力 | — | +0.2 | 35000万 | 30 | 0 | — | 55.0 | 42.0 | 0.30 | <ma20 | 1.5% | MA双熊 |
| ... |

Removed stocks (failed hard filters): list them with reason (liquidity or ATR>8% only).
Columns: MA50=Price vs MA50, 情绪=Sentiment sub-score, 连板=consecutive boards, 封板=seal quality, 换手%=yesterday turnover rate.
```

---

## Structured Dataset Generation

**Objective:** Aggregate all data into structured tables. Output `mapper.md` as a machine-consumable decision dataset. **No natural-language analysis, no recommendations, no summaries, no derived levels (support/resistance).**

### Data Sources

Already available from previous stages:
- Auction metrics (Phase 1): `percent`, `amount`, `volume`
- K-line indicators (Phase 2): ma20, ma50, RSI, MACD, MACDH, percent_b, ATR, atr_pct, turnover, amount, change_pct
- Theme scores: Theme_Heat from themes.md
- Sentiment: emotion sub-score (scored from `board_streak`, `seal_quality`, limit-up frequency from Phase 2)

Additional fetches in this stage:

### Fetch Money Flow

**Timing note:** Money flow data reflects the **previous trading day** when running pre-market. Use data as a directional proxy for capital sentiment. When running intraday, live money flow is available.

```bash
# Industry money flow (行业资金流向)
python .opencode/skills/stock-analysis/scripts/fetch_money_flow.py --json

# Individual stock money flow (个股资金流向) — requires cookie
python .opencode/skills/stock-analysis/scripts/fetch_money_flow.py --stock --json
```

| Type | Usage |
|------|-------|
| Industry money flow | Calibrate composite score `Money_Flow` dimension for stocks in that industry |
| Stock money flow | Verify individual stock capital direction (主力净流入/流出 major net inflow/outflow) |

### Compute Fields

#### Auction Signal

Auction data was already fetched in Phase 1. In the A-share market, the final 5 minutes of call auction (9:20-9:25) often provide the strongest prior signal of the day, more predictive than money flow.

Compute `auction_score` (0-100):

```
auction_score = Auction Change% × 0.40 + Auction Amount × 0.35 + Auction Turnover Rate × 0.25
```

| # | Factor | Weight | Scoring |
|---|--------|--------|---------|
| 1 | **Auction Change%** | 40% | `abs(percent)`. ±2~5% = 100; ±1~2% = 85; ±0.5~1% = 70; ±0~0.5% = 50; >±5% = 40 (auction anomaly, watch for manipulation). Direction: positive = full score, negative = halved |
| 2 | **Auction Amount** | 35% | `amount_10000` from `fetch_stock.py` (unit: 万). ≥5000万 = 100; 2000-5000万 = 75; 500-2000万 = 50; <500万 = 20. |
| 3 | **Auction Turnover Rate** (optional) | 25% | `auction_volume / float_shares`. ≥0.3% = 100; 0.1-0.3% = 70; <0.1% = 40. Skip if float shares unavailable (weight merges into Auction Amount) |

Note: Auction data is only meaningful for pre-market runs. For intraday runs, set auction_score = 50 (neutral).

#### Composite Score

For each stock:

```
composite_score = Theme_Heat × 0.30 + News_Impact × 0.20 + Auction_Signal × 0.20 + Tech_Score × 0.20 + Money_Flow × 0.10
```

| Factor | Weight | Source |
|--------|--------|--------|
| Theme Heat | 30% | Best source_themes heat value from themes.md |
| News Impact | 20% | News relevance to this specific stock (0-100, judged from news.md) |
| Auction Signal | 20% | From Auction Signal section above (Auc Chg%/Amt/TO computed from Phase 1 data); intraday runs use 50 neutral |
| Tech Score | 20% | From Technical Enrichment (Traditional×0.70 + Sentiment×0.30) |
| Money Flow | 10% | Capital flow: industry net inflow direction and magnitude (high noise, down-weighted) |

Range: 0-100. Money_Flow is inherently noisy (Eastmoney/Tonghuashun statistical calibers differ, lagging indicator), therefore minimized. Auction Signal is the single strongest A-share prior for pre-market runs.

#### Direction

**Directional feature — column value only, no prose analysis:**

| Direction | Condition |
|-----------|-----------|
| bullish | composite >= 70 AND news impact >= 60 |
| neutral-bull | composite >= 55 AND news impact >= 50 |
| neutral | composite >= 45 |
| bearish | composite < 45 OR negative news impact |

#### ThemeRole Extraction

Batch-fetch role tags for all pool stocks from Theme Library. Role Tags are an independent dimension; they cannot be reverse-derived from Composite Score.

```bash
python .opencode/skills/theme-library/scripts/query_theme.py stock <code1>,<code2>,... --roles --json
```

Returns each stock's `tags` list (cumulative, non-exclusive):

| Tag | Condition | Meaning |
|-----|-----------|---------|
| `Anchor` | `anchor = true` in any matched theme | Market-recognized bellwether, theme anchor stock |
| `IndustryLeader` | `industry_score >= 50` in any matched theme | Industry representative stock |
| `Candidate` | `candidate_score >= 60` in any matched theme | Currently worth focused analysis |
| `MultiTheme` | `theme_count >= 2` | Cross-theme map stock, high fault tolerance |

Write Role Tags to Candidate Pool `RoleTags` column, comma-separated (e.g. `Anchor,IndustryLeader,MultiTheme`). Write `—` if no tags.

---

### Output: mapper.md

Generate `mapper.md` as a pure structured dataset. **6 sections. No prose anywhere.** Sorted by `composite_score DESC`.

---

#### Section 1: Market State

Structured key-value table. Extract from news.md market overview + financing flow data.

```markdown
## Market State

| Field | Value |
|-------|-------|
| DominantThemes | [[comma-separated top 2-3 themes by heat]] |
| FinancingFlow | [[net financing flow direction and magnitude]] |
| RiskFlags | [[comma-separated: RMBWeakness, MetalCrash, RateHike, etc.]] |
```

#### Section 2: Theme Ranking

```markdown
## Theme Ranking

| Theme | Heat | Rank |
|-------|------|------|
```

Sorted by Heat DESC. All themes with Heat >= 60.

#### Section 3: Candidate Pool

All stocks with Composite Score >= 55. Sort by Composite DESC.

```markdown
## Candidate Pool

| Code | Name | Composite | Direction | Theme | RoleTags | Emotion | Turnover% | Risk |
|------|------|-----------|-----------|-------|----------|---------|-----------|------|
```

Column sources:

| Column | Source |
|--------|--------|
| Direction | From Direction computation (bullish / neutral-bull / neutral / bearish) — column value only |
| Theme | Primary theme (highest heat theme from source_themes) |
| RoleTags | From ThemeRole query (Anchor / IndustryLeader / Candidate / MultiTheme, comma-separated) |
| Emotion | From theme_stocks.md sentiment sub-score |
| Turnover% | From theme_stocks.md yesterday turnover rate |
| Risk | From theme_stocks.md Risk flags (e.g. RSI>75, 昨-7%, Auction<-5%) |

#### Section 4: Strategy Inputs

**ALL** Candidate Pool stocks must be covered. Do NOT truncate to Top 5 or Top 8.

```markdown
## Strategy Inputs

| Code | Price | MA20 | ATR | ATR% | High20 | Low20 |
|------|-------|------|-----|------|--------|-------|
```

Data source: K-line records from Technical Enrichment Phase 2. No additional API calls.

| Column | Source | Formula |
|--------|--------|---------|
| Price | Auction price from Phase 1 batch call | From `fetch_stock.py` output (or `price` from Phase 2 if auction unavailable) |
| MA20 | `ma20` field | From Phase 2 output |
| ATR | `atr` field | From Phase 2 output |
| ATR% | `atr_pct` field | Pre-computed |
| High20 | `high20` field | Pre-computed by `fetch_pool_indicators.py` |
| Low20 | `low20` field | Pre-computed by `fetch_pool_indicators.py` |

#### Section 5: Observation Pool

All stocks with Composite Score < 55. Full list, no truncation.

```markdown
## Observation Pool

| Code | Name | Composite | Theme | Reason |
|------|------|-----------|-------|--------|
```

Reason examples:
- `BelowThreshold` — Composite < 55
- `TechnicalRisk` — failed soft filter, flagged in theme_stocks.md
- `WeakTheme` — theme heat below threshold

#### Section 6: Excluded Stocks

Extracted from theme_stocks.md `### Removed Stocks (Failed Hard Filters)` section.

```markdown
## Excluded Stocks

| Code | Name | ExclusionReason |
|------|------|-----------------|
```

Examples: `Auction<-5%, MA趋势弱`, `非核心主题`, `RSI>75且无多头动能`

---

### Deleted Content

The following sections and content types are **NEVER** included in mapper.md:

- Market background prose (市场背景 / 大盘方向 / 情绪温度 paragraph)
- Tiered ranking labels (第一梯队 / 第二梯队 classification)
- Individual stock analysis paragraphs with natural-language commentary (个股分解分析 with 新闻影响分析 / 技术面分析 / 资金面分析 / 综合 paragraphs)
- Industry money flow section (行业资金流向 with prose commentary)
- Summary / Conclusion (总结 / 综合评价 / 核心标的 / 风险点评 / 风格偏好)
- Support / Resistance levels (支撑/阻力位, ATR Stop Distance, VWAP)
- Any form of trading recommendations or buy/stop/target suggestions
- Impact direction prose (retained only as a column value in Candidate Pool)

---

### Step 2 → Step 3 Data Contract

The **Strategy Inputs** table in mapper.md is the **authoritative source** for Step 3 on these fields:

- Price
- MA20
- ATR
- ATR%
- High20
- Low20

**Step 3 must use Strategy Inputs values directly.**

Re-fetch from API only if:
- Field is missing (N/A, null, empty)
- Field is invalid (negative, zero where nonsensical)
- Stale data detected (exceeds freshness window)

**Default behavior: no re-fetch.** Step 3 should load Strategy Inputs and proceed to calculation — never start with "I'll need to fetch data" or "Need ATR/MA20/High20".
