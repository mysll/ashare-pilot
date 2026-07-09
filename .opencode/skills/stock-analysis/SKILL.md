---
name: stock-analysis
description: >
  Fetch real-time and historical stock market data for Chinese and international markets.
  Use when the user needs to check stock prices, market data, K-line history, financial
  information, Dragon and Tiger List (龙虎榜), technical indicators(macd, rsi, boll etc),
  Margin Trading data (融资融券), or Industry Money Flow (行业资金流向) for A stocks
  (sh/sz/bj), HK stocks, US stocks, or futures (domestic/oversea).
  Triggers on requests like "check stock price", "stock quote", "market data", "historical data",
  "K-line", "龙虎榜", "融资融券", "技术指标", "资金流向" or any query involving stock codes.
---

# Stock Analysis

Fetch real-time and historical stock data from Chinese financial APIs.

Scripts live in `.opencode/lib/fetch/` (shared) and the data source classes are in `.opencode/lib/datasources/`.

## Quick Start

### Real-time Data

```bash
python .opencode/lib/fetch/fetch_stock.py sh000001,sz399001
python .opencode/lib/fetch/fetch_stock.py hk00700,usr_nvda --json
python .opencode/lib/fetch/fetch_stock.py sh600519 --csv -o output.csv   # Save as CSV
python .opencode/lib/fetch/fetch_stock.py --search "茅台"
python .opencode/lib/fetch/fetch_stock.py sh600519 -o output.txt           # Save to file
python .opencode/lib/fetch/fetch_stock.py sh600519 --json -o output.json   # Save as JSON
```

### Intraday K-line (Minute Data)

```bash
python .opencode/lib/fetch/fetch_stock.py sh600519 --intraday              # Today's 5-min K-line
python .opencode/lib/fetch/fetch_stock.py sh600519 --intraday --scale 1    # Today's 1-min K-line
python .opencode/lib/fetch/fetch_stock.py sh600519 --intraday --scale 15   # Today's 15-min K-line
python .opencode/lib/fetch/fetch_stock.py sh600519 --intraday --days 3     # Last 3 days, 5-min K-line
python .opencode/lib/fetch/fetch_stock.py sh600519 --intraday --days 5 --scale 1  # Last 5 days, 1-min K-line
python .opencode/lib/fetch/fetch_stock.py sh600519 --intraday --json       # JSON output
python .opencode/lib/fetch/fetch_stock.py sh600519 --intraday --csv        # CSV output
```

**Intraday Parameters:**
| Parameter | Description | Default |
|-----------|-------------|---------|
| `--intraday` | Enable intraday K-line mode | - |
| `--scale` | Minute interval (1, 5, 15, 30, 60) | 5 |
| `--days` | Number of days (1-5) | 1 (today only) |

**Note**: `--days` controls how many days of data to fetch, ranging from 1 (today only) to 5 (maximum).

**Intraday Fields:** `time`, `open`, `high`, `low`, `close`, `volume`, `amount`, `ma_price5`, `ma_volume5`

**Note:** Intraday K-line only supports A stocks (sh/sz/bj prefix).

### All A Stocks (Bulk Data)

```bash
python .opencode/lib/fetch/fetch_all_astocks.py                  # Summary output
python .opencode/lib/fetch/fetch_all_astocks.py -o stocks.csv    # Save as CSV (default)
python .opencode/lib/fetch/fetch_all_astocks.py -o stocks.json --json-output  # Save as JSON
python .opencode/lib/fetch/fetch_all_astocks.py --json           # Print JSON to stdout
python .opencode/lib/fetch/fetch_all_astocks.py --source sina    # Force Sina source
python .opencode/lib/fetch/fetch_all_astocks.py --source eastmoney  # Eastmoney source (has volume_ratio)
```

**Parameters:**
| Parameter | Description | Default |
|-----------|-------------|---------|
| `--source` | Data source: `eastmoney` (has volume_ratio) or `sina` (no volume_ratio) | `sina` |
| `--json-output` | Save as JSON instead of CSV when using `-o` | - |

Returns ~5500 A stocks with: code, name, price, yestclose, updown, percent, high, low, open, volume, amount, turnover, volume_ratio, swing, pe, pb, total_mv, float_mv, market, source.

