---
name: daily-stock-mapping
description: Step 2 of daily-market-analysis pipeline. Consumes canonical news.json plus readable news.md, produces themes.json, validated theme_stocks.json, mapper.annotations.json, validated mapper.json, and mapper.strategy_view.json.
---

# Daily Stock Mapping

Loaded by the `sector-analyst` subagent as Step 2 of the daily-market-analysis pipeline.

## Stage I/O

| Stage | Input | Output |
|-------|-------|--------|
| Theme Extraction | compact input from canonical news.json | themes.json |
| Prepare | themes.json + structured market/news/LHB sources | theme_stocks.json + compact mapper input |
| Structured Dataset | theme_stocks.json | mapper.annotations.json -> mapper.json -> mapper.strategy_view.json |

## Scope

Trading scope is config-driven — see `config/trading-scope.json`. Do not hard-code board exclusions in generated artifacts or scripts; apply the config decision and record the matched rule/reason.

**Core Rule:** Theme Library is the ONLY valid source of themes and theme-stock mappings. Never invent themes, concepts, or stocks.

**JSON contract rule:** the two LLM stages write only `predict/{date}/themes.json` and candidate-complete sparse `predict/{date}/mapper.annotations.json`. Scripts own theme/stock membership, source flags, Pattern defaults, assembly, and validation. `theme_stocks.annotations.json` has been deleted with no compatibility reader. Step 2 does not generate Markdown files.

**Format Rule:** The LLM authors JSON perception annotations, not full machine artifacts. Scripts own validated JSON assembly.

**Layer Boundary (V5):** This skill is **perception only** — classification, detection, and pattern recognition. Python scripts produce `raw_observation` + `computed_perception` per stock (each field with `{value, confidence, trace}`). **Direction / RiskSeverity / OverrideHint are Step 3 (Reasoning) territory.** Step 2 NEVER produces Direction, buy/stop/target, or strategic judgment.

## Red Flags — STOP and Restart

| Symptom | Fix |
|---------|-----|
| Skipped `themes.json` validation | Validate `themes.json` before building the stock universe. |
| `themes[].status` uses `excluded`, `candidate`, or another synonym | Replace it with exactly one of `tradeable`, `watch`, or `discarded`, then revalidate. |
| Skipped deterministic `theme_stocks.json` publication | Run `uv run --frozen ashare-pilot mapping daily prepare`; do not hand-write membership or source flags. |
| Skipped `mapper.annotations.json` or `mapper.json` | Generate annotations, then run annotation validation, JSON build, and mapper validation before Step 3. |
| Theme name not in Theme Library | Discard. Theme Library is the only source. |
| Stock in pool but source not in {candidates, market, news_direct, lhb} | Remove. All stocks must be traceable. |
| Scope-excluded stock entered `theme_stocks.json.stocks[]` | Move to `board_excluded[]` using `config/trading-scope.json` matched rule/reason. |
| LLM hand-wrote the complete `mapper.json` | Regenerate through the mapper JSON scripts; LLM should provide perception annotations, not own the full file contract. |
| `uv run --frozen ashare-pilot mapping daily build-theme-stock-universe` skipped `themes.json` | Build from validated `themes.json`, then build base from the locked universe. |
| Step 2 produces Direction / RiskSeverity / OverrideHint | Violation (V5 Invariant 1). Step 2 is Perception only. |
| Step 2 makes causal inference ("capital inflow drove rally") | Violation. Correlation OK; causation forbidden. |
| Candidate Pool row missing `CompositeTrace` or confidence | Re-add. V5 audit trail is mandatory. |
| `risk_flags` contains liquidity tokens | Remove. Liquidity hard-filter is handled separately. |
| Stock with `fetch_failed: true` enters Candidate Pool | Move to Observation Pool, reason=`Indicators_Fetch_Failed`. |
| `Strategy Inputs` numeric values differ from `pool_indicators.json` | Fix base inputs or annotations, then rerun `uv run --frozen ashare-pilot mapping daily build-mapper-base`, `uv run --frozen ashare-pilot mapping daily build-mapper`, and `uv run --frozen ashare-pilot mapping daily validate-mapper`. |

---

## Theme Extraction

**Objective:** Match news items to themes from Theme Library via retrieval, not generation.

First run `uv run --frozen ashare-pilot mapping daily build-theme-evidence`.
That deterministic command owns reads of canonical `news.json` and the Theme
Library. For the LLM phase, read only `.theme_evidence_input.json` and
[references/theme-evidence-rubric.md](references/theme-evidence-rubric.md).
Do not reopen `news.json`/`news.md`, query the full theme list, or inspect any
stock/mapper artifact.

### Match News to Themes

Use every evidence row supplied by `.theme_evidence_input.json`. Match those
retrieved rows using, in priority order:

1. Theme name (exact)
2. Aliases (exact)
3. Keywords (exact)
4. Member concepts
5. Semantic alignment (weakest)

One news item may match multiple themes.

### Theme Confidence

For each matched theme, calculate `confidence` (0-100):

| Confidence | Meaning |
|------------|---------|
| 90-100 | Explicit theme/concept name in news text |
| 75-89 | Strong keyword or alias match |
| 60-74 | Semantic match with supporting evidence |
| <60 | Weak — discard |

Discard `confidence < 60`.

### Theme Heat

Calculate `theme_heat` (0-100) as **Base Heat (daily signals) + Policy Bonus (fine-tuning)**:

```
Base Heat  = market_action × 0.45 + emotion × 0.30 + news_density × 0.15 + capital × 0.10
Final Heat = Base Heat + PolicyBonus × PolicyPolarity
```

| Base Factor | Weight | Meaning |
|-------------|--------|---------|
| market_action | 45% | Sector price/volume/limit-up direction (**the market votes**; direction is endogenous: up→high, down→low) |
| emotion | 30% | Media attention and sentiment (**direction-gated** — see rubric) |
| news_density | 15% | Related news count density (raw integer, normalized to 0-100 before weighting) |
| capital | 10% | Capital activity / financing / institutional participation (**use data when available, default 45 otherwise — minimal impact**) |

