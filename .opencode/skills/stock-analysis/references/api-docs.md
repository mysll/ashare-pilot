# Stock API Documentation

## Sina Finance API (A Stock, US Stock, Futures)

### Endpoint

```
GET https://hq.sinajs.cn/list={codes}
```

### Parameters

- `codes`: Comma-separated stock codes (e.g., `sh600519,sz000001,usr_nvda`)
- Use `$` instead of `.` in codes (e.g., `us.baba` -> `us$baba`)

### Headers

- `User-Agent`: Browser-like UA string (required, otherwise returns empty)
- `Referer`: `http://finance.sina.com.cn/`
- `Accept-Language`: `zh-CN,zh;q=0.9`

### Response Format

```
var hq_str_sh600519="贵州茅台,1738.000,1732.690,1734.730,1744.810,1725.010,...";
var hq_str_usr_nvda="英伟达,166.4700,-0.63,...";
```

### A Stock Fields (sh/sz/bj)

| Index | Field     | Description           |
| ----- | --------- | --------------------- |
| 0     | name      | Stock name            |
| 1     | open      | Opening price         |
| 2     | yestclose | Previous close        |
| 3     | price     | Current price         |
| 4     | high      | Day high              |
| 5     | low       | Day low               |
| 6     | buy1      | Bid price             |
| 7     | sell1     | Ask price             |
| 8     | volume    | Trading volume (lots) |
| 9     | amount    | Trading amount (CNY)  |
| 30    | date      | Date (YYYY-MM-DD)     |
| 31    | time      | Time (HH:MM:SS)       |

### US Stock Fields (usr\_)

| Index | Field      | Description                    |
| ----- | ---------- | ------------------------------ |
| 0     | name       | Stock name                     |
| 1     | price      | Current price                  |
| 2     | percent    | Change percent (signed string) |
| 3     | time       | Update time                    |
| 5     | open       | Opening price                  |
| 6     | high       | Day high                       |
| 7     | low        | Day low                        |
| 10    | volume     | Trading volume                 |
| 21    | afterPrice | Pre/post market price          |
| 26    | yestclose  | Previous close                 |

### Domestic Futures Fields (nf\_)

**Commodity futures** (e.g., `nf_RB0` for rebar):

| Index | Field     | Description         |
| ----- | --------- | ------------------- |
| 0     | name      | Contract name       |
| 2     | open      | Opening price       |
| 3     | high      | Day high            |
| 4     | low       | Day low             |
| 8     | price     | Current price       |
| 10    | yestclose | Previous settlement |
| 14    | volume    | Trading volume      |

**Stock index futures** (e.g., `nf_IF0` for CSI 300):

| Index | Field      | Description         |
| ----- | ---------- | ------------------- |
| 0     | open       | Opening price       |
| 1     | high       | Day high            |
| 2     | low        | Day low             |
| 3     | price      | Close/current price |
| 4     | volume     | Trading volume      |
| 13    | yestclose  | Previous close      |
| 14    | yestsettle | Previous settlement |
| 49    | name       | Contract name       |

Supported index futures: `IC` (CSI 500 中证500), `IF` (CSI 300 沪深300), `IH` (SSE 50 上证50), `IM` (CSI 1000 中证1000), `TF` (5-year bond 5年期国债), `TS` (2-year bond 2年期国债), `T` (10-year bond 10年期国债), `TL` (30-year bond 30年期国债).

### Oversea Futures Fields (hf\_)

| Index | Field     | Description            |
| ----- | --------- | ---------------------- |
| 0     | price     | Current price          |
| 2     | buy1      | Bid price              |
| 3     | ask1      | Ask price              |
| 4     | high      | Day high               |
| 5     | low       | Day low                |
| 6     | time      | Update time (HH:MM:SS) |
| 7     | yestclose | Previous settlement    |
| 8     | open      | Opening price          |
| 12    | date      | Date (YYYY-MM-DD)      |
| 13    | name      | Contract name          |
| 14    | volume    | Trading volume         |

