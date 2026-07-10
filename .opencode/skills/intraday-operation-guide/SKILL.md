---
name: intraday-operation-guide
description: Use when the user wants one-shot intraday human trading instructions based on today's morning strategy and current market data. Reads predict/{date}/strategy.json + mapper.json, fetches current quotes and 5-minute intraday K-lines, then outputs actionable A/B/C/D operation guidance. This skill does NOT place orders.
---

# Intraday Operation Guide

Turn the morning strategy into a simple human execution sheet using current intraday data.

This skill is for: "现在怎么操作", "根据早盘策略给我盘中操作", "执行一次给我买/等/放弃说明".

It is NOT an automated trading skill. It gives instructions for a human trader.

## Inputs

Required:
- `predict/{YYYY-MM-DD}/strategy.json`
- `predict/{YYYY-MM-DD}/mapper.json`

Optional:
- `predict/{YYYY-MM-DD}/theme_stocks.md`
- `memory/RULES.md`
- `memory/SHARED_RULES.md`

## Output

Write:

```text
operation/{YYYY-MM-DD}/operation_guide.md
```

## Workflow

### Step 1 - Run Intraday Snapshot

Run:

```bash
python .opencode/skills/intraday-operation-guide/scripts/build_operation_snapshot.py --date {YYYY-MM-DD} --json -o operation/{YYYY-MM-DD}/operation_snapshot.json
```

The script:
- reads strategy stocks and execution constraints from `strategy.json`
- reads MA5/MA20/ATR/High20 from `mapper.json`
- fetches current quotes in one batch
- fetches today's 5-minute K-line for each strategy stock
- computes mechanical execution signals

Do not manually judge "放量", "站稳", "高开低走", or "回踩确认" before reading the JSON. The script normalizes these into explicit flags.

### Step 2 - Read Rules

Read full content:

```text
memory/RULES.md
memory/SHARED_RULES.md
```

Use rules only to adjust the operation class or caution notes. Do not invent new rules.

### Step 3 - Generate Operation Guide

Read:

```text
operation/{YYYY-MM-DD}/operation_snapshot.json
predict/{YYYY-MM-DD}/strategy.json
predict/{YYYY-MM-DD}/mapper.json
```

Write `operation_guide.md` in Chinese.

## Operation Classes

Every strategy stock MUST be assigned exactly one class:

| Class | Meaning | Human action |
|-------|---------|--------------|
| A | 现在可参与 | Can buy now if no personal position conflict |
| B | 等确认 | Wait for the listed trigger; do not buy before trigger |
| C | 只观察 | Watch only; no new buy today unless later skill rerun upgrades it |
| D | 放弃/回避 | Do not buy today |

## Mechanical Signal Meanings

The script outputs these normalized flags:

| Flag | Meaning |
|------|---------|
| `above_ma5` | current price >= MA5 |
| `above_ma20` | current price >= MA20 |
| `near_ma5` | current price within +/-0.5 ATR of MA5 |
| `near_ma20` | current price within +/-0.5 ATR of MA20 |
| `volume_confirmed` | latest 5-min volume >= 1.5x recent 5-min average |
| `price_strength_confirmed` | latest 5-min candle closes green and near its high |
| `first_bar_red_flag` | early session shows a large red 5-min candle |
| `high_open_fade` | opened strong but current price has faded meaningfully from open/high |
| `extended_from_anchor` | price is far above the relevant MA anchor |
| `below_vwap` | current price is below estimated intraday VWAP |
| `data_warning` | missing or suspicious data; downgrade at least one class |

LLM should use these flags directly. Avoid telling the user to "watch volume" without saying what the current computed signal says.

## Class Decision Guide

Default mapping:

### A - Now Can Participate

Use A only when:
- morning direction is `看多` or `偏多`
- `price_strength_confirmed = true`
- `below_vwap = false`
- no `first_bar_red_flag`
- no `high_open_fade`
- not hard-risk or data-warning