Policy is a **low-frequency stock variable** (policies change weekly/monthly) while heat needs **daily-frequency** ranking (markets change daily). It is therefore a capped bonus, not a weighted factor. Policy can **amplify** heat and act as a tiebreaker, but cannot **create** heat (a dead theme at Base 30 + 10 bonus = 40, still cold; a crash theme with max national-strategy bonus still cannot overcome the direction gate).

Direction is carried by the **emotion gate + market_action dual axis**: crash themes collapse on both, bullish themes rise on both, policy bonus alone cannot rescue.

**Policy Bonus (0-10, capped, polarity-gated):**

```
Final Heat = Base Heat + PolicyBonus × PolicyPolarity

  PolicyPolarity:
    Bullish for the theme (policy supports/boosts)  → +1.0  (full bonus)
    Neutral / ambiguous / long-term background      → +0.5  (halved, default)
    Bearish for the theme (policy suppresses/hurts) →  0.0  (zero — bearish policy must not inflate heat)
```

| Tier | Bonus | Criteria |
|------|:-----:|----------|
| None | +0 | No policy angle |
| Local | +2 | Province/city-level document, local pilot |
| Ministry | +5 | Ministry-level (MIIT/NDRC/CSRC) document or statement naming the theme |
| State Council | +8 | State Council executive meeting / document naming the theme |
| National Strategy | +10 | Written into national strategy / five-year plan (e.g., domestic chip independence) |

**Polarity judgment (per-theme, from `news.json`):**
- **Bullish (+1.0)**: Policy text contains language like "encourage / support / promote / subsidy / tax cut / relax / establish / pilot / development plan" → policy direction aligns with the theme's interests.
- **Neutral (+0.5)**: Policy is a long-term / background / routine document (e.g., regulatory framework, industry standard) or text contains "standardize / improve / revise / adjust" with no clear directional impact → **default value**.
- **Bearish (0.0)**: Policy text contains "tighten / cancel subsidy / tax increase / restrict / phase out / crackdown / inspection" → policy direction **suppresses** the theme. Must NOT award positive bonus.

> **Hard constraint**: Polarity judgment for a theme must cite a specific
> `news.json` item as `news#<id>`. A bearish policy receiving a non-zero bonus =
> direction bug — same class of error as the emotion direction gate treating
> panic as bullish. When uncertain about polarity, use `+0.5` (neutral) and
> annotate `polarity=uncertain`.
>
> **Polarity can differ across themes**: The same policy can have different directions for different themes — "restrict fuel vehicles" is bullish for New Energy Vehicles (+1.0) but bearish for traditional auto (0.0).

---

### Sub-score Rubrics (LLM MUST follow)

**Policy:** No longer a 0-100 sub-score. Apply the Policy Bonus table above with **polarity gate** (bullish ×1.0 / neutral ×0.5 / bearish ×0.0). Only count **fresh, same-day** policy that explicitly names the theme; stale/background policy still gets its tier bonus → then through polarity gate. Polarity judgment must cite a specific `news#<id>` from `news.json`. When uncertain, default to `+0.5` (neutral) and annotate `polarity=uncertain`. Theme survival depends solely on `Final Heat`.

**Capital (C) — weight 10%, default 45 when no data:**

| Score | Condition |
|-------|-----------|
| 85-100 | Financing inflow / dragon-tiger net buy aligned with theme (today or yesterday) |
| 65-84 | Sector volume expansion, margin expansion |
| 45-64 | Neutral |
| <45 | Outflow or no signal — use 45 default |

**Emotion (E) — attention × direction gate:**

Step 1 — Raw attention score `E_raw` (media/attention density, direction-agnostic):

| Score | Condition |
|-------|-----------|
| 90-100 | ≥3 flash items + hot-stock list + limit-up/down cluster in theme (high attention only) |
| 75-89 | 2 news items or 1 major headline |
| 60-74 | Semantic match only, low media density |
| <60 | Discard |

Step 2 — Direction coefficient. Determine from canonical `news.json` items whether the theme's attention is bull-driven or panic-driven:

| Theme Direction | Criteria | Coeff |
|-----------------|----------|:---:|
| Bullish catalyst | Limit-up cluster / sector leading / net inflow / positive headline catalyst | ×1.0 |
| Mixed / neutral | Mixed price action, no consensus direction | ×0.8 |
| Panic / crash-driven | Sector crash / limit-down cluster / trending due to sell-off / MajorEvent=Negative dominant / "crash·dump·liquidation·avoid" semantics | ×0.5 |

`emotion = E_raw × direction_coefficient`

> **Purpose:** Prevent panic-driven high attention from being misread as high bullish heat. Crash sectors still earn high `E_raw` for high attention, but the direction gate clamps emotion to ~0.5, preventing them from monopolizing the tradeable pool.

**market_action (M) — sector price/volume momentum.** Direction is endogenous (up→high, down→low). Data source: price signals in canonical `news.json` items (market sentiment hot-list, commodity moves, limit-ups, sector moves). If the Stock Pool Build stage has already fetched query_theme `market` views, use `top_gainers` / `cross_rank_highlights` as corroboration.

| Score | Condition |
|-------|-----------|
| 85-100 | ≥2 limit-ups in theme / sector top gainer / top_gainers cluster (≥3 stocks ≥5%) |
| 65-84 | One limit-up or sector outperforming / multiple ≥3% / cross_rank bellwether launch |
| 45-64 | Mixed, flat sector, no clear direction |
| 25-44 | Sector declining, capital outflow |
| <25 | Sector crash / limit-down cluster / panic sell-off |

**News density (N) —** Integer count of distinct news items mapped to the theme (display cap 10). Normalized as `min(count, 10) / 10 × 100` for weighting.

### Catalyst Exception (LLM-discretionary, high-quality single-catalyst override)

`market_action` is **backward-looking** pre-market and will miss sectors that were dormant yesterday but are ignited by today's news (e.g., a first-ever IPO approval sparking the robotics sector). Allow the LLM a narrow exception for a single high-quality catalyst — strict whitelist + guardrails, **default to not triggering**.

**Trigger (all 3 conditions must hold):**

