# Trading Office Agents

## Environment Setup

```bash
# Required environment variable
set PYTHONIOENCODING=utf-8

# Optional eager sync; uv run also syncs automatically
uv sync --frozen
```

Runtime commands use `uv run --frozen ashare-pilot ...`; `uv` is the only
required environment manager and `mise` is an optional developer shortcut.
All entry points use uv's default project environment `.venv`; do not set
`UV_PROJECT_ENVIRONMENT` or require manual activation. GUI clients such as
OpenCode Desktop do not activate a virtual environment, and `uv run` handles
the environment automatically.

**Prerequisites:**
- Chrome browser installed (required for cookie extraction)
- `.cookie` restored from a trusted source or generated on Windows; the core
  CLI does not load East Money credentials from `.env`

**Cookie setup (Windows-only):**
```bash
update_cookie.bat    # Opens Chrome for login/captcha verification
```

## Stock Code Prefixes

| Market | Prefix | Example | Scope |
|--------|--------|---------|-------|
| A Stock Shanghai | `sh` | `sh600519` | ✅ Active |
| A Stock Shenzhen | `sz` | `sz000001` | ✅ Active |
| A Stock Beijing | `bj` | `bj835185` | ❌ Excluded |
| Shanghai STAR | `sh688` | `sh688981` | ❌ Excluded |
| HK Stock | `hk` | `hk00700` | Daily pipeline excluded |
| US Stock | `usr_` | `usr_nvda` | Daily pipeline excluded |
| Domestic Future | `nf_` | `nf_IF0` | Daily pipeline excluded |
| Oversea Future | `hf_` | `hf_OIL` | Daily pipeline excluded |

**Trading scope:** Only `sh` and `sz` prefixes (excludes STAR board `sh688*` and BSE `bj*`). See `config/trading-scope.json`.

## Directory Layout

```
predict/{date}/          Daily pipeline outputs (news.json, news.md, themes.json, theme_stocks.json, mapper.json, strategy.json, daily_report.html)
intraday/{date}/         Intraday overnight outputs (intraday_mapper.base.json, annotations.json, intraday_mapper.json, overnight_strategy.json, overnight_strategy.html)
.cache/intraday/{date}/  Intraday compute cache (market_breadth, indices, concept_dashboard, scan_pool, compute_pool_enriched, theme_ranking, opportunity_pool)
memory/daily/{date}/     Morning verification (verification.md)
memory/intraday/{date}/  Intraday verification (intraday_verification.md)
memory/RULES.md          Learned morning rules; an empty template in a zero-history project
memory/INTRADAY_RULES.md Learned intraday rules; an empty template in a zero-history project
memory/SHARED_RULES.md   Learned shared rules; an empty template in a zero-history project
memory/RULE_GOVERNANCE.md Initialized lifecycle/evidence policy; contains no strategy rules
memory/PERFORMANCE.md    Initialized zero-sample ledger; updated from actual reviews
memory/MEMORY.md         Initialized memory navigation and write-path description
.opencode/agents/        Custom subagent definitions (financial-news-analyst, financial-news-mapper, intraday-market-observer, trading-strategist)
src/ashare_pilot/        Agent-neutral Python APIs and the unified CLI
config/                  Authoritative project configuration
data/theme-library/      Authoritative persistent theme data
```

## Two-Agent System

**Morning Agent (9:20 weekdays):** Reads `RULES.md` + `SHARED_RULES.md`; zero-history templates contain no rule rows. Generates `predict/{date}/strategy.json` (HTML report optional).

**Intraday Agent (14:30 weekdays):** Orchestrates skill `intraday-market-analysis`. Reads `INTRADAY_RULES.md` + `SHARED_RULES.md`; zero-history templates contain no rule rows. Canonical outputs: `intraday/{date}/intraday_mapper.json` + `overnight_strategy.json`; human board: `overnight_strategy.html`. JSON is the only inter-step contract.

