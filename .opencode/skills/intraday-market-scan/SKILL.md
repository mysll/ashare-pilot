---
name: intraday-market-scan
description: Use when dispatched at ~14:30 as the first step of intraday overnight analysis. Scans market breadth, indices, capital flows, concept rankings. Produces MarketState and ScanPool. NEVER outputs stock-level scoring or trading recommendations.
---

# Intraday Market Scan (Skill 1)

## Purpose

Determine what the market is REALLY trading today at 14:30. Market → Hot Spots → Stocks.

This is the Compute layer of the overnight alpha pipeline. Output is pure structured perception — no reasoning, no scoring, no trading recommendations.

## Pipeline Position

```
[14:30 Trigger]
    ↓
Skill 1: intraday-market-scan (THIS)
    → MarketState + ScanPool (300-500 stocks, basic data only)
    ↓
Skill 2: intraday-stock-discovery
    → ComputePool (80-150) + ThemeRanking
    ↓
Skill 3: overnight-strategy
    → OpportunityPool (20-40) + intraday_mapper.md
```

## Inputs

- Real-time East Money push2 API (cookie-based auth from `.cookie` file)

## Execute: Data Fetching

Run these scripts in parallel (all independent calls):

```bash
python .opencode/skills/stock-analysis/scripts/fetch_market_breadth.py --json
python .opencode/skills/stock-analysis/scripts/fetch_stock.py sh000001,sz399001,sz399006,sh000688,sh000852 --json
python .opencode/skills/stock-analysis/scripts/fetch_concept_ranking.py --json --top 20
python .opencode/skills/stock-analysis/scripts/fetch_north_bound.py --json
python .opencode/skills/stock-analysis/scripts/build_scan_pool.py --compute-pool-size 120 --json
```

Save outputs to intermediate files under `.cache/intraday/`.

## Output: MarketState

Synthesize from the script outputs into this structured format. ALL numbers come from script output — LLM generates zero numbers.

```markdown
## Market Strength
- 上证: {price} ({change}%)
- 深成: {price} ({change}%)
- 创业板: {price} ({change}%)
- 科创50: {price} ({change}%)
- 中证1000: {price} ({change}%)

## Market Breadth
- 上涨: {up} / 下跌: {down} (上涨比 {ratio}%)
- 涨停: {limit_up} / 跌停: {limit_down}
- 平均涨幅: {avg}%

## Capital Direction
- 北向资金净流入: {total_net}亿
- 主力资金方向: (infer from concept ranking net flows)

## Active Concepts (Top 10)
| # | 概念 | 涨幅 | 上涨/下跌 | 龙头 | 领涨涨幅 | 净流入(亿) |
|---|------|------|-----------|------|----------|------------|
```

## Output: ScanPool

The `build_scan_pool.py` output (JSON) contains the Scan Pool (300-500 stocks, basic data only — NO MACD/RSI/ATR/Bollinger).

Save to: `intraday/{date}/market_state.md` and `.cache/intraday/scan_pool.json`

## Constraints

- DO NOT compute any technical indicators (MACD, RSI, ATR, Bollinger) — that's Skill 2 territory
- DO NOT output Direction, RiskSeverity, buy/sell recommendations — that's Skill 3 territory
- DO NOT reference news or morning predictions — this is pure market observation
- All numbers MUST come from script output; LLM generates zero numeric values
- Use `bash` tool with parallel invocations for speed (target < 5s compute time)
- Scan Pool is 300-500 stocks with only basic market data fields