### Historical Data (A stocks only)

```bash
python .opencode/lib/fetch/fetch_history.py sh600519                  # Last 3 months
python .opencode/lib/fetch/fetch_history.py sh600519 --range 5d       # Last 5 calendar days
python .opencode/lib/fetch/fetch_history.py sz000001 --range 1m       # Last 1 month
python .opencode/lib/fetch/fetch_history.py sh600519 --range 1y --json
python .opencode/lib/fetch/fetch_history.py sh600519 --csv
python .opencode/lib/fetch/fetch_history.py sh600519 --start 20260101 --end 20260331
python .opencode/lib/fetch/fetch_history.py sh600519 -o output.txt    # Save to file
python .opencode/lib/fetch/fetch_history.py sh600519 --json -o output.json   # Save as JSON
python .opencode/lib/fetch/fetch_history.py sh600519 --csv -o output.csv     # Save as CSV
```

`--range` accepts any positive integer followed by `d`, `w`, `m`, or `y`
(calendar days/weeks/months/years), such as `2d`, `5d`, `2w`, `3m`, or `1y`.

### Technical Indicators (A stocks only)

```bash
python .opencode/lib/fetch/fetch_indicators.py sh600519                  # Default indicators (SMA, MACD, RSI, Bollinger)
python .opencode/lib/fetch/fetch_indicators.py sh600519 --range 5d       # Last 5 calendar days
python .opencode/lib/fetch/fetch_indicators.py sz000001 --range 6m       # Last 6 months
python .opencode/lib/fetch/fetch_indicators.py sh600519 --indicators rsi,macd,close_50_sma
python .opencode/lib/fetch/fetch_indicators.py sh600519 --json           # JSON output
python .opencode/lib/fetch/fetch_indicators.py sh600519 --csv            # CSV output
python .opencode/lib/fetch/fetch_indicators.py --list                    # List available indicators
python .opencode/lib/fetch/fetch_indicators.py sh600519 -o output.txt    # Save to file
python .opencode/lib/fetch/fetch_indicators.py sh600519 --json -o output.json   # Save as JSON
python .opencode/lib/fetch/fetch_indicators.py sh600519 --csv -o output.csv     # Save as CSV
```

**Available Indicators:**
| Indicator | Description |
|-----------|-------------|
| `close_10_ema` | 10-day Exponential Moving Average |
| `close_50_sma` | 50-day Simple Moving Average |
| `close_200_sma` | 200-day Simple Moving Average |
| `macd` | MACD Line |
| `macds` | MACD Signal Line |
| `macdh` | MACD Histogram |
| `rsi` | Relative Strength Index (14-period) |
| `boll` | Bollinger Band Middle (20-period) |
| `boll_ub` | Bollinger Upper Band |
| `boll_lb` | Bollinger Lower Band |
| `atr` | Average True Range (14-period) |
| `vwma` | Volume Weighted Moving Average (20-period) |

### Dragon and Tiger List (龙虎榜)

```bash
python .opencode/lib/fetch/fetch_special.py lhb                        # Latest data
python .opencode/lib/fetch/fetch_special.py lhb --date 2026-03-31      # Specific date
python .opencode/lib/fetch/fetch_special.py lhb --code 600519          # Specific stock
python .opencode/lib/fetch/fetch_special.py lhb --json                 # JSON output
python .opencode/lib/fetch/fetch_special.py lhb -o output.txt          # Save to file
python .opencode/lib/fetch/fetch_special.py lhb --json -o output.json  # Save as JSON
```

### Margin Trading (融资融券)

```bash
python .opencode/lib/fetch/fetch_special.py rzye                       # Market overview
python .opencode/lib/fetch/fetch_special.py rzye --top 20              # Top 20 records
python .opencode/lib/fetch/fetch_special.py rzye --json                # JSON output
python .opencode/lib/fetch/fetch_special.py rzye -o output.txt         # Save to file
python .opencode/lib/fetch/fetch_special.py rzye --json -o output.json # Save as JSON
```

### Money Flow (资金流向)

