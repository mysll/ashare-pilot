# Trading Office Agents

## Environment Setup

```bash
# Required environment variable
set PYTHONIOENCODING=utf-8

# Python dependencies
pip install -r .opencode/scripts/requirements.txt    # requests, websocket-client
```

**Prerequisites:**
- Chrome browser installed (required for cookie extraction)
- `.env` file (not tracked in git):
  ```
  EASTMONEY_USERNAME=your_username
  EASTMONEY_PASSWORD=your_password
  EASTMONEY_COOKIE_BACKEND=file   # optional: skip auto-login fallback
  ```

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

**Trading scope:** Only `sh` and `sz` prefixes (excludes STAR board `sh688*` and BSE `bj*`). See `.opencode/config/trading-scope.json`.

## Directory Layout

```
predict/{date}/          Daily pipeline outputs (news.md, themes.md, theme_stocks.md, mapper.md, strategy.md)
intraday/{date}/         Intraday pipeline outputs (intraday_mapper.md)
memory/daily/{date}/     Morning verification (verification.md)
memory/intraday/{date}/  Intraday verification (intraday_verification.md)
memory/RULES.md          Morning trading rules — MUST read before generating strategy
memory/INTRADAY_RULES.md Intraday trading rules — MUST read before generating intraday strategy
memory/SHARED_RULES.md   Shared rules (both agents)
memory/PERFORMANCE.md    Cumulative performance & key dates
memory/MEMORY.md         Memory system navigation
.opencode/agents/        Custom subagent definitions (financial-news-analyst, financial-news-mapper, intraday-market-observer, trading-strategist)
```

## Two-Agent System

**Morning Agent (9:20 weekdays):** Reads `RULES.md` + `SHARED_RULES.md`. Generates `predict/{date}/strategy.md`.

**Intraday Agent (14:30 weekdays):** Reads `INTRADAY_RULES.md` + `SHARED_RULES.md`. Generates `intraday/{date}/intraday_mapper.md`.

Both agents write verification after market close: Morning → `memory/daily/{date}/verification.md`, Intraday → `memory/intraday/{date}/intraday_verification.md`. Rules are versioned with verification history.

## Key Scripts

All scripts support `--json` (structured), `-o <file>`, and `--csv`. Fetch scripts are in `.opencode/lib/fetch/`.

```bash
# Real-time quotes
python .opencode/lib/fetch/fetch_stock.py sh600519,hk00700 --json
python .opencode/lib/fetch/fetch_stock.py --search "茅台"

# Historical K-line & indicators (A stocks only, 前复权)
python .opencode/lib/fetch/fetch_history.py sh600519 --range 1y
python .opencode/lib/fetch/fetch_indicators.py sh600519 --indicators rsi,macd,boll

# Dragon & Tiger / Margin / Money Flow
python .opencode/lib/fetch/fetch_special.py lhb --json
python .opencode/lib/fetch/fetch_special.py rzye --top 20
python .opencode/lib/fetch/fetch_money_flow.py --json

# News
python .opencode/skills/daily-news-brief/scripts/fetch_news.py

# Theme Library queries
python .opencode/skills/theme-library/scripts/query_theme.py list --json
python .opencode/skills/theme-library/scripts/query_theme.py candidates <theme> --json
python .opencode/skills/theme-library/scripts/query_theme.py stock sz000977,sh601869 --roles --json
```

## Theme Library Build Order

Mandatory sequence. Steps depend on prior output. Or use the all-in-one batch file:

```bash
update_theme.bat                                           # Full build (concepts + stocks + library)
update_theme_stock.bat                                     # Skip concepts, only stocks + library

python .opencode/skills/theme-library/scripts/fetch_concepts.py -q     # 1. Board list (resume on failure)
python .opencode/skills/theme-library/scripts/fetch_concept_stocks.py  # 2. Member stocks (after concepts exist)
python .opencode/skills/theme-library/scripts/build_library.py         # 3. Build index files
```

## Daily Pipeline Rules

- **NEVER** use `fetch_all_astocks.py` in the pipeline (~5500 stocks, 60s — too slow for pre-market)
- Target only stocks in the pool (30-50), not full market
- All output files are markdown written directly by the LLM — do NOT write scripts to generate them
- A-share scope only (sh/sz prefix). HK/US and other markets are excluded from the daily workflow
- Pre-market data availability: auction data from 9:15-9:25, technicals from yesterday's close, money flow is yesterday's

## Memory & Rules System

Before generating `strategy.md`, MUST read `memory/RULES.md` for active trading rules. Before generating `intraday_mapper.md`, MUST read `memory/INTRADAY_RULES.md`. After market close, Morning writes to `memory/daily/{date}/verification.md`, Intraday writes to `memory/intraday/{date}/intraday_verification.md`. New rule discoveries update the corresponding rules file with verification history.

## Automation

```bash
auto.bat                        # Cron daemon (default: 9:20 weekday daily-market-analysis)
python .opencode/scripts/cron-daemon.py --dry-run    # Check next run
python .opencode/scripts/cron-daemon.py --once        # Run once immediately
```