Both agents write verification after market close: Morning → `memory/daily/{date}/verification.md`, Intraday → `memory/intraday/{date}/intraday_verification.md`. Rules are versioned with verification history.

## Core Commands

Run the project CLI through `uv run --frozen ashare-pilot`. Leaf commands preserve the former JSON,
CSV, text, output-file, default-value, and failure contracts.

```bash
# Real-time quotes
uv run --frozen ashare-pilot market-data quote sh600519,hk00700 --json
uv run --frozen ashare-pilot market-data quote --search "茅台"

# Historical K-line & indicators (A stocks only, 前复权)
uv run --frozen ashare-pilot market-data history sh600519 --range 1y
uv run --frozen ashare-pilot indicators calculate sh600519 --indicators rsi,macd,boll

# Dragon & Tiger / Margin / Money Flow
uv run --frozen ashare-pilot market-data special lhb --json
uv run --frozen ashare-pilot market-data special rzye --top 20
uv run --frozen ashare-pilot market-data money-flow --json

# News (daily workflow: one fetch writes both canonical JSON and readable Markdown)
uv run --frozen ashare-pilot news fetch --date YYYY-MM-DD --output-dir predict/YYYY-MM-DD

# Theme Library queries
uv run --frozen ashare-pilot themes query list --json
uv run --frozen ashare-pilot themes query candidates <theme> --json
uv run --frozen ashare-pilot themes query stock sz000977,sh601869 --roles --json
```

## Theme Library Build Order

Mandatory sequence. Steps depend on prior output. Or use the all-in-one batch file:

```bash
update_theme.bat                                           # Full build (concepts + stocks + library)
update_theme_stock.bat                                     # Skip concepts, only stocks + library

uv run --frozen ashare-pilot themes concepts fetch -q     # 1. Board list (resume on failure)
uv run --frozen ashare-pilot themes concepts fetch-stocks  # 2. Member stocks (after concepts exist)
uv run --frozen ashare-pilot themes library build         # 3. Build index files
```

## Daily Pipeline Rules

- **NEVER** use `uv run --frozen ashare-pilot market-data stocks all` in the pipeline (~5500 stocks, 60s — too slow for pre-market)
- Target only stocks in the pool (30-50), not full market
- `news.json` is script-generated and is the canonical news evidence contract;
  `news.md` may be reorganized by the LLM as a readable briefing
- Require `predict/{date}/news.json` before Step 2; all downstream news evidence
  references use `news#<id>` and never Markdown line numbers
- A-share scope only (sh/sz prefix). HK/US and other markets are excluded from the daily workflow
- Pre-market data availability: auction data from 9:15-9:25, technicals from yesterday's close, money flow is yesterday's

## Memory & Rules System

Initialize a new project with `uv run --frozen ashare-pilot automation memory init`. This creates navigation, zero-sample performance, governance, empty rule templates, and empty indexes, and never overwrites existing memory. Empty rule tables mean no learned rules and must not be filled with invented history. Before generating morning strategy, read `memory/RULES.md` + `memory/SHARED_RULES.md`. Before generating overnight strategy, read `memory/INTRADAY_RULES.md` + `memory/SHARED_RULES.md`. After market close, Morning writes to `memory/daily/{date}/verification.md`, and Intraday writes to `memory/intraday/{date}/intraday_verification.md`. `memory/RULE_GOVERNANCE.md` MUST be read before changing any rule lifecycle; single-day discoveries are never executable rules.

## Automation

```bash
auto.bat                        # Cron daemon (default: 9:20 weekday daily-market-analysis)
uv run --frozen ashare-pilot automation scheduler run --dry-run    # Check next run
uv run --frozen ashare-pilot automation scheduler run --once        # Run once immediately
uv run --frozen ashare-pilot automation rules check     # Validate rule IDs, capacity, lifecycle sections, and references
```