1. A **fresh, same-day** single catalyst in one of these whitelist categories:
   - Industry-first / landmark **IPO** ("first X stock on A-shares", bellwether listing)
   - **First-ever** national policy/strategy release (not stale policy; stale policy is covered by Policy Bonus)
   - Bellwether company **flagship product launch / technology breakthrough** (industry-level)
   - National-level / far-above-expectation **major contract win**
2. Direction is **bullish or neutral** (if the catalyst stock gaps down / is sold off → no promotion)
3. Catalyst is **single, nameable, traceable** to a specific news line (NewsLink required)

**Effect:**

- LLM may set `Final Heat = max(original_Final, 57)` — just enough to cross the threshold, not inflated (catalyst is expectation, not confirmation).
- **Mandatory tag:** `CATALYST(price-unconfirmed)`, confidence = 60 (below normal, marking expectation).
- HeatTrace notes the override, e.g.: `M45/E80×1.0/N20/C45 Base52 →Cat57 [IPO news#42]`.

**Guardrails (MUST):**

- Maximum **2** Catalyst exceptions per day (prevent LLM from promoting every positive item).
- Only **first-ever / national-level / bellwether flagship** events qualify; routine positives (ordinary contract wins, minor product launches, second-tier company announcements) do **NOT** trigger.
- Does **NOT** stack with Policy Bonus — Catalyst Exception is a floor on Final (`max`), not an additional bonus.
- Exception tag passes through to mapper → Step 3; **Step 3 MUST use "first 5-min candle confirmation" entry** (buy only on volume-backed green candle; abandon on gap-up-then-fade), reusing the defensive entry pattern to avoid gap-trap risk.

### Rank & Filter

Sort by `Final Heat DESC`.

- **Tradeable pool:** `Final Heat >= 55`. Max 20 themes. (Includes Catalyst Exception themes promoted to 57, tagged `CATALYST`.)
- **Watch Themes:** `40 <= Final Heat < 55` AND direction is bullish (emotion coefficient ×1.0, or market_action >= 50). Mark `status = "watch"` in `themes.json`. **Not tradeable, no position, excluded from Stock Pool Build.** Visible to Step 3 for rotation awareness. Panic/crash-driven themes do NOT enter Watch (wrong direction, no observation value).
- **Discarded:** Every emitted theme that is neither Tradeable nor Watch. Mark `status = "discarded"` in `themes.json`.

**Hard enum contract for `themes[].status`:**

Use exactly one of these lowercase machine enums: `tradeable`, `watch`,
`discarded`. Do not use semantic or display synonyms such as `excluded`,
`candidate`, `rejected`, or Chinese labels. “Excluded from the tradeable/stock
pool” describes behavior; it is never a valid `status` value.

### Output Contract: themes.json

```json
{
  "schema_version": "daily_themes.v1",
  "date": "YYYY-MM-DD",
  "themes": [
    {
      "rank": 1,
      "name": "AI算力",
      "status": "tradeable",
      "heat": 72,
      "confidence": 92,
      "direction": "bullish",
      "subscores": {
        "market_action": 70,
        "emotion_raw": 80,
        "emotion_coefficient": 1.0,
        "news_density": 60,
        "capital": 45,
        "policy_bonus": 0,
        "policy_polarity": "neutral",
        "base": 68
      },
      "matched_concepts": ["算力", "数据中心"],
      "evidence": "news#2",
      "reason": "AI infra news and market action aligned"
    }
  ]
}
```

Columns: `MktAct` = market_action (Base anchor, 45%); `Emotion(raw)` = pre-gate attention; `Dir` = direction coefficient (×1.0 / ×0.8 / ×0.5); `Capital` = 45 when no data; `PolBonus` = Policy Bonus raw (0-10, before polarity gate); `PolDir` = polarity coefficient (bull×1.0 / neut×0.5 / bear×0.0); `Base` = M×0.45+(E_raw×Dir)×0.30+N×0.15+C×0.10. `Final = Base + PolBonus × PolDir`.

Final Heat < 55 excluded from tradeable pool; 40-54 with bullish direction → Watch Themes.

**Hard enum contract for `themes[].direction`:**

Use exactly one of these lowercase machine enums. Do not invent synonyms, mixed-language labels, or display labels in `themes.json`; human-readable Chinese labels belong only in downstream renderers.

| Enum | Meaning | Emotion coeff |
|------|---------|:---:|
| `bullish` | Bullish catalyst: sector leading, limit-up cluster, net inflow, or positive headline catalyst | ×1.0 |
| `mixed` | Direction split: mixed price action, commodity/news support without equity confirmation, or no consensus | ×0.8 |
| `panic` | Crash-driven attention: sell-off, limit-down cluster, negative major event, or avoid semantics | ×0.5 |
| `neutral` | Background/routine theme with no actionable direction | ×0.8 |
| `unknown` | Direction cannot be determined from cited evidence | ×0.8 |

Validation rejects missing or non-whitelisted direction values. If you need a new direction, update `uv run --frozen ashare-pilot mapping daily validate-themes`, this table, and downstream render labels together; do not add a one-off value in generated JSON.

### Theme Extraction Constraints

- Theme names MUST come from Theme Library
- Never invent themes
- Concepts are matching signals only, not output
- Confidence must be calculated, not guessed
- News `evidence` must cite one or more canonical IDs such as `news#77`; never
  cite category-local positions, Markdown lines/ranges, or legacy
  `themes.md#...`. Non-news market evidence must use its own explicit namespace.

---

## Stock Pool Build

**Objective:** Convert themes into deduplicated stock pools with source-theme tracking.

### Retrieve Candidate Stocks

`uv run --frozen ashare-pilot mapping daily build-theme-stock-universe` reads validated `themes.json` and Theme Library JSON directly for the selected tradeable themes. The LLM writes theme decisions to JSON; it does not hand-build the stock pool table or pass theme lists as CLI text. `uv run --frozen ashare-pilot mapping daily build-theme-stock-base` only reads the locked universe plus refreshed indicators.

For supplemental stocks that are not already covered by the Theme Library candidate path, write one optional JSON file before building the universe:

```text
predict/{date}/theme_stocks.extra.json
```

Shape:

```json
{
  "schema_version": "daily_theme_stocks_extra.v1",
  "date": "YYYY-MM-DD",
  "stocks": [
    {
      "code": "sz300308",
      "name": "中际旭创",
      "source": "news_direct",
      "source_themes": ["AI算力", "光通信"],
      "score": 85,
      "news_ref": "news#77",
      "market_ref": "top_amount#1"
    }
  ]
}
```

Allowed `source` values are descriptive, not filtering authorities: `market_active`, `news_direct`, `lhb`, or `manual`. Scope and technical filters still apply in scripts.

If using `uv run --frozen ashare-pilot themes query market`, place selected active names in `theme_stocks.extra.json`; do not add more CLI stock parameters.

The market view can provide evidence for extra stocks:

| Field | Content | Use |
|-------|---------|-----|
| `cross_rank_highlights` | Stocks in ≥2 top-N lists, with `attention_score` + `industry_score` | Edge diffusion, bellwether launch, theme mainline signals |
| `market_attention` | Composite: 0.6×turnover + 0.25×turnover_rate + 0.15×volume_ratio (percentile ranks) | Stocks with `attention_score >= 80` → add as `source = "market_active"` |
| `top_gainers` | Strongest by `change_pct`, with `industry_score` | Stocks with `change_pct >= 3%` → add as `source = "market_active"` |

### Inject News-mentioned Stocks

Scan `news.json.items` for explicitly mentioned A-share stocks (codes or names).
Use `news.md` only for narrative context. For each selected supplemental stock:
1. Resolve name → code via `uv run --frozen ashare-pilot market-data quote --search` or LLM knowledge
2. Add it to `theme_stocks.extra.json` with `source = "news_direct"`, score = rough NewsImpact estimate
3. Mark `news_direct: true`

News-mentioned stocks skip theme-library constraints but NOT the board filter.

```bash
uv run --frozen ashare-pilot market-data quote --search "Stock Name" --json
```

### Dragon & Tiger List Injection

```bash
uv run --frozen ashare-pilot market-data special lhb --json
```

For each LHB stock (~50 records):
1. Look up theme membership: `uv run --frozen ashare-pilot themes query stock <code> --json`
2. If the stock belongs to ANY selected tradeable theme → add to `theme_stocks.extra.json`
3. Mark `source: lhb` with score: net buy > 0 = 85; limit-up = 90; limit-down = skip

### Supplement with Pure Stocks

`uv run --frozen ashare-pilot mapping daily build-theme-stock-universe` already includes top pure stocks from Theme Library. Increase `--top-pure` only when the generated universe is too narrow.

### Deduplicate & Board Filter

1. Merge `source_themes` lists, keep highest score across themes, record all theme associations
2. Apply board filter from `config/trading-scope.json`; use the matched config rule/reason, never hard-code excluded prefixes
3. News-mentioned (`news_direct: true`) and LHB stocks bypass score-based dedup but NOT the board filter

### Stock Pool Constraints

- Stocks come from Theme Library plus optional `theme_stocks.extra.json` entries for market/news/LHB supplemental names
- Never generate stocks manually — must be traceable to a source
- `source_themes` must be preserved
- LHB and news-mentioned stocks may be added through `theme_stocks.extra.json`, but they still go through scope and technical filters
- Board filter applied BEFORE Technical Enrichment — never fetch indicators for excluded boards
- If a theme's post-filter candidate count drops below 8, re-run pure stock supplement with `--top 20` (max 1 round)

---

## Technical Enrichment

**Objective:** Enrich each stock with market data and technical indicators, then filter out disqualified stocks.

### Fetch Data — Phase 1: Auction Snapshot

```bash
uv run --frozen ashare-pilot market-data quote <code_1>,<code_2>,...,<code_N> --json
```

Combine ALL pool stocks into ONE comma-separated call. During call auction (9:15-9:25), returns live auction data.

| Auction Metric | JSON Field | Notes |
|---------------|-----------|-------|
| Auction Change% | `percent` | `(price - yestclose) / yestclose × 100` |
| Auction Amount | `amount_10000` | Cumulative auction turnover, unit: 万 (10k CNY) |
| Auction Turnover Rate | `volume` / float_shares | Optional; `null` if float_shares unavailable |

### Fetch Data — Phase 2: Technical Indicators

```bash
uv run --frozen ashare-pilot indicators pool fetch <code_1>,<code_2>,...,<code_N> --json -o <output_file>
```

**Timeout: 5 minutes** (fetch + compute across full pool). One call covers the entire pool. Output is a flat JSON array — 25 fields per stock across 3 layers (raw indicators, feature engineering, scoring). All numeric values are float/int.

Key output fields:

| Field | Layer | Purpose |
|-------|-------|---------|
| `price`, `close` | K-line | Current price, yesterday's close |
| `turnover`, `change_pct`, `amount` | K-line | Turnover rate, change%, amount (万) |
| `rsi`, `macd`, `macdh` | Indicator | RSI(14), MACD line & histogram |
| `ma20`, `ma50` | Indicator | 20-SMA, 50-SMA |
| `boll_ub`, `boll_lb` | Indicator | Bollinger bands |
| `atr`, `atr_pct` | Indicator | ATR(14), ATR as % of close |
| `high20`, `low20` | Feature | 20-day high/low |
| `percent_b` | Feature | `(close - boll_lb) / (boll_ub - boll_lb)` |
| `board_streak` | Feature | Consecutive limit-up days (int) |
| `seal_quality` | Feature | `sealed` / `unsealed` / `broken` / `—` |
| `limit_up_freq` | Feature | Limit-up count in last 10 records |
| `traditional` | Score | 6-factor weighted sub-score (0-100) |
| `sentiment` | Score | max(board_sentiment, market_sentiment) |
| `tech_score` | Score | `traditional × 0.70 + sentiment × 0.30` |
| `risk_flags` | Score | Array of risk markers (e.g. `["RSI>75","MA_bear"]`) |
| `vol_ratio_5d` | Feature | Today's amount / 5-day avg amount |

### Missing Data Handling