## Tencent Finance API (HK Stock)

### Endpoint

```
GET https://qt.gtimg.cn/q=r_{codes}&fmt=json
```

### Parameters

- `codes`: Comma-separated codes prefixed with `r_` (e.g., `r_hk00700`)
- `fmt`: Response format (`json`)

### Headers

- `User-Agent`: Browser-like UA string
- `Referer`: `https://stockapp.finance.qq.com/`

### Response Format

```json
{
  "r_hk00700": ["腾讯控股", "00700", ..., "484.400", "481.600", "484.400", ...]
}
```

### Fields

| Index | Field     | Description    |
| ----- | --------- | -------------- |
| 1     | name      | Stock name     |
| 3     | price     | Current price  |
| 4     | yestclose | Previous close |
| 5     | open      | Opening price  |
| 9     | buy1      | Bid price      |
| 19    | sell1     | Ask price      |
| 30    | time      | Update time    |
| 33    | high      | Day high       |
| 34    | low       | Day low        |
| 36    | volume    | Trading volume |
| 37    | amount    | Trading amount |

## Stock Search API

### Endpoint

```
GET https://proxy.finance.qq.com/ifzqgtimg/appstock/smartbox/search/get?q={keyword}
```

### Response Format

```json
{
  "data": {
    "stock": [["sh", "600519", "贵州茅台", "GZMT"]]
  }
}
```

### Fields

| Index | Field        | Description                  |
| ----- | ------------ | ---------------------------- |
| 0     | market       | Market code (sh/sz/bj/hk/us) |
| 1     | code         | Stock code                   |
| 2     | name         | Stock name                   |
| 3     | abbreviation | Name abbreviation            |

## Sina Market Center API (Bulk A Stock Data)

### Endpoint

```
GET https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData
```

**Note**: This API does NOT provide volume ratio (量比). The field is set to "-" in output.

### Eastmoney API (Bulk A Stock Data - includes volume ratio)

**Endpoint**:
```
GET https://push2.eastmoney.com/api/qt/clist/get
```

**Parameters**:

| Param | Description | Example |
|-------|-------------|---------|
| `pn` | Page number | `1` |
| `pz` | Page size (max 100 per page) | `100` |
| `po` | Sort order | `1` |
| `np` | No pagination flag | `1` |
| `ut` | Token (required) | `fa5fd1943c747385f9554f5b7d918a9e` |
| `fltt` | Float type | `2` |
| `invt` | Investor type | `2` |
| `fid` | Sort field | `f12` |
| `fs` | Market filter | `m:0+t:6,m:0+t:13,m:0+t:80,m:1+t:2,m:1+t:23` |
| `fields` | Data fields | `f12,f14,f2,f3,f4,f5,f6,f7,f8,f10,f15,f16,f17,f18,f20,f21` |

**Market Filter (`fs`) Breakdown**:
- `m:0+t:6` = 深市主板
- `m:0+t:13` = 深市创业板
- `m:0+t:80` = 深市科创板
- `m:1+t:2` = 沪市主板
- `m:1+t:23` = 沪市科创板

**Fields**:

| Field | Description |
|-------|-------------|
| `f12` | Stock code (pure, no prefix) |
| `f14` | Stock name |
| `f2` | Current price |
| `f3` | Change percent |
| `f4` | Change amount |
| `f5` | Volume (lots) |
| `f6` | Amount |
| `f7` | Swing (振幅) |
| `f8` | Turnover rate (换手率) |
| `f10` | **Volume ratio (量比)** ← Key field |
| `f15` | High |
| `f16` | Low |
| `f17` | Open |
| `f18` | Previous close |
| `f20` | Total market cap (万) |
| `f21` | Float market cap (万) |

**Anti-Scraping Notes**:
- API may reject requests during non-trading hours
- Requires proper User-Agent header
- Maximum 100 records per page regardless of `pz` parameter
- May require ~55 pages for full A-stock list (~5500 stocks)

