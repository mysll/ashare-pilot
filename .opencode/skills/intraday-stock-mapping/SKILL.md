---
name: intraday-stock-mapping
description: >
  Intraday perception layer for Step 2 of intraday-market-analysis pipeline.
  Builds Dual Pool (Tracking + Discovery), enriches with V5 technical indicators
  and intraday K-line data, computes Tradeability/OvernightScore/TailFlow fields,
  outputs intraday_mapper.md as V5 7-section structured perception dataset.
---

# Intraday Stock Mapping (V5 Perception)

Loaded by intraday-market-observer when dispatched for intraday perception.

## V5 架构角色

```
Compute (Python)
    ↓
Perception (Step 2 — intraday_mapper.md — 你在这里)
    ↓
Reasoning (Step 3 — intraday-strategy)
    ↓
Decision (tail_strategy.md)
```

Step 2 is **perception only**. Classification, detection, pattern recognition per V5
Minimal Inference whitelist. **No Direction / RiskSeverity / OverrideHint** (V5 Invariant 1).

## Scope

A-shares only (sh/sz prefix). Board exclusions per `../daily-stock-mapping/config/trading-scope.json`
(sh688/bj excluded by default).

**Core Rule:** Theme Library is the ONLY valid source of themes and theme-stock mappings.

**Format Rule:** All output files are markdown. Write them directly — do NOT write scripts.

## Stage I/O

| Stage | Input | Output |
|-------|-------|--------|
| 1. Dual Pool Construction | market_snapshot.md + Morning mapper.md | Stock Pool (tracking + discovery) |
| 2. Technical Enrichment | Pool codes | Pool (V5 schema enriched) |
| 3. Intraday Fields | Enriched pool + intraday K-line | Tradeability / OvernightScore / TailFlow |
| 4. Structured Dataset | All above + money flow + theme roles | intraday_mapper.md (7-section) |

---

## Stage 1: Dual Pool Construction

### A. Morning Tracking Pool (~30-40%)

**Degradation**: 若 `mapper.md` 不存在或无法读取 → Tracking Pool = 空，直接进入 Discovery Pool (100%)。不报错，不阻塞。

From `predict/{date}/mapper.md`:
- Extract Candidate Pool Top20 (by Composite Score DESC)
- Extract stocks from Strategy Inputs table
- Deduplicate → `source = "tracking"`
- Mark `tracking_reason`: "Morning TopN" or "Morning Strategy"

**Purpose:** Track whether Morning hypotheses materialized. These stocks get NO
priority boost — they compete equally with Discovery Pool stocks.

### B. Intraday Discovery Pool (~60-70%)

From `market_snapshot.md` Leading Sectors + real-time market data:

```bash
# Real-time market leaders from theme library
python .opencode/skills/theme-library/scripts/query_theme.py market <theme> --top 15 --json

# Real-time quotes for potential leaders
python .opencode/skills/stock-analysis/scripts/fetch_stock.py <codes> --json
```

Discovery sources (LLM-driven, not script-generated):

1. **Leading sector stocks** (from market_snapshot.md Leading Sectors)
   - Theme Library `market` view → cross_rank_highlights + top_gainers
   - Mark `source = "discovery"`, `discovery_reason = "sector_leader"`

2. **Limit-up ladder stocks** (连板梯队, from market_snapshot.md)
   - 首板质量高 (早封板+不放量) → add
   - 连板龙头 (≥2板+封死) → add
   - Mark `discovery_reason = "limit_up_ladder"`

3. **Volume surge stocks** (成交额放大, from market_snapshot.md)
   - 成交额 > 20亿 + 换手 > 5% but < 20% → add
   - Mark `discovery_reason = "volume_surge"`

4. **Capital inflow stocks** (主力资金流入, from fetch_money_flow.py --stock)
   - 主力净流入 > 1亿 + 主力净占比 > 5% → add
   - Mark `discovery_reason = "capital_inflow"`

5. **LHB stocks** (from fetch_special.py lhb)
   - Theme-filtered (belongs to any theme in Leading Sectors)
   - Net buy > 0 → add with score based on net buy magnitude
   - Mark `source = "lhb"`, `discovery_reason = "lhb_net_buy"`

### C. Merge & Deduplicate