When a factor's raw data is `None`: skip that factor's sub-score, renormalize remaining weights by `present_weight / sum(present_weights)`. If all 6 traditional factors are missing: `traditional = null` → `tech_score = null` → stock demoted to Observation Pool (`IndicatorsMissing`). If Phase 2 fetch fails entirely: JSON `{"code", "fetch_failed": true}` → Observation Pool (`Indicators_Fetch_Failed`).

### Scoring: tech_score

Pre-computed by `uv run --frozen ashare-pilot indicators pool fetch`. Read directly; no recalculation needed.

```
tech_score = Traditional × 0.70 + Sentiment × 0.30
```

**Traditional sub-score:** MA_Trend(22%) + MACD_Mom(19%) + RSI(13%) + Liquidity(22%) + BB_Position(16%) + ATR_Risk(9%)

| # | Factor | Weight | Scoring |
|---|--------|--------|---------|
| 1 | MA Trend | 22% | Price > ma20 > ma50 = 100; Price > ma20, ma20 < ma50 = 60; Price < ma20, ma20 > ma50 = 40; Price < ma20, ma20 < ma50 = 0 (dual bear) |
| 2 | MACD Mom | 19% | macdh > 0 and accelerating = 100; macdh > 0 = 75; abs(macdh) < 0.05 (crossing 0) = 50; macdh < 0 not deepening = 25; macdh < 0 and deepening = 0 |
| 3 | RSI | 13% | 45-60 = 100; 60-70 = 80; 30-45 = 70; 70-75 = 40; >75 or <30 = 0 |
| 4 | Liquidity | 22% | amount in 亿: ≥5 = 100; 3-5 = 70; 1-3 = 40; <1 = 0 |
| 5 | BB Position | 16% | percent_b 0.4-0.6 = 100; 0.6-0.8 = 80; 0.2-0.4 = 70; >0.8 = 60; <0.2 = 20 |
| 6 | ATR Risk | 9% | atr_pct 1.5-3% = 100; 3-5% = 70; <1.5% = 60; >5% = 30 |

**Sentiment sub-score:** max(Board Sentiment, Market Sentiment)

**Board Sentiment** = Board Streak(50%) + Limit-up Frequency(25%) + Seal Quality(25%)

| Factor | Weight | Scoring |
|--------|--------|---------|
| Board Streak | 50% | ≥3 = 100; 2 = 85; 1 = 65; 0 = 0 |
| Limit-up Freq | 25% | ≥3 = 100; 2 = 80; 1 = 60; 0 = 0 |
| Seal Quality | 25% | sealed = 100; unsealed = 60; broken = 15; — = 0 |

Broken-board decay: when `board_streak == 0` and `limit_up_freq >= 2`, streak_s = max(0, 45); freq ≥1 → max(0, 35); first day after break → max(0, 40).

**Market Sentiment** = Turnover Rate(35%) + High20 Proximity(25%) + Volume Ratio(20%) + Momentum(20%)

Direction correction: when `change_pct < 0`, Turnover and Volume Ratio sub-scores ×0.5 (prevents high-volume sell-off from being misread as high sentiment).

| Factor | Weight | Scoring |
|--------|--------|---------|
| Turnover Rate | 35% | ≥10% = 100; 5-10% = 85; 3-5% = 70; 1-3% = 55; 0.5-1% = 35; <0.5% = 20 |
| High20 Proximity | 25% | close ≥ h20×0.99 = 100; ≥0.95 = 85; ≥0.88 = 65; ≥0.75 = 45; <0.75 = 25 |
| Volume Ratio | 20% | ≥2.0 = 100; 1.5-2.0 = 85; 1.2-1.5 = 70; 0.8-1.2 = 50; 0.5-0.8 = 35; <0.5 = 20 |
| Momentum | 20% | abs(change_pct): near limit = 100; ≥7% = 90; ≥5% = 80; ≥3% = 65; ≥1% = 50; ≥0% = 35; <0% = 20 |

### Hard Filters

Remove stocks that fail ANY hard filter:

| Filter | Reject Condition | Data Source | ExclusionSource |
|--------|-----------------|-------------|-----------------|
| Liquidity | `amount` < 30000 (万) = 3亿 | fetch_pool_indicators | `hard-filter` |
| Extreme Volatility | atr_pct > 8% | fetch_pool_indicators | `hard-filter` |
| Fetch failed | `fetch_failed: true` | fetch_pool_indicators | `indicators-fetch-failed` |

### Technical Risk Flags

Risk markers only — **not auto-reject**. Step 2 classifies RiskType; RiskSeverity is Step 3 territory.

| Flag | Condition | RiskType (Step 2) |
|------|-----------|-------------------|
| RSI>75 | RSI > 75 | `overbought` |
| RSI<30 | RSI < 30 | `oversold_opportunity` |
| MA Bear | Price < ma20 AND ma20 < ma50 | `trend_weak` |
| Broken Board | seal_quality = "broken" | `broken_board` |
| Auc<-5% | auction change < -5% | `auction_anomaly` |

### Soft Filter

- Keep stocks with `tech_score >= 50`. `tech_score = null` → Observation Pool.
- Stocks with `tech_score 50-59`: flag `tech_risk: true`.
- Risk flags alone do NOT remove stocks from pool.

### Output Contract: deterministic theme_stocks.json

After the LLM writes and validates `themes.json`, run the prepare orchestration:

```bash
uv run --frozen ashare-pilot mapping daily validate-themes --date {YYYY-MM-DD}
uv run --frozen ashare-pilot mapping daily prepare --date {YYYY-MM-DD}
```

Do not run `prepare` until `validate-themes` passes. If validation fails, the
same theme-extraction LLM stage must correct only the reported contract fields
and rerun `validate-themes` once. If the second validation fails, stop and
report the remaining errors; never let `prepare` discover a known-invalid
`themes.json`.

Prepare validates themes, batches selected-theme market views, generates source flags from actual Theme Library/news/market/LHB inputs, expands the universe, fetches indicators sequentially, publishes `theme_stocks.json`, and writes `.mapper_annotation_input.json`. Missing sources remain false. Intermediate files contain no translated source prose or `source_explanation`.

---

## Structured Dataset Generation

