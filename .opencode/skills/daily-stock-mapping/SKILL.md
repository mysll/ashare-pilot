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
| Structured Dataset Generation | theme_stocks.md (enriched) | mapper.md (7-section structured dataset: Market State, Theme Ranking, Candidate Pool, Strategy Inputs, Score Trace, Observation Pool, Excluded Stocks) |

## Scope

A-shares only (sh/sz prefix). Ignore HK/US and other markets. Board exclusions (`sh688*`, `bj*`) are **config-driven** — see `config/trading-scope.json` (§ Board Exclusion Policy). Default policy excludes both.

**Core Rule:** Theme Library is the ONLY valid source of themes and theme-stock mappings. Never invent themes, concepts, or stocks.

**Format Rule:** All intermediate files are markdown. Write them directly — do NOT write scripts to generate JSON. The LLM is the author, not a code generator.

**Layer Boundary:** Script outputs V5 nested JSON (`raw_observation` + `computed_perception` per stock, each field with `{value, confidence, trace}`). Skill layer (Step 2) is **perception only** — classification, detection, pattern recognition per V5 Minimal Inference whitelist. Composite / PerceptionTrace aggregation is Python territory. **Direction / RiskSeverity / OverrideHint application are Step 3 Reasoning territory.** Step 2 NEVER produces Direction, buy/stop/target, or strategic judgment.

## Red Flags — STOP and Restart the Stage

| Symptom | Fix |
|---------|-----|
| Theme name not found in Theme Library | Discard. Theme Library is the only source. |
| Stock entered pool but source not in {candidates, market, news_direct, lhb} | Remove. All stocks must be traceable to one of 4 sources. |
| Stock in `config/trading-scope.json` excluded boards entered pool | Remove. Board exclusion is config-driven, not hardcoded. |
| Wrote a Python/JS script to generate JSON intermediate file | Delete script. Write markdown directly. |
| theme_stocks.md row missing `source_themes` column | Re-add. Downstream needs WHY a stock is in pool. |
| mapper.md contains buy/stop/target recommendations | Remove. Strategy is Step 3 territory. |
| **Step 2 produces Direction / RiskSeverity / OverrideHint** | Violation. These are Step 3 Reasoning territory. Step 2 is Perception only (V5 Invariant 1). |
| **Step 2 makes causal inference** ("资金流入带动上涨") | Violation. Correlation OK; causation forbidden. |
| Candidate Pool row missing `CompositeTrace` or `tech_score.confidence` | Re-add. V5 audit trail mandatory. |
| `risk_flags` array contains `流动性<3亿` token | Remove. Liquidity hard-filter is handled in SKILL layer. |
| Stock with `fetch_failed: true` from Phase 2 enters Candidate Pool | Move to Observation Pool `Reason=Indicators_Fetch_Failed`. V5: fetch_failed rows have empty raw_observation + computed_perception. |

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
| news_count | 20% | Number and density of related news (raw integer, normalized to 0-100 before weighting) |

> **News double-counting decision (V4-U)**: theme_heat 公式保留 `news_count × 0.20`，新闻对 composite 的总有效权重约 26%（theme_heat 间接 + NewsImpact 直接 20%）。**依靠 NewsImpact 在 MajorEvent=Negative 时 cap=60 缓解叠加膨胀**，作为设计接受。日常权重重叠不改。

**Theme heat sub-score rubric (LLM MUST follow)**

Policy (P):

| Score | Condition |
|-------|-----------|
| 90-100 | 国家/行业政策明确点名主题；监管文件、国务院、部委 |
| 75-89 | 强政策代理（标准、补贴、试点区）无头条政策 |
| 60-74 | 间接政策受益（供应链、本地化） |
| <60 | 无政策角度 — discard theme |

Capital (C):

| Score | Condition |
|-------|-----------|
| 85-100 | 融资流入/北向/龙虎榜净买入与主题对齐（今日或昨日） |
| 65-84 | 板块成交放大、融资扩张 |
| 45-64 | 中性 |
| <45 | 流出或无资金信号 — 用 45 default |

Emotion (E):

| Score | Condition |
|-------|-----------|
| 90-100 | ≥3 flash 项 + 热股榜 + 主题内涨停簇 |
| 75-89 | 2 条新闻 或 1 条重大头条 |
| 60-74 | 仅语义匹配，媒体密度低 |
| <60 | discard |

**News count (N)** — 映射到主题的不同新闻条数原始计数（整数，显示截断至 20）。加权时按 `count / 20 × 100` 归一化到 0-100。

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

**Priority:** `cross_rank_highlights` 表示该股出现在 ≥2 个 top-N 列表中，`attention_score` 与 `industry_score` 值已给出 — LLM 据此判断边缘扩散 / 中军启动 / 主题主线信号，可用 Anomaly 字段在 mapper.md 中透传。

### Inject News-mentioned Stocks

Scan `news.md` for **explicitly mentioned A-share stocks** (codes or names). For each:

1. Resolve stock name → code via `fetch_stock.py --search "名称"` or LLM knowledge of common codes
2. Add to pool with `source = "news_mentioned"`, `score = News_Impact`（per-stock rubric 见 § Structured Dataset Generation → NewsImpact；news_mentioned 阶段先按 R4×P3=95 之类粗估，下游 Structured Dataset 阶段按矩阵重打）
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

