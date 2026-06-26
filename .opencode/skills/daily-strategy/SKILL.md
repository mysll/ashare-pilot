---
name: daily-strategy
description: Generate daily trading strategy from mapper data. Used as Step 3 of daily-market-analysis pipeline. Subagent loads this skill via prompt instruction and executes the workflow.
---

# Daily Strategy Generation

Loaded by trading-strategist subagent when dispatched for pipeline strategy generation.

## Workflow

```
Date:       provided in prompt (YYYY-MM-DD)
Mapper:     provided in prompt (predict/{date}/mapper.md)
```

1. Read {Mapper} **Market State** section — 市场状态, 主题优先级, 仓位环境
2. Read {Mapper} **Candidate Pool** — 候选池, Direction, MajorEventFlag, 风险标记
3. Read {Mapper} **Strategy Inputs** table — Price, MA20, ATR, ATR%, High20, Low20 (**authoritative source**)
4. Fetch market indices via `fetch_stock.py` (see "Market Context Fetch" below) — compute 大盘方向 / 结构性强度 / 成交水位 signals
5. Read `memory/RULES.md` — active trading rules with verification history
6. Generate `predict/{date}/strategy.md` (include an inline **Market Context** section)

---

## Direction Authority

`Direction` and `MajorEventFlag` from `mapper.md` are **authoritative**. Do NOT recompute Direction.

- Do NOT reinterpret `News Impact` to adjust Direction.
- Do NOT upgrade or downgrade Direction unless the field is missing from mapper.md.
- Consume `MajorEventFlag` as-is; do not re-derive it from news.

Direction has already passed through Composite Mapping → Risk Ceiling → MajorEvent Override → Clamp in Step 2. Step 3's job is to trade within that Direction, not to second-guess it.

---

## Market Context Fetch

Fetch 3 index quotes in a single batch call (fast, ~3s):

```bash
python .opencode/skills/stock-analysis/scripts/fetch_stock.py sh000001,sz399001,sh000688 --json
```

| Index | Code | Purpose |
|-------|------|---------|
| 上证指数 | sh000001 | 大盘方向（全市场情绪） |
| 深证成指 | sz399001 | 深圳市场水位 |
| 科创50 | sh000688 | 科技权重指标（结构性行情强度） |

Compute these signals (used by the Market State → Parameter Adjustment table below):

| Signal | Calculation | Interpretation |
|--------|-------------|----------------|
| **大盘方向** | `percent` of sh000001 | >+0.5% = 强市, ±0.5% = 震荡, <-0.5% = 弱市, <-1.5% = 恐慌 |
| **结构性强度** | `科创50% - 上证%` | >2% = 科技主线虹吸, 资金高度集中 |
| **成交水位** | from news.md market overview section | ≥2万亿 = 活跃, 1-2万亿 = 正常, <1万亿 = 冷清 |

**Timing note:** The call auction closes at 09:25; index data is only valid after that. This skill MUST NOT run the fetch before 09:25:10. If the skill is entered earlier, it MUST sleep until 09:25:10 (e.g. compute `seconds_until = 09:25:10 - now` then `time.sleep(seconds_until)` — or loop polling the clock) before running `fetch_stock.py`. The 10s buffer after 09:25 ensures the exchange has finalized and published auction-close index values. Pre-market runs (after 09:25:10, before 09:30) return auction-close data; runs at/after 09:30 return live quote data.

---

## Market State → Parameter Adjustment

Use the signals computed above (大盘方向 / 结构性强度 / 成交水位), plus mapper **Market State** (DominantThemes, RiskFlags, FinancingFlow), to set strategy parameters:

| 市场状态 | 仓位系数 | 止损倍数 | 推荐标的数 | 非主线处理 |
|---------|:---:|:---:|:---:|------|
| 强市 + 放量 | ×1.0 | 1.5×ATR | 10只 | 可轻度参与(≤2只) |
| 震荡 | ×1.0 | 1.5×ATR | 10只 | 降权(≤1只) |
| 弱市(-0.5~-1.5%) | ×0.7 | 2×ATR | 7只 | 全部剔除 |
| 恐慌(<-1.5%) | ×0.5 | 2×ATR（放宽防洗） | 5只 | 全部剔除 |
| 极端分化(科创-上证>3%) | 主线×1.0 非主线×0.5 | 主线1.5× 非主线2× | 8只 | 只在主线板块选 |

Stop-loss widens in weak markets (2×ATR) to avoid noise stops, tightens in strong markets (1.5×ATR) to protect gains. Systematic — no LLM ad-hoc judgment.

---

## Buy / Stop / Target Formulas

For each stock, derive quantitative levels from the **Strategy Inputs** table in {Mapper}:

| 参数 | 公式 | 数据来源 |
|------|------|---------|
| **买入区间** | `[MA20, MA20 + 0.5×ATR]` | Strategy Inputs.MA20, .ATR |
| **止损价** | `买入价 - 1.5×ATR` | Strategy Inputs.ATR |
| **止盈目标一** | `High20` | Strategy Inputs.High20 |
| **止盈目标二** | `High20 + ATR` | Strategy Inputs.High20, .ATR |

Strategy Inputs table is the **authoritative source** — use its values directly, do not re-derive or re-fetch.

### MA20 vs Low20 支撑选择

- If MA20 > Low20 → use MA20 as primary support
- If MA20 < Low20 (bearish) → use Low20 as last-resort support, flag stock as high-risk

### Data Source Rule

Strategy Inputs table in mapper.md is the **authoritative source** for:

- Price
- MA20
- ATR
- ATR%
- High20
- Low20

Use these values directly. Re-fetch from API ONLY if:
- Field is missing (N/A, null)
- Field is invalid (negative, zero where nonsensical)
- Stale data detected

**Default: no re-fetch.** Do not start with "Need ATR" or "I'll need to fetch data."

---

## Coverage & Scope

- **Scope:** A-shares only (sh/sz prefix)
- **Coverage:** ALL stocks in Strategy Inputs table (i.e., all Candidate Pool stocks with Composite >= 55)
- **Size:** Minimum 10, maximum 25

---

## Output: strategy.md

**Quantitative foundation:** Buy zones, stops, and targets are formula-driven — validate and adjust based on context, do not invent numbers.

### Structure

- **Market Context** section (inline) — index levels (上证/深证/科创50), 大盘方向, 结构性强度, 成交水位, and the resulting 市场状态 classification used for parameter adjustment
- 3 "super predictions" — each from a **different sector**, with quantitative entry/stop/target levels
- 7 "buy/sell recommendations" — with formula-derived levels + LLM context adjustment
- 1-5 ⭐ ratings on all recommendations
- Final list: 10 stock predictions (code, name, sector, rating, direction, buy zone, take profit, stop loss)
- For each stock: include entry/stop/target rationale (e.g. "买入区间=[MA20, MA20+0.5ATR], 止损=低MA20-1.5ATR, 止盈=High20")

### Memory Integration

**BEFORE** generating → READ `memory/RULES.md` for active rules and past lessons

**AFTER** generating → append strategy entry to `memory/daily/INDEX.md`:
  ```markdown
  | {MM-DD} | 策略 | <top 3 picks with ratings> | [`strategy`](../../predict/{YYYY-MM-DD}/strategy.md) |
  ```
