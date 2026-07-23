# Mapper V4 — Step 2 Output Schema Revision (Design Only)

Date: 2026-06-27  
Status: **Draft for review** — field design only, no pipeline code changes in this document

## Background

Mapper V3 (2026-06-24) successfully formalized the Step 2 → Step 3 data contract: structured tables, no prose, Strategy Inputs as authoritative source. Side effect: LLM judgment space collapsed to a few underspecified scores (News_Impact, theme_heat sub-scores) while deterministic logic (Direction, Risk Ceiling) was documented as LLM-executed rules.

This revision keeps V3's structure and reproducibility, but **rebalances**:

| Keep tight (script / formula) | Loosen (LLM + rubric) |
|-------------------------------|------------------------|
| composite weights, tech_score, auction_score | News_Impact scoring |
| Strategy Inputs (Price, MA20, ATR, …) | MajorEventFlag judgment |
| mapper section layout | Anomaly annotation |
| hard filters (liquidity, atr_pct) | theme_heat sub-scores (policy/capital/emotion) |

**Design principle:** *Formulas should not be LLM-computed; judgments should not be LLM-stripped.*

---

## Scope

| In scope | Out of scope |
|----------|----------------|
| New / renamed columns in `mapper.md` | Python script implementation |
| Rubrics for LLM-scored fields | Changes to `themes.md` / `theme_stocks.md` |
| Step 3 read rules (companion note) | Backtest automation |
| Config schema for board exclusions | Theme Library rebuild |

Companion updates (when implemented, not in this doc):

- `.agents/skills/daily-stock-mapping/SKILL.md` — column definitions + rubrics
- `.agents/skills/daily-strategy/SKILL.md` — read new columns, explicit RULE overrides
- `memory/RULES.md` — map RULE IDs to `RiskType` / `OverrideHint` tokens

---

## Mapper V4 Section Layout

Still **7 sections**, still **no prose paragraphs**. Section count +1: **Score Trace** (optional compact table).

| # | Section | Change from V3 |
|---|---------|----------------|
| 1 | Market State | +2 fields |
| 2 | Theme Ranking | +1 field per row |
| 3 | Candidate Pool | **Major column revision** |
| 4 | Strategy Inputs | unchanged |
| 5 | Score Trace | **new** (optional, recommended) |
| 6 | Observation Pool | +Anomaly on flagged rows |
| 7 | Excluded Stocks | +ExclusionSource |

---

## Section 1: Market State

```markdown
## Market State

| Field | Value |
|-------|-------|
| DominantThemes | 半导体(91), AI算力(80) |
| FinancingFlow | +61.31亿净买入 |
| RiskFlags | RMBWeakness, APACPressure |
| BoardPolicy | sh688=exclude, bj=exclude |
| RegimeHint | strong-sector / neutral / weak / panic |
```

| Field | Type | Source | Notes |
|-------|------|--------|-------|
| DominantThemes | string | themes.md top 2–3 | unchanged |
| FinancingFlow | string | news / fetch_special | unchanged |
| RiskFlags | string | news.md macro scan | comma-separated tokens |
| **BoardPolicy** | string | config | reflects active exclusion policy, not implicit |
| **RegimeHint** | enum | LLM + index pre-read | `strong-sector` \| `neutral` \| `weak` \| `panic` — **hint only**, Step 3 confirms with live index |

`RegimeHint` thresholds (reference, not hard-coded in Step 2):

| Value | Condition (上证竞价/昨收) |
|-------|---------------------------|
| panic | < -1.5% |
| weak | -1.5% ~ -0.5% |
| neutral | ±0.5% |
| strong-sector | neutral index BUT dominant theme heat ≥ 85 OR 科创50 > +2% |

---

## Section 2: Theme Ranking

Add **HeatTrace** column — compact audit of theme_heat sub-scores.

```markdown
| Theme | Heat | Rank | HeatTrace |
|-------|------|------|-----------|
| 半导体 | 91 | 1 | P85/C70/E95/N8 |
```

| Token | Meaning |
|-------|---------|
| P | policy 0–100 |
| C | capital 0–100 |
| E | emotion 0–100 |
| N | news_count (integer) |

Formula unchanged: `heat = P×0.40 + C×0.15 + E×0.25 + N×0.20` (normalized news_count to 0–100 before weighting).

### Theme heat sub-score rubric (LLM MUST follow)

**Policy (P)**

| Score | Condition |
|-------|-----------|
| 90–100 | National/industry policy explicitly names the theme; regulatory file, State Council, ministry |
| 75–89 | Strong policy proxy (standard, subsidy, pilot zone) without headline policy |
| 60–74 | Indirect policy benefit (supply chain, localization) |
| <60 | No policy angle — discard theme (existing rule) |