**Objective:** Aggregate all data into `mapper.annotations.json`, then use scripts to assemble validated `mapper.json` and project `mapper.strategy_view.json`. No recommendations or derived trade levels in Step 2.

### Data Sources

Already available: auction metrics (Phase 1), K-line indicators (Phase 2), theme scores (`themes.json`), emotion sub-score.

Additional fetches in this stage:

### Fetch Money Flow

```bash
# Industry money flow
uv run --frozen ashare-pilot market-data money-flow --json

# Individual stock money flow (requires cookie)
uv run --frozen ashare-pilot market-data money-flow --stock --json
```

Money_Flow scoring:

```
Money_Flow = 0.6 × IndustryFlowScore + 0.4 × StockFlowScore

  IndustryFlowScore = clamp(50 + 100 × net_inflow / sector_float_cap, 0, 100)
  StockFlowScore    = 50 + sign(net_inflow) × min(|net_inflow| / amount, 1) × 50
```

- Cookie failure / fetch error → `Money_Flow = 50` (neutral), add `MoneyFlowStale` to RiskFlags
- Pre-market: use yesterday's data as direction proxy
- Missing sector float cap → `IndustryFlowScore = 50`, renormalize to 100% StockFlowScore

### Compute Fields

#### Auction Signal

```
auction_score = AucChg% × 0.40 + AucAmt × 0.35 + AucTO × 0.25
```

First classify by abs(percent), then apply direction (negative halved):

| abs(percent) | Base |
|-------------|------|
| ±2~5% | 100 |
| ±1~2% | 85 |
| ±0.5~1% | 70 |
| ±0~0.5% | 50 |
| >±5% | 40 (anomaly) |

If `percent < 0`: score /= 2. If float_shares unavailable, renormalize: `AucChg% × 0.533 + AucAmt × 0.467`. For intraday runs: `auction_score = 50` (neutral).

| Factor | Weight | Scoring |
|--------|--------|---------|
| AucChg% | 40% | See boundary table above |
| AucAmt | 35% | ≥5000万 = 100; 2000-5000 = 75; 500-2000 = 50; <500 = 20 |
| AucTO | 25% | ≥0.3% = 100; 0.1-0.3% = 70; <0.1% = 40; skip if unavailable |

#### Composite Score

```
composite_score = Theme_Heat × 0.30 + News_Impact × 0.20 + Auction_Signal × 0.20 + Tech_Score × 0.20 + Money_Flow × 0.10
```

| Factor | Weight | Source |
|--------|--------|--------|
| Theme Heat | 30% | Best source_theme heat from themes.json/theme_stocks.json |
| News Impact | 20% | News relevance to this specific stock (0-100) |
| Auction Signal | 20% | From auction formula above; intraday = 50 neutral |
| Tech Score | 20% | Traditional×0.70 + Sentiment×0.30 |
| Money Flow | 10% | Capital flow direction (high noise, down-weighted) |

### V5 Perception Architecture

Step 2 is **perception only**. All Direction / Severity / Override decisions are Step 3 Reasoning territory.

#### Minimal Inference Whitelist (Step 2 Allowed)

| # | Type | Example | Executor |
|---|------|---------|----------|
| 1 | Numeric compression | P/C/E sub-scores (rubric) | LLM |
| 2 | Matrix classification | R×P cell lookup → NewsImpact | LLM |
| 3 | Ternary classification | Discrete event → MajorEvent Polarity | LLM |
| 4 | Flag classification | risk_flags → RiskType | LLM (table lookup) |
| 5 | Sparse Pattern override | Only a reviewed dimension that differs from the script default | LLM |
| 6 | Structural pattern label | Genuine anomaly only; omit otherwise | LLM |

#### Forbidden Reasoning (Step 2 MUST NOT)

- Direction (base / final / any form)
- RiskSeverity (1/2/3 scoring — Step 3 territory)
- OverrideHint application
- Causal inference ("inflow drove rally", "because of")
- Trend prediction ("expected to continue rising")
- Buy/sell recommendations
- Theme-level MajorEvent (sector sentiment goes through ThemeHeat/NewsImpact; MajorEvent must name a company)

### V5 Pattern — Multi-Dim State Model

Each stock independently scored on 5 dimensions (non-orthogonal):

| Dimension | States | Rubric |
|-----------|--------|--------|
| **heat** | `RISING` / `FALLING` / `STABLE` | theme_heat today vs yesterday; first day → `STABLE` conf=50 |
| **leader** | `STABLE` / `DIVERGENCE` / `ABSENT` | Anchor + board_streak≥1→STABLE; Anchor broken-board→DIVERGENCE; no Anchor→ABSENT |
| **auction** | `LEADING` / `LAGGING` / `MATCH` / `NEUTRAL` | abs(auc_chg)>1% same-direction as theme_heat→LEADING; opposite>1%→LAGGING; <0.5%→NEUTRAL |
| **rotation** | `PRIMARY` / `SECONDARY` / `TERTIARY` / `NONE` | MultiTheme+limit-up cluster→PRIMARY; purity≥0.7→SECONDARY; in pool→TERTIARY |
| **volume** | `SURGE` / `NORMAL` / `DRY` | amount in 亿: ≥8→SURGE; 3-8→NORMAL; <3→DRY |

### V5 Confidence Rules

All computed_perception fields must carry confidence:

| Field | Confidence Formula | Executor |
|-------|-------------------|----------|
| `theme_heat.subscores.M` | LLM per market_action rubric hit clarity 0-100 | LLM |
| `theme_heat.subscores.E/C` | LLM per rubric tier: 90(full)/75(mid)/55(edge) | LLM |
| `theme_heat.subscores.N` | `min(news_count/5, 1) × 100` | Python |
| `theme_heat.policy_bonus` | Tier lookup 0/2/5/8/10 × PolDir (bull×1.0 / neut×0.5 / bear×0.0); deterministic, no confidence | LLM |
| `theme_heat.value` | `min(M, E, N, C confidences)` (Base factors; policy_bonus excluded from min) | Python |
| `news_impact.value` | Matrix cell weight × 100 ± adjustments | LLM |
| `major_event.polarity` | Default Neutral=90; P/N by evidence strength | LLM |
| `risk_type` | 100 (machine lookup, deterministic) | Python |
| `pattern.*.state` | Deterministic base; sparse reviewed override only | Python + LLM override |
| `tech_score.value` | `present_factor_count / 6 × 100` | Python |

