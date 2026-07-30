---
name: daily-market-analysis
description: Use when users request comprehensive daily financial market analysis workflow - generates news briefing, stock data mapping, and trading strategy recommendations in sequence.
---

# Daily Market Analysis Workflow (V5)

3-step pipeline implementing the V5 Compute → Perception → Reasoning architecture:
Step 2 NEVER produces Direction or RiskSeverity (V5 Invariant 1). Step 3 is the sole Reasoning layer.

## Mandatory Sub-Agent Dispatch (V5 Invariant 3)

This skill is a pure orchestrator. Every step MUST be dispatched to the designated
subagent_type via the task tool. The main orchestrator MUST NOT inline any analysis,
mapping, scoring, or strategy reasoning work. Violating this constraint renders the
sub-agent model/temperature/permission configuration ineffective.

## Performance Constraints

**DO NOT** use `uv run --frozen ashare-pilot market-data stocks all` in this pipeline. It fetches ~5500 stocks and takes 30-60s — too slow for pre-market delivery.

All data fetching targets ONLY stocks in the pool (theme library candidates + news-mentioned), typically 30-50 stocks. Never fetch full market data.

Target wall-clock: Step 1 (news + themes) + Step 2 (mapping) + Step 3 (strategy) should
normally publish by 09:35. The workflow still starts at 09:20; do not move work
before that boundary.

Report end-to-end recorded time only when all three timing files are complete
artifact-linked runs. Use `step1_timing.total_recorded_seconds +
step2_timing.total_recorded_seconds + step3_timing.total_recorded_seconds`;
never compare only Step 2 after moving Theme work into Step 1.

---

## Step 1: News and Theme Perception

**Agent:** `sector-analyst`

**Action:** Execute the following one unambiguous `daily-theme-extraction`
workflow.

**sector-analyst prompt (exact format, MUST NOT deviate):**

```
Load skill `daily-theme-extraction` and execute.

Date: {YYYY-MM-DD}

Outputs:
- predict/{YYYY-MM-DD}/news.json
- predict/{YYYY-MM-DD}/news.md
- predict/{YYYY-MM-DD}/themes.json
```

**CRITICAL:** Do NOT inline any news, Theme inputs, formulas, validator errors,
or artifact contents. Keep the prompt clean.

**Outputs:** `news.json`, `news.md`, `themes.json`, and report-only
`step1_timing.json`

---

## Step 2: Stock Data Mapping (Perception Layer)

**Agent:** `equity-analyst`

**Action:** Execute the following one unambiguous `daily-stock-mapping` workflow.

**equity-analyst prompt (exact format, MUST NOT deviate):**

```
Load skill `daily-stock-mapping` and execute.

Date: {YYYY-MM-DD}

Inputs:
- predict/{YYYY-MM-DD}/news.json
- predict/{YYYY-MM-DD}/themes.json

Outputs:
- predict/{YYYY-MM-DD}/theme_stocks.extra.json (optional supplemental source)
- predict/{YYYY-MM-DD}/theme_stocks.universe.json
- predict/{YYYY-MM-DD}/theme_stocks.base.json
- predict/{YYYY-MM-DD}/theme_stocks.json
- predict/{YYYY-MM-DD}/mapper.annotations.json
- predict/{YYYY-MM-DD}/mapper.json
- predict/{YYYY-MM-DD}/mapper.strategy_view.json
```

**CRITICAL:** Do NOT inline any file content, scoring formulas, filter rules, or analysis. Keep the prompt clean.

**Outputs:** `theme_stocks.json`, `mapper.annotations.json`, `mapper.json`,
`mapper.strategy_view.json`, and report-only `step2_timing.json`

---

## Step 3: Trading Strategy (Reasoning Layer)

**Agent:** `portfolio-manager`

**Action:** Execute the following one unambiguous `daily-strategy` workflow.

**portfolio-manager prompt (exact format, MUST NOT deviate):**

```
Load skill `daily-strategy` and execute.

Date: {YYYY-MM-DD}

Input:
- predict/{YYYY-MM-DD}/mapper.strategy_view.json

Outputs:
- predict/{YYYY-MM-DD}/strategy.json
- predict/{YYYY-MM-DD}/daily_report.html
```

**CRITICAL:** Do NOT inline any file content, scoring formulas, filter rules,
validator errors, or analysis. The portfolio-manager owns prepare, compact
input reads, draft generation, validation repair, finalize, and timing.

**Output:** `predict/{YYYY}-{MM}-{DD}/strategy.json` (`daily_strategy.v3`) and `predict/{YYYY}-{MM}-{DD}/daily_report.html`