**Capital (C)**

| Score | Condition |
|-------|-----------|
| 85–100 | Financing flow / northbound / LHB net buy aligned with theme today or yesterday |
| 65–84 | Sector turnover elevated, margin expansion |
| 45–64 | Neutral |
| <45 | Outflow or no capital signal — use 45 default |

**Emotion (E)**

| Score | Condition |
|-------|-----------|
| 90–100 | ≥3 flash items + hot-stock list presence + limit-up cluster in theme |
| 75–89 | 2 news items or 1 major headline |
| 60–74 | Semantic match only, low media density |
| <60 | discard |

**News count (N)** — raw count of distinct news items mapped to theme (integer, cap display at 20).

---

## Section 3: Candidate Pool (core revision)

### V3 columns (retained)

`Code`, `Name`, `Composite`, `Theme`, `RoleTags`, `Emotion`, `Turnover%`, `Risk`

### V3 columns (changed)

| V3 | V4 | Change |
|----|-----|--------|
| `Direction` | `DirectionBase` + `DirectionFinal` | split base vs post-override |
| `MajorEventFlag` | `MajorEvent` | same enum, stricter rubric below |
| `Risk` (free text) | `RiskFlags` + `RiskType` | structured |

### V4 new columns

| Column | Type | Description |
|--------|------|-------------|
| **NewsImpact** | int 0–100 | per-stock, rubric below (was implicit in composite) |
| **NewsLink** | string | news item id or ≤15 char anchor, e.g. `flash#3`, `finance#12` |
| **CompositeTrace** | string | compact: `T91/N82/A75/Tech78/MF65` |
| **DirectionBase** | enum | from composite mapping only (scriptable) |
| **DirectionFinal** | enum | after RiskHint + MajorEvent adjustments |
| **RiskType** | enum | primary risk category for Step 3 routing |
| **RiskSeverity** | int 1–3 | 1=informational, 2=caution, 3=hard caution |
| **OverrideHint** | string | comma-separated RULE tokens Step 3 should consider |
| **Anomaly** | string ≤30 chars | optional; structural pattern outside rubric |

### Example row

```markdown
| Code | Name | Composite | DirectionBase | DirectionFinal | Theme | RoleTags | NewsImpact | NewsLink | Emotion | Turnover% | RiskFlags | RiskType | RiskSeverity | OverrideHint | Anomaly | MajorEvent |
|------|------|-----------|---------------|----------------|-------|----------|------------|----------|---------|-----------|-----------|----------|--------------|--------------|---------|------------|
| sh603986 | 兆易创新 | 76.72 | bullish | neutral-bull | 半导体 | IndustryLeader,Candidate | 88 | flash#2 | 92.5 | 7.61% | RSI>75 | overbought | 2 | R37 | — | None |
| sh600048 | 保利发展 | 42.1 | bearish | bearish | 房地产 | — | 35 | — | 10 | 1.2% | RSI<30,MA双熊 | oversold-opportunity | 1 | R61 | 利空出尽缩量 | None |
```

---

## Direction model (replaces uniform Risk Ceiling)

### Step A — DirectionBase (deterministic, scriptable)

| Composite | DirectionBase |
|-----------|---------------|
| ≥ 70 | bullish |
| 55–69 | neutral-bull |
| 45–54 | neutral |
| < 45 | bearish |

### Step B — RiskType + RiskSeverity (no Direction change yet)

Each `RiskFlags` entry maps to **one primary** RiskType (highest severity wins):

| RiskFlag | RiskType | RiskSeverity | Rationale |
|----------|----------|:------------:|-----------|
| RSI>75 | `overbought` | 2 | caution, not identical to trend break |
| RSI<30 | `oversold-opportunity` | **1** | opportunity hint — **not** same as MA双熊 |
| MA双熊 | `trend-weak` | 3 | structural weakness |
| 炸板 | `broken-board` | 2 | event review (R39/R35) |
| Auc<-5% | `auction-anomaly` | 2 | manipulation / panic auction |
| ATR>8% | (hard exclude) | — | stays in Excluded, not pool |

**Key change from V3:** RSI<30 severity **1** (informational); MA双熊 severity **3**. V3 capped all at `neutral-bull` uniformly.

### Step C — DirectionFinal (soft constraint + hints)

Apply adjustments **in order**, record in `OverrideHint`:

```
DirectionFinal = DirectionBase
FOR each adjustment:
  IF MajorEvent = Positive  → shift +1 level (cap bullish)
  IF MajorEvent = Negative  → shift -1 level (cap bearish)
  IF RiskSeverity = 3 AND RegimeHint != strong-sector
                        → cap at neutral-bull (was: all flags)
  IF RiskSeverity = 2     → no automatic cap; set OverrideHint only
  IF RiskSeverity = 1     → no cap; set OverrideHint only
CLAMP to [bearish … bullish]
```

