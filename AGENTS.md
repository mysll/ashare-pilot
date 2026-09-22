# A-Share Pilot Agents

## Environment Setup

```bash
# Required environment variable (Windows cmd)
set PYTHONIOENCODING=utf-8

# Bash / Linux equivalent
export PYTHONIOENCODING=utf-8

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
- OpenCode CLI available on `PATH` when using the scheduler
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
predict/{date}/          Daily V5 outputs (news/themes, stock pool, mapper, strategy.json, daily_report.html, timing files)
intraday/{date}/         Intraday overnight outputs (mapper base/annotations/final, overnight_strategy.json, overnight_strategy.html)
operation/{date}/        Intraday human-operation snapshots, decisions, run pointers, and operation_guide.html
research/intraday-shadow/{date}/ Validation-only shadow rule contracts; never consumed by strategy
.cache/intraday/{date}/  Intraday compute cache (market_breadth, indices, concept_dashboard, scan_pool, compute_pool_enriched, theme_ranking, opportunity_pool)
memory/daily/{date}/     Morning verification (verification.json and verification.md)
memory/intraday/{date}/  Intraday verification (intraday_verification.md)
memory/RULES.md          Learned morning rules; an empty template in a zero-history project
memory/INTRADAY_RULES.md Learned intraday rules; an empty template in a zero-history project
memory/SHARED_RULES.md   Learned shared rules; an empty template in a zero-history project
memory/EXPERT_RULES.md   Expert-authorized Daily/Overnight rules; initialized empty
memory/RULE_GOVERNANCE.md Initialized lifecycle/evidence policy; contains no strategy rules
memory/PERFORMANCE.md    Initialized zero-sample ledger; updated from actual reviews
memory/MEMORY.md         Initialized memory navigation and write-path description
.agents/skills/          Canonical workflow and leaf-skill instructions
.opencode/agents/        Specialist agents (sector/equity/microstructure/performance analysts, macro strategist, portfolio manager)
.opencode/commands/      User-facing daily, intraday, review, and operation-guide commands
resources/schemas/       Authoritative JSON schemas for inter-step contracts
resources/templates/     Initialized memory and report templates
src/ashare_pilot/        Agent-neutral Python APIs and the unified CLI
config/                  Authoritative project configuration
data/theme-library/      Authoritative persistent theme data
logs/                    Scheduler and task logs
```

## Analysis and Execution Workflows

**Morning Analysis (09:20 trading days):** Orchestrates `daily-market-analysis` and its designated specialist agents. Reads `RULES.md` + `SHARED_RULES.md` plus applicable `EXPERT_RULES.md`; zero-history templates contain no rule rows. Canonical strategy output is validated `daily_strategy.v3` at `predict/{date}/strategy.json`; the human board is `daily_report.html`.

**Opening Operation Guide (on demand after 09:35):** Orchestrates `intraday-operation-guide`. It discovers the valid 09:35/09:40 confirmation state, may perform a later recheck, and publishes immutable snapshots/decisions plus `operation_run.latest.json` and `operation_guide.html`. This is human guidance only and never places orders. Run the state-aware lifecycle instead of manually choosing a confirmation stage:

```bash
uv run --frozen ashare-pilot operations guide run --date YYYY-MM-DD
```

**Intraday Overnight Analysis (14:30 trading days):** Orchestrates `intraday-market-analysis`. Reads `INTRADAY_RULES.md` + `SHARED_RULES.md` plus applicable `EXPERT_RULES.md`; zero-history templates contain no rule rows. Canonical outputs are validated `intraday_mapper.v3` at `intraday/{date}/intraday_mapper.json` and `intraday_overnight_strategy.v3` at `overnight_strategy.json`; the human board is `overnight_strategy.html`.

After the deterministic intraday compute/scoring phases succeed, the core pipeline refreshes
`intraday_shadow_rule_validation.v1` non-blockingly. This contract is validation-only:
it must never feed mapper/strategy generation, create recommendations, or update learned rules
automatically.

Reviews use the canonical JSON contracts and actual market results. Morning review writes under `memory/daily/{date}/`; intraday review writes under `memory/intraday/{date}/`. Rules are versioned with verification history and may only advance according to `memory/RULE_GOVERNANCE.md`.

### Agent Ownership

