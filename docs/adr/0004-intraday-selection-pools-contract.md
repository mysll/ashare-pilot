# ADR-0004：Intraday 双池选股与发布合同

- 状态：Accepted
- 日期：2026-07-27
- 范围：14:30 尾盘隔夜流水线的评分资格、执行资格、双池、数据质量、Mapper 与最终发布合同
- 关联：[当前流程](../current-intraday-stock-selection.md)、[最终开发计划](../intraday-stock-selection-final-development-plan.md)、[领域术语表](../intraday-stock-selection-glossary.md)
- 前置决策：[ADR-0003 盘中主题证据链](0003-intraday-theme-evidence-contract.md)

## 背景

当前流水线先对 Compute Pool 评分并按 A/B/C 截取 Opportunity Pool，之后才在
mapper base 中计算 `execution_state`。封板、板块排除和关键报价缺失的股票可以先
占据 Top 30，再被 Reasoning 强制观望。使用当前 `execution_state` 重算
2026-07-20 至 2026-07-27 六个缓存日，149 个 Opportunity 名额中有 104 个不可
交易，占 69.8%。

系统还存在以下合同问题：

- `opportunity_pool` 同时承载“值得观察”和“适合执行”两种含义；
- A/B/C 是全评分池相对名次，却被用作进入 Opportunity Pool 的硬条件；
- 数据缺失可通过默认 raw 或中位数替换获得分数；
- 资金流 partial 未覆盖股票会跳过资金绝对地板；
- `Theme Continuity` 实际是召回来源与个股资金的代理，不读取 Theme Ranking；
- 基础策略政策、代码合同描述和盘后学习规则共同使用 Ixx/Rxx 语言，边界不清；
- 旧 Schema 无法准确表达执行候选、可执行但不推荐、确定性不可执行三类结果。

本 ADR 只解决选股与发布合同。本期不建立通用 `run_id`、原子发布、历史缓存隔离或
跨阶段哈希机制。

## 领域边界

系统明确区分三类知识：

### 基础策略政策

人为预先制定并由确定性代码执行，包括：

- Recall Policy；
- Scoreability Policy；
- Scoring Policy；
- Money Flow Policy；
- Trend Policy；
- VWAP Eligibility Policy；
- Execution Policy；
- Data Quality Policy。

基础策略可以包含配置阈值，并在无历史、空规则项目中正常存在。

### 代码合同

Schema、字段所有权、公式版本和发布不变量的说明。代码合同由代码、配置、ADR 和
测试共同维护，不参与规则容量或胜负验证。

### 学习规则

`memory/INTRADAY_RULES.md` 和 `memory/SHARED_RULES.md` 中经过治理的
`EMPIRICAL` 或 `RISK_POLICY`。新系统允许规则表为空。学习规则只能收紧最终建议，
不能修改 Compute 层事实。

## 决策

### 1. 使用执行池和观察池

`opportunity_pool.json` 被 `selection_pools.json` 直接替换：

```text
.cache/intraday/{date}/selection_pools.json
```

新合同只有两个确定性候选池：

| 池 | 定义 |
|----|------|
| `executable_pool` | 数据可评分，且执行状态、资金、趋势、VWAP/I14 等基础资格全部通过的股票。 |
| `observation_pool` | 值得保留证据，但至少一项确定性执行资格不通过的股票。 |

约束：

- `executable_pool` 最多 30 只，不要求填满；
- `observation_pool` 最多 30 只，不要求填满；
- 不可执行股票永远不能用于填充执行池；
- 数据完整但执行池为空是正常成功结果；
- 删除 `opportunity_pool`、`leader_watch`、`premium_candidates` 和
  `early_breakout`；
- 不保留旧 Schema 兼容读取或输出。

### 2. 分离 Scoreability 与 Executability

流水线顺序调整为：

```text
Compute Pool
  → Scoreability Gate
       ├─ 可评分 → Scored Pool → 唯一 rank/rank_tier
       └─ 不可评分 → Unscored Observation
  → Execution Eligibility
       ├─ 通过 → Executable Pool
       └─ 不通过 → Scored Observation
```

Scoreability 只回答“九维 raw 是否可以从真实数据计算”。不得使用缺失默认值或中位数
替换，把不可评分股票伪装成正常评分股票。

以下数据完整股票仍可评分，但不一定可执行：

- 封板；
- 跌破 VWAP；
- 主力资金低于配置门槛；
- Trend raw 低于地板。

以下股票不可评分：

- 九维所需关键报价缺失；
- 个股资金流未覆盖或字段不完整；
- `technicals=no_data` 或评分所需技术字段不完整。

VWAP 不参与九维 raw，因此 VWAP 缺失不阻止评分，但会阻止进入执行池。