## Sina Market Center API (Bulk A Stock Data)

**Note**: This API does NOT provide volume ratio (量比). The field is set to "-" in output.

### Endpoint

```
GET https://vip.stock.finance.sina.com.cn/quotes_service/api/json_v2.php/Market_Center.getHQNodeData
```

### Parameters

| Param     | Description                      | Example        |
| --------- | -------------------------------- | -------------- |
| `page`    | Page number (starts from 1)      | `1`            |
| `num`     | Number of records per page       | `80`           |
| `sort`    | Sort field                       | `symbol`       |
| `asc`     | Sort direction (0=desc, 1=asc)   | `1`            |
| `node`    | Market node                      | `hs_a`         |

### Headers

- `User-Agent`: Browser-like UA string (required)
- `Referer`: `https://vip.stock.finance.sina.com.cn/market_center/`

### Response Format

```json
[
  {
    "symbol": "sh600519",
    "code": "600519",
    "name": "贵州茅台",
    "trade": "1453.96",
    "pricechange": "-6.53",
    "changepercent": "-0.45",
    ...
  }
]
```

### Fields

| Field          | Description                |
| -------------- | -------------------------- |
| `symbol`       | Full code with market (sh/sz) |
| `code`         | Stock code only            |
| `name`         | Stock name                 |
| `trade`        | Current price              |
| `pricechange`  | Price change (涨跌额)      |
| `changepercent`| Change percent (涨跌幅)    |
| `settlement`   | Previous close (昨收)      |
| `open`         | Opening price              |
| `high`         | Day high                   |
| `low`          | Day low                    |
| `volume`       | Trading volume (lots)      |
| `amount`       | Trading amount (元)        |
| `turnoverratio`| Turnover rate (换手率)     |
| `per`          | P/E ratio (市盈率)         |
| `pb`           | P/B ratio (市净率)         |
| `mktcap`       | Market cap (万)            |
| `nmc`          | Float market cap (万)      |

**Note**: Sina API does NOT provide volume ratio (量比) or swing (振幅).
These fields are set to "-" in the output from `fetch_all_astocks.py`.

### Notes

- Returns ~5500 A stocks (sh/sz/bj combined)
- Pagination: 80 records per page recommended
- Fetch time: ~45 seconds for all data
- Supports sorting by any field

## Sohu Finance API (Historical Daily K-line)

### Endpoint

```
GET https://q.stock.sohu.com/hisHq
```

### Parameters

| Param      | Description                               | Example                |
| ---------- | ----------------------------------------- | ---------------------- |
| `code`     | Stock code in `cn_{code}` format          | `cn_600519`            |
| `start`    | Start date (YYYYMMDD)                     | `20260101`             |
| `end`      | End date (YYYYMMDD)                       | `20260331`             |
| `stat`     | Statistics flag (use `1`)                 | `1`                    |
| `order`    | Sort order `D`=desc, `A`=asc              | `D`                    |
| `period`   | Period `d`=daily, `w`=weekly, `m`=monthly | `d`                    |
| `callback` | JSONP callback function name              | `historySearchHandler` |
| `rt`       | Response type (use `jsonp`)               | `jsonp`                |

### Code Format

Only A stocks (sh/sz) are supported. Convert to Sohu format:

- `sh600519` → `cn_600519`
- `sz000001` → `cn_000001`

### Response Format (JSONP)

```javascript
historySearchHandler([{
  "code": "cn_600519",
  "stat": [...],
  "hq": [
    ["2026-03-31", "1468.00", "1450.00", "30.00", "2.11%", "1448.41", "1479.93", "61691", "901548.62", "0.49%"],
    ...
  ]
}])
```

### Fields (hq array)