1. Merge Tracking + Discovery, deduplicate by stock code
2. If same stock in both pools → keep `source = "tracking+discovery"`, use higher score
3. Apply board filter (per trading-scope.json)
4. Max pool size: 50 stocks

---

## Stage 2: Technical Enrichment

Reuse Morning pipeline's V5 technical enrichment:

```bash
python .opencode/skills/stock-analysis/scripts/fetch_stock.py <code_1>,<code_2>,...,<code_N> --json
python .opencode/skills/daily-stock-mapping/scripts/fetch_pool_indicators.py <code_1>,...,<code_N> --json
```

V5 nested schema fields received:
`code, price, close, turnover, change_pct, amount, rsi, macd, macdh, ma20, ma50,
boll_ub, boll_lb, atr, high20, low20, atr_pct, percent_b, board_streak, seal_quality,
limit_up_freq, traditional, sentiment, tech_score, risk_flags`

**Hard Filters** (same as Morning):
| Filter | Reject Condition | ExclusionSource |
|--------|-----------------|-----------------|
| Liquidity | amount < 30000 (万元) = 3亿 | hard-filter |
| Extreme Volatility | atr_pct > 8% | hard-filter |
| Indicators fetch failed | fetch_failed: true | indicators-fetch-failed |

**Additional Intraday-specific data:**

```bash
# Intraday minute K-line (5-min, today only)
python .opencode/skills/stock-analysis/scripts/fetch_stock.py <code> --intraday --json
# Extract: 尾盘30分钟量价形态, 全天量比, 盘中高/低点
```

---

## Stage 3: Intraday Fields Computation

### Tradeability (LLM Classification)

Per `memory/INTRADAY_RULES.md` I01. Output: `Suitable` / `Watch` / `Extended` / `Avoid`.

| State | Condition |
|-------|-----------|
| **Suitable** | 主线 + 龙头活跃 + 尾盘承接 + OvernightScore ≥ 75 |
| **Watch** | 主线但龙头分歧 或 OvernightScore 60-74 |
| **Extended** | 方向正确但涨幅>7%且连板≥2 或 封板质量下降 |
| **Avoid** | 非主线 或 OvernightScore < 60 或 已炸板 |

### OvernightScore (LLM Scoring, 0-100)

Per `memory/INTRADAY_RULES.md` I02:

| Factor | Weight | Scoring (0-100 per factor) |
|--------|:------:|----------------------------|
| 主线地位 | 25% | Leading Sector Top3→100; Top5→80; 其余→50; 非主线→20 |
| 龙头状态 | 20% | RoleTags含Anchor+封板→100; Anchor未封板→70; IndustryLeader→60; 非龙头→30 |
| 成交量 | 15% | 成交额≥10亿→100; 5-10亿→75; 3-5亿→50; <3亿→20 |
| 封板质量 | 15% | seal_quality=封死→100; 未封板→50; 炸板→10; —→0 |
| 资金持续性 | 15% | TailFlow=Strong Inflow→100; Weak Inflow→70; Neutral→50; Outflow→25 |
| 尾盘承接 | 10% | 尾盘30分钟量比>1.5且价格稳定→100; 量比>1+微跌<1%→70; 跳水>2%→20 |

### TailFlow (LLM Classification)

Per `memory/INTRADAY_RULES.md` I03. Output: `Strong Inflow` / `Weak Inflow` / `Neutral` / `Outflow`.

| State | Condition |
|-------|-----------|
| **Strong Inflow** | 尾盘30min量比>2 + 主力净流入>3000万 |
| **Weak Inflow** | 量比1.2-2 或 主力净流入1000-3000万 |
| **Neutral** | 量比0.8-1.2 |
| **Outflow** | 量比<0.8 且 主力净流出 |

Data sources:
- `fetch_money_flow.py --stock` (主力净流入)
- `fetch_stock.py --intraday` (尾盘30分钟量比/价格变化)

---

## Stage 4: Structured Dataset → intraday_mapper.md

V5 7-section structured perception dataset. **No prose.** Sorted by composite_score DESC.

### Section 1: Market State