Emotion direction coefficient (×1.0/×0.8/×0.5) affects emotion **value** only, not confidence (confidence is attention-hit clarity).

### V5 Conditional Reread (Step 3)

Step 3 defaults to **not re-reading news**. Resolve the one cited `news#<id>`
from `news.json` only when one of these conditions triggers:

| Trigger | Quantitative Criterion | Reread Scope |
|---------|----------------------|--------------|
| Anomaly exists | `Anomaly != "--"` | Single news line at NewsLink |
| Low confidence | Any `confidence < 60` | Single news line at NewsLink |
| Hard contradiction | Any of 3 below | NewsLink + cross_rank |

**Three Hard Contradictions (machine-detectable):**
1. `theme_heat >= 80 AND tech_score < 40`
2. `major_event = "Positive" AND composite < 50`
3. `auction_change_pct > +3% AND news_impact < 40`

**Forbidden:** Step 3 scanning full `news.json` or `news.md` for theme re-mapping.

### MajorEvent

Default `None`. Requires explicit company-name + discrete event:

| Value | Required Evidence |
|-------|-------------------|
| **Positive** | Named company + discrete event: order win, restructuring, earnings >20% beat, product approval |
| **Negative** | Named company + discrete event: penalty, investigation, fraud, suspension, major share reduction |
| **None** | Everything else — including sector sentiment, industry pricing, forum announcements |

When uncertain, use `None`.

### NewsImpact Rubric (per-stock, 0-100)

Two-dimensional lookup. LLM selects ONE cell; may interpolate ±5 and explain in `mapper.annotations.json` trace.

**Relevance (rows):**

| Tier | Code | Condition |
|------|------|-----------|
| R4 | Direct | Company name or code in headline |
| R3 | Supply-chain | Customer/supplier/contract partner named |
| R2 | Sector | Theme-level news, no company name |
| R1 | Proxy | Index/peer/industry data only |
| R0 | None | No connection — should not be in pool |

**Prominence (columns):**

| Tier | Code | Condition |
|------|------|-----------|
| P3 | Headline | Title subject or lead paragraph |
| P2 | Body | Body mention with material detail |
| P1 | List | Table/list/chain mention only |
| P0 | Absent | — |

**Score matrix:**

|  | P3 Headline | P2 Body | P1 List |
|--|:-----------:|:-------:|:-------:|
| **R4 Direct** | 95 | 85 | 70 |
| **R3 Supply-chain** | 80 | 70 | 55 |
| **R2 Sector** | 65 | 55 | 40 |
| **R1 Proxy** | 45 | 35 | 25 |

**Adjustments (stack, cap 0-100):**

| Condition | Δ |
|-----------|---|
| Same stock in ≥2 news sources same day | +5 |
| Negative sentiment (penalty / investigation) | -20 |
| MajorEvent = Positive / Negative | Use MajorEvent instead; NewsImpact **cap=60 for Negative** |

`NewsLink` = canonical `news.json` pointer in the form `news#<id>`.

### Anomaly Field (≤50 chars)

Purpose: surface structural patterns that rubrics flatten. The contract is
exactly `anomaly: string|null`; structured objects are forbidden. Omit the
field or use `null` when no genuine anomaly exists.

| Allowed | Forbidden |
|---------|-----------|
| Pattern labels ("3-day shrink-volume first board") | Buy/sell advice |
| Cross-theme ("spans Semi + AI Compute") | Price targets |
| Event shape ("limit-up open then re-seal") | >50 chars |

**Mandatory** if: market_active cross_rank_highlights entry, LHB injection with net buy > 0, board_streak ≥ 2 but Composite < 70, or RiskType alone insufficient. Otherwise omit it or use `null`; do not emit repetitive default prose.

### Deterministic Role Tags

| Tag | Condition | Meaning |
|-----|-----------|---------|
| `ThemeLibrary` | selected-theme candidate/pure/leader membership | Theme Library source |
| `MarketActive` | qualifying structured market-view rule | Actual market-view source |
| `NewsDirect` | canonical direct name/code match or accepted extra with valid `news#id` | Direct news source |
| `LHB` | in-scope structured LHB row | LHB source |
| `MultiTheme` | at least two `source_themes` | Cross-theme membership |
| `Anchor` | `anchor=true` in Theme Library metadata | Theme anchor |

Python writes `role_tags`; the LLM must not add or remove them.

---

## Output: mapper.annotations.json -> mapper.json -> mapper.strategy_view.json

`mapper.annotations.json` is the only LLM-authored machine artifact in this stage. `mapper.json` is assembled and validated by scripts. `mapper.strategy_view.json` is projected from `mapper.json` for Step 3.

### LLM Output Contract: mapper.annotations.json

Load only [references/mapper-semantics-rubric.md](references/mapper-semantics-rubric.md) plus `.mapper_annotation_input.json` for this LLM phase. The compact input links each candidate's `source_themes`, `direct_news_refs`, and `theme_news_refs` to deduplicated top-level `news_evidence`; use only those linked rows for candidate news semantics.

Write:

```text
predict/{date}/mapper.annotations.json
```

Required shape:

```json
{
  "schema_version": "daily_mapper_annotations.v1",
  "date": "YYYY-MM-DD",
  "stocks": [
    {
      "code": "sz000001",
      "news_relevance": {"r": "R2", "p": "P2", "confidence": 80, "evidence": "news#2", "trace": "why"},
      "major_event": {"polarity": "positive", "confidence": 90, "evidence": "news#2", "trace": "named discrete event"},
      "pattern": {
        "rotation": {"state": "PRIMARY", "confidence": 90, "trace": "reviewed override"}
      },
      "anomaly": "genuine structural anomaly",
      "news_link": "news#2"
    }
  ]
}
```

Do not write `mapper.json` by hand.

