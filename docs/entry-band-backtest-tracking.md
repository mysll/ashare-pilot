# 买入区间影子回测运行跟踪

> 正式数据起点: 2026-07-09  
> 当前状态: 样本积累中  
> 系统说明: [entry-band-backtest-system.md](entry-band-backtest-system.md)

---

## 1. 跟踪目标

本文件记录 Entry Band shadow backtest 的运行状态、数据质量、阶段结论和后续任务。

从 **2026-07-09** 起的数据作为正式连续观察样本。此前生成的数据只用于验证管线,
默认不并入后续滚动窗口和规则调整证据。

固定统计命令:

```bash
python .opencode/skills/daily-trading-review/scripts/entry_band_shadow_backtest.py \
  --since 2026-07-09
```

在样本达到文档规定的门槛前,只积累证据,不调整真实交易规则。

---

## 2. 起点验收: 2026-07-09

### 2.1 产物与数据链

| 检查项 | 结果 |
|------|------|
| `predict/2026-07-09/strategy.json` | 通过 `daily_strategy.v1` 校验 |
| 策略股票数 | 10 |
| `memory/daily/2026-07-09/verification.json` | 已生成 |
| 策略与复盘股票代码 | 10/10 一致 |
| `pool_indicators.json` 匹配 | 10/10 |
| 从 `strategy.json` 读取 | 是,未解析 `strategy.md` |
| shadow backtest | 正常运行,无脚本 warning |

### 2.2 起点样本

| 候选区间 | 有效观察数 |
|------|------:|
| `MA20_ZONE` | 10 |
| `MA10_ZONE` | 10 |
| `MA5_ZONE` | 10 |
| `OPEN_CONFIRM` | 8 |
| 合计 | 38 |

`OPEN_CONFIRM` 少于股票数是正常的:只有首根 5 分钟 K 线满足企稳条件时才启用。
其中 `sz300567` 当日缺少分时数据,不能评估 `OPEN_CONFIRM`。

### 2.3 数据质量说明

- 10 只股票的日行情均出现 `daily_history_missing_used_realtime_quote` warning。
- 当日盘后即时复盘可以保留这些样本,但不应用实时快照重新覆盖历史日期。
- `sz300567` 出现 `intraday_empty`,其均线候选区间仍可使用,仅排除
  `OPEN_CONFIRM`。
- 当前发现的 `actual_entry` 触及判定问题在 2026-07-08 已存在,不是本次
  `strategy.json` 调整引入的。
- `actual_entry` 的问题不影响四类 `shadow_bands` 的区间相交计算,因此不阻塞
  从 2026-07-09 开始积累影子样本。

### 2.4 起点结论

2026-07-09 的 JSON 调整未造成数据断链,当天数据可作为正式起点。当前样本只用于
确认系统能够持续运行,不能据此比较买入区间优劣或修改交易规则。

---

## 3. 每日复盘检查

每天盘后完成以下检查:

- [ ] `strategy.json` 通过校验。
- [ ] `verification.json` 成功生成,且明确读取 `strategy.json`。
- [ ] 策略股票数与复盘股票数一致。
- [ ] `pool_indicators_available` 无异常缺失。
- [ ] 检查 `fetch_failed`、`daily_history_missing`、`intraday_empty` 等 warning。
- [ ] 运行从 `2026-07-09` 开始的 shadow backtest。
- [ ] 不因单日结果调整 `RULES.md`。

缺失的候选区间不补造数据。应保留 `enabled=false` 或 warning,让回测自然排除。

---

## 4. 后续计划

### P0: 修正复盘数据口径

- [ ] 修复 `actual_entry` 触及判断,要求当天价格区间真正覆盖锚点。
- [ ] 统一 `OPEN`、`OPEN_CONFIRM`、`首根5min` 的策略和复盘口径。
- [ ] 增加 `verification.json` 校验器,检查 schema、日期、股票映射、OHLC、
  指标、候选区间及缺失状态。
- [ ] 为上述边界情况补充自动化测试。

这组任务不阻塞 shadow 数据积累,但应在使用“真实策略 vs 影子策略”比较前完成。

### P1: 完成首个滚动窗口

- [ ] 累积满 5 个交易日后生成第一份窗口小结。
- [ ] 分别报告 `regime + entry_profile` 下的触及率、持收收益、MAE、击穿率、
  踏空率和 ZoneScore。
- [ ] 单独列出行情或分时数据不完整的样本。
- [ ] 只记录观察,不提出规则升级。

### P2: 扩充场景字段

- [ ] 将 `position_state` 写入 `verification.json`。
- [ ] 将 `mainline`、`risk_type`、`rating` 纳入可分组字段。
- [ ] 按以下顺序增加分层,避免样本过度切碎:

```text
regime + entry_profile
→ position_state
→ mainline
→ risk_type / rating
```

### P3: 达到决策样本门槛

- [ ] 同一场景有效样本达到 20 后,才比较 MA20、MA10、MA5。
- [ ] `OPEN_CONFIRM` 同一场景有效样本达到 15 后,才评估是否引入。
- [ ] 候选区间连续两个滚动窗口领先,且风险指标未明显恶化,才形成规则变更建议。
- [ ] 规则建议依次经过人工审核、小仓观察和盘后验证。
- [ ] 验证稳定后再更新 `memory/RULES.md`,不自动修改交易规则。

---

## 5. 阶段记录

| 日期 | 交易日序号 | 累计股票 | 累计候选观察 | 状态 | 备注 |
|------|------:|------:|------:|------|------|
| 2026-07-09 | D1 | 10 | 38 | 正常 | 正式起点; `sz300567` 缺少分时数据 |

后续每日不必在本表记录单只股票结果。每 5 个交易日更新一次阶段汇总,出现数据契约
变化或严重质量异常时即时记录。

---

## 6. 当前下一步

1. 每天继续正常生成 `verification.json` 并积累 shadow 样本。
2. 实现 P0 的数据口径修复和验证器。
3. 第 5 个交易日结束后更新本文件,生成第一个滚动窗口小结。