2. **Board filter — config-driven** (read `config/trading-scope.json`):
   - 默认排除 `sh688*` (科创板 STAR) 和 `bj*` (北交所 BSE)
   - excluded 股票写入 `Removed Stocks` 节并标 `ExclusionSource=board-policy`
   - 不 silence-drop：	board-policy 排除的股要在 Excluded Stocks 列出（Step 3 / 配置审计需要）

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

| # | Code | Name | Best Score | Source Themes | News? | LHB? | Mkt? |
|---|------|------|-----------|---------------|-------|------|------|
| 1 | sz000977 | 浪潮信息 | 94.2 | AI算力(94.2), 英伟达产业链(47.3) | ✓ | — | — |
| 2 | sh603019 | 中科曙光 | 88.5 | AI算力(88.5) | — | ✓ | — |
| 3 | sh600522 | 中天科技 | 81.8 | AI算力(81.8) | — | — | ✓ |
| ... |

Source Themes format: ThemeName(score). News?/LHB?/Mkt? = ✓ marks source channels. Mkt? = from market_active query. Board filter: see `config/trading-scope.json`. Anchor 判定在 Structured Dataset Generation 阶段一次性查 RoleTags，本表不列 Anch? 临时代号。
```

### Constraints

- Stocks come from four sources: Theme Library queries, `news.md` mentions, LHB list (post theme-filter), **and** `market` active signals
- Never generate stocks manually — must be traceable to one of the four sources
- `source_themes` must be preserved — downstream stages need to know WHY a stock is in the pool
- LHB and news-mentioned stocks are always kept; if they fail technical hard filters, flag for manual review instead of removal
- Market-active stocks (`source: market_active`) are supplemental — they bypass theme library candidate ranking but NOT board/technical filters
- Deduplication is mandatory before Technical Enrichment to avoid redundant API calls
- Board filter（per `config/trading-scope.json`）is applied BEFORE Technical Enrichment — never fetch indicators for excluded boards
- If a theme's post-filter hard-filter candidate count drops below 8, re-run pure stock supplement with `--top 20` for that theme — **最多 1 轮**，不可无限循环（P3-2）

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
| **Raw indicators (13)** | Data | (excluding `code`) |
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
| `traditional` | 6-factor weighted sub-score (0-100, renormalized for missing factors) | Tech score input |
| `sentiment` | 3-factor weighted sub-score (0-100) | Tech score input |
| `tech_score` | `traditional × 0.70 + sentiment × 0.30` (0-100) — `null` if traditional is null | Composite input |
| `risk_flags` | `["RSI>75","RSI<30","ATR>8%","MA双熊","炸板"]` — risk markers for Step 3（V4-U: 已删 `流动性<3亿`，由 SKILL hard filter 处理） | Risk column |
| `fetch_failed` | Optional `true` placeholder when Phase 2 fetch errored on this code — entry has no other fields | Failure marker |

**Skill layer uses these directly** — no need to re-derive %B, ATR%, board streak, seal quality, or tech_score from raw K-line data. Skill's job: composite, direction, hard/soft filter decisions, table population.

No further API calls needed. Read the JSON directly — do NOT write scripts to parse it.

### Missing Data Handling (P0-4)

`fetch_pool_indicators.py` 不再静默将缺失因子填为 50（旧 V3 行为会系统性拔高缺数据股票分数）。V4-U 新行为：

- 任一因子原始数据 `None` → 该因子**子分跳过**，剩余因子权重按 `present_weight / sum(present_weights)` **重归一化**
- 副作用（正向收益）：V3 weights = 1.01（22+19+13+22+16+9），V4-U 始终除以 sum(present_weights)，所以传统子分最大上限为 100 而非 101。修正 V3 潜在 bug。
- 全部 6 个传统因子缺失 → `traditional = null` → `tech_score = null` → 股票降入 Observation Pool 标 `IndicatorsMissing`
- Phase 2 fetch 异常 → JSON 仅有 `{"code", "fetch_failed": true}` → 同样降入 Observation Pool，标 `Indicators_Fetch_Failed`

### Scoring

`tech_score` (0-100) is **pre-computed by `fetch_pool_indicators.py`** and available in the output as `traditional`, `sentiment`, and `tech_score`. Formulas are documented here for transparency — the Skill layer reads the pre-computed values directly, no recalculation needed.

```
tech_score = Traditional × 0.70 + Sentiment × 0.30
```

**Traditional Technical sub-score (0-100):** MA_Trend × 0.22 + MACD_Mom × 0.19 + RSI × 0.13 + Liquidity × 0.22 + BB_Position × 0.16 + ATR_Risk × 0.09（缺失因子按 § Missing Data Handling 重归一）

| # | Factor | Weight | Scoring |
|---|--------|--------|---------|
| 1 | **MA Trend** | 22% | Price > ma20 > ma50 = 100; Price > ma20, ma20 < ma50 = 60; **Price < ma20, ma20 > ma50 = 40 (V4-U 回踩中期多头新增)**; Price < ma20, ma20 < ma50 = 0 (双熊) |
| 2 | **MACD Mom** | 19% | macdh > 0 AND prev_macdh < macdh = 100 (加速); macdh > 0 = 75; **abs(macdh) < 0.05 = 50 (crossing 0)**; macdh < 0 (not deepening) = 25; **macdh < 0 AND prev_macdh > macdh = 0 (deepening)** — V4-U 实现 5 级（脚本读取 records[last_idx-1].macdh 判加速/deepening） |
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

| Filter | Reject Condition | Data Source | ExclusionSource |
|--------|-----------------|-------------|------------------|
| Liquidity | `amount` < 30000 (万元) = 3亿 (300M CNY). Note: `amount` field unit is 万元 | fetch_pool_indicators (`amount` field) | `hard-filter` |
| Extreme Volatility | atr_pct > 8% (abnormal volatility) | fetch_pool_indicators (`atr_pct` field) | `hard-filter` |
| Indicators fetch failed | `fetch_failed: true` in Phase 2 JSON | fetch_pool_indicators (placeholder row) | `indicators-fetch-failed` |

**NOTE (P0-3)**: 流动性 < 3亿 已不再注入 `risk_flags` 数组（剧本里删除）。它仅作为 hard filter 删除股票到 Excluded Stocks，不重复标 flag。`ATR>8%` 也是 hard filter，但脚本仍会写进 `risk_flags`（保留作为 audit 痕迹）。

### Technical Risk Flags

The following conditions are **risk markers only**, not auto-reject triggers. Step 2 **only classifies RiskType**; RiskSeverity (1/2/3) is **Step 3 Reasoning territory** (V5 Invariant 1). V5 Step 2 does NOT give severity:

| Flag | Condition | RiskType (Step 2) → Severity (Step 3) |
|------|-----------|------------|
| RSI>75 | RSI > 75 | `overbought` → Step 3 decides severity based on regime |
| RSI<30 | RSI < 30 | `oversold_opportunity` → Step 3 decides |
| MA双熊 | Price < ma20 AND ma20 < ma50 | `trend_weak` → Step 3 decides |
| 炸板 | seal_quality = "炸板" | `broken_board` → Step 3 decides |
| Auc<-5% | auction change < -5% | `auction_anomaly` → Step 3 decides |

**V5 difference from V4-U**：1/2/3 severity grading removed from Step 2. Step 3 reads `RiskType` set + RegimeHint + MajorEvent → determines severity. OverrideHint token 在 Step 3 真正从 RULES.md 应用。

### Soft Filter

- Keep stocks with `tech_score >= 50`。`tech_score = null` (因子全缺) 也降入 Observation。
- Stocks with `tech_score 50-59` flagged as `tech_risk: true` in output。
- Stocks carrying `MA双熊`, `RSI>75`, `RSI<30`, or `炸板` flags **不**因这些 flag 单独移除。RiskType 分类由 Step 2 给；RiskSeverity 评定由 Step 3 据 Regime + RiskType set 决定（V5）。`RiskFlags` 列必须显示所有 flag。

### Enrich theme_stocks.md

Add technical columns to the stock table. Only remove rows that failed **hard filters** (liquidity < 3亿 / atr_pct > 8% / fetch_failed)。Stocks with technical risk flags (`MA双熊`, `RSI>75`, `RSI<30`, `炸板`) remain in the table with their flags shown in the `Risk?` column.

```markdown
## Stock Pool (After Technical Enrichment)