| Index | Field      | Description                    |
| ----- | ---------- | ------------------------------ |
| 0     | date       | Trading date (YYYY-MM-DD)      |
| 1     | open       | Opening price                  |
| 2     | close      | Closing price (前复权)         |
| 3     | change     | Price change                   |
| 4     | change_pct | Change percent (e.g., "2.11%") |
| 5     | low        | Day low                        |
| 6     | high       | Day high                       |
| 7     | volume     | Trading volume (lots)          |
| 8     | amount     | Trading amount (10k CNY)       |
| 9     | turnover   | Turnover rate                  |

### Notes

- Returns data in **descending** date order by default; reverse for chronological
- `close` is **前复权** (forward-adjusted for dividends/splits)
- Only supports A stocks (sh/sz), not HK/US/futures

## East Money Datacenter API (Dragon and Tiger List & Margin Trading)

### Endpoint

```
GET https://datacenter-web.eastmoney.com/api/data/v1/get
```

### Common Parameters

| Param         | Description                           |
| ------------- | ------------------------------------- |
| `reportName`  | Report identifier (see below)         |
| `columns`     | Use `ALL` for all columns             |
| `pageSize`    | Number of records per page            |
| `pageNumber`  | Page number (starts from 1)           |
| `sortColumns` | Sort field(s), comma-separated        |
| `sortTypes`   | Sort direction(s), `-1`=desc, `1`=asc |
| `source`      | Use `WEB`                             |
| `client`      | Use `WEB`                             |
| `filter`      | Filter expression (optional)          |

### Headers

- `User-Agent`: Browser-like UA string
- `Referer`: `https://data.eastmoney.com/`

### Dragon and Tiger List (龙虎榜)

**Report Name**: `RPT_DAILYBILLBOARD_DETAILSNEW`

**Filter**: `(TRADE_DATE='YYYY-MM-DD 00:00:00')` - Note: requires full datetime format

**Key Fields**:

| Field                | Description              |
| -------------------- | ------------------------ |
| `SECURITY_CODE`      | Stock code               |
| `SECURITY_NAME_ABBR` | Stock name               |
| `CLOSE_PRICE`        | Closing price            |
| `CHANGE_RATE`        | Change percent           |
| `TURNOVERRATE`       | Turnover rate (%)        |
| `DEAL_AMOUNT_RATIO`  | Deal amount ratio (%)    |
| `BILLBOARD_NET_AMT`  | Net buy/sell amount (元) |
| `BILLBOARD_BUY_AMT`  | Total buy amount (元)    |
| `BILLBOARD_SELL_AMT` | Total sell amount (元)   |
| `BUY_RATIO`          | Buy ratio (%)            |
| `SELL_RATIO`         | Sell ratio (%)           |
| `EXPLANATION`        | Abnormal reason          |
| `TRADE_DATE`         | Trading date             |
| `MARKET`             | Market (SH/SZ/BJ)        |

### Margin Trading (融资融券)

**Report Name**: `RPTA_WEB_RZRQ_LSSH` (Market-level historical data)

**Key Fields**:

| Field      | Description                                  |
| ---------- | -------------------------------------------- |
| `DIM_DATE` | Date                                         |
| `SCDM`     | Market code (001=沪市, 002=深市, 007=北交所) |
| `RZYE`     | 融资余额 (Margin balance)                    |
| `RZMRE`    | 融资买入额 (Margin buy)                      |
| `RZCHE`    | 融资偿还额 (Margin repay)                    |
| `RZJME`    | 融资净买入 (Net margin buy)                  |
| `RQYE`     | 融券余额 (Short balance)                     |
| `RQYL`     | 融券余量 (Short volume)                      |
| `RZRQYE`   | 融资融券余额 (Total)                         |

**Market Code Mapping (SCDM)**:

| Code | Market |
| ---- | ------ |
| 001  | 深市   |
| 002  | 北交所 |
| 007  | 沪市   |

### Notes

- API returns JSON with `success`, `result`, `message` fields
- Response encoding is UTF-8
- Filter dates must include time component (`YYYY-MM-DD 00:00:00`)
- Monetary values are in CNY (元), convert to 亿 for display

