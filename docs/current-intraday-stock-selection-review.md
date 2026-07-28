# Intraday 选股系统评审与改造建议

- 评审日期：2026-07-27
- 评审对象：[当前 Intraday 选股、评分与过滤流程](current-intraday-stock-selection.md)
- 评审范围：14:30 尾盘隔夜流水线的运行可靠性、候选生成、评分有效性、数据降级、交易资格与验证闭环
- 文档性质：历史评审；建议已由 [ADR-0004](adr/0004-intraday-selection-pools-contract.md)
  和 [最终开发计划](intraday-stock-selection-final-development-plan.md) 落地，不作为当前生产契约

## 1. 总体结论

当前系统已经具备较好的软件工程骨架：

- 召回、数据补全、评分、Reasoning 和发布校验边界清楚；
- 行情、评分、执行资格和止损价格由确定性代码管理；
- LLM 不能覆盖计算字段；
- 数据质量状态能够随结果向下游传播；
- 封板、板块范围、I13、I14 和止损条件具有发布前强校验；
- 已建立盘后复盘、规则治理和单元测试。

但系统当前更适合作为**尾盘观察与人工决策支持系统**，尚不适合把
`opportunity_pool`、A/B 档或 `overnight_score` 直接解释为经过验证的可交易推荐。

主要原因不是某个权重不够准确，而是以下四个结构性问题：

1. 可交易资格计算晚于 Top K 截断，候选容量被大量封板股占据；
2. 资金流 partial 场景使用有方向性偏差的中位数插补，同时放宽绝对地板；
3. 总编排不 fail-fast，可能在阶段失败后继续消费同日期残留文件；
4. 当前分数高度暴露于当日强势与资金拥挤，尚无稳定的样本外 T+1 Alpha 证据。

建议优先修复运行正确性和候选资格顺序，再讨论评分权重。

## 2. 评审评分

| 维度 | 评分 | 说明 |
|------|:----:|------|
| 工程与数据契约 | 7/10 | 分层、字段所有权和校验边界较成熟 |
| 风险控制与可追溯性 | 7/10 | 最终发布能阻止多类不可执行建议，但部分约束介入过晚 |
| 候选生成质量 | 4/10 | 召回标签、候选容量和数据缺失会产生明显偏置 |
| 评分有效性证据 | 3/10 | 已有复盘出现负相关，尚未完成冻结版本的连续前向验证 |
| 实盘就绪度 | 4/10 | 可以辅助决策，不宜把相对排名直接当交易信号 |

这些评分评价的是当前实现成熟度，不代表收益承诺。

## 3. P0：必须优先修复

### 3.1 在 Top K 之前计算可交易资格

#### 当前问题

当前顺序是：

```text
评分
  → A/B/C/D
  → floor
  → Top 30
  → mapper base
  → execution_state
```

封板、排除板和关键报价缺失只有在 mapper base 阶段才被标记为
`eligible=false`。这些股票已经占用了 `opportunity_pool` 名额，后续
Reasoning 只能把它们改成观望，不能从第 31 名以后补入可交易股票。

使用当前 `execution_state` 对 2026-07-20 至 2026-07-27 六个缓存日重新计算：

| 日期 | Opportunity Pool | 不可交易 | 不可交易占比 |
|------|-----------------:|---------:|-------------:|
| 2026-07-20 | 17 | 11 | 64.7% |
| 2026-07-21 | 29 | 19 | 65.5% |
| 2026-07-22 | 14 | 6 | 42.9% |
| 2026-07-23 | 29 | 19 | 65.5% |
| 2026-07-24 | 30 | 24 | 80.0% |
| 2026-07-27 | 30 | 25 | 83.3% |
| **合计** | **149** | **104** | **69.8%** |

这说明“封板股晚过滤”不是边缘情况，而是候选容量的主要损耗来源。

#### 建议设计

拆分观察池和执行池：

```text
Scored Pool
  ├─ Observation Pool
  │    └─ 可包含封板股，用于主题、情绪和 T+1 观察
  └─ Executable Candidate Pool
       ├─ execution_state.eligible = true
       ├─ floor_pass = true
       ├─ 主题/行业集中度约束
       └─ 按分数截取 executable Top K
```

`execution_state` 应在评分完成后、最终候选截断前生成。若业务希望分析封板股，
应把它们放入独立的 `observation_pool`，而不是占用可执行 Top K。

建议新增明确字段：

```json
{
  "observation_pool": [],
  "executable_pool": [],
  "executable_pool_target_size": 30,
  "executable_pool_actual_size": 18,
  "non_executable_summary": {
    "sealed_limit_up": 21,
    "board_policy": 0,
    "quote_data_missing": 1
  }
}
```

#### 验收标准