```bash
# Industry money flow (行业资金流向)
python .opencode/lib/fetch/fetch_money_flow.py                  # Top 50 industries (default)
python .opencode/lib/fetch/fetch_money_flow.py --top 20         # Top 20 industries
python .opencode/lib/fetch/fetch_money_flow.py --json           # JSON output
python .opencode/lib/fetch/fetch_money_flow.py --csv            # CSV output
python .opencode/lib/fetch/fetch_money_flow.py -o flow.csv      # Save as CSV

# Individual stock money flow (个股资金流向)
python .opencode/lib/fetch/fetch_money_flow.py --stock          # Top 50 stocks (default)
python .opencode/lib/fetch/fetch_money_flow.py --stock --top 20 # Top 20 stocks
python .opencode/lib/fetch/fetch_money_flow.py --stock --json   # JSON output
python .opencode/lib/fetch/fetch_money_flow.py --stock --csv    # CSV output

# Use custom cookie file
python .opencode/lib/fetch/fetch_money_flow.py --stock --cookie /path/to/.cookie
```

### Concept Ranking (概念板块排行)

```bash
python .opencode/lib/fetch/fetch_concept_ranking.py --top 20 --json
```

### Limit-Up Pool (涨停池)

```bash
python .opencode/lib/fetch/fetch_limit_up_pool.py --top 20 --json
```

### Turnover Ranking (换手率排行)

```bash
python .opencode/lib/fetch/fetch_turnover_ranking.py --top 20 --json
```

### Market Breadth (市场宽度)

```bash
python .opencode/lib/fetch/fetch_market_breadth.py --json
python .opencode/lib/fetch/fetch_market_breadth.py --cache-dir intraday/2026-06-30 --json
```

### Board Money Flow (板块资金流向)

```bash
python .opencode/lib/fetch/fetch_board_money_flow.py concept --json
python .opencode/lib/fetch/fetch_board_money_flow.py industry --top 20 --json
```

## Stock Code Format

| Market             | Prefix | Example    |
| ------------------ | ------ | ---------- |
| A Stock (Shanghai) | `sh`   | `sh600519` |
| A Stock (Shenzhen) | `sz`   | `sz000001` |
| A Stock (Beijing)  | `bj`   | `bj835185` |
| HK Stock           | `hk`   | `hk00700`  |
| US Stock           | `usr_` | `usr_nvda` |
| Domestic Future    | `nf_`  | `nf_IF0`   |
| Oversea Future     | `hf_`  | `hf_OIL`   |

## Scripts (`.opencode/lib/fetch/`)

| Script               | Purpose                          | Markets          |
| -------------------- | -------------------------------- | ---------------- |
| `fetch_stock.py`     | Real-time quotes & intraday K-line | All (intraday: A only) |
| `fetch_all_astocks.py` | Bulk real-time data (~5500 stocks) | A stocks      |
| `fetch_history.py`   | Historical daily K-line (前复权) | A stocks (sh/sz) |
| `fetch_indicators.py`| Technical indicators analysis    | A stocks (sh/sz) |
| `fetch_special.py`   | 龙虎榜 & 融资融券                | A stocks         |
| `fetch_money_flow.py`| Money flow (行业/个股资金流向) | All industries/stocks |
| `fetch_concept_ranking.py` | Concept board ranking       | A stocks         |
| `fetch_limit_up_pool.py`   | Limit-up stock pool         | A stocks         |
| `fetch_turnover_ranking.py`| Turnover rate ranking       | A stocks         |
| `fetch_market_breadth.py`  | Market breadth statistics   | A stocks         |
| `fetch_board_money_flow.py`| Board-level money flow      | A stocks         |

## Data Source Classes (`.opencode/lib/datasources/`)

| Class | Source |
| ----- | ------ |
| `SinaDataSource` | Sina Finance (A/US/futures real-time, intraday) |
| `TencentDataSource` | Tencent Finance (HK stocks) |
| `SohuDataSource` | Sohu Finance (historical daily K-line) |
| `EastMoneyDataSource` | East Money (money flow, dragon/tiger, margin, board flow) |
| `EastMoneyIntradayDataSource` | East Money (intraday ranking, concept ranking, breadth, etc.) |

Import from any script:
```python
sys.path.insert(0, str(Path(__file__).resolve()...))  # point to .opencode/
from lib.datasources import EastMoneyIntradayDataSource
```