**OverrideHint tokens** (Step 3 MUST read before applying RULES.md):

| Token | When set | Step 3 meaning |
|-------|----------|----------------|
| `R37` | RiskType=overbought AND theme heat ≥ 85 | strong market: do not auto-exclude for RSI |
| `R61` | RiskType=oversold-opportunity | tiered entry; no same-day build |
| `R39-v3` | RiskType=broken-board AND theme heat ≥ 80 | limit-up broken-board watch mode |
| `R35-v3` | Emotion ≥ 85 AND board_streak ≥ 1 | continuation probe eligible |
| `R73` | RiskType=trend-weak AND RegimeHint=weak | MA20 buffer / wider stop |
| `R74` | RiskType=trend-weak AND RegimeHint=strong-sector | do not downgrade for MA alone |

DirectionFinal is a **default stance**, not a hard veto. Step 3 log must cite `OverrideHint` when deviating.

---

## NewsImpact rubric (per-stock, 0–100)

Two-dimensional lookup. LLM picks **one cell**, may interpolate ±5 with one-line reason in Score Trace.

### Dimension 1: Relevance (rows)

| Tier | Code | Condition |
|------|------|-----------|
| R4 | Direct | Company name or code in headline |
| R3 | Supply-chain | Customer/supplier/contract partner named |
| R2 | Sector | Theme-level news, no company name |
| R1 | Proxy | Index/peer/industry data only |
| R0 | None | No link — should not be in pool |

### Dimension 2: Prominence (columns)

| Tier | Code | Condition |
|------|------|-----------|
| P3 | Headline | Title subject or first paragraph lead |
| P2 | Body | Mentioned in body, material detail |
| P1 | List | Table/list/chain mention only |
| P0 | Absent | — |

### Score matrix

|  | P3 Headline | P2 Body | P1 List |
|--|:-----------:|:-------:|:-------:|
| **R4 Direct** | 95 | 85 | 70 |
| **R3 Supply-chain** | 80 | 70 | 55 |
| **R2 Sector** | 65 | 55 | 40 |
| **R1 Proxy** | 45 | 35 | 25 |

**Adjustments (stack, cap 0–100):**

| Condition | Δ |
|-----------|---|
| Same stock in ≥2 news sources same day | +5 |
| Negative sentiment (penalty, investigation) | −20 |
| MajorEvent = Positive / Negative | use MajorEvent instead; NewsImpact capped at 60 for Negative |

`NewsLink` = shortest pointer to source row in `news.md` (e.g. `flash#3`).

---

## MajorEvent rubric (stricter than V3)

| Value | Required evidence |
|-------|-------------------|
| **Positive** | Named company + discrete event: order win, restructuring, earnings beat >20%, product approval |
| **Negative** | Named company + discrete event: penalty, investigation, fraud, suspension, major reduction |
| **None** | Everything else — **including** industry booms, TSMC price hike, forum opening |

Default **None**. Step 2 must not use MajorEvent for theme-level catalysts.

---

## Anomaly field (≤30 Chinese chars)

**Purpose:** Pass structural patterns that rubrics flatten, without reopening prose mapper.

| Allowed | Example |
|---------|---------|
| Pattern labels | `三日缩量首板`, `板块龙头猝死`, `边缘扩散新龙头` |
| Cross-theme | `跨半导体+AI算力` |
| Event shape | `涨停开板二次封` |

| Forbidden | Reason |
|-----------|--------|
| Buy/sell advice | Step 3 territory |
| Price targets | Step 3 territory |
| >30 chars | keep table scannable |

**When required:** set Anomaly when ANY of:

- stock added via `market_active` cross_rank_highlights
- LHB injection with net buy > 0
- board_streak ≥ 2 but Composite < 70
- LLM confidence that RiskType alone misrepresents setup

Otherwise `—`.

---

## Section 5: Score Trace (new, optional)

One row per Candidate Pool stock. Enables audit without prose.

```markdown
## Score Trace

| Code | CompositeTrace | DirectionPath | NewsImpactCalc |
|------|----------------|---------------|----------------|
| sh603986 | T91×0.3+N88×0.2+A60×0.2+Tech78×0.2+MF70×0.1=76.7 | bullish→(RSI>75,sev2)→nb +R37 | R4×P3=95→88(多源+5) |
```

| Column | Content |
|--------|---------|
| CompositeTrace | weighted terms → rounded result |
| DirectionPath | base → risk adjustment → final + hints |
| NewsImpactCalc | matrix cell + adjustments |

