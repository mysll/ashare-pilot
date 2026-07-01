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
Skill 3: intraday-strategy
    → OpportunityPool (20-40) + intraday_mapper.md
```

## Inputs

- Real-time East Money push2 API (cookie-based auth from `.cookie` file)
- Theme library index (concept → stock membership for Momentum dimension)

## Execute: Data Fetching

Run these scripts in parallel (all independent calls):

```bash
python .opencode/skills/stock-analysis/scripts/fetch_market_breadth.py --json
python .opencode/skills/stock-analysis/scripts/fetch_stock.py sh000001,sz399001,sz399006,sh000688,sh000852 --json
python .opencode/skills/intraday-market-scan/scripts/build_concept_dashboard.py --json --top 100
python .opencode/skills/stock-analysis/scripts/fetch_north_bound.py --json
python .opencode/skills/stock-analysis/scripts/build_scan_pool.py --compute-pool-size 120 --json
```

Save outputs to intermediate files under `.cache/intraday/`.

## Output: MarketState

Synthesize from the script outputs into this structured format. ALL numbers come from script output — LLM generates zero numbers.

### Market Strength
Extract from `indices.json`:
```markdown
## Market Strength
- 上证: {price} ({change}%)
- 深成: {price} ({change}%)
- 创业板: {price} ({change}%)
- 科创50: {price} ({change}%)
- 中证1000: {price} ({change}%)
```

### Market Breadth
Extract from `market_breadth.json`:
```markdown
## Market Breadth
- 上涨: {up} / 下跌: {down} (上涨比 {ratio}%)
- 涨停: {limit_up} / 跌停: {limit_down}
```

### Capital Direction
Extract from `north_bound.json` and `concept_dashboard.json`:
```markdown
## Capital Direction
- 北向资金净流入: {total_net}亿
- 主力资金方向: (infer from concept_dashboard.json Capital ranking — mention the capital leader)
```
**CRITICAL:** When you mention a concept in the narrative (e.g., "CPO概念净流入排名第一"),
the reader MUST be able to verify it in the Theme Dashboard table's Capital column.
Always cross-check: the concept you reference in prose MUST appear in the Dashboard table.

### Theme Dashboard
Extract from `concept_dashboard.json`. Each concept is a multi-dimensional object. 
Build a table showing the top 15 concepts by Composite rank, with all dimension ranks visible:

```markdown
## Theme Dashboard
| # | Theme | Perf | Capital | Breadth | Momentum | Composite |
|---|-------|------|---------|---------|----------|-----------|
| 1 | 国产芯片 | 27 | 4 | 2 | 2 | 1(94.5) |

Legend:
Perf = Performance rank (涨幅排位): answers "today's market recognition?"
Capital = Capital rank (资金排位): answers "sustained buying pressure?"
Breadth = Breadth rank (广度排位): answers "sector resonance or single-stock hype?"
Momentum = Momentum rank (持续性排位): answers "strengthening or fading?" (based on limit_up/first_board/continued_board counts)
Composite = Weighted blend (Capital 35% + Breadth 25% + Momentum 25% + Performance 15%)
```

When describing the table in narrative, align description with the column:
- "Performance最强的是X" → reference Perf column
- "资金最稳的是Y" → reference Capital column
- "赚钱效应最广的是Z" → reference Breadth column
- "持续性最强的是W" → reference Momentum column
- "综合最强" → reference Composite column


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
- Each concept in the Theme Dashboard is a multi-dimensional object — reference the correct column for the narrative: Capital column for capital claims, Perf column for performance claims, etc.
- If a concept is mentioned in prose (e.g., "CPO资金第一"), its row MUST be visible in the Dashboard table for reader verification