## Output Fields

**Real-time**: `code`, `name`, `price`, `open`, `yestclose`, `high`, `low`, `volume`, `amount`, `float_shares`, `updown`, `percent`, `time`, `market`

Note: `float_shares` (流通股本, 股) only available for A stocks (sh/sz/bj); `null` for HK/US/futures.

**Intraday K-line**: `time`, `open`, `high`, `low`, `close`, `volume`, `amount`, `ma_price5`, `ma_volume5`

**Bulk A Stocks**: `code`, `name`, `price`, `yestclose`, `updown`, `percent`, `high`, `low`, `open`, `volume`, `amount`, `turnover`, `volume_ratio`, `swing`, `pe`, `pb`, `total_mv`, `float_mv`, `market`, `source`

**Note**: `volume_ratio` and `swing` are only available from Eastmoney source; Sina source sets them to "-".

**Historical**: `date`, `open`, `close`, `high`, `low`, `change`, `change_pct`, `volume`, `amount`, `turnover`

**Dragon & Tiger**: `date`, `code`, `name`, `close`, `change_pct`, `turnover_rate`, `deal_ratio`, `net_buy`, `buy_amt`, `sell_amt`, `buy_ratio`, `sell_ratio`, `abnormal`, `market`

**Margin Trading**: `date`, `market_code`, `market`, `rzye`(融资余额), `rzmre`(融资买入), `rzjme`(融资净买), `rzrqye`(融资融券余额)

**Industry Money Flow**: `code`, `type`, `industry`, `net_inflow`(主力净流入,亿), `source`

**Stock Money Flow**: `code`, `name`, `price`, `change_pct`, `main_net_inflow`(主力净流入,亿), `main_ratio`(主力净占比), `super_large_net`(超大单,亿), `super_large_ratio`, `large_net`(大单,亿), `large_ratio`, `medium_net`(中单,亿), `medium_ratio`, `small_net`(小单,亿), `small_ratio`, `source`

**Concept Ranking**: `code`, `name`, `change_pct`, `change_amt`, `turnover`, `up_count`(上涨家数), `down_count`(下跌家数), `lead_stock`(领涨股), `lead_change`(领涨股涨幅), `net_inflow`(主力净流入,亿), `total_mv`(总市值)

**Limit-Up Pool**: `code`, `name`, `price`, `change_pct`, `turnover`, `volume_ratio`, `amount`, `board`(板块), `total_mv`

**Limit-Down Pool**: `code`, `name`, `price`, `change_pct`, `turnover`, `volume_ratio`, `amount`, `board`(板块), `total_mv`

**Turnover Ranking**: `code`, `name`, `price`, `change_pct`, `amount`(成交额), `turnover`(换手率), `volume_ratio`, `total_mv`

**Market Breadth**: `total`(总数), `up_count`(上涨), `down_count`(下跌), `flat_count`(平盘), `up_ratio`(上涨比例), `limit_up_count`(涨停), `limit_down_count`(跌停), `avg_change`(平均涨幅), `timestamp`, `source`

**Board Money Flow (概念/行业板块资金流向)**: `code`, `name`, `value`(净流入,亿), `field`(排序字段), `board_type`(concept/industry), `source`

## Workflow

1. **Identify market**: Determine stock code prefix from user query or use `--search`
2. **Fetch data**: Run appropriate script based on data type
3. **Present results**: Use `--json` for structured data, `--csv` for CSV, `-o FILE` to save to file, default for human-readable

## API Details

See [references/api-docs.md](references/api-docs.md) for API endpoints, response formats, and field mappings.

## Notes

- Real-time: Sina Finance (A/US/futures), Tencent Finance (HK)
- Intraday K-line: Sina Finance (A stocks only)
- Bulk A Stocks: Eastmoney API (default, has volume_ratio), Sina Market Center API (fallback, ~5500 stocks)
- Historical: Sohu Finance (前复权 daily K-line, A stocks only)
- Dragon & Tiger / Margin / Money Flow: East Money Datacenter API
- Stock Money Flow: East Money push2 API (requires cookie, see `.cookie` file)
- Data has ~15s delay; not suitable for HFT
- Oversea futures may have network restrictions in some regions
