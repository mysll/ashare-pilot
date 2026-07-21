# 买入区间影子回测系统

> 日期: 2026-07-06  
> 状态: v1 设计与落地说明  
> 范围: daily-strategy → daily-trading-review → Entry Band shadow backtest
> 运行跟踪: [entry-band-backtest-tracking.md](entry-band-backtest-tracking.md)

---

## 1. 目的

这个系统要解决的问题不是"MA5 和 MA20 哪个更好",而是:

> 在不同市场状态、不同交易画像、不同个股位置下,应该输出什么样的有效买入区间。

过去的买入区间大多是规则映射:

```text
回调布局 → MA20
强势主线 → MA5
涨停接力 → 开盘/首根K确认
```

这种映射有两个问题:

1. **只验证真实采用的锚**,无法知道同一天如果用 MA10/MA5/OPEN 会怎样。
2. **容易把成交质量和踏空成本分开看**,导致 MA20 成交后质量不错,但强势日可能严重踏空。

新系统采用"影子回测"方式:真实策略照常执行,但复盘时对每只推荐股票同时模拟多种候选买入区间,让它们在同一天、同一批股票上横向比较。

---

## 2. 核心原则

### 2.1 JSON 是数据源

JSON 是系统固定产物和唯一数据源。Markdown 如有生成,只做人读报告,不作为回测数据源。

数据流:

```text
predict/{date}/strategy.json
predict/{date}/pool_indicators.json
        ↓
generate_verification_json.py
        ↓
memory/daily/{date}/verification.json
        ↓
entry_band_shadow_backtest.py
```

`strategy.md` 已取消固定生成,策略阶段只要求产出并校验 `strategy.json`。`verification.md`
可继续作为人读复盘报告,但量化研究不解析 Markdown 表格。

### 2.2 买入区间不是由评级单独决定

评级回答的是:

```text
这只股票值不值得做,可以给多少仓位。
```

买入区间回答的是:

```text
这只股票在当前市场和交易形态下应该怎么做。
```

因此买入区间要按以下维度分组验证:

- `regime`: strong-sector / neutral / weak / panic
- `entry_profile`: 趋势跟随 / 回调布局 / 强势接力 / 防御布局 / 暂不参与
- `rating`: 5★ / 4★ / 3★
- `position_state`: PULLBACK / TREND / EXTENDED
- `mainline`: 主线 / 非主线
- `risk_type`: overbought / trend_weak / broken_board 等

### 2.3 先影子比较,再改规则

真实交易规则不要因为单日结果频繁变化。先让候选区间每天后台比赛,等某个场景下胜负稳定,再小步调整规则。

---

## 3. 系统组件

### 3.1 `strategy.json`

由 `daily-strategy` 生成,位置:

```text
predict/{date}/strategy.json
```

它是早盘最终策略决策的机器版本,应包含:

- 股票代码、名称、板块
- 方向、评级
- 交易策略 `entry_profile`
- 锚点 `anchor`
- 入场条件 `entry_trigger`
- 不买条件
- 仓位预算
- 规则应用
- profile: playbook / preferred_anchor / chase_policy / entry_window

生成后必须校验:

```bash
python .opencode/skills/daily-strategy/scripts/validate_strategy_json.py predict/{date}/strategy.json
```

校验失败时,必须修正 `strategy.json`,不要临时写转换脚本。

### 3.2 `verification.json`

由盘后复盘生成,位置:

```text
memory/daily/{date}/verification.json
```

生成命令:

```bash
python .opencode/skills/daily-trading-review/scripts/generate_verification_json.py --date {YYYY-MM-DD} --pretty
```

若旧日期没有 `strategy.json`,可以临时回退:

```bash
python .opencode/skills/daily-trading-review/scripts/generate_verification_json.py \
  --date {YYYY-MM-DD} \
  --codes code1,code2,... \
  --regime strong-sector \
  --pretty
```

`verification.json` 合并三类数据:

| 来源 | 内容 |
|------|------|
| `strategy.json` | 最终策略画像、评级、入场逻辑 |
| `pool_indicators.json` | MA5/MA20/ATR/position_state/risk_type 等早盘事实 |
| 盘后行情接口 | 当日 open/low/high/close、首根5分K |

### 3.3 `entry_band_shadow_backtest.py`

回测脚本位置:

```text
.opencode/skills/daily-trading-review/scripts/entry_band_shadow_backtest.py
```

运行:

```bash
python .opencode/skills/daily-trading-review/scripts/entry_band_shadow_backtest.py --since {YYYY-MM-DD}
```

机器输出:

```bash
python .opencode/skills/daily-trading-review/scripts/entry_band_shadow_backtest.py --since {YYYY-MM-DD} --json
```

---

## 4. 候选买入区间

当前默认比较四类候选区间:

| 候选区间 | 公式 | 含义 |
|------|------|------|
| `MA20_ZONE` | `[MA20, MA20 + 0.5×ATR]` | 传统回调布局 |
| `MA10_ZONE` | `[MA10, MA10 + 0.4×ATR]` | MA20 太深、MA5 太追时的中间层 |
| `MA5_ZONE` | `[MA5, MA5 + 0.5×ATR]` | 强势趋势跟随 |
| `OPEN_CONFIRM` | `[Open, Open + 0.3×ATR]` 且首根5分K企稳 | 开盘确认/接力试仓 |

这些区间只是候选项。真实策略可以只采用其中一个,但回测会同时评估所有候选项。

---

## 5. 回测指标

每个候选区间都会统计:

| 指标 | 含义 |
|------|------|
| 触及率 | 当日是否有机会成交 |
| 持收收益 | 触及后按区间上沿入场,持有到收盘的收益 |
| MAE | 触及后最大不利波动 |
| 胜率 | 持收收益 > 0 的比例 |
| 击穿率 | 持收收益 <= -1.5% 的比例 |
| 踏空率 | 未触及但股票上涨 |
| 踏空涨幅 | 未触及时错过的 open→close 涨幅 |
| 观望正确率 | 未触及且股票下跌 |
| ZoneScore | 综合触及质量、踏空成本、风险后的评分 |

`ZoneScore` 只适合同一个 `regime + playbook` 内比较,不要跨场景直接比较。

---

## 6. 如何用回测优化买入区间

### 6.1 每天复盘时

1. `daily-strategy` 生成 `strategy.json`。
2. 校验 `strategy.json`。
3. 盘后运行 `generate_verification_json.py`。
4. 写人读版 `verification.md`。
5. 定期运行 shadow backtest。

### 6.2 每 5 个交易日滚动观察

每 5 个交易日跑一次:

```bash
python .opencode/skills/daily-trading-review/scripts/entry_band_shadow_backtest.py --since {start_date}
```

观察重点:

- strong-sector + 趋势跟随: MA5 是否显著优于 MA10/MA20
- strong-sector + 回调布局: MA10 是否比 MA20 更少踏空
- weak + 回调布局: MA20 是否仍提供观望保护
- EXTENDED + 高评级: 是否应该继续 WATCH_ONLY
- OPEN_CONFIRM: 是否提高触及率但显著恶化 MAE

### 6.3 调整规则的门槛

不要用一两天结果改规则。建议门槛:

| 调整方向 | 触发条件 |
|------|------|
| MA20 → MA10 | 同一场景样本 >=20, MA10 ZoneScore 连续两个窗口优于 MA20,击穿率未明显恶化 |
| MA10 → MA5 | strong-sector/趋势跟随中 MA5 踏空改善明显,且 MAE 不高于 MA10 太多 |
| 引入 OPEN_CONFIRM | 样本 >=15,企稳组胜率明显高于击穿组,且 MAE 可控 |
| 保留 MA20/观望 | weak/panic 中观望正确率高,避免跌幅大于踏空成本 |
| 废弃某锚 | 连续 3 个同场景窗口 ZoneScore 垫底,且没有保护价值 |

### 6.4 调整顺序

买入区间调整要小步走:

```text
MA20 → MA10 → MA5 → OPEN_CONFIRM → 小仓追入扩展
```

不要从 MA20 直接跳到无条件追开盘。每次只改变一个变量,否则回测无法归因。

---

## 7. 例子

如果回测显示:

```text
regime = strong-sector
entry_profile = 趋势跟随
MA5_ZONE ZoneScore 连续优于 MA20_ZONE
MA5_ZONE 踏空率显著更低
MA5_ZONE 击穿率不高于 MA20_ZONE +10pp
```

则可以考虑把该场景的默认买区从:

```text
MA20_ZONE
```

调整为:

```text
MA5_ZONE 或 MA10_ZONE
```

如果回测显示:

```text
regime = weak
entry_profile = 回调布局
MA20_ZONE 触及率低,但观望正确率高
MA5_ZONE 虽然触及多,但 MAE 和击穿率显著恶化
```

则应保留 MA20 或改为 WATCH_ONLY,而不是为了成交率前移买区。

---

## 8. 后续优化方向

1. 让 `strategy.json` 覆盖所有早盘最终决策字段,减少复盘阶段二次推理。
2. 在 `verification.json` 中补充 `mainline`, `theme_heat`, `position_state`, `risk_type` 等分组字段。
3. 扩展 shadow bands:
   - `VWAP_PULLBACK`
   - `TAIL_SUPPORT`
   - `MA20_SHIFT`
   - `R76_CHASE_EXT`
4. 给 `ZoneScore` 增加可配置权重,不同 regime 使用不同 `miss/risk/avoid` 权重。
5. 每周生成一份 Entry Band 小结,只更新证据;满足门槛后再改规则。

---

## 9. 一句话总结

买入区间优化不是靠判断"MA5 科学还是 MA20 科学",而是让所有候选区间在每天的真实推荐池里后台比赛。等某个场景下的赢家稳定出现,再把它升级为规则。