| # | Code | Name | Best Score | Source Themes | Auc% | AucAmt | 情绪 | 连板 | 封板 | Tech | RSI | %B | MA50 | 换手% | Risk? |
|---|------|------|-----------|---------------|------|--------|------|------|------|------|-----|----|----------|-------|-------|
| 1 | sz000977 | 浪潮信息 | 94.2 | AI算力 | +1.2 | 3200万 | 75 | 1板 | 封死 | 78.5 | 55.3 | 0.62 | >ma50 | 6.8% | No |
| 2 | sh600522 | 中天科技 | 88.5 | AI算力 | -0.5 | 800万 | 30 | 0 | — | 68.0 | 48.2 | 0.45 | >ma50 | 2.1% | No |
| 3 | sh603986 | 兆易创新 | 92.0 | 半导体 | +3.5 | 8500万 | 85 | 2连板 | 封死 | 65.0 | 72.0 | 0.85 | >ma50 | 15.2% | RSI>75 |
| 4 | sh600XXX | 某股 | 70.0 | AI算力 | +0.2 | 35000万 | 30 | 0 | — | 55.0 | 42.0 | 0.30 | <ma20 | 1.5% | MA双熊 |
| ... |

Removed stocks (failed hard filters): list them with reason + ExclusionSource (`hard-filter` / `indicators-fetch-failed`).
Anch? 列已删 — Anchor 由 Structured Dataset 阶段一次性 `query_theme.py stock <code> --roles` 查 RoleTags 给出，本表不重复标。
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

**Money_Flow 打分公式（P1-1，V4-U 新增）**

```
Money_Flow = 0.6 × IndustryFlowScore + 0.4 × StockFlowScore

  IndustryFlowScore = clamp(50 + 100 × 行业净流入 / 行业流通市值, 0, 100)
  StockFlowScore    = 50 + sign(主力净流入) × min(|净流入| / amount, 1) × 50
```

