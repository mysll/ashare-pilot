---
name: intraday-operation-guide
description: Use when the user wants one-shot intraday human trading instructions based on today's morning strategy and current market data. Reads predict/{date}/strategy.json + mapper.json, fetches current quotes and 5-minute intraday K-lines, then outputs actionable A/B/C/D operation guidance as operation_guide.html (Bloomberg × IC memo × quant board). This skill does NOT place orders.
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
operation/{YYYY-MM-DD}/operation_guide.html
```

Canonical human board is HTML. Do not write `operation_guide.md` as the primary deliverable.

## Workflow

### Step 1 - Run Intraday Snapshot

Run the first confirmation after the completed opening bar:

```bash
python .opencode/skills/intraday-operation-guide/scripts/build_operation_snapshot.py \
  --date {YYYY-MM-DD} --slot 09:35 --write-latest \
  -o operation/{YYYY-MM-DD}/operation_snapshot_0935.json
```

Run the primary second confirmation after 09:40, using the first snapshot for
state-transition validation:

```bash
python .opencode/skills/intraday-operation-guide/scripts/build_operation_snapshot.py \
  --date {YYYY-MM-DD} --slot 09:40 --write-latest \
  --previous-snapshot operation/{YYYY-MM-DD}/operation_snapshot_0935.json \
  -o operation/{YYYY-MM-DD}/operation_snapshot_0940.json
```

Do not overwrite slot snapshots. `operation_snapshot.latest.json` is only a
convenience projection for reading.

### Late delivery policy

Confirmation starts from the first slot available after Step 3 has fully
generated, normalized, validated, and rendered its outputs. Never backfill a
missed slot:

| First available snapshot | Required handling |
|---|---|
| `09:35` | normal initial confirmation |
| `09:40` without previous snapshot | `WAIT_SECOND_CONFIRMATION`, every stock capped at B and zero position |
| `09:45` with a `09:40` previous snapshot | normal continuation; B→A may execute |
| `09:45` or later without previous snapshot | `OBSERVE_ONLY`, every stock capped at C/D |

Always read `delivery_confirmation` separately from
`market_confirmation`. A late workflow is an execution-delivery problem, not a
claim that the market itself is weak.

The script:
- reads strategy stocks and execution constraints from `strategy.json`
- reads MA5/MA20/ATR/High20 from `mapper.json`
- fetches the three market indices and computes `regime_live` + `global_action`
- fetches current quotes in one batch
- fetches today's 5-minute K-line for each strategy stock
- discards any 5-minute bucket that is not complete at snapshot time
- separates the fixed 09:30-09:35 `first_bar` from `latest_completed_bar`
- computes mechanical execution signals, class caps, position caps, and T+1 controls
- applies aggregate `portfolio_limits` after all stock/theme/transition decisions:
  single-stock cap, theme exposure, correlated-name count, then total new exposure

Validate the generated snapshot before writing the guide:

```bash
python .opencode/skills/intraday-operation-guide/scripts/validate_operation_snapshot.py operation/{YYYY-MM-DD}/operation_snapshot_0940.json
```

Then build and validate the deterministic decision contract:

```bash
python .opencode/skills/intraday-operation-guide/scripts/build_operation_decision.py \
  --snapshot operation/{YYYY-MM-DD}/operation_snapshot_0940.json \
  -o operation/{YYYY-MM-DD}/operation_decision_0940.json
python .opencode/skills/intraday-operation-guide/scripts/validate_operation_decision.py \
  operation/{YYYY-MM-DD}/operation_decision_0940.json
```

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
operation/{YYYY-MM-DD}/operation_snapshot_0940.json
operation/{YYYY-MM-DD}/operation_decision_0940.json
predict/{YYYY-MM-DD}/strategy.json
predict/{YYYY-MM-DD}/mapper.json
```

Use `operation_decision.json` as the source for final class and position. The
snapshot provides supporting signals only. The HTML board must not invent a class or
position that differs from the validated decision contract.

Before considering any A row, require
`delivery_confirmation.execution_action=EVALUATE`. Both
`WAIT_SECOND_CONFIRMATION` and `OBSERVE_ONLY` require zero new exposure.

For `daily_strategy.v2`, stock-specific `t1_risk_plan` fields are preserved
verbatim into `t1_controls.t1_exit_plan` with `source=daily_strategy.v2`.
Generic T+1 text is allowed only for projected historical v1 strategies.

The snapshot also contains `theme_confirmations` derived from the bounded daily
strategy pool and per-stock `transition` metadata. `FAILED`/`FADING` themes cap
stocks at C, `NARROW` caps at B, and a D stock cannot upgrade in a later slot.

### Step 4 - Render HTML Board

After the decision contract is validated, render the human board:

```bash
python .opencode/skills/intraday-operation-guide/scripts/render_operation_guide_html.py \
  --date {YYYY-MM-DD} \
  --decision operation/{YYYY-MM-DD}/operation_decision_0940.json \
  --snapshot operation/{YYYY-MM-DD}/operation_snapshot_0940.json \
  --output operation/{YYYY-MM-DD}/operation_guide.html
```

