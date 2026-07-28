# Intraday 选股领域术语表

- 版本：1.0
- 日期：2026-07-27
- 关联：[ADR-0004](adr/0004-intraday-selection-pools-contract.md)、[最终开发计划](intraday-stock-selection-final-development-plan.md)

## 核心领域对象

| 术语 | 定义 | 不表示 |
|------|------|--------|
| Scan Pool | 三路召回合并、交易范围过滤后的广域候选集合。 | 最终推荐。 |
| Compute Pool | Scan Pool 按 QuickScore 截取、进入昂贵数据补全的股票集合，默认 120 只。 | 已通过交易资格。 |
| Scoreability | 九维 raw 是否可以从真实、完整的必需数据计算。 | 是否值得买、是否可以成交。 |
| Scored Pool | 通过 Scoreability Gate 并获得 `overnight_score`、`rank`、`rank_tier` 的股票集合。 | 全部可执行。 |
| Executability | 股票是否满足执行状态、资金、趋势、VWAP/I14 等基础资格。 | Reasoning 最终一定推荐。 |
| Executable Pool | Scored Pool 中通过全部确定性执行资格的股票，按原分数最多取 30 只。 | 已经形成仓位。 |
| Observation Pool | 评分完整但不可执行，或因个股数据缺失不可评分、但值得保留证据的股票，最多 30 只。 | 可行动 watchlist。 |
| Recommendation | Executable Pool 中被 Reasoning 赋予可行动 Direction 的股票。 | 所有 executable candidate。 |
| Eligible Watchlist | Executable Pool 中数据和交易资格合格，但 Reasoning 最终决定观望的股票。 | 数据缺失或封板股票。 |
| Observation | Observation Pool 的最终只读解释。 | Direction、仓位或 T+1 交易计划。 |

## 排名与评分

| 术语 | 定义 |
|------|------|
| QuickScore | 召回后用于分配 Compute 资源的粗排分，不是最终隔夜分。 |
| OvernightScore | Scored Pool 内九维百分位加权结果。V1.3 仍使用原公式，仅调整字段名称和评分样本资格。 |
| `rank` | 股票在 Scored Pool 中按 OvernightScore 降序的位置。 |
| `rank_tier` | Scored Pool 相对名次 A/B/C/D，不是绝对质量或 Tradeability。 |
| `tier` | 严格等于 `rank_tier` 的字段；不再参与执行池入选门槛。 |
| `source_capital_proxy` | 原 `theme_continuity`。由 `source_pool` 等级与个股主力净流入 sigmoid 组成，不代表主题热度。 |
| Theme Support Shadow | Theme Ranking 与成员角色形成的只读影子证据，不参与评分或执行。 |
| Absolute Floor | 基于原始数据的最低质量约束，例如资金配置门槛和 Trend raw 门槛。 |

## 政策、合同与规则

| 术语 | 定义 |
|------|------|
| Base Policy / 基础策略政策 | 人为预先设计、由确定性代码执行的召回、评分、质量与执行策略。新系统也存在。 |
| Code Contract / 代码合同 | Schema、字段所有权、版本和不变量说明，由代码与测试验证。 |
| Learned Rule / 学习规则 | 从复盘证据形成并受生命周期治理的 EMPIRICAL 或 RISK_POLICY。新系统可以为空。 |
| Recall Policy | 三路来源、交易范围和 QuickScore 的基础策略。 |
| Scoreability Policy | 决定九维是否可以从真实数据计算。 |
| Scoring Policy | 九维 raw、百分位、权重、Regime 缩放和 rank 规则。 |
| Money Flow Policy | 资金分页停止、最低执行门槛及 complete/partial/unavailable 行为。 |
| Trend Policy | 技术数据完整性、Trend raw 和绝对地板。 |
| VWAP Eligibility Policy | VWAP 与 I14 对执行池/观察池归属的基础代码约束。 |
| Execution Policy | 交易范围、封板、报价完整性和最终可执行状态。 |
| Data Quality Policy | 数据源缺失时中断、显式 unavailable 或个股降级的确定性行为。 |

## 数据质量状态

| 状态 | 定义 |
|------|------|
| `complete` | 目标数据按合同完整获取。 |
| `threshold_reached` | 按排序分页到达配置最低资金门槛后主动停止，不是故障。 |
| `partial` | 获取在完成前中断；本合同将未覆盖股票直接视为低于资金配置门槛。 |
| `unavailable` | 数据源整体不可用。是否中断由该数据源的 Data Quality Policy 决定。 |
| `scored` | 股票通过 Scoreability Gate，具有真实九维 raw 和最终分数。 |
| `unscored` | 股票关键评分数据缺失，不生成默认 raw、分数或 rank。 |

## 执行状态

| 术语 | 定义 |
|------|------|
| `execution_state` | Python 根据交易范围、涨停价、实时报价和封板状态生成的不可覆盖事实。 |
| `eligible` | `execution_state` 层面具备尾盘成交资格；仍需通过资金、趋势和 VWAP 等执行资格。 |
| `sealed_limit_up` | 当前价达到计算涨停价且等于日内最高价，只能观察。 |
| `board_policy` | 股票被统一 `trading-scope.json` 排除。 |
| `quote_data_missing` | 计算执行状态所需的价格、高价或昨收缺失。 |
| `i14_exemption=watch` | VWAP Eligibility Policy 保留观察，但不允许执行。 |
| `i14_exemption=cautious_hold` | VWAP Eligibility Policy 允许进入执行池，但 Direction 最高为谨慎持有。 |

## 文件合同

| 文件 | 角色 |
|------|------|
| `selection_pools.json` | Compute 层双池 canonical 合同，替代 `opportunity_pool.json`。 |
| `intraday_mapper.base.json` | 确定性市场、主题、双池和执行事实。 |
| `intraday_mapper.annotations.json` | LLM 对执行候选和观察候选的分离语义注释。 |
| `intraday_mapper.json` | Base 与 annotations 合并后的 validated canonical contract。 |
| `overnight_strategy.json` | 面向执行与复盘的 recommendations、eligible watchlist、observations。 |
| `overnight_strategy.html` | 人类阅读看板。 |

## 关键不变量

1. Observation 永远不能被学习规则升级为 executable。
2. Executable 不等于 recommendation。
3. `rank_tier` 不等于 Tradeability。
4. 缺失数据不等于中性数据。
5. 空 executable pool 是正常业务结果。
6. 可选接口失败必须显式输出 unavailable，不能伪装成正常空集合。
7. LLM 不能覆盖任何行情、评分、主题、地板、池归属或执行状态。