- cookie 失效 / fetch 失败 → `Money_Flow = 50`（中性），RiskFlags 追加 `MoneyFlowStale`
- intraday 实时 money flow 用上述公式；pre-market 走昨日数据作 direction proxy
- 行业流通市值缺失时 `IndustryFlowScore = 50`，仅用 StockFlowScore（权重重归一为 100% StockFlow）

### Compute Fields

#### Auction Signal

Auction data was already fetched in Phase 1. In the A-share market, the final 5 minutes of call auction (9:20-9:25) often provide the strongest prior signal of the day, more predictive than money flow.

Compute `auction_score` (0-100):

```
auction_score = Auction Change% × 0.40 + Auction Amount × 0.35 + Auction Turnover Rate × 0.25
```

| # | Factor | Weight | Scoring |
|---|--------|--------|---------|
| 1 | **Auction Change%** | 40% | `abs(percent)`. ±2~5% = 100; ±1~2% = 85; ±0.5~1% = 70; ±0~0.5% = 50; >±5% = 40 (auction anomaly, watch for manipulation)。方向：positive = full score, negative = halved |
| 2 | **Auction Amount** | 35% | `amount_10000` from `fetch_stock.py` (unit: 万). ≥5000万 = 100; 2000-5000万 = 75; 500-2000万 = 50; <500万 = 20. |
| 3 | **Auction Turnover Rate** (optional) | 25% | `auction_volume / float_shares`. ≥0.3% = 100; 0.1-0.3% = 70; <0.1% = 40. Skip if float shares unavailable → see below |

**Auction Change% 边界顺序（P1-3，V4-U 固化）**：

```
先按 abs 分级 → 再按正负方向调整 → clip [0, 100]

abs(percent):
  ±2~5%   → 100
  ±1~2%   → 85
  ±0.5~1% → 70
  ±0~0.5% → 50
  >±5%    → 40

if percent < 0: score /= 2     （halved）
```

明确边界情况：
- `-3%` = 100 / 2 = **50**（不是 85 / 2）
- `-0.3%` = 50 / 2 = **25**
- `-6%` = 40 / 2 = **20**（异常竞价）
- `+3%` = **100**（正向完整分）
- `+6%` = **40**（异常正竞价 watch）

**Auction Turnover Rate 缺失时归一（P1-2，V4-U 固化）**：

```
若 float_shares 不可得：
  auction_score = AucChg% × (0.40 / 0.75) + AucAmt × (0.35 / 0.75)
                 = AucChg% × 0.533 + AucAmt × 0.467
```

按 0.40:0.35 比例重归一，**不**简单将权重并入 AucAmt。

Note: Auction data is only meaningful for pre-market runs. For intraday runs, set `auction_score = 50`（中性）。

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

### V5 Perception Architecture (Invariant 1)

Step 2 is **perception only**. V5 contracts define which minimal inferences are allowed. All Direction / Severity / Override decisions are Step 3 Reasoning territory.

#### V5 Minimal Inference 白名单（Step 2 Allowed）

| # | 类型 | 例子 | 谁执行 |
|---|------|------|--------|
| 1 | 数值压缩 | P/C/E 子分 （rubric） | LLM 给子分 |
| 2 | 矩阵分类 | R×P cell 查表 → NewsImpact | LLM (matrix lookup) |
| 3 | 三元分类 | 离散事件 → MajorEvent Polarity (Positive/Negative/Neutral) | LLM |
| 4 | Flag 分类 | risk_flags → RiskType (overbought/trend_weak/...) | LLM (查表) |
| 5 | Pattern 识别 | 多维状态模型每维独立打 state | LLM (5 dimensions) |
| 6 | 结构模式标签 | Anomaly ≤50 中文字 (V5放宽) | LLM (自然语言) |

#### V5 Forbidden Reasoning（Step 2 严禁）

- ✗ Direction (base / final / 任何形态)
- ✗ RiskSeverity (1/2/3 评分 — 归 Step 3)
- ✗ OverrideHint 应用
- ✗ 因果推断（"A 推动上涨"、"因为资金流入"）
- ✗ 趋势预测（"预计继续上涨"、"可能回调"）
- ✗ 买卖建议 (buy/stop/target)
- ✗ 主题级 MajorEvent（行业景气只允许 ThemeHeat/NewsImpact 承载；MajorEvent 必须点名公司）

---

#### V5 Pattern — 多维状态模型（非正交，5 维独立）

每只股在以下 5 个维度各自独立打 state + confidence（perception 内的 pattern recognition）：

| Dimension | States | Rubric (简版) |
|-----------|--------|---------------|
| **heat** | `RISING` / `FALLING` / `STABLE` | theme_heat 今日 vs 昨日；首日无历史则 `STABLE` confidence=50 |
| **leader** | `STABLE` / `DIVERGENCE` / `ABSENT` | RoleTags含Anchor且board_streak≥1→STABLE；Anchor但断板→DIVERGENCE；无Anchor→ABSENT |
| **auction** | `LEADING` / `LAGGING` / `MATCH` / `NEUTRAL` | abs(auc_chg)>1%且同向theme_heat→LEADING；反向>1%→LAGGING；<0.5%→NEUTRAL |
| **rotation** | `PRIMARY` / `SECONDARY` / `TERTIARY` / `NONE` | MultiTheme+板块涨停簇→PRIMARY；纯度≥0.7→SECONDARY；可入池→TERTIARY |
| **volume** | `SURGE` / `NORMAL` / `DRY` | amount/10000 ≥ 8亿→SURGE；3-8亿→NORMAL；<3亿→DRY（注意 hard filter 边界） |