Every deterministic candidate must appear exactly once and must include `news_relevance` with confidence plus canonical evidence or a concise trace. `major_event`, `anomaly`, and individual `pattern` dimensions are sparse: omit them unless they carry real semantics. Missing coverage blocks publication; extra non-candidate rows warn and skip. Uniform R2/P2 is allowed when compact candidate evidence is uniformly theme-level; a candidate with `direct_news_refs` or `NewsDirect` must not be downgraded to R2.

After prepare and writing `mapper.annotations.json`, run:

```bash
uv run --frozen ashare-pilot mapping daily finalize --date {YYYY-MM-DD} --validation-retries <0-or-1>
```

`uv run --frozen ashare-pilot mapping daily prepare` owns deterministic membership, source flags, sequential indicators, filters, and compact annotation targets. `uv run --frozen ashare-pilot mapping daily finalize` gates candidate coverage, builds the deterministic mapper base, overlays sparse semantics, validates the mapper, and writes the Step 3 view. Both update report-only `step2_timing.json`; diagnostic write failure does not invalidate trading contracts. An upstream stage refresh invalidates recorded downstream stages, and `total_recorded_seconds` is populated only when all four timed stages are artifact-linked within the same run.

Market source flags use top-N `cross_rank_highlights` plus the full selected-theme threshold sets `threshold_attention` (`attention_score >= 80`) and `threshold_gainers` (`change_pct >= 3%`). Display top-N lists must never truncate threshold qualification.

`uv run --frozen ashare-pilot mapping daily prepare` validates the in-memory `theme_stocks.json` contract before publishing it. `uv run --frozen ashare-pilot mapping daily finalize` revalidates its schema/date/technical projection, requires both input dates to equal `--date`, and treats extra non-candidate annotation rows as warning-and-skip rather than requiring candidate semantics.

The sector-analyst must record both measured LLM stages so byte, wall time, and
validation retry changes remain visible:

```bash
uv run --frozen ashare-pilot mapping daily build-timing --date {YYYY-MM-DD} --stage theme_llm --duration <seconds> --input predict/{YYYY-MM-DD}/.theme_evidence_input.json --output predict/{YYYY-MM-DD}/themes.json --validation-retries <0-or-1>
uv run --frozen ashare-pilot mapping daily build-timing --date {YYYY-MM-DD} --stage mapper_annotation_llm --duration <cumulative-seconds> --input predict/{YYYY-MM-DD}/.mapper_annotation_input.json --output predict/{YYYY-MM-DD}/mapper.annotations.json --validation-retries <0-or-1>
```

On validation failure, collect the complete validator error set, fix all
reported fields in the owning LLM artifact once, record one validation retry,
and rerun the validator/finalize once. If the second attempt fails, stop and
report the full remaining error set; never loop and never ask the general
orchestrator to edit Step 2 artifacts.

| Column | Source | Notes |
|--------|--------|-------|
| Price | Phase 1 auction or Phase 2 close | Three states: PrevClose / Auction / Live |
| PriceSource | `PrevClose` \| `Auction` \| `Live` | Resolves price 3-state ambiguity |
| MA20 | `ma20` field | Phase 2 |
| MA5 | `ma5` field | Phase 2 |
| ATR / ATR% | `atr`, `atr_pct` | Pre-computed |
| High20 / Low20 | `high20`, `low20` | Pre-computed |

Validation rules:

- Every Candidate Pool code must have exactly one `strategy_inputs` object in `mapper.json`.
- `Price`, `MA20`, `MA5`, `ATR`, `ATR%`, `High20`, and `Low20` must match
  `raw_observation.*.value` from `pool_indicators.json`.
- If `pool_indicators.json` has a numeric value, `mapper.json` and
  `mapper.strategy_view.json` must not output `null` for that field.
- `PriceSource` is `PrevClose` when sourced from `pool_indicators.json`.
- Any mismatch report means the LLM should fix annotations or deterministic base
  inputs, then rerun the mapper JSON build/validation sequence before Step 3.

| ExclusionSource | Meaning |
|-----------------|---------|
| `board-policy` | Config-driven board exclusion |
| `hard-filter` | Liquidity < 3亿 / atr_pct > 8% |
| `indicators-fetch-failed` | Phase 2 fetch failure |
| `soft-filter` | tech_score < 50 |
| `manual` | LLM explicit exclusion with reason |

### Board Exclusion Policy

Config in `config/trading-scope.json`:

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

Step 2 reads config → writes `BoardPolicy` to Market State. Overrides allow single-code exceptions.

---

## Step 3 Read Contract

Step 3 **MUST** read in order:

1. `Market State`: BoardPolicy, DominantThemes, FinancingFlow, RiskFlags
2. `Candidate Pool`: all columns
3. `Strategy Inputs`: Price, PriceSource, MA20, MA5, ATR, ATR%, High20, Low20
   (script-injected from `pool_indicators.json`)
4. `memory/RULES.md`
5. `news.json` (**single-ID conditional lookup only** — see V5 Conditional Reread triggers)

Step 3 **MUST NOT**:
- Re-derive Composite or NewsImpact (Python-computed, confidence-tagged)
- Scan full `news.json` or `news.md` for theme re-mapping (forbidden — V5 Invariant 2)
- Ignore low-confidence signals (`confidence < 60`)
- Re-fetch Strategy Inputs fields (unless missing/null/stale)

## Step 2 → Step 3 Data Contract

The **`candidate_pool[*].strategy_inputs` fields in mapper.json** are authoritative for: Price, PriceSource, MA20, MA5, ATR, ATR%, High20, Low20 after `uv run --frozen ashare-pilot mapping daily validate-mapper` passes. Step 3 normally reads their projection at `mapper.strategy_view.json:candidates[*].strategy_inputs`.

**Default: no re-fetch.** Step 3 loads `mapper.strategy_view.json` Strategy Inputs and proceeds. Re-fetch from API only if: field is missing (N/A, null, empty), field is invalid (negative, zero where nonsensical), or stale data detected.

Phase 3 contract: `predict/{date}/mapper.annotations.json` is the LLM perception input, `predict/{date}/mapper.json` is the validated full machine contract, and `predict/{date}/mapper.strategy_view.json` is the Step 3 reading contract.