- `executable_pool` 中所有股票必须满足 `execution_state.eligible=true`；
- 不可交易股票不得占用 `executable_pool_target_size`；
- 当可交易股票不足目标数量时，必须明确输出实际数量和原因，不得用不可交易股票填充；
- mapper 和 LLM 继续看到观察池摘要，但只允许对执行池生成持仓方向；
- 增加“前 30 名全部封板时能够继续向后补充可交易候选”的冻结测试；
- 增加主题集中约束后自动补位测试。

### 3.2 总编排改为 fail-fast 和原子发布

#### 当前问题

`automation intraday run` 会记录子命令失败，但不会根据
`result["success"]` 停止后续阶段。如果同日期目录中已有旧 JSON，后续阶段可能继续
消费残留文件。主函数也没有聚合失败并返回非零状态。

潜在故障链：

```text
本轮 enrich 失败
  → 同日期 compute_pool_enriched.json 旧文件仍存在
  → technical/theme/score 继续运行
  → 生成混合不同运行批次的结果
  → 调度器可能仍将任务视为成功
```

这会破坏“同一批次证据”和“固定快照”的基本假设。

#### 建议设计

每次运行使用独立 `run_id` 和临时目录：

```text
.cache/intraday/{date}/runs/{run_id}/
  manifest.json
  all_stocks_cache.json
  market_breadth.json
  indices.json
  concept_dashboard.json
  scan_pool.json
  compute_pool_enriched.json
  theme_ranking.json
  opportunity_pool.json
```

只有全部必需阶段成功后，才原子更新：

```text
.cache/intraday/{date}/current.json
```

`manifest.json` 至少记录：

- `run_id`；
- 业务日期；
- 开始和完成时间；
- 每个阶段的状态、退出码和耗时；
- 每个输入、输出文件的 SHA-256；
- 数据抓取时间；
- 评分与配置版本；
- 是否允许发布；
- 失败原因。

#### 验收标准

- 任一必需阶段失败后，不得调用依赖它的后续阶段；
- 任一必需阶段失败时 CLI 必须非零退出；
- 本轮失败不得修改 `current.json`；
- 下游必须校验日期、`run_id` 和输入哈希；
- 同日期旧文件存在时，失败运行不得复用旧文件；
- 增加阶段失败、旧缓存污染、日期不一致和哈希不一致测试。

### 3.3 修正 partial 资金流的统计语义

#### 当前问题

资金流接口按主力净流入降序分页。若前部页面成功、后部页面失败，未覆盖股票不是
随机缺失，而更可能处于较低的资金排名。

当前处理同时做了两件事：

1. I11 把缺失资金维度替换为有效样本中位数；
2. absolute floor 对未覆盖股票跳过主力净流入检查。

这种组合会对未覆盖股票产生系统性乐观偏差：它们既获得“中等资金质量”，又不需要
证明绝对净流入为正。

#### 建议设计

区分三类缺失：

| 类型 | 含义 | 建议处理 |
|------|------|----------|
| `threshold_reached` | 已知低于配置门槛 | 资金地板失败 |
| `partial_tail_missing` | 排序分页后段因请求失败而未覆盖 | 不得以中位数进入资金评分；执行池 fail-closed |
| `unavailable` | 全池接口不可用 | 发布降级观察池；资金依赖型执行池关闭或使用独立无资金模型 |

对 `partial_tail_missing`，优先顺序建议为：

1. 重试失败页；
2. 仍失败则对未覆盖股票关闭 Capital、Intensity、Conviction、Consistency；
3. 不参与依赖资金流的执行排名；
4. 可以保留在观察池，并明确 `capital_evidence=unknown`。

不要把“未知”转换成“同池中位数”。若确需插补，只能用于展示或研究，并必须带有
独立的 `imputed=true` 标记，不能直接获得可执行资格。

#### 验收标准

- partial 未覆盖股票不得因插补通过资金地板；
- 缺失数据不能提高任何股票相对名次；
- 输出覆盖率、缺失类型和受影响股票数量；
- 覆盖率低于配置门槛时，执行层有确定性的降级动作；
- 测试证明同一股票从完整数据变成缺失后，执行资格或分数不会改善。

## 4. P1：评分与候选结构改造

### 4.1 让主题维度真正表达主题持续性

当前 `Theme Continuity` 是：

```text
source_pool ordinal × 70%
  + sigmoid(main_net_inflow) × 30%
```

它没有读取 `theme_ranking.json`，也没有表达跨日持续性。建议先重命名现有维度，避免
语义误导：

```text
Theme Continuity → Source Strength
```

然后新增真正的确定性主题特征：