## East Money push2 API (Stock Money Flow)

### Endpoint

```
GET https://push2.eastmoney.com/api/qt/clist/get
```

### Parameters

| Param   | Description                          | Example |
|---------|--------------------------------------|---------|
| `cb`    | JSONP callback function              | `jQuery_callback` |
| `fid`   | Sort field                           | `f62` (主力净流入) |
| `po`    | Sort order (1=desc, 0=asc)           | `1` |
| `pz`    | Page size (number of stocks)         | `50` |
| `pn`    | Page number                          | `1` |
| `np`    | No pagination flag                   | `1` |
| `fltt`  | Float type                           | `2` |
| `invt`  | Investor type                        | `2` |
| `ut`    | Token                                | `8dec03ba335b81bf4ebdf7b29ec27d15` |
| `fs`    | Market filter                        | `m:0+t:6+f:!2,m:0+t:13+f:!2,...` |
| `fields`| Data fields                          | `f12,f14,f2,f3,f62,f184,f66,...` |

### Market Filter (`fs`) Breakdown

- `m:0` = 深市, `m:1` = 沪市
- `t:6` = A股, `t:13` = 创业板, `t:80` = 科创板, `t:2` = 主板, `t:23` = 科创板注册制, `t:7` = 创业板注册制, `t:3` = 创业板注册制
- `f:!2` = 过滤掉ST股票

### Fields

| Field  | Description |
|--------|-------------|
| `f12`  | Stock code (pure, no prefix) |
| `f13`  | Market code (0=深市, 1=沪市) |
| `f14`  | Stock name |
| `f2`   | Current price |
| `f3`   | Change percent |
| `f62`  | 主力净流入 (元) |
| `f184` | 主力净流入占比 (%) |
| `f66`  | 超大单净流入 (元) |
| `f69`  | 超大单净流入占比 (%) |
| `f72`  | 大单净流入 (元) |
| `f75`  | 大单净流入占比 (%) |
| `f78`  | 中单净流入 (元) |
| `f81`  | 中单净流入占比 (%) |
| `f84`  | 小单净流入 (元) |
| `f87`  | 小单净流入占比 (%) |

### Required Headers (Anti-Scraping)

This API has strict anti-scraping measures. Required headers:

| Header | Value |
|--------|-------|
| `accept` | `*/*` |
| `accept-language` | `zh-CN,zh;q=0.9,en;q=0.8` |
| `connection` | `keep-alive` |
| `host` | `push2.eastmoney.com` |
| `referer` | `https://data.eastmoney.com/zjlx/detail.html` |
| `sec-ch-ua` | `"Chromium";v="146", "Not-A.Brand";v="24", "Google Chrome";v="146"` |
| `sec-ch-ua-mobile` | `?0` |
| `sec-ch-ua-platform` | `"Windows"` |
| `sec-fetch-dest` | `script` |
| `sec-fetch-mode` | `no-cors` |
| `sec-fetch-site` | `same-site` |
| `user-agent` | `Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36` |
| `cookie` | Valid cookie string (see below) |

**Important Notes**:
- `sec-ch-ua` version must match `user-agent` Chrome version
- Do NOT set `accept-encoding` header manually (let requests handle gzip decompression)
- Cookie is required for stable access

### Cookie Configuration

Cookie is stored in `.cookie` file in project root:

```
# Cookie storage for external APIs
# Format: KEY=VALUE (one per line)

EASTMONEY_COOKIE=your_cookie_here
```

**How to obtain cookie**:
1. Open `https://data.eastmoney.com/zjlx/` in browser
2. Open DevTools (F12) → Network tab
3. Find requests to `push2.eastmoney.com`
4. Copy the `Cookie` header value from request headers
5. Update `.cookie` file

**Custom cookie file**:
```bash
python scripts/fetch_money_flow.py --stock --cookie /path/to/custom.cookie
```

### Response Format (JSONP)