- `sector-analyst`: daily news and Theme perception
- `equity-analyst`: daily stock-pool and mapper perception
- `portfolio-manager`: daily and overnight strategy reasoning
- `market-microstructure-analyst`: intraday market and stock perception
- `macro-strategist`: intraday mapper reasoning
- `performance-analyst`: daily and intraday review

When a workflow skill mandates specialist dispatch, the orchestrator must use those exact roles and keep inter-agent prompts limited to the paths and outputs defined by the skill. JSON files are the only inter-step contracts.

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

# Validate published strategy contracts
uv run --frozen ashare-pilot strategy daily validate predict/YYYY-MM-DD/strategy.json
uv run --frozen ashare-pilot strategy overnight validate intraday/YYYY-MM-DD/overnight_strategy.json

# Build and validate the isolated intraday shadow-rule contract
uv run --frozen ashare-pilot review intraday shadow build --as-of YYYY-MM-DD --replace
uv run --frozen ashare-pilot review intraday shadow validate research/intraday-shadow/YYYY-MM-DD/shadow_rule_validation.json

# Side-car limit-up cluster screen (informational only, never feeds the strategy)
uv run --frozen ashare-pilot screen limit-up-cluster --date YYYY-MM-DD --json

# Expert Rules (prefer $manage-expert-rules for semantic/capability checks)
uv run --frozen ashare-pilot automation rules expert list
uv run --frozen ashare-pilot automation rules expert --help

# State-aware opening confirmation and human operation board (never places orders)
uv run --frozen ashare-pilot operations guide run --date YYYY-MM-DD

# Generate daily verification data after market close
uv run --frozen ashare-pilot review daily verify --help
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
- Daily V5 ownership is strict: Step 1 produces news + Themes; Step 2 is perception
  only and MUST NOT produce Direction or RiskSeverity; Step 3 is the sole reasoning layer
- `mapper.strategy_view.json` is the compact Step 2 → Step 3 contract; the Step 3
  LLM writes selected-only decisions and deterministic code finalizes `strategy.json`
- `strategy.json` uses qualitative `WATCH_ONLY` / `LIGHT` / `STANDARD` position
  tiers; do not reintroduce legacy numeric position contracts
- A-share scope only (sh/sz prefix). HK/US and other markets are excluded from the daily workflow
- Pre-market data availability: auction data from 9:15-9:25, technicals from yesterday's close, money flow is yesterday's

## Memory & Rules System

Initialize a new project with `uv run --frozen ashare-pilot automation memory init`. This creates navigation, zero-sample performance, governance, empty learned-rule templates, an empty `EXPERT_RULES.md`, and empty indexes, and never overwrites existing memory. Empty rule tables mean no learned rules and must not be filled with invented history. Before generating morning strategy, read `memory/RULES.md` + `memory/SHARED_RULES.md` + applicable `memory/EXPERT_RULES.md`. Before generating overnight strategy, read `memory/INTRADAY_RULES.md` + `memory/SHARED_RULES.md` + applicable `memory/EXPERT_RULES.md`. Expert Rules exist immediately, are limited to Daily/Overnight, and are maintained through `$manage-expert-rules` or the trusted CLI bypass. After market close, Morning writes to `memory/daily/{date}/verification.md`, and Intraday writes to `memory/intraday/{date}/intraday_verification.md`. `memory/RULE_GOVERNANCE.md` MUST be read before changing any learned-rule lifecycle; single-day discoveries are never executable learned rules.

## Automation

```bash
auto.bat                        # Windows: start the configured trading-day task daemon
./auto.sh                       # Bash/Linux equivalent
uv run --frozen ashare-pilot automation scheduler run --dry-run                 # Validate config and show upcoming runs
uv run --frozen ashare-pilot automation scheduler run --once daily-analysis     # Run one configured task now
uv run --frozen ashare-pilot automation scheduler run --config path/to/tasks.json
uv run --frozen ashare-pilot automation rules check     # Validate rule IDs, capacity, lifecycle sections, and references
```

Scheduler tasks are defined in `config/cron-tasks.json`. Times use
the `Asia/Shanghai` timezone from `config/trading-calendar.json` and
run only on configured A-share trading days. `T0` means the trigger trading
day; `TP1` means the previous trading day. The default schedule runs morning
analysis at 09:20, previous-day intraday review at 09:45, intraday overnight
analysis at 14:30, and morning-strategy review at 15:10. The opening operation
guide remains state-aware and on demand unless explicitly added as a scheduler
task. Config changes require a daemon restart, and schedules missed while the
daemon was stopped are not replayed.
