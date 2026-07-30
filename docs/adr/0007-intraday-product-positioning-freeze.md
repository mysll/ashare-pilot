# ADR-0007：Intraday 隔夜 STANDARD 切片暂停（产品定位冻结）

- 状态：Accepted（冻结包）
- 日期：2026-07-30
- 范围：Intraday 14:30 隔夜流水线对 `STANDARD` 仓位档（即 ADR-0006 中愿意承担 2% 单笔风险的执行档）的允许范围与解冻条件
- 关联：[ADR-0006 风险预算仓位](0006-risk-based-position-sizing.md)、[Intraday 切片归因冻结](../review/intraday-slice-attribution-2026-07-frozen.md)
- 来源：2026-07-30 grilling 会话冻结包

## 背景

2026-07-02 ~ 2026-07-29 共 15 个尾盘持仓日，按 14:30 `market_breadth.json`
的 `up_ratio` 分桶归因（详见切片归因冻结报告）：

| Regime 桶 | n | 平均 T+1 | 胜率 |
|-----------|---:|--------:|----:|
| weak <25% | 3 | -3.01% | 0/3 |
| weak 25-40% | 3 | +0.22% | 2/3 |
| neutral ≥40% | 9 | **-1.14%** | 3/9 = 33% |
| 合计 | 15 | ≈ -1.2%/d | 4/15 = 27% |

关键事实：即使 T 日市场广度 ≥40%（含 4 日 >70%）的"看似非弱"日子，overnight
持仓 T+1 仍平均亏损 -1.14%、胜率仅 33%。**当前可观测样本下，三个 regime 桶
没有任何一桶达到 ADR-0006 规定的 STANDARD 准入条件**（正期望 + 样本数 + 显著
跑赢弱市基线）。

依据 ADR-0006，在 edge 未经切片测量证实的切片中，所有可执行候选默认上限 `LIGHT`
或 `WATCH_ONLY`。结合 ADR-0006 的风险预算与 Kelly 逻辑，负期望下诚实仓位即
零仓。本 ADR 将此规则在产品层显式冻结。

## 决策

### 1. STANDARD 档冻结

自本 ADR 接受日起，`overnight_strategy.json` 与人类可读板报必须执行：

- 严禁输出 `STANDARD` 等级推荐；
- 仓位档生成器对任何 overnight 候选最多输出 `LIGHT`（1% 单笔风险预算）；
- 一切 LLM 在 Reasoning 阶段不得赋予 `STANDARD`；若触发，最终发布校验失败。

### 2. LIGHT 档可用 regime 缩窄

`LIGHT` 仅在以下情形允许出现持仓项；否则全 `WATCH_ONLY`：

| Regime（由现行 `market_assessment.regime` 判定） | 允许 LIGHT？ |
|------------------------------------------------|------------|
| weak（I13 触发，上涨比<15%） | 否 → 全 WATCH_ONLY |
| weak（15% ≤ up_ratio <25%） | 否 → 全 WATCH_ONLY |
| weak（25% ≤ up_ratio <40%） | 允许，最多 1 只 LIGHT |
| neutral | 允许，最多 3 只 LIGHT |
| strong | 允许，最多 5 只 LIGHT（仍非 STANDARD） |

> 注：`neutral≥40` 仍 t-1.14% 负期望，LIGHT 仓位（1% 单笔风险预算）下输血的
> 单日组合风险已被压到个位 bp，损失容忍度允许继续观察样本而不放弃信号感知。
> 这是"研究探针"姿态，不是"可盈利仓位"建议。

### 3. 解冻条件（任意一项触发才重评）

1. **样本门槛**：累计 ≥5 个 trend-strong regime 交易日（trend-strong 定义见
   切片报告 §5.1）；
2. **切片新证据**：新增 pool-wide 切片，发现 Bart-agreed `STANDARD` 切片
   （avg T+1 >0.5% ∧ Rank IC>0 ∧ n≥10 ∧ 显著跑赢 weak<40% 基线 ≥1pp）。

满足任一条件后启动一次 grilling 复审；复审通过才解冻 `STANDARD` 并改写本 ADR 状态。

### 4. 与现有学习规则的兼容

- I01（游戏级 ≥75 → Suitable 阈值）继续，但其产物可执行等级强制天花板 `LIGHT`；
- I13（极端弱市零仓）优先，与本 ADR 决策 2 一致；
- I05、I12、I16、I19、I20、I21.a 等防御规则**收紧继续生效**——它们与"上限 LIGHT"
  联合构成的最弱基线不应被放松。

### 5. 不在本 ADR 范围

- 不冻结 learned rule 的候选→观察→有效生命周期；
- 不动 daily 早盘策略（`daily_strategy.v1`）仓位档；
- 不实施 overnight 入场/持有交互的构造改造（如改为 T+1 早盘确认后入场）——
  留待切片刷新后视结论再开 ADR。

## 结果

产品语义重新校准：当前 intraday 在已积累样本内不提议 `STANDARD` 风险仓位。
Reasoning 层允许感知个票并给 LIGHT 探针（含 regime 缩窄），但持仓决策的"可盈利"
判断在 evidence 切片刷新后才有资格做。这一冻结让系统对"我目前没证实能赚隔夜钱"
有诚实表达，并给出客观重启门槛。