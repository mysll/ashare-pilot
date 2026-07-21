# Mapper V3 RESTRUCTURING — Design Spec

Date: 2026-06-24

## Objective

Restructure Mapper from a human-readable analysis report into a structured decision dataset for Step 3 consumption. The data contract between Step 2 and Step 3 is formalized.

## Scope

Two files modified:

| File | Change |
|------|--------|
| `.opencode/skills/daily-stock-mapping/SKILL.md` | Rewrite Impact Analysis, delete S/R extraction, add data contract rules |
| `.opencode/skills/daily-strategy/SKILL.md` | Update workflow, formulas, coverage, data source rules |

## Output Structure (mapper.md)

6 sections, no prose, no recommendations:

| # | Section | Format | Description |
|---|---------|--------|-------------|
| 1 | Market State | Key-value table | MarketRegime, DominantThemes, Style, FinancingFlow, RiskFlags |
| 2 | Theme Ranking | Table | Theme / Heat / Rank |
| 3 | Candidate Pool | Table | Code / Name / Composite / Direction / Theme / RoleTags / Emotion / Turnover% / Risk |
| 4 | Strategy Inputs | Table | Code / Price / MA20 / ATR / ATR% / High20 / Low20 — ALL candidates |
| 5 | Observation Pool | Table | Code / Name / Composite / Theme / Reason — full list, no truncation |
| 6 | Excluded Stocks | Table | Code / Name / ExclusionReason |

## Deleted Content

- Market background prose (市场背景)
- Tiered ranking labels (第一梯队/第二梯队)
- Individual stock analysis paragraphs (个股分解分析)
- Industry money flow commentary (行业资金流向)
- Summary/conclusion (总结)
- Support/Resistance section (支撑/阻力位)
- ATR Stop Distance, VWAP
- Any trading recommendations

## Adjustments from Initial Draft

1. **Direction kept** (downgraded to column): Candidate Pool retains `Direction` (bullish/neutral-bull/neutral/bearish) — directional feature, not prose
2. **Observation Pool Reason**: explicit `Reason` column added (BelowThreshold, TechnicalRisk, WeakTheme)
3. **Re-fetch rule softened**: "禁止重新拉数" → "authoritative source; re-fetch only for missing/invalid/stale fields"

## Step 2 → Step 3 Data Contract

Strategy Inputs table is the single authoritative source for: Price, MA20, ATR, ATR%, High20, Low20.

Step 3 re-fetch rule:
- Use Strategy Inputs values directly
- Re-fetch from API only if: field missing (N/A), field invalid (negative/zero), or stale data detected
- Default: no re-fetch

## Affected Pipeline Stages

| Stage | Status |
|-------|--------|
| Theme Extraction → themes.md | UNCHANGED |
| Stock Pool Build → theme_stocks.md | UNCHANGED |
| Technical Enrichment → theme_stocks.md enriched | UNCHANGED |
| Impact Analysis → mapper.md | COMPLETELY REWRITTEN |
| Support/Resistance → mapper.md | DELETED |

## Success Criteria

Step 3 execution log no longer contains:
- "Need ATR"
- "Need MA20"
- "Need Recent High"
- "Need additional data"
- "I'll need to fetch data"

Instead:
- "Load Mapper Strategy Inputs"
- "Read Candidate Pool"
- "Calculate Entry/Stop/Targets"