同一只股可同时 `heat=RISING + leader=DIVERGENCE`（非正交）。Step 3 读多个维度的组合做 reasoning。

Pattern.*.confidence：LLM 按 rubric 命中清晰度标 0-100。无历史的 `heat=STABLE` confidence 默认 50。

---

#### V5 Confidence Rules

所有 computed_perception 字段必须携 confidence。公式如下：

| 字段 | Confidence 公式 | 谁算 |
|------|----------------|------|
| `theme_heat.subscores.P/C/E` | LLM 按 rubric 命中等级：90(满档)/75(中等)/55(边缘) | LLM |
| `theme_heat.subscores.N` | `min(news_count/5, 1) × 100` | Python |
| `theme_heat.value` | `min(P, C, E, N confidences)` | Python |
| `news_impact.value` | matrix cell weight × 100 ± adjustments | LLM |
| `major_event.polarity` | Default Neutral=90；P/N by evidence strength (headline=90, body=70) | LLM |
| `risk_type` | 100 (机器查表，固定) | Python |
| `pattern.*.state` | LLM 按 rubric 命中清晰度 0-100 | LLM |
| `tech_score.value` | `present_factor_count / 6 × 100` (fetch_pool_indicators.py V5 内置) | Python |

**Confidence 校准**：V5 上线后 1-2 周统计所有 computed_perception confidence 分布；若某字段 confidence 长期 > 85 则阈值上调 +10。

---

#### V5 Conditional Reread（Step 3 回查条件）

Step 3 **默认不重读 news.md**。仅在以下触发条件下通过 `NewsLink` 指针单条回查：

| 触发条件 | 量化判据 | 回读范围 |
|---------|---------|----------|
| Anomaly 存在 | `Anomaly != "--"` | NewsLink 指向的单条新闻行 |
| 低 Confidence | 任一 `computed_perception.*.confidence < 60` | NewsLink 指向的单条新闻行 |
| 硬矛盾 | 满足下三条之一 | NewsLink + cross_rank |

**三条 Hard Contradictions（机器可判）**：
1. `theme_heat.value >= 80 AND tech_score.value < 40`（主题高热但个股技术面极弱）
2. `major_event.polarity = "Positive" AND composite.value < 50`（有公司正向事件但综合分极低）
3. `auction_change_pct > +3% AND news_impact.value < 40`（竞价强但新闻关联弱）

**严禁**：Step 3 扫全文 news.md 重新做主题映射。

---

#### MajorEvent

V4-U 比 V3 严格 rubric — 默认 `None`：

| Value | Required evidence |
|-------|-------------------|
| **Positive** | 点名公司 + 离散事件：订单中标、重组、业绩 >20% 超、产品获批 |
| **Negative** | 点名公司 + 离散事件：处罚、立案、造假、停牌、大幅减持 |
| **None** | 其他一切 — **包括**行业景气、TSMC 涨价、论坛开幕 |

**Default rule**: 每只股票默认 `None` — 除非新闻明确点名公司并带离散事件。
**Responsibility separation**:
- `ThemeHeat` → 主题级动能
- `NewsImpact` → 新闻关联度与情绪
- `MajorEvent` → 公司级事件 override only

不确定时用 `None`。Uncertainty 不应创造 Positive/Negative flag。

#### NewsImpact Rubric（per-stock, 0-100）

V4-U 二维查表。LLM 选 **一格**，可插值 ±5 并在 Score Trace 给一行 reason。

**Dimension 1: Relevance（rows）**

| Tier | Code | Condition |
|------|------|-----------|
| R4 | Direct | 公司名或代码在头条 |
| R3 | Supply-chain | 客户/供应商/合同方被点名 |
| R2 | Sector | 主题级新闻，无公司名 |
| R1 | Proxy | 仅指数/同行/行业数据 |
| R0 | None | 无关联 — 不应在 pool |

**Dimension 2: Prominence（columns）**

| Tier | Code | Condition |
|------|------|-----------|
| P3 | Headline | 标题主体或首段 lead |
| P2 | Body | 正文提及，material detail |
| P1 | List | 仅表/列表/chain 提及 |
| P0 | Absent | — |

**Score matrix**

|  | P3 Headline | P2 Body | P1 List |
|--|:-----------:|:-------:|:-------:|
| **R4 Direct** | 95 | 85 | 70 |
| **R3 Supply-chain** | 80 | 70 | 55 |
| **R2 Sector** | 65 | 55 | 40 |
| **R1 Proxy** | 45 | 35 | 25 |

**Adjustments（叠加，cap 0-100）**

| Condition | Δ |
|-----------|---|
| 同股同日出现在 ≥2 个新闻源 | +5 |
| Negative sentiment（penalty / investigation） | -20 |
| MajorEvent = Positive / Negative | 用 MajorEvent 替代；NewsImpact **cap=60 for Negative**（缓解 News 双重计入叠加膨胀，见 § Theme Heat 决策②） |