- 股票所属主题的 `core_heat`；
- `diffusion_heat`；
- 股票与主题的 core/qualified/edge 关系；
- 主题内上涨家数和强势成员广度；
- 主题资金净流入；
- 主题连续活跃天数；
- 热度相对前一日的变化；
- 股票在主题内的领涨、跟涨或扩散位置。

建议不要把一个主题总分直接复制给全部成员，而是计算：

```text
StockThemeScore =
    ThemeDynamicStrength
  × MembershipQuality
  × StockRoleWeight
  × ContinuationEvidence
```

主题输入缺失时应输出 unknown，不应回退为个股资金流。

### 4.2 降低资金维度重复计权

当前以下维度高度相关：

- Theme 中的主力净流入；
- Capital；
- Intensity；
- Conviction；
- Consistency；
- Tail 中的换手和量比。

百分位化只能统一量纲，不能消除相关性。建议在冻结样本上输出维度相关矩阵，并将特征
按家族分组：

```text
Theme family
Capital family
Price-action family
Trend family
Risk family
Liquidity family
```

每个家族设置总权重上限，避免同一底层数据以不同公式重复获得权重。

候选方案：

- Capital：绝对净流入和流通市值归一化后的净流入率二选一；
- Intensity：只有在证明相对 Capital 有增量信息后保留；
- Conviction/Consistency：合并成一个资金结构质量维度；
- Tail：剥离换手容量，专注尾盘价格行为；
- Liquidity：单独使用成交额、自由流通市值和预估冲击成本。

### 4.3 `source_pool` 改为多标签证据

当前按召回顺序去重，只保留第一个来源。这会把“同时命中多路”降维成单一类别，也让
来源调用顺序影响后续分数。

建议结构：

```json
{
  "source_pools": ["limit_up", "turnover", "gain_range"],
  "source_evidence": {
    "limit_up_rank": 12,
    "turnover_rank": 31,
    "gain_rank": 8
  }
}
```

QuickScore 应根据多路证据聚合，而不是按第一个标签赋固定基础分。

### 4.4 QuickScore 加入真实流动性和召回质量

当前 `amount` 被解析但未使用，“TurnoverCapacity”实际只使用换手率。换手率不能
替代成交额，也不能表达策略仓位的市场冲击。

建议加入：

- 当日成交额；
- 自由流通市值；
- 近 20 日成交额中位数；
- 当前成交额相对历史分位；
- 目标仓位占成交额比例；
- 估算冲击成本；
- 停牌、涨停封单和报价完整性。

每一路召回还应输出质量状态：

```json
{
  "recall_quality": {
    "limit_up": {"status": "complete", "count": 60},
    "turnover": {"status": "unavailable", "count": 0},
    "gain_range": {"status": "complete", "count": 214}
  }
}
```

如果正常应有大量结果的来源突然为 0，不能静默进入后续流程。

### 4.5 技术指标缺失不得自动通过趋势地板

当前技术数据缺失时 Trend raw 固定为 0.5，而趋势地板为 0.3，因此未知数据会自动
通过。

建议将状态拆开：

```text
trend_value
trend_available
trend_quality
```

执行池要求 `trend_available=true`，或使用明确的无技术数据降级模型。不得用中性值
同时代表“真实中性趋势”和“数据缺失”。

### 4.6 重新定义 A/B/C 的产品语义

A/B/C 当前只是强制相对名次。即使全池质量很差，也会产生靠前档位，而且 Top 30
常被 A/B 占满，C 档很少进入。

建议：

- 保留 `rank_tier` 作为纯展示字段；
- 新增独立的 `tradeability` 或 `quality_band` 绝对门槛；
- 不允许界面把 A 解释为高胜率或强买入；
- 若业务需要不同类型候选，使用配额而不是单一总分截断：
  - 趋势延续；
  - 早期突破；
  - 主题扩散；
  - 低位承接；
- 每类配额均从 `eligible=true` 股票中补位。

## 5. P2：验证与研究体系

### 5.1 冻结版本后做连续前向验证

当前盘后复盘很有价值，但规则和权重频繁变化时，同一批数据容易同时承担：

- 发现问题；
- 发明规则；
- 验证规则。

这会产生数据窥探和过拟合。建议每个评分版本至少记录：

- `model_version`；
- `feature_version`；
- `rule_version`；
- `scope_version`；
- 生效日期；
- 冻结结束条件。

版本冻结期间，只允许修复数据污染、契约错误和明显实现 bug，不根据单日收益调整
权重。

### 5.2 建立简单基线

新模型必须和简单策略比较，而不是只看自身胜率：

1. 全部 eligible 股票等权；
2. eligible 中按当日涨幅排序；
3. eligible 中按主力净流入排序；
4. eligible 中按 Trend Quality 排序；
5. 随机 eligible Top K；
6. 空仓基线；
7. 适用指数基线，如中证 1000、深证成指或创业板指。