---

## Output Files

| File | Content | Layer / Step |
|------|---------|-------------|
| `predict/{date}/news.json` | Canonical fetched news with global incremental IDs (`daily_news.v1`) | Perception (Step 1) |
| `predict/{date}/news.md` | Script-generated readable briefing; not an evidence contract | Perception (Step 1) |
| `predict/{date}/themes.json` | Deterministically assembled Theme contract (`daily_themes.v2`) | Perception (Step 1) |
| `predict/{date}/step1_timing.json` | Artifact-linked news/Theme timing diagnostics | Observability |
| `predict/{date}/theme_stocks.extra.json` | Optional LLM supplemental stocks for market/news/LHB sources | Perception (Step 2.2 input) |
| `predict/{date}/theme_stocks.universe.json` | Script-built pre-indicator stock universe for `uv run --frozen ashare-pilot indicators pool fetch` | Perception (Step 2.2 bridge) |
| `predict/{date}/theme_stocks.base.json` | Script-built deterministic stock-pool base with scope and filters | Perception (Step 2.2-2.3) |
| `predict/{date}/theme_stocks.json` | Validated stock-pool machine contract (`daily_theme_stocks.v2`) | Perception (Step 2) |
| `predict/{date}/mapper.annotations.json` | LLM-owned Step 2 perception annotations (`daily_mapper_annotations.v1`) | Perception (Step 2.4) |
| `predict/{date}/mapper.json` | Full validated Step 2 machine contract (`daily_mapper.v2`) | Perception (Step 2) |
| `predict/{date}/mapper.strategy_view.json` | Compact Step 3 reading contract (`daily_strategy_input.v2`) projected from mapper.json | Perception → Reasoning bridge |
| `predict/{date}/step2_timing.json` | Report-only stage duration, byte, failure, and count diagnostics | Observability |
| `predict/{date}/.strategy_llm_input.json` | Non-contract compact all-candidate Step 3 decision input | Step 3 workflow |
| `predict/{date}/strategy.draft.json` | Non-contract selected-only LLM decisions linked by content hash | Step 3 workflow |
| `predict/{date}/step3_timing.json` | Report-only prepare/LLM/finalize timing and artifact fingerprints | Observability |
| `predict/{date}/strategy.json` | Conditional pre-open decisions with qualitative `WATCH_ONLY/LIGHT/STANDARD` position tiers (`daily_strategy.v3`) | Reasoning (Step 3) |
| `predict/{date}/daily_report.html` | Daily readable summary rendered from JSON: themes, strategy table, stock details, observation/excluded pools, referenced news | Reasoning (Step 3 readable output) |

## Quick Reference

| Layer | Step | Agent | Input | Output | Key V5 constraint |
|-------|------|-------|-------|--------|-------------------|
| Perception | 1 | sector-analyst + daily-theme-extraction | — | news.json + news.md + themes.json | Step 1 subagent owns fetch and all validation |
| Perception | 2 | equity-analyst + daily-stock-mapping V5 | validated news.json + themes.json | prepare -> mapper.annotations.json -> finalize -> mapper.strategy_view.json | **No Direction / RiskSeverity** (Invariant 1) |
| Reasoning | 3 | portfolio-manager + daily-strategy V5 | compact all-candidate input + RULES/SHARED_RULES + applicable EXPERT_RULES | selected-only draft -> strategy.json + daily_report.html | Final decisions remain LLM-owned; Python completes deterministic contracts |

Phase 3 is a black-box `portfolio-manager` dispatch. Its `daily-strategy` leaf
skill owns prepare → compact draft → finalize; full source JSON remains outside
the hot LLM context.

## Common Usage

- "Get today's market analysis"
- "Run daily analysis workflow"
- "Generate trading recommendations"
- "/daily-new-analysis"

## Notes

- Each step depends on previous output
- Directory: `predict/{YYYY}-{MM}-{DD}/` (e.g., `predict/2026-04-07/`)
- All output in Chinese (中文)
- **V5 architecture:** Compute (Python) → Perception (Steps 1-2) → Reasoning (Step 3) → Decision (`strategy.json` + `daily_report.html`)
- `uv run --frozen ashare-pilot indicators pool fetch` outputs V5 nested JSON (`raw_observation` + `computed_perception` each with `{value, confidence, trace}` per field)
- Step 2 NEVER produces Direction / RiskSeverity — Step 3 is the sole Reasoning authority
- Daily pipeline runs at any time; data availability depends on market state (see § Execution Timing)
