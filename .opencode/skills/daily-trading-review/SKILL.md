---
name: daily-trading-review
description: Review daily strategy results after market close, generate machine-readable verification data, write a human review, and update trading memory/rules.
---

# Daily Trading Review

Use after market close or when the user asks for 复盘 / verification / review.

## Core Rule

`verification.json` is the authoritative data source for backtests and rule learning.

`verification.md` is a human-readable report. Do not make quantitative scripts depend on Markdown table parsing.

## Inputs

- `predict/{date}/strategy.json` — preferred machine-readable strategy input.
- `predict/{date}/strategy.md` — fallback human report if `strategy.json` is missing.
- `predict/{date}/pool_indicators.json` — used automatically by scripts when present for MA/ATR and technical context.
- `memory/RULES.md` and `memory/SHARED_RULES.md` — read before judging rule performance.

## Step 1: Load Strategy

Prefer `predict/{YYYY-MM-DD}/strategy.json`. It contains final Step 3 decisions: stocks, rating, entry profile, anchor, rules, and machine profile.

If `strategy.json` is missing, read `strategy.md` and pass stock codes explicitly as a fallback.

## Step 2: Generate Verification JSON

Run before writing `verification.md`:

```bash
python .opencode/skills/daily-trading-review/scripts/generate_verification_json.py --date {YYYY-MM-DD} --pretty
```

If `strategy.json` is missing, use fallback:

```bash
python .opencode/skills/daily-trading-review/scripts/generate_verification_json.py \
  --date {YYYY-MM-DD} --codes sh600000,sz000001,... --regime {panic|weak|neutral|strong-sector} --pretty
```

Output:

```text
memory/daily/{YYYY-MM-DD}/verification.json
```

The script fetches market data directly, uses `pool_indicators.json` when available, and generates:

- actual OHLC
- MA5 / MA10 / MA20 / ATR
- first 5-minute candle state
- candidate Entry Band shadow results:
  - `MA20_ZONE`
  - `MA10_ZONE`
  - `MA5_ZONE`
  - `OPEN_CONFIRM`

Optional shadow backtest:

```bash
python .opencode/skills/daily-trading-review/scripts/entry_band_shadow_backtest.py --since {YYYY-MM-DD}
```

Treat early shadow results as evidence collection only. Do not update entry rules until enough forward samples accumulate by regime/playbook.

## Step 3: Write Human Review

Write:

```text
memory/daily/{YYYY-MM-DD}/verification.md
```

Keep the report concise and Chinese-first.

Required sections:

```markdown
# 验证复盘 {YYYY-MM-DD}

## 市场环境
- RegimeHint: {panic|weak|neutral|strong-sector}
- 上证 / 深证 / 科创50: ...

## 结果摘要
- 买入触及率:
- 触及后胜率:
- 踏空:
- 观望正确:
- 5星成功率:

## 买入结果表

| # | 代码 | 名称 | 评级 | 策略 | 入场锚 | 开盘 | 最低 | 盘中最高 | 收盘 | 触及 | 首根K确认 | 利润给回% | 结果 |
|---|------|------|:---:|------|--------|:---:|:---:|:---:|:---:|:---:|:---:|:---:|:---:|

## Super Predictions 验证

## 规则触发记录

| 规则编号 | 规则名称 | 触发标的 | 结果 | 累计验证次数 |
|----------|----------|----------|------|:----------:|

## 关键教训

## 次日策略调整
```

Buy result table constraints:

- `代码`: `sh`/`sz` + 6 digits.
- `策略`: `趋势跟随` / `回调布局` / `强势接力` / `防御布局` / `暂不参与`.
- `入场锚`: `MA5:price` / `MA10:price` / `MA20:price` / `OPEN:price` / `追入:price` / `—`.
- `触及`: `是` / `否` / `—`.
- `首根K确认`: `企稳` / `击穿` / `未触及` / `—`.
- `结果`: `成功` / `部分成功` / `失败` / `踏空` / `观望正确`.

Do not hand-calculate MAE or hold-to-close in Markdown; scripts derive them from JSON.

## Step 4: Update Memory

Update only when there is evidence:

- `memory/daily/INDEX.md` — add links to strategy/review.
- `memory/RULES.md` — morning/opening/auction/first-K rules.
- `memory/SHARED_RULES.md` — general rules.
- `memory/INTRADAY_RULES.md` — tail/T+1 rules.
- `memory/PERFORMANCE.md` — periodically update summary stats and key dates.

New rules start in observation status. Include:

- rule statement
- evidence
- how to apply
- validation count/status

## Output Files

| File | Purpose |
|------|---------|
| `memory/daily/{date}/verification.json` | Machine data for backtests |
| `memory/daily/{date}/verification.md` | Human-readable review |
| `memory/daily/INDEX.md` | Daily memory index |
| `memory/RULES.md` / `SHARED_RULES.md` / `INTRADAY_RULES.md` | Rule updates |

## Notes

- If `predict/{date}/strategy.json` is missing, stop and ask to run daily-market-analysis first.
- Always read `memory/RULES.md` and `memory/SHARED_RULES.md` before assessing rule performance.
- Output review content in Chinese.