Style contract (must match renderer): **Bloomberg Terminal × 投委会 Memo × A股量化策略看板**.

- Dark terminal cockpit (indices, regime, global_action, class mix)
- Investment-committee memo bullets (portfolio call, A/B lists, discipline)
- Quant board tables + A/B execution cards + C/D watch cards + theme radar + risk limits

Prefer the deterministic renderer. LLM narrative is optional and must not diverge
from `final_class` / `final_position_max` in the decision JSON.

## Operation Classes

Every strategy stock MUST be assigned exactly one class:

| Class | Meaning | Human action |
|-------|---------|--------------|
| A | 现在可参与 | Can buy now if no personal position conflict |
| B | 等确认 | Wait for the listed trigger; do not buy before trigger |
| C | 只观察 | Watch only; no new buy today unless later skill rerun upgrades it |
| D | 放弃/回避 | Do not buy today |

The snapshot provides `decision_guardrails.mechanical_class` and
`decision_guardrails.max_allowed_class`. The LLM may keep or downgrade the
mechanical class, but MUST NOT upgrade above `max_allowed_class`.

`market_confirmation.global_action` is a hard portfolio gate:

| global_action | Rule |
|---|---|
| `NORMAL` | A is mechanically possible |
| `SELECTIVE` | A is possible only when stock confirmation passes; position is reduced |
| `WAIT` | Every stock is capped at B |
| `NO_NEW_BUY` | Every stock is capped at C/D; no new position |

## Mechanical Signal Meanings

The script outputs these normalized flags:

| Flag | Meaning |
|------|---------|
| `above_ma5` | current price >= MA5 |
| `above_ma20` | current price >= MA20 |
| `near_ma5` | current price within +/-0.5 ATR of MA5 |
| `near_ma20` | current price within +/-0.5 ATR of MA20 |
| `latest_completed_bar.volume_confirmed` | latest completed 5-min volume >= 1.5x completed-bar baseline; null means insufficient baseline |
| `latest_completed_bar.price_strength_confirmed` | latest completed 5-min candle closes green and near its high |
| `first_bar.red_flag` | the completed 09:30-09:35 bar is a large red candle |
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
- `first_bar.red_flag = false`
- no `high_open_fade`
- not hard-risk or data-warning
- `decision_guardrails.max_allowed_class = A`
- final position does not exceed `decision_guardrails.position.final_max`

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

Primary deliverable: `operation/{date}/operation_guide.html` via
`render_operation_guide_html.py`.

HTML sections (fixed by renderer):

1. **Topbar** — 盘中操作总控台 · date/slot/generated time
2. **Cockpit** — market regime + indices · portfolio exposure/A-B-C-D counts · class mix
3. **投委会纪要** — 5-bullet IC memo (call, exposure, A list, B list, discipline)
4. **一句话操作总表** — class/code/name/sector/morning/price/position/trigger/reason
5. **A/B 执行卡片** — 30s cards: 早盘意图 / 当前信号 flags / 操作 / 触发或失效 / T+1
6. **C/D 观察与回避** — short reason cards only
7. **主题确认雷达** — theme_state / advance / VWAP ratios
8. **风控与交付** — global_action, delivery gate, portfolio limits, observable risks

All Chinese labels. Style tokens align with `daily_report.html` /
`overnight_strategy.html` (dark terminal, cyan accent, red-up/green-down A-share
convention).

## Card Rules

- The card must be executable by a human in under 30 seconds.
- Do not ask the user to judge "是否放量"; use `volume_confirmed=true/false`.
- Do not ask the user to judge "是否站稳"; use `price_strength_confirmed`, `above_ma5`, `above_ma20`, and `below_vwap`.
- If morning strategy has `不买条件` and snapshot confirms it, class MUST be D.
- If morning strategy has `锚点`, show current distance to that anchor using `dist_atr`.
- Keep each card short. Long thesis and reasoning belong in `strategy.json`, not here.
- Renderer is authoritative for HTML layout; do not hand-author divergent HTML.

## Constraints

- Do not place orders.
- Do not output exact order prices unless they already exist as MA/ATR anchors in mapper/strategy.
- Do not recommend adding to a stock with `D`.
- If data is missing, downgrade; never upgrade based on guesswork.
- Never exceed the morning `position_budget` or any mechanical position cap.
- Never exceed `portfolio_allocation.limits`; final allocation order is
  deterministic by rating, confirmed theme, sustained confirmation, requested
  budget, then stock code.
- For a new A-share position, never write "跌破即卖出" as a same-day action.
  Express the level as a pre-entry cancellation condition; after execution it
  becomes a T+1 risk alert and next-day exit-plan input.
- If current time is before 09:35, mark the guide as "early signal, rerun after first 5-minute bar".
- If current time is after 14:45, do not suggest new intraday chase buys; use "尾盘风险" framing.
- All output in Chinese.