```markdown
## Market State

| Field | Value |
|-------|-------|
| DominantThemes | (Leading Sectors top 2-3) |
| Breadth | 涨停xx, 跌停xx, 炸板率xx% |
| CapitalDirection | 北向±xx亿, 主力±xx亿 |
| BoardPolicy | sh688=exclude, bj=exclude |
| RegimeHint | (Step 3 Reasoning territory — not Step 2) |
```

### Section 2: Theme Ranking

```markdown
## Theme Ranking

| Theme | Market Heat | Rank | Leader Status | Breadth | Capital |
|-------|------------|------|---------------|---------|---------|
| AI算力 | 92 | 1 | Active (xx涨停) | Wide (n只>+3%) | ++流入 |
```

Market Heat components (LLM-assessed):
- Leader Status: 龙头是否继续带动 (封板=活跃, 分歧=减弱, 跳水=破坏)
- Breadth: 板块扩散程度 (n只上涨>3%)
- Capital: 资金持续性 (与 market_snapshot Capital Flow 对齐)
- Rotation: 是否出现轮动信号

### Section 3: Candidate Pool

```markdown
## Candidate Pool

| Code | Name | Source | Tradeability | Overnight | TailFlow | comp.value | tech.value | th_heat | risk_type | pattern.heat | pattern.leader | pattern.rotation | anomaly | RoleTags |
|------|------|--------|-------------|-----------|----------|-----------|------------|---------|-----------|-------------|---------------|-----------------|---------|----------|
| sh603986 | 兆易创新 | tracking+discovery | Suitable | 92 | Strong Inflow | 88.5 | 78.5 | 91 | overbought | RISING | STABLE | PRIMARY | 主线龙头连续封板 | Anchor,IndustryLeader |
| sz000977 | 浪潮信息 | discovery | Watch | 68 | Weak Inflow | 62.0 | 55.0 | 91 | trend_weak | RISING | DIVERGENCE | SECONDARY | 龙头断板尾盘承接弱 | Anchor,MultiTheme |
```

**Composite Score formula (Intraday):**

```
composite = ThemeHeat × 0.25 + TechScore × 0.20 + MoneyFlow × 0.15
          + OvernightScore × 0.20 + TailFlowScore × 0.20
```

TailFlowScore: Strong Inflow=100, Weak Inflow=70, Neutral=50, Outflow=25.

### Section 4: Strategy Inputs

```markdown
## Strategy Inputs

| Code | Price | PriceSource | MA20 | MA5 | ATR | ATR% | High20 | Low20 |
|------|-------|-------------|------|-----|-----|------|--------|-------|
```

PriceSource = `Live` (盘中实时). All other fields from V5 schema.

### Section 5: Score Trace

```markdown
## Score Trace

| Code | CompositeTrace | PerceptionTrace |
|------|----------------|-----------------|
| sh603986 | T91×0.25+Tech78.5×0.20+MF85×0.15+ON92×0.20+TF100×0.20=89.3 | Direction/RiskSeverity→Step 3 ReasoningTrace |
```

### Section 6: Observation Pool

```markdown
## Observation Pool

| Code | Name | Composite | Theme | Reason | Anomaly |
|------|------|-----------|-------|--------|---------|
| sz000123 | 某股 | 48 | AI算力 | BelowThreshold | 尾盘缩量横盘待突破 |
```

Reasons: `BelowThreshold` / `TechnicalRisk` / `WeakTheme` / `Indicators_Fetch_Failed`

### Section 7: Excluded Stocks

```markdown
## Excluded Stocks

| Code | Name | ExclusionReason | ExclusionSource |
|------|------|-----------------|-----------------|
| sh688256 | 寒武纪 | 科创板不可交易 | board-policy |
| sz300975 | 商络电子 | atr_pct=9.0% > 8% | hard-filter |
```

---

## Red Flags — STOP and Restart the Stage

| Symptom | Fix |
|---------|-----|
| Theme name not in Theme Library | Discard. Library is the only source. |
| Stock pool > 50 after dedup | Trim lowest OvernightScore stocks. |
| Tracking Pool stock not traceable to Morning mapper.md | Remove. |
| mapper.md contains buy/stop/target | Remove. Strategy is Step 3 territory. |
| **Step 2 produces Direction / RiskSeverity** | Violation. Step 3 Reasoning territory. |
| Candidate Pool row missing OvernightScore or TailFlow | Re-add. Intraday mandatory fields. |
