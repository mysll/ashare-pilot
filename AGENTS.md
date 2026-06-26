# Trading Office Agents

## Stock Code Prefixes

| Market | Prefix | Example |
|--------|--------|---------|
| A Stock Shanghai | `sh` | `sh600519` |
| A Stock Shenzhen | `sz` | `sz000001` |
| A Stock Beijing | `bj` | `bj835185` |
| HK Stock | `hk` | `hk00700` |
| US Stock | `usr_` | `usr_nvda` |
| Domestic Future | `nf_` | `nf_IF0` |
| Oversea Future | `hf_` | `hf_OIL` |

## Directory Layout

```
predict/{date}/          Daily pipeline outputs (news.md, themes.md, theme_stocks.md, mapper.md, strategy.md)
memory/daily/{date}/     Verification & review (verification.md) — written post-market
memory/RULES.md          Trading rules — MUST read before generating strategy
memory/PERFORMANCE.md    Cumulative performance & key dates
memory/MEMORY.md         Memory system navigation
```

## Key Scripts

All scripts under `.opencode/skills/` support `--json` (structured), `-o <file>`, and `--csv`.

```bash
# Real-time quotes
python .opencode/skills/stock-analysis/scripts/fetch_stock.py sh600519,hk00700 --json
python .opencode/skills/stock-analysis/scripts/fetch_stock.py --search "茅台"

# Historical K-line & indicators (A stocks only, 前复权)
python .opencode/skills/stock-analysis/scripts/fetch_history.py sh600519 --range 1y
python .opencode/skills/stock-analysis/scripts/fetch_indicators.py sh600519 --indicators rsi,macd,boll

# Dragon & Tiger / Margin / Money Flow
python .opencode/skills/stock-analysis/scripts/fetch_special.py lhb --json
python .opencode/skills/stock-analysis/scripts/fetch_special.py rzye --top 20
python .opencode/skills/stock-analysis/scripts/fetch_money_flow.py --json

# News
python .opencode/skills/daily-news-brief/scripts/fetch_news.py

# Theme Library queries
python .opencode/skills/theme-library/scripts/query_theme.py list --json
python .opencode/skills/theme-library/scripts/query_theme.py candidates <theme> --json
python .opencode/skills/theme-library/scripts/query_theme.py stock sz000977,sh601869 --roles --json
```

## Theme Library Build Order

Mandatory sequence. Steps depend on prior output:

```bash
python .opencode/skills/theme-library/scripts/fetch_concepts.py -q     # 1. Board list (resume on failure)
python .opencode/skills/theme-library/scripts/fetch_concept_stocks.py  # 2. Member stocks (after concepts exist)
python .opencode/skills/theme-library/scripts/build_library.py         # 3. Build index files
```

## Daily Pipeline Rules

- **NEVER** use `fetch_all_astocks.py` in the pipeline (~5500 stocks, 60s — too slow for pre-market)
- Target only stocks in the pool (30-50), not full market
- All output files are markdown written directly by the LLM — do NOT write scripts to generate them
- Board filter: `sh688*` (科创) and `bj*` (北交) stocks are always excluded
- A-share scope only (sh/sz prefix). HK/US and other markets are excluded from the daily workflow
- Pre-market data availability: auction data from 9:15-9:25, technicals from yesterday's close, money flow is yesterday's

## Memory & Rules System

Before generating `strategy.md`, MUST read `memory/RULES.md` for active trading rules. After market close, verification goes to `memory/daily/{date}/verification.md`. New rule discoveries update `memory/RULES.md` with verification history.

## Cookie Setup (East Money APIs)

Some East Money endpoints require authentication. Auto-login requires credentials in `.env`:

```
EASTMONEY_USERNAME=your_username
EASTMONEY_PASSWORD=your_password
```

```
python .opencode/skills/stock-analysis/scripts/refresh_cookie.py --refresh
```

Set `EASTMONEY_COOKIE_BACKEND=file` in `.env` to disable auto-login fallback.