### 3. 只保留一套排名

保留：

- `rank`；
- `rank_tier`；
- 等值字段 `tier`，其值仍严格等于 `rank_tier`。

排名在 Scored Pool 中按 `overnight_score` 降序计算：

- A：前 10%；
- B：前 40%；
- C：前 70%；
- D：其余。

`rank_tier` 只表示 Scored Pool 相对位置：

- 不再作为进入执行池的硬条件；
- 不等于 Tradeability；
- 不产生第二套 executable rank；
- 执行池直接按原 `overnight_score`/`rank` 顺序过滤资格后截取最多 30 只。

本期不增加统一最低 `overnight_score`。绝对质量由原始数据地板和执行资格表达。

### 4. 资金流政策

权威配置为：

```text
config/setting.json
market_data.stock_money_flow_min_inflow_yuan
```

同一个配置值同时控制资金流分页停止和执行资格：

```text
main_net_inflow_yuan >= configured minimum
```

状态处理：

| 状态 | 行为 |
|------|------|
| `complete` | 使用真实股票级资金字段和配置门槛。 |
| `threshold_reached` | 未返回股票直接视为低于配置门槛。 |
| `partial` | 未覆盖股票直接视为低于配置门槛，不做 I11 资金中位数替换。 |
| `unavailable` | 流水线中断，不生成最终推荐。 |

资金字段不完整的股票不可评分，只能进入 unscored observation。全池 unavailable
不得用无方差百分位生成中性资金贡献。

### 5. 技术指标政策

- 有完整技术数据时继续使用当前 Trend Quality 公式；
- Trend absolute floor 保持 `raw >= 0.3`；
- 个股 `technicals=no_data` 或关键技术字段不完整时不可评分，只能进入观察池；
- 技术指标整体不可用时流水线中断；
- 不使用 `Trend raw=0.5` 或 `raw=0.2` 代表缺失。

### 6. VWAP 与 I14 政策

I14 已经是 Compute 层的基础代码约束，不依赖学习规则是否为空。本期保留其算法行为，
并将其归类为 `VWAPEligibilityPolicy`。

分流规则：

| 状态 | 池 |
|------|----|
| `price >= VWAP` | 可继续竞争执行池 |
| `i14_exemption=watch` | 只进入观察池 |
| `i14_exemption=cautious_hold` | 可进入执行池，最终方向最高为谨慎持有 |
| 跌破 VWAP 且无 I14 豁免 | 只进入观察池 |
| VWAP 缺失或 `<=0` | 只进入观察池 |

若 Compute Pool 中全部股票 VWAP 无效，流水线中断。

### 7. Execution State 前置并复核

`execution_state` 在 Compute Pool 完成报价和技术补全后，由
`mapping.intraday_contract.execution_state()` 生成。

- 双池构建直接使用该字段；
- mapper base 使用同一纯函数重新计算并比对；
- 存储状态与重算状态不一致时中断；
- LLM 不得创建、修改或覆盖；
- 封板、板块排除和关键报价缺失不能进入执行池。

Scan 和 Execution State 必须调用同一个交易范围解析函数，并读取同一个
`config/trading-scope.json`。Scan 阶段不再维护简化的前缀过滤副本。

### 8. 数据源最低完整性

硬失败条件：

- 全市场快照不是 `complete`；
- 上证指数 `sh000001` 缺失或无有效数值；
- 深证成指 `sz399001` 缺失或无有效数值；
- Scan Pool 少于 `compute_pool_size`；
- 股票资金流整体 unavailable；
- 技术指标整体不可用；
- Theme Ranking 生成失败；
- 全部候选 VWAP 无效；
- Scored Pool 为空；
- selection pools、mapper、annotations 或 strategy 验证失败。

允许降级但不中断：

- 成交额榜接口 unavailable，前提是其它召回形成的 Scan Pool 不少于
  `compute_pool_size`；
- Concept Dashboard unavailable；
- 创业板指、科创50、中证1000等辅助指数单个或全部缺失；
- 个别股票报价、资金、技术或 VWAP 不完整，受影响股票进入观察池或被观察池 Top 30
  截断。

可选接口失败必须写出本轮显式 `status=unavailable` 合同，禁止以正常空数组表达
失败。

本期不建立通用 run manifest、原子发布和旧缓存治理。上述中断只针对本 ADR 明确列出
的必需数据与合同。

### 9. 召回与 QuickScore

本期保持：

- 三路召回顺序；
- QuickScore 公式和权重；
- `source_pool` 单标签语义；
- `compute_pool_size` 默认 120。

只新增每路召回的 `status`、数量和错误摘要。成交额榜 unavailable 时允许继续，但
Scan Pool 不得少于 Compute Pool 目标数量。