`NewsLink` = 指向 `news.md` 源行的最短指针（如 `flash#3`, `finance#12`）。

#### Anomaly 字段（≤50 中文字）

**目的**：透传 rubric 会扁平化的结构性模式，不重开 prose mapper。

| Allowed | Example |
|---------|---------|
| 模式标签 | `三日缩量首板`, `板块龙头猝死`, `边缘扩散新龙头` |
| 跨主题 | `跨半导体+AI算力` |
| 事件形态 | `涨停开板二次封` |

| Forbidden | 原因 |
|-----------|------|
| 买卖建议 | Step 3 领地 |
| 价格目标 | Step 3 领地 |
| >50 char | 保持表可扫描 |

**必需情形** — 任一即写：

- 股票经由 `market_active` cross_rank_highlights 入池
- LHB 注入且净买入 > 0
- board_streak ≥ 2 但 Composite < 70
- LLM 判定 RiskType 单独不足以描述 setup

否则 `—`。

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

Generate `mapper.md` as a pure structured dataset. **7 sections. No prose anywhere.** Sorted by `composite_score DESC`.

---

#### Section 1: Market State

Structured key-value table。Extract from news.md market overview + 融资 + 指数预读。

```markdown
## Market State

| Field | Value |
|-------|-------|
| DominantThemes | 半导体(91), AI算力(80) |
| FinancingFlow | +61.31亿净买入 |
| RiskFlags | RMBWeakness, APACPressure |
| BoardPolicy | sh688=exclude, bj=exclude |
| RegimeHint | (Step 3 Reasoning territory, not Step 2) |
```

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| DominantThemes | string | themes.md top 2-3 | 不变 |
| FinancingFlow | string | news / fetch_special | 不变 |
| RiskFlags | string | news.md 宏观扫描 | 逗号分隔 token |
| **BoardPolicy** | string | `config/trading-scope.json` | 反映实际排除策略，非硬编码 |
| **RegimeHint** | enum | **Step 3 Reasoning 评定**（不是 Step 2）| Step 2 不输出 RegimeHint。Step 3 据上证竞价 + 科创50 + 主题 heat 综合评定 |

**RegimeHint 阈值**（参考，Step 3 Reasoning 在使用时评定）：

| Value | Condition（上证竞价/昨收） |
|-------|---------------------------|
| panic | < -1.5% |
| weak | -1.5% ~ -0.5% |
| neutral | ±0.5% |
| strong-sector | neutral index BUT dominant theme heat ≥ 85 OR 科创50 > +2% |

#### Section 2: Theme Ranking

V4-U 新增 `HeatTrace` 审计列：

```markdown
## Theme Ranking

| Theme | Heat | Rank | HeatTrace |
|-------|------|------|-----------|
| 半导体 | 91 | 1 | P85/C70/E95/N8 |
```

| Token | 含义 |
|-------|------|
| P | policy 0-100 |
| C | capital 0-100 |
| E | emotion 0-100 |
| N | news_count（整数，归一化前） |

Sorted by Heat DESC. All themes with Heat >= 60。

#### Section 3: Candidate Pool

All stocks with Composite Score >= 55. Sort by Composite DESC.

```markdown
## Candidate Pool

| Code | Name | comp.value | comp.conf | tech.value | tech.conf | th_heat.value | th_heat.conf | news_imp.value | news_imp.conf | maj_ev.pol | risk_type.value | pattern.heat | pattern.leader | pattern.auct | auc.value | anomaly | NewsLink |
|------|------|-----------|---------------|----------------|-------|----------|------------|----------|---------|-----------|-----------|----------|--------------|--------------|---------|------------|
| sh603986 | 兆易创新 | 86.7 | 87 | 78.5 | 100 | 91.0 | 88 | 88 | 90 | Neutral | overbought | RISING | STABLE | LEADING | 92.5 | 缩量首板板块龙头启动 | flash#2 |
| sh600048 | 保利发展 | 42.1 | 50 | 23.7 | 67 | 35.0 | 55 | 35 | 90 | None | oversold_opportunity,trend_weak | FALLING | ABSENT | LAGGING | 10.0 | 利空出尽缩量 | — |
```

Column sources：

| Column | Source |
|--------|--------|
| comp.value | Composite score (Python 加权，V5 下沉)  |
| comp.conf | Composite confidence (weighted avg of sub-confidence) |
| tech.value | tech_score from Phase 2 |
| tech.conf | present_factor_count/6 × 100 |
| th_heat.value / .conf | ThemeHeat from themes.md |
| news_imp.value / .conf | NewsImpact R×P cell |
| maj_ev.pol | MajorEvent Polarity (Positive/Negative/Neutral) — V5 不拆 Detection/Impact |
| risk_type.value | From Phase 2（Step 2 分类，machine lookup） |
| pattern.* | V5 Pattern 5 维度 — heat/leader/auction/rotation/volume |
| auc.value | Auction score |
| anomaly | V5 Anomaly ≤50 中文字（pattern summary） |
| NewsLink | news.md 源行最短指针 |
| Direction / Severity | **Step 3 Reasoning output** (not in mapper.md Candidate Pool) |
| Anomaly | ≤50 中文字，看 § Anomaly 字段；无则 `—` |
| RoleTags | From ThemeRole query (Anchor/IndustryLeader/Candidate/MultiTheme) |