```javascript
jQuery_callback({"rc":0,"rt":6,"svr":183119941,"lt":1,"full":1,"dlmkts":"","data":{"total":5282,"diff":[{"f1":2,"f2":131.9,"f3":9.35,"f12":"603083","f13":1,"f14":"剑桥科技","f62":852301408.0,...}]}});
```

### Notes

- Returns ~5282 A stocks total
- Monetary values in 元, convert to 亿 for display
- Cookie may expire periodically; update when API returns empty data

## Technical Indicators

Technical indicators are calculated locally from historical K-line data fetched via Sohu Finance API. Only A stocks (sh/sz) are supported.

### Available Indicators

| Indicator    | Description                          | Default |
| ------------ | ------------------------------------ | ------- |
| `close_10_ema`  | 10-day Exponential Moving Average    | No      |
| `close_50_sma`  | 50-day Simple Moving Average         | Yes     |
| `close_200_sma` | 200-day Simple Moving Average        | Yes     |
| `macd`          | MACD Line (12-26 EMA difference)     | Yes     |
| `macds`         | MACD Signal Line (9-day EMA of MACD) | Yes     |
| `macdh`         | MACD Histogram (MACD - Signal)       | No      |
| `rsi`           | Relative Strength Index (14-day)     | Yes     |
| `boll`          | Bollinger Band Middle (20-day SMA)   | Yes     |
| `boll_ub`       | Bollinger Band Upper (Middle + 2σ)   | Yes     |
| `boll_lb`       | Bollinger Band Lower (Middle - 2σ)   | Yes     |
| `atr`           | Average True Range (14-day)          | No      |
| `vwma`          | Volume Weighted Moving Average (20)  | No      |

### Calculation Methods

- **SMA**: Simple average of closing prices over period
- **EMA**: Exponential moving average with multiplier `2/(period+1)`
- **MACD**: EMA(12) - EMA(26), Signal = EMA(9) of MACD
- **RSI**: `100 - 100/(1 + RS)` where RS = avg_gain / avg_loss over 14 days
- **Bollinger**: Middle = SMA(20), Upper/Lower = Middle ± 2 × std_dev
- **ATR**: Average of True Range (max of H-L, H-C_prev, L-C_prev)
- **VWMA**: Volume-weighted average over period

### Notes

- Indicators require sufficient historical data (e.g., 200-day SMA needs ≥200 records)
- First values may be `null` until enough data points accumulated
- Uses 前复权 closing prices from Sohu Finance

## Script Output Options

All scripts support the following common output parameters:

### Common Parameters

| Parameter | Description                              | Example                  |
| --------- | ---------------------------------------- | ------------------------ |
| `--json`  | Output as JSON format                    | `--json`                 |
| `-o FILE` | Save output to file                      | `-o output.txt`          |
| `--csv`   | Output as CSV (fetch_history.py only)    | `--csv`                  |

### Output Behavior

- Without `-o`: Output is printed to stdout
- With `-o` + `--json`: File saved as JSON format
- With `-o` + `--csv`: File saved as CSV format (fetch_stock.py, fetch_history.py, fetch_indicators.py)
- With `-o` only: File saved as plain text format

### Examples by Script

**fetch_stock.py**:
```bash
python fetch_stock.py sh600519 -o output.txt           # Save table to file
python fetch_stock.py sh600519 --json -o output.json   # Save JSON to file
python fetch_stock.py sh600519 --csv -o output.csv     # Save CSV to file
python fetch_stock.py sh600519 --intraday              # Today's 5-min K-line
python fetch_stock.py sh600519 --intraday --scale 1    # Today's 1-min K-line
python fetch_stock.py sh600519 --intraday --days 3 --json  # Last 3 days K-line as JSON
python fetch_stock.py sh600519 --intraday --csv        # Intraday K-line as CSV
```