以下暂不修改：

- `amount` 进入 QuickScore；
- 多标签 `source_pools`；
- 7%～9% Momentum 档；
- concept leads 第四路召回。

### 10. 评分字段改名与 Theme Shadow

评分版本升级为：

```text
V1.3_SelectionPools
```

`theme_continuity` 直接改名为 `source_capital_proxy`：

- raw 公式不变；
- 权重保持 18%；
- `score_trace` 和权重常量只使用新名称；
- 不输出旧字段别名；
- 历史 JSON 不迁移。

Theme Ranking 本期不进入 `overnight_score`。mapper base 为每只入选股票增加：

```json
{
  "theme_support_shadow": {
    "available": true,
    "primary_theme": "AI算力",
    "member_role": "core",
    "core_heat": 82.4,
    "diffusion_heat": 46.1,
    "theme_rank": 2,
    "membership_weight": 1.0,
    "missing_reason": null
  }
}
```

Shadow：

- 沿用 ADR-0003 的 `primary_theme()` 确定性选择；
- 只用于 mapper、报告和后续验证；
- 不影响 score、rank、floor、池归属或仓位；
- 主题或动态排名不可用时输出 `available=false` 和明确原因，不填中性数值。

### 11. Schema v2

保留稳定文件名，直接升级 Schema：

| 文件 | Schema |
|------|--------|
| `intraday_mapper.base.json` | `intraday_mapper_base.v2` |
| `intraday_mapper.annotations.json` | `intraday_mapper_annotations.v2` |
| `intraday_mapper.json` | `intraday_mapper.v2` |
| `overnight_strategy.json` | `intraday_overnight_strategy.v2` |

mapper 系列使用：

- `executable_stocks`；
- `observation_stocks`。

Annotations 分离为：

- `executable_annotations`：完整 Tradeability、Direction、仓位和 T+1 计划；
- `observation_annotations`：仅
  `observation_summary`、`watch_condition`、`risk_note`。

观察注释禁止输出：

- Direction；
- Tradeability；
- Position Plan；
- Stop Loss；
- T+1 买卖计划；
- 任何可行动仓位。

最终策略提供三个视图：

| 视图 | 来源 |
|------|------|
| `recommendations` | executable stocks 中 Direction 可行动的股票 |
| `eligible_watchlist` | executable stocks 中被 Reasoning 判为观望的股票 |
| `observations` | deterministic observation pool |

### 12. 学习规则权限

学习规则可以：

- 将 executable candidate 从 recommendation 降为 eligible watchlist；
- 降低仓位；
- 收紧止损、止盈或 T+1 条件；
- 增加风险说明。

学习规则不得：

- 把 observation candidate 升级为 executable；
- 修改分数、rank、floor、execution_state 或池归属；
- 修改行情、资金、技术或主题事实；
- 在空规则项目中虚构默认规则。

所有实际应用的学习规则必须进入 `rules_applied`。

## Observation Pool 排序

Observation Pool 是不同失败原因的有限展示视图：

1. 已评分观察股按 `overnight_score` 降序、代码稳定排序；
2. 未评分观察股按 `quick_score` 降序、代码稳定排序；
3. 已评分观察股优先于未评分观察股；
4. 最多保留 30 只；
5. 根级摘要保存截断前各 `observation_reason` 的总数量。

每只观察股包含：

- `observation_reasons`：所有确定性原因；
- `primary_observation_reason`：按固定优先级选出的主原因；
- `score_status=scored|unscored`；
- 可用的原始证据；
- 不包含执行计划。

主原因优先级为：

```text
board_policy
quote_data_missing
sealed_limit_up
money_flow_below_configured_minimum
money_flow_data_missing
technical_data_missing
vwap_data_missing
vwap_below_without_exemption
i14_watch
trend_floor_failed
```

## 明确排除

本 ADR 不包括：

- 通用 fail-fast 重构；
- `run_id`、原子发布、输入输出哈希或旧缓存隔离；
- QuickScore 调参；
- `source_pool` 多标签；
- Theme Ranking 进入生产评分；
- 统一最低 OvernightScore；
- 收益率或胜率上线门槛；
- I10、I14 数值标定；
- learned rule 的新增、升级或退役；
- 旧 JSON 与旧 Schema 兼容。

## 结果

系统将明确区分“有完整证据并且可交易”“有完整证据但不可交易”和“数据不足只能
观察”。Top 30 不再被封板股占位，A/B/C 不再充当执行资格，缺失数据不再通过默认值
获得推荐资格。最终输出可在没有学习规则、没有可执行股票的情况下正常成立，同时
保持评分公式和 QuickScore 行为基本稳定。