If omitted, Candidate Pool must still have `CompositeTrace` column (minimal form).

---

## Section 6: Observation Pool

Unchanged threshold (Composite < 55). Add optional **Anomaly** column for stocks worth next-day watch despite low composite.

---

## Section 7: Excluded Stocks

```markdown
| Code | Name | ExclusionReason | ExclusionSource |
|------|------|-----------------|-----------------|
| sh688256 | 寒武纪 | 科创板不可交易 | board-policy |
| sz300975 | 商络电子 | atr_pct=9.0% > 8% | hard-filter |
```

| ExclusionSource | Meaning |
|-----------------|---------|
| `board-policy` | config-driven (sh688/bj) |
| `hard-filter` | liquidity / atr_pct |
| `soft-filter` | tech_score < 50 (if still excluded) |
| `manual` | LLM explicit exclude with reason |

---

## Board exclusion config (design)

Not embedded in SKILL prose. Proposed `config/trading-scope.json`:

```json
{
  "boards": {
    "sh688": { "exclude": true, "reason": "STAR board — account scope" },
    "bj": { "exclude": true, "reason": "BSE — account scope" },
    "sh": { "exclude": false },
    "sz": { "exclude": false }
  },
  "overrides": []
}
```

Step 2 reads config → writes `BoardPolicy` in Market State.  
Overrides allow single-code exceptions without editing SKILL.

**Impact:** semiconductor/AI themes recover 688 leaders in **Observation / cross-reference** when policy toggled — they appear in Excluded with `ExclusionSource=board-policy`, not silently dropped.

---

## Step 3 read contract (companion summary)

Step 3 **MUST** read in order:

1. `Market State.RegimeHint`
2. `Candidate Pool`: `DirectionFinal`, `RiskType`, `RiskSeverity`, `OverrideHint`, `Anomaly`
3. `Strategy Inputs` (unchanged — authoritative for MA20/ATR/High20/Low20)
4. `memory/RULES.md`

Step 3 **MUST NOT**:

- Re-derive Composite or NewsImpact
- Ignore `OverrideHint` when rule applies
- Treat `DirectionFinal` as hard veto when `OverrideHint` present

**Example decision log line (target format):**

```
sh603986: DirectionFinal=neutral-bull, OverrideHint=R37, RegimeHint=strong-sector → apply R37, retain 4★, MA20 buy zone unchanged
```

---

## Migration from V3

| V3 field | V4 mapping |
|----------|------------|
| Direction | → DirectionBase + DirectionFinal |
| MajorEventFlag | → MajorEvent |
| Risk | → RiskFlags + RiskType + RiskSeverity |
| (none) | + NewsImpact, NewsLink, OverrideHint, Anomaly, CompositeTrace |

**Backward compatibility:** Step 3 skill may accept V3 mappers during transition if `DirectionFinal` absent → treat `Direction` as both base and final, `OverrideHint=—`.

---

## Success criteria

| Metric | Target |
|--------|--------|
| Step 2 output | still zero prose paragraphs |
| NewsImpact | every pool stock has matrix cell citation in Score Trace |
| Risk differentiation | RSI<30 and MA双熊 never share same RiskType |
| Step 3 logs | cite OverrideHint on ≥80% of RSI>75 decisions in strong-sector days |
| Anomaly usage | ≥1 row/day on active market days without buy advice |
| Audit | third party can recompute DirectionBase + Composite from Trace alone |

---

## Non-goals (explicit)

- Replacing LLM for theme semantic matching
- Restoring individual stock analysis paragraphs
- Moving buy/stop/target into Step 2
- Auto-implementing scripts in this revision

---

## Open questions

1. **Score Trace mandatory or optional?** Recommended mandatory for Composite ≥ 70 stocks only (reduce table width).
2. **RegimeHint vs Step 3 index fetch** — duplicate signal; Step 3 index fetch remains authoritative for intraday, RegimeHint is pre-market prior only.
3. **R73/R74** — referenced in SKILL today but not in RULES.md; define before enabling OverrideHint tokens.
4. **JSON sidecar** — future option: emit `mapper.json` identical schema for programmatic backtest; out of scope for V4 markdown-only phase.

---

## Summary

Mapper V4 keeps V3's skeleton and data contract, but:

1. **Splits** direction into base (formula) vs final (soft, hint-driven)
2. **Grades** risk instead of uniform ceiling
3. **Rubrics** NewsImpact and theme heat sub-scores
4. **Adds** Anomaly (30 chars) as controlled black-swan channel
5. **Externalizes** board policy to config

LLM role shifts from *rule executor* to *rubric applier + anomaly annotator* — which is the capacity actually worth paying for.
