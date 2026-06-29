---
name: intraday-market-analysis
description: >
  Intraday trading analysis workflow for 14:30 tail positioning.
  3-step pipeline: Market Snapshot → Intraday Perception → Tail Strategy.
  Independent of Morning Agent; Morning strategy used only for optional Prediction Review.
---

# Intraday Market Analysis (V1)

3-step pipeline implementing V5 Compute → Perception → Reasoning architecture:

| Layer | Step | Agent | Output |
|-------|------|-------|--------|
| Compute | Python scripts | fetch_stock.py / fetch_pool_indicators.py / fetch_money_flow.py / query_theme.py | raw data |
| Perception | Step 1 | LLM | market_snapshot.md |
| Perception | Step 2 | intraday-market-observer + intraday-stock-mapping | intraday_mapper.md |
| Reasoning | Step 3 | trading-strategist + intraday-strategy | tail_strategy.md (+ PredictionReview) |

Step 2 NEVER produces Direction or RiskSeverity (V5 Invariant 1).

## Design Principle

**Intraday Agent is independently deployable, independently runnable, and independently backtestable.**

Morning Strategy is: *"Optional Reference for Prediction Review, never a dependency for Trading Reasoning."*

Intraday Agent 对 Morning 的依赖度为 零:
- `mapper.md` 存在 → Tracking Pool 激活 (附加增强)
- `mapper.md` 不存在 → 纯 Discovery Pool 运行 (完整功能)
- `strategy.md` 存在 → Prediction Review 段输出 (附加 Audit)
- `strategy.md` 不存在 → 跳过 Review, 标注原因

## Workflow

```
Step 1: Market Snapshot (~14:30)
  Python (parallel):
    fetch_stock.py sh000001,sz399001,sh000688 --json
    fetch_money_flow.py --json
    fetch_special.py lhb --json
  LLM:
    生成 market_snapshot.md
    (指数/宽度/情绪/涨停梯队/主力板块/LHB)

Step 2: Intraday Perception
  Agent: intraday-market-observer
  Skill: intraday-stock-mapping
  Input: market_snapshot.md (+ mapper.md 可选)
  Output: intraday_mapper.md
    (V5 7-section: Dual Pool + Tradeability/OvernightScore/TailFlow)

Step 3: Tail Strategy
  Agent: trading-strategist
  Skill: intraday-strategy
  Input: intraday_mapper.md + SHARED_RULES.md + INTRADAY_RULES.md
         (+ strategy.md 可选, 仅 for Prediction Review)
  Output: tail_strategy.md
    (Direction/RiskSeverity/Tail Action/Tomorrow Expectation + ReasoningTrace
     + PredictionReview)
```

## Execution Timing

- **Target time**: ~14:30 (尾盘前30分钟)
- **All data types available**: real-time prices, intraday K-line, money flow, LHB
- Target wall-clock: complete before 14:55

## Data Availability

| Data Type | Source | Available | Note |
|-----------|--------|:---------:|------|
| Real-time index quotes | fetch_stock.py | ✓ | 上证/深证/科创50 |
| Real-time stock prices | fetch_stock.py (pool) | ✓ | Live |
| Intraday minute K-line | fetch_stock.py --intraday | ✓ | 5-min/1-min, up to 5 days |
| Technical indicators | fetch_pool_indicators.py | ✓ | V5 nested schema, intraday refresh |
| Industry money flow | fetch_money_flow.py | ✓ | Real-time intraday |
| Stock money flow | fetch_money_flow.py --stock | ✓ | Requires cookie |
| Dragon & Tiger list | fetch_special.py lhb | ✓ | Today's session |
| Theme market view | query_theme.py market | ✓ | Cross-rank + attention + gainers |

## Performance Constraints

- **DO NOT** use `fetch_all_astocks.py` (~5500 stocks, too slow)
- Target pool: 30-50 stocks
- Parallel bash calls for independent fetches

---

## Step 1: Market Snapshot

**Executor:** LLM (no subagent — pure data aggregation + structured output)

**Python commands** (run in parallel):

```bash
python .opencode/skills/stock-analysis/scripts/fetch_stock.py sh000001,sz399001,sh000688 --json
python .opencode/skills/stock-analysis/scripts/fetch_money_flow.py --json
python .opencode/skills/stock-analysis/scripts/fetch_special.py lhb --json
```

**Task:** Aggregate into `predict/{YYYY-MM-DD}/market_snapshot.md`:

```markdown
# Market Snapshot

Date: {YYYY-MM-DD}   Time: ~14:30

## Indices

| Index | Code | Price | Change% | Assessment |
|-------|------|-------|---------|------------|
| 上证指数 | sh000001 | xxxx | +x.xx% | 强 / 震荡 / 弱 / 恐慌 |
| 深证成指 | sz399001 | xxxx | +x.xx% | |
| 科创50 | sh000688 | xxxx | +x.xx% | 结构性强度 vs 上证: +x.xx% |

## Market Breadth

| Metric | Value | Signal |
|--------|-------|--------|
| 涨停家数 | xx | |
| 跌停家数 | xx | |
| 炸板率 | xx% | |
| 连板梯队 | xx板:n只, xx板:n只 | |
| 两市成交额 | xxxx亿 | 活跃 / 正常 / 冷清 |
| 北向资金 | ±xx亿 | |
| 主力资金 | ±xx亿 | |

## Leading Sectors (Top 8 by Change%)

| Rank | Sector | Change% | Turnover(亿) | Capital Flow | Leader Stocks |
|------|--------|---------|-------------|-------------|---------------|
| 1 | AI算力 | +x.x% | xxx | ++流入 | xxx(涨停), xxx(+x.x%) |
| 2 | Robot | +x.x% | xxx | +流入 | xxx(连板x) |
| ... |

## Market Sentiment

- **Direction**: Strong / Neutral / Weak / Panic
- **Character**: 主线集中 / 板块轮动 / 普涨 / 普跌 / 分化
- **Notable**: (异常现象: 突发跳水 / 尾盘放量 / 权重异动等)

## LHB Highlights (龙虎榜精选)

| Code | Name | Change% | Net Buy(万) | Reason | Theme Match |
|------|------|---------|------------|--------|-------------|
| xxx | xxx | +x.x% | xxxx | 涨停/振幅 | AI算力(候选) |
| ... |
```

---

## Step 2: Intraday Perception

**Agent:** `intraday-market-observer`

**Prompt (exact format, MUST NOT deviate):**

```
Load skill `intraday-stock-mapping` and execute.

Date: {YYYY-MM-DD}

Inputs:
- predict/{YYYY-MM-DD}/market_snapshot.md                     (必需)
- predict/{YYYY-MM-DD}/mapper.md                              (可选 — Tracking Pool 来源。不存在则纯 Discovery 运行)

Outputs:
- predict/{YYYY-MM-DD}/intraday_mapper.md
```

**CRITICAL:** Do NOT inline any file content, scoring formulas, filter rules, or analysis. Keep the prompt clean.

**Output:** `predict/{YYYY-MM-DD}/intraday_mapper.md`

---

## Step 3: Tail Strategy

**Agent:** `trading-strategist`

**Prompt (exact format, MUST NOT deviate):**

```
Load skill `intraday-strategy` and execute.

Date: {YYYY-MM-DD}

Inputs:
- predict/{YYYY-MM-DD}/intraday_mapper.md
- memory/SHARED_RULES.md
- memory/INTRADAY_RULES.md

Optional (for Prediction Review only — do NOT use for reasoning):
- predict/{YYYY-MM-DD}/strategy.md                           (不存在则跳过 Prediction Review)

Output:
- predict/{YYYY-MM-DD}/tail_strategy.md
```

**CRITICAL:** Do NOT inline any file content, data summaries, or analysis. Keep the prompt clean.

**Output:** `predict/{YYYY-MM-DD}/tail_strategy.md`

---

## Output Files

| File | Content | Layer / Step |
|------|---------|-------------|
| `predict/{date}/market_snapshot.md` | 盘中市场快照 (指数/宽度/情绪/板块/LHB) | Perception (Step 1) |
| `predict/{date}/intraday_mapper.md` | V5 7-section 盘中感知数据集 (Dual Pool + Tradeability/OvernightScore/TailFlow) | Perception (Step 2) |
| `predict/{date}/tail_strategy.md` | 尾盘布局策略 + ReasoningTrace + PredictionReview | Reasoning (Step 3) |

## Quick Reference

| Layer | Step | Agent | Input | Output | V5 Constraint |
|-------|------|-------|-------|--------|---------------|
| Perception | 1 | LLM | Python fetches | market_snapshot.md | Pure data, no analysis |
| Perception | 2 | intraday-market-observer + intraday-stock-mapping | market_snapshot.md (+ mapper.md 可选) | intraday_mapper.md | **No Direction / RiskSeverity** |
| Reasoning | 3 | trading-strategist + intraday-strategy | intraday_mapper.md + rules (+ strategy.md 可选) | tail_strategy.md | Morning strategy = Audit only, 可选 |