#### Section 4: Strategy Inputs

**ALL** Candidate Pool stocks must be covered. Do NOT truncate to Top 5 or Top 8。Candidate Pool > 50 行时按 Composite 降序每 25 行一个子表（P3-3）。

```markdown
## Strategy Inputs

| Code | Price | PriceSource | MA20 | ATR | ATR% | High20 | Low20 |
|------|-------|-------------|------|-----|------|--------|-------|
```

Data source: K-line records from Technical Enrichment Phase 2. No additional API calls.

| Column | Source / Formula | Notes |
|--------|--------|---------|
| **Price** (P0-6) | `fetch_stock.py` Phase 1 ; fallback to `price` from Phase 2 | 三态：昨收 / 竞价 / 盘中实时 |
| **PriceSource** (P0-6, V4-U 新增) | `PrevClose` \| `Auction` \| `Live` | 解决 V3 Price 字段三态漂移 |
| MA20 | `ma20` field | Phase 2 |
| ATR | `atr` field | Phase 2 |
| ATR% | `atr_pct` field | Pre-computed |
| High20 | `high20` field | Pre-computed |
| Low20 | `low20` field | Pre-computed |

**PriceSource 三态决定**（V4-U P0-6）：

| PriceSource | 含义 | 运行时机 |
|-------------|------|----------|
| `PrevClose` | 昨日收盘 | pre-market < 9:15 |
| `Auction` | 集合竞价价 | 9:15-9:25 |
| `Live` | 盘中实时 | intraday 运行 |

#### Section 5: Score Trace（V4-U 新增）

每行一个 Candidate Pool 股。无 prose 也能审计。

```markdown
## Score Trace

| Code | CompositeTrace | DirectionPath | NewsImpactCalc |
|------|----------------|---------------|----------------|
| sh603986 | comp: T91×0.3+N88×0.2+A92.5×0.2+Tech78.5×0.2+MF50×0.1=86.7 | perception: R4×P3=95→88; present_factors=6/6 conf=100 | Direction/RiskSeverity/Override → Step 3 ReasoningTrace |
```

| Column | Content |
|--------|--------|
| CompositeTrace | 加权项 → 四舍五入结果 |
| PerceptionTrace | computed_perception 子分推导路径 (ThemeHeat/NewsImpact/tech_score formula form) |
| ReasoningPath | **空白列（Step 3 ReasoningTrace 填充）** — mapper.md 只留占位列 |

**最低形式要求**：Candidate Pool 表必须含 `CompositeTrace` 列。Score Trace 表对 `Composite ≥ 70` 的股票强制（其余可选）。

`CompositeTrace` 紧凑形式：`T<theme_heat>×0.3+N<news_impact>×0.2+A<auction>×0.2+Tech<tech_score>×0.2+MF<money_flow>×0.1=<composite>`。
DirectionPath 格式：**空白列** — Direction 属 Step 3 Reasoning output，不在 mapper.md。本列供 Step 3 回填 ReasoningTrace。

#### Section 6: Observation Pool

All stocks with Composite Score < 55. Full list, no truncation. 新增 Anomaly 列（V5）— 含 risk flag 但仍值得次日观察的可见标记。

```markdown
## Observation Pool

| Code | Name | Composite | Theme | Reason | Anomaly |
|------|------|-----------|-------|--------|---------|
| sz000123 | 某股 | 48 | 半导体 | BelowThreshold | 三日缩量首板 |
```

Reason examples:
- `BelowThreshold` — Composite < 55
- `TechnicalRisk` — tech_score < 50 / RiskSeverity=3 但 keeping for watch
- `WeakTheme` — theme heat below threshold
- `Indicators_Fetch_Failed` — Phase 2 placeholder (P0-7)
- `IndicatorsMissing` — 全部 traditional 因子缺数据 (P0-4)

#### Section 7: Excluded Stocks

Extracted from theme_stocks.md `### Removed Stocks` 节。新增 `ExclusionSource` 列（V4-U）：

```markdown
## Excluded Stocks

| Code | Name | ExclusionReason | ExclusionSource |
|------|------|-----------------|-----------------|
| sh688256 | 寒武纪 | 科创板不可交易 | board-policy |
| sz300975 | 商络电子 | atr_pct=9.0% > 8% | hard-filter |
```

| ExclusionSource | Meaning |
|-----------------|---------|
| `board-policy` | `config/trading-scope.json` 驱动（sh688/bj） |
| `hard-filter` | liquidity < 3亿 / atr_pct > 8% |
| `indicators-fetch-failed` | Phase 2 fetch 失败（P0-7） |
| `soft-filter` | tech_score < 50 |
| `manual` | LLM 显式排除并附 reason |

---

### Board Exclusion Policy (V4-U 配置化)

写入 `.opencode/skills/daily-stock-mapping/config/trading-scope.json`：

```json
{
  "boards": {
    "sh688": { "exclude": true, "reason": "STAR board — account scope" },
    "bj":    { "exclude": true, "reason": "BSE — account scope" },
    "sh":    { "exclude": false },
    "sz":    { "exclude": false }
  },
  "overrides": []
}
```