如果九维模型不能稳定超过简单基线，不应增加复杂度。

### 5.3 核心评价指标

至少按全市场状态和主题状态分层报告：

| 类别 | 指标 |
|------|------|
| 排序质量 | Spearman Rank IC、Top-K 与 Bottom-K 收益差 |
| 收益 | T+1 开盘、最高、最低、收盘收益和超额收益 |
| 执行 | 14:50–14:57 实际可成交价、滑点、冲击成本 |
| 风险 | MAE、尾部损失、最大回撤、跌停暴露 |
| 命中 | 正收益率、止盈触达率、止损触发率 |
| 候选质量 | eligible 覆盖率、不可交易占位率、数据缺失率 |
| 组合 | 主题集中度、行业集中度、换手率、成本后收益 |

评分有效性必须主要在**非封板 eligible 子集**上检验。把不可买的封板股混入相关性
统计，会同时测量“涨停状态”与评分，无法回答可执行股票之间的排序是否有效。

### 5.4 当前证据的解释边界

已有复盘提供了重要反例：

- 2026-07-10 的 Score 与 T+1 收益 Spearman 约为 -0.31；
- 当日高分组平均收益低于低分组；
- 多个资金与热度维度在涨停潮反转日呈负相关；
- 2026-07-24 也出现高分封板股弱、低分 eligible 股票较强的现象。

这些结果不能凭单日判定模型无效，但足以否定“分数越高就稳定拥有更高隔夜收益”的
未经验证解释。后续应检验：

```text
score 是否能在同一 regime、同一 execution eligibility、
相近流动性和相近主题状态下稳定排序 T+1 收益。
```

## 6. 推荐实施顺序

### Phase 1：运行正确性

1. 编排 fail-fast；
2. 临时 run 目录与原子发布；
3. manifest、哈希和时间戳；
4. 下游拒绝旧批次或混合批次输入；
5. 补齐失败路径测试。

完成标准：不能再生成“过程失败但看起来成功”的策略。

### Phase 2：候选池正确性

1. execution_state 前置；
2. observation/executable 双池；
3. 可交易候选自动补位；
4. 主题与行业集中度约束；
5. partial 资金流 fail-closed。

完成标准：`executable_pool` 的每一个名额都可交易、证据完整且不被封板股占位。

### Phase 3：特征语义修复

1. Theme Continuity 重命名；
2. 接入真实主题持续性；
3. source 多标签化；
4. 资金特征去重；
5. 增加流动性和冲击成本；
6. 技术缺失与中性趋势分离。

完成标准：每个维度名称、输入和经济含义一致，底层数据重复计权可被审计。

### Phase 4：Alpha 验证

1. 冻结版本；
2. 建立简单基线；
3. 连续前向积累样本；
4. 仅在达到预设样本门槛后评估改权重；
5. 报告成本后组合收益和风险。

完成标准：在至少一个冻结的样本外窗口中，模型对 eligible 股票的排序稳定优于简单
基线，且风险指标没有不可接受的恶化。

## 7. 建议新增的自动化验收用例

| 编号 | 场景 | 期望 |
|------|------|------|
| IT01 | enrich 阶段失败且同日期存在旧文件 | 立即非零退出，不运行后续阶段 |
| IT02 | Top 30 全部封板，第 31～60 名可交易 | executable pool 从后续名次补足 |
| IT03 | 资金流 partial，股票未覆盖 | 不得通过资金插补提升排名或资格 |
| IT04 | 技术数据缺失 | 不得以 Trend=0.5 自动通过执行地板 |
| IT05 | turnover 召回返回 0 | 输出 source unavailable；按策略中止或降级 |
| IT06 | 同一股票命中三路召回 | 保留全部来源及各自排名 |
| IT07 | mapper 输入来自不同 run_id | 拒绝构建 |
| IT08 | A/B 股票不可交易，C/D 股票可交易 | 按执行策略补位，不机械保留 A/B |
| IT09 | 同主题候选超过上限 | 自动补入下一只不同主题 eligible 股票 |
| IT10 | 缺失 confidence 或覆盖率低于阈值 | 不得发布可行动方向 |

## 8. 最终建议

短期内不建议继续微调九维权重。当前最具确定性收益的工作是：

1. 防止失败流程和旧缓存产生伪成功结果；
2. 把不可交易股票从可执行候选容量中前置分流；
3. 消除 partial 资金流的乐观插补；
4. 在 eligible 子集上重新验证评分。

完成这些工作后，`overnight_score` 才有一个干净、可成交、可复现的评价对象。否则继续
调权重，很可能只是在优化被封板状态、缺失数据和召回顺序共同污染的历史结果。