**Real-time Quote Fields** (JSON/CSV):
| Field | Type | Description |
|-------|------|-------------|
| `code` | str | Stock code with market prefix |
| `name` | str | Stock name |
| `price` | str | Current price |
| `open` | str | Opening price |
| `yestclose` | str | Previous close |
| `high` | str | Day high |
| `low` | str | Day low |
| `volume` | str | Trading volume (lots) |
| `amount` | str | Trading amount (CNY) |
| `amount_10000` | str | Trading amount divided by 10000 (e.g., CNY/10000 for A stocks). Only present when `amount` is available. |
| `float_shares` | int/null | Float shares (流通股本, 股). A stocks only; `null` for HK/US/futures |
| `updown` | str | Price change (signed) |
| `percent` | str | Change percent (signed, with `%`) |
| `time` | str | Update time |
| `market` | str | Market identifier (`A`, `US`, `Future`, `OverseaFuture`) |

Note: `float_shares` is fetched from Sina StockService API (流通股本变更历史), independent of the quote API. May return `null` if the upstream API is unavailable.

**Intraday K-line Parameters**:
| Parameter | Description | Default |
|-----------|-------------|---------|
| `--intraday` | Enable intraday K-line mode | - |
| `--scale` | Minute interval (1, 5, 15, 30, 60) | 5 |
| `--days` | Number of days (1-5) | 1 (today only) |

**Note**: Use `--days` to specify how many days of intraday K-line data to fetch (1-5 days). Default is 1 (today only).

**Intraday K-line Fields**:
| Field | Description |
|-------|-------------|
| `time` | Timestamp (YYYY-MM-DD HH:MM:SS) |
| `open` | Opening price |
| `high` | High price |
| `low` | Low price |
| `close` | Closing price |
| `volume` | Trading volume (lots) |
| `amount` | Trading amount (CNY) |
| `ma_price5` | 5-period MA of price |
| `ma_volume5` | 5-period MA of volume |

**fetch_history.py**:
```bash
python fetch_history.py sh600519 -o output.txt         # Save table to file
python fetch_history.py sh600519 --json -o output.json # Save JSON to file
python fetch_history.py sh600519 --csv -o output.csv   # Save CSV to file
```

**fetch_special.py**:
```bash
python fetch_special.py lhb -o output.txt              # Save table to file
python fetch_special.py lhb --json -o output.json      # Save JSON to file
python fetch_special.py rzye -o output.txt             # Save table to file
python fetch_special.py rzye --json -o output.json     # Save JSON to file
```

**fetch_indicators.py**:
```bash
python fetch_indicators.py sh600519 -o output.txt      # Save table to file
python fetch_indicators.py sh600519 --json -o output.json  # Save JSON to file
python fetch_indicators.py sh600519 --csv -o output.csv     # Save CSV to file
```

**fetch_all_astocks.py**:
```bash
python fetch_all_astocks.py -o stocks.csv              # Save CSV (default)
python fetch_all_astocks.py -o stocks.json --json-output  # Save JSON
```

**fetch_money_flow.py**:
```bash
# Industry money flow
python fetch_money_flow.py                            # Top 50 industries (default)
python fetch_money_flow.py --top 20                   # Top 20 industries
python fetch_money_flow.py --json                     # JSON output
python fetch_money_flow.py --csv -o flow.csv          # Save as CSV

# Individual stock money flow
python fetch_money_flow.py --stock                    # Top 50 stocks (default)
python fetch_money_flow.py --stock --top 100          # Top 100 stocks
python fetch_money_flow.py --stock --json             # JSON output
python fetch_money_flow.py --stock --csv              # CSV output
python fetch_money_flow.py --stock --cookie /path/.cookie  # Custom cookie file
```

**Money Flow Parameters**:
| Parameter | Description | Default |
|-----------|-------------|---------|
| `--stock` | Fetch individual stock money flow (instead of industry) | - |
| `--top N` | Number of items to fetch | 50 |
| `--cookie FILE` | Custom cookie file path | `.cookie` in project root |