Step 2 读 config → 写 `BoardPolicy` 到 Market State。overrides 允许单代码例外，无需改 SKILL。

**影响**：toggled 时半导体/AI 主题 688 龙头以 `ExclusionSource=board-policy` 出现在 Excluded Stocks，非沉默丢弃。

---

### Deleted Content

The following sections and content types are **NEVER** included in mapper.md:

- Market background prose（市场背景 / 大盘方向 / 情绪温度 paragraph）
- Tiered ranking labels（第一梯队 / 第二梯队 classification）
- 个股分解分析 prose paragraphs（新闻影响分析 / 技术面分析 / 资金面分析 / 综合）
- 行业资金流向 prose section（行业资金流向 with prose commentary）
- 总结 / 综合评价 / 核心标的 / 风险点评 / 风格偏好 全段
- 支撑/阻力位、ATR Stop Distance、VWAP 等 derived levels
- 任何形式的买卖建议或 stop/target
- Direction 推导 prose（Step A/B/C 中间态不写 mapper.md；Direction 属 Step 3 Reasoning output，Mapper 不输出）
- NewsImpact 矩阵选择 prose（仅 Score Trace 写一行 calc，无段落）
- Anomaly > 30 字或含买卖建议 / 价格目标

---

### Step 3 Read Contract（V4-U 新增）

Step 3 **MUST** read in order:

1. `Market State`：`BoardPolicy`, `DominantThemes`, `FinancingFlow`, `RiskFlags`
2. `Candidate Pool`：`comp.value`, `comp.conf`, `tech.value`, `tech.conf`, `th_heat.value`, `th_heat.conf`, `news_imp.value`, `news_imp.conf`, `maj_ev.pol`, `risk_type.value`, `pattern.*`, `auc.value`, `anomaly`, `NewsLink`
3. `Strategy Inputs`：`Price`, `PriceSource`, `MA20`, `ATR`, `ATR%`, `High20`, `Low20`
4. `memory/RULES.md`
5. `news.md`（**仅做 Conditional Reread 单条回查** — 见 § V5 Conditional Reread 触发条件）

Step 3 **MUST NOT**:

- 重新派生 Composite 或 NewsImpact（Python 已算且每字段带 confidence）
- 扫全文 news.md 重新做主题映射（严禁 — V5 Invariant 2）
- 忽略 `computed_perception.*.confidence < 60` 的低置信信号
- 重新 fetch Strategy Inputs 已给字段（除非 missing/null/stale）

**示例 decision log 行（目标格式）**：

```
sh603986: comp=86.7(py), risk_type=overbought, pattern=heat_RISING+leader_STABLE → Direction=bullish, RiskSeverity=2(R37 trigger), Regime=strong-sector → retain 4★
```

---

### Step 2 → Step 3 Data Contract

The **Strategy Inputs** table in mapper.md is the **authoritative source** for Step 3 on these fields:

- Price
- PriceSource
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

**Default behavior: no re-fetch.** Step 3 loads Strategy Inputs and proceeds.

**V5 新增约束**：Step 3 默认不重读 news.md（Conditional Reread 触发除外）。Python 已给 `composite.value` + 子分 confidence — Step 3 直接消费，不经两步推导。

---

### Migration: V4-U → V5

| V4-U field | V5 mapping |
|----------|-------------|
| DirectionBase / DirectionFinal | → **Removed from Step 2** (Step 3 Reasoning output) |
| MajorEvent | → `maj_ev.pol` (polarity stays Step 2; weight stays Step 3) |
| RiskSeverity | → **Removed from Step 2** (Step 3 derives from RiskType + Regime) |
| OverrideHint placeholder | → **Removed from Step 2** (Step 3 applies from RULES.md) |
| (none) | + Pattern 5 dimensions (heat/leader/auction/rotation/volume) |
| (none) | + per-field confidence (all computed_perception fields) |
| (none) | + Conditional Reread mechanism (3 triggers + 3 hard contradictions) |

**Backward compatibility**：V5 不向后兼容 V4-U。V5 mapper 不含 Direction/RiskSeverity/OverrideHint — Step 3 自行推理。V4-U mapper 输入 V5 Step 3 可兼容（缺 Direction 时 Step 3 自行推理 Direction + Severity）。

---

## Open Questions（ retained，Phase 5 companion 阶段定）

1. Score Trace 强制范围：建议 `Composite ≥ 70` 强制，其余可选 — 待 Phase 5 落定
2. `RegimeHint` vs Step 3 intraday index fetch 重叠：intraday Step 3 实时 fetch authoritative，RegimeHint 仅 pre-market prior — 已确认
3. `R73 / R74` 在 `memory/RULES.md` 是否已定义：Phase 5 落定后启用 OverrideHint token
4. MACD 加速判定阈值 `mh > prev_mh` 用 0 量级还是 0.1 量级：脚本暂定 `abs(mh) < 0.05` 判 crossing
5. `query_theme.py pure --all-themes` 批量化：作为 follow-up issue 跟进
6. News 双重计入权重问题：决策② 接受 V4 cap=60 缓解方案 — 已确认