Prefer A when also:
- `above_ma5 = true`
- `volume_confirmed = true`
- strategy is `趋势跟随` or strong-sector mainline

### B - Wait For Confirmation

Use B when thesis is still valid but current price action is not clean:
- near anchor but no volume confirmation
- above MA20 but below MA5
- strategy says 回调布局/防御布局
- mild high-open fade but not broken

Give exactly one trigger, e.g.:
- "重新站回 MA5 且 5分钟放量确认"
- "回踩 MA20 不破后收回 5分钟阳线"
- "跌破 VWAP 前不买，收回 VWAP 后再评估"

### C - Watch Only

Use C when:
- non-mainline
- setup quality is acceptable but timing is poor
- high extension makes entry unattractive
- rule conflict exists
- signal is mixed

### D - Give Up / Avoid

Use D when:
- hard-filter stock appears in strategy
- invalid stock code
- data warning is severe
- price below VWAP and weakening
- high-open fade + large red 5-min candle
- current price is far extended and no safe entry remains
- stock is excluded by board policy

## Required Output Format

```markdown
# 盘中操作说明 - YYYY-MM-DD HH:MM

## 总结

| 项目 | 结论 |
|------|------|
| 当前市场 | ... |
| 今日总仓位建议 | ... |
| 可立即参与(A) | N只 |
| 等确认(B) | N只 |
| 只观察(C) | N只 |
| 放弃(D) | N只 |

## 一句话操作

| 类别 | 代码 | 名称 | 早盘策略 | 当前状态 | 操作说明 | 触发/失效 |
|------|------|------|----------|----------|----------|-----------|
| A | ... | ... | ... | ... | ... | ... |

## 操作卡片

Each strategy stock gets one compact card. The card is the primary output for the user.

### A | code name | 现在可参与

| 项目 | 内容 |
|------|------|
| 早盘意图 | 方向 / 评级 / 交易策略 |
| 当前信号 | price vs anchor, VWAP, 5min强弱, volume flag |
| 操作 | 现在可参与 / 半仓 / 标准仓 |
| 仓位上限 | from morning strategy, downgraded if needed |
| 失效 | one clear condition |
| 备注 | one sentence only |

### B | code name | 等确认

| 项目 | 内容 |
|------|------|
| 早盘意图 | ... |
| 当前问题 | why not now |
| 触发后操作 | exact trigger + position |
| 不买条件 | exact condition |

### C | code name | 只观察

One short paragraph: why it is watch-only.

### D | code name | 放弃/回避

One short paragraph: why it should not be bought today.

## A类 - 可参与

For each A stock:
- Why now
- Suggested max position from morning strategy, adjusted by current signal
- Invalid condition

## B类 - 等确认

For each B stock:
- Exact trigger
- Do-not-buy condition

## C/D类 - 不主动买

Short reason per stock.

## 风险提醒

- Mention only risks observable from snapshot or rules.
```

## Card Rules

- The card must be executable by a human in under 30 seconds.
- Do not ask the user to judge "是否放量"; use `volume_confirmed=true/false`.
- Do not ask the user to judge "是否站稳"; use `price_strength_confirmed`, `above_ma5`, `above_ma20`, and `below_vwap`.
- If morning strategy has `不买条件` and snapshot confirms it, class MUST be D.
- If morning strategy has `锚点`, show current distance to that anchor using `dist_atr`.
- Keep each card short. Long thesis and reasoning belong in `strategy.json`, not here.

## Constraints

- Do not place orders.
- Do not output exact order prices unless they already exist as MA/ATR anchors in mapper/strategy.
- Do not recommend adding to a stock with `D`.
- If data is missing, downgrade; never upgrade based on guesswork.
- If current time is before 09:35, mark the guide as "early signal, rerun after first 5-minute bar".
- If current time is after 14:45, do not suggest new intraday chase buys; use "尾盘风险" framing.
- All output in Chinese.




