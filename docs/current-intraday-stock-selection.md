# 当前 Intraday 双池选股、评分与发布流程

- 版本：3.0
- 更新日期：2026-07-28
- 状态：Current
- 权威决策：[ADR-0004](adr/0004-intraday-selection-pools-contract.md)
- 术语：[Intraday 选股领域术语表](intraday-stock-selection-glossary.md)

## 1. 当前合同

14:30 流水线使用确定性的执行池与观察池：

```text
executable_pool
  Scoreability 通过，且交易范围、封板、资金、趋势、VWAP/I14 全部合格

observation_pool
  数据完整但至少一项执行资格失败，或关键评分数据缺失而不可评分
```

`selection_pools.json` 是 Compute 层唯一候选合同。A/B/C/D 是 Scored Pool
内唯一一套相对排名，不决定池归属，也不等于 Tradeability。没有合适执行候选是正常
业务结果，最终发布 `risk_posture=zero` 与观察视图。

当前系统严格区分三类约束：

- Recall、Scoreability、Scoring、Money Flow、Trend、VWAP/I14、Execution 和
  Data Quality 是确定性基础策略政策，在空规则项目中仍然生效；
- Schema、字段所有权、公式版本与 validator 是代码合同；
- `memory/INTRADAY_RULES.md` 与 `memory/SHARED_RULES.md` 是经过治理的学习规则，
  只能收紧最终建议，不能修改 Compute 层事实或确定性池归属。

旧 `opportunity_pool`、`leader_watch`、`premium_candidates` 和
`early_breakout` 已删除，不再兼容读取或输出旧 Schema。

## 2. 数据流

```text
完整全市场快照
  ├─ 市场宽度
  ├─ 必需指数 + 辅助指数质量
  ├─ Concept Dashboard（允许 unavailable）
  └─ 三路召回
       ├─ 涨停池
       ├─ 成交额榜（允许 unavailable）
       └─ 2%～9% 涨幅池
             ↓ 统一 trading-scope
          Scan Pool（不得少于 Compute 目标）
             ↓ QuickScore，默认 Top 120
          Compute Pool
             ↓ 行情 / VWAP / 股票资金流 / 技术指标
             ↓ execution_state
             ↓ Theme Ranking v2
          Scoreability Gate
             ├─ 完整 → Scored Pool → V1.3 九维 → 唯一 rank
             │                            ↓ Executability
             │                  executable / scored observation
             └─ 缺失 → unscored observation
                                      ↓
                          selection_pools.json
                                      ↓
                      intraday_mapper.base.v2
                                      ↓
                  两个精确覆盖 annotation 数组
                                      ↓
                       intraday_mapper.v3
                                      ↓
        recommendations / eligible_watchlist / observations
                                      ↓
             overnight_strategy.v3 + validated HTML
```

## 3. 召回与 QuickScore

三路按顺序去重，`source_pool` 保留第一次命中：

| 来源 | 上限/条件 | 标签 |
|---|---|---|
| 涨停池 | Top 100 | `limit_up` |
| 成交额榜 | Top 200 | `turnover` |
| 涨幅池 | Top 500 中 2%～9% | `gain_range` |

Scan 与 `execution_state` 均调用
`ashare_pilot.market_data.trading_scope`，使用 exact override、最长前缀和
`config/trading-scope.json`。QuickScore 公式及三路顺序保持不变，只用于 Compute
资源粗排，不是隔夜推荐分。

每路保存 `status/count/error`。成交额榜 unavailable 时，若其它两路经 scope
过滤后仍达到 Compute 目标可继续；否则命令返回非零。

## 4. 数据质量

硬停止：

- 全市场快照不是 `complete`；
- `sh000001` 或 `sz399001` 缺失、价格或涨幅非有限数值；
- Scan Pool 少于 Compute 目标；
- 股票资金流整体 unavailable 或没有任何有效目标股票；
- 技术指标有效股票数为零；
- Theme Ranking v2 构建失败；
- 全部候选 VWAP 无效；
- Scored Pool 为空；
- 任一双池、Mapper、annotations 或 strategy validator 失败。

允许降级：

- 成交额榜 unavailable；
- Concept Dashboard unavailable；
- 辅助指数缺失；
- 个股报价、资金、技术或 VWAP 缺失。

允许降级的接口必须写显式 unavailable/partial 合同。个股数据缺失只影响该股票，不
会通过默认 raw 或中位数替换获得分数。

股票资金流使用以下确定性语义：

| 状态 | 处理 |
|---|---|
| `complete` | 使用真实股票级资金字段，并应用配置门槛。 |
| `threshold_reached` | 未返回股票视为低于配置门槛。 |
| `partial` | 未覆盖股票视为低于配置门槛；不做资金中位数替换。 |
| `unavailable` | 流水线中断，不生成最终推荐。 |

资金字段不完整的个股不可评分。技术数据遵循相同的 fail-closed 原则：完整数据继续
计算 Trend Quality；`technicals=no_data` 或评分必需技术字段不完整的个股不可
评分；技术指标整体不可用时中断。缺失技术数据不得用 `Trend raw=0.5`、`0.2`
或其它默认值代替。

VWAP 不属于九维评分输入，但属于执行资格。个别股票 VWAP 缺失或无效时仍可评分、
只能观察；全部候选 VWAP 无效时中断。

## 5. Scoreability

`assess_scoreability()` 至少要求：

- 评分必需的价格、高低价、昨收为有限数值且区间不矛盾；
- 股票资金 `available=true`；
- `main_net_inflow_yuan`、main/super-large/large/medium/small 完整且一致；
- MA5/MA10/MA20、Bollinger zone、MA alignment、above MA5 完整；
- QuickScore、涨幅、换手率、量比和召回来源可解析。

未通过者为 `score_status=unscored`，只进入观察集合，且没有
`overnight_score/rank/rank_tier/tier`。

VWAP 不参与九维 raw，因此 VWAP 缺失仍可评分，但不能执行。

## 6. V1.3 九维评分

| 维度 | 权重 |
|---|---:|
| `source_capital_proxy` | 18% |
| capital continuity | 18% |
| tail strength | 14% |
| position advantage | 9% |
| risk penalty | -10% |
| intensity | 9% |
| conviction | 9% |
| consistency | 5% |
| trend quality | 8% |

`source_capital_proxy` 的 raw 保持原公式：

```text
source_pool base × 0.7
  + sigmoid(main_net_inflow, center=1亿, steepness=1.5) × 0.3
```

它是召回来源与个股资金代理，不是主题热度。V1.3 不执行缺失字段中位数替换。
合同中的完整评分版本名为 `V1.3_SelectionPools`；旧
`theme_continuity` 字段不再输出，历史 JSON 不迁移。

Scored Pool 按 `overnight_score DESC, code ASC` 生成唯一 rank：
A=前10%、B=前40%、C=前70%、D=其余，且 `tier == rank_tier`。

## 7. 执行资格与双池

`assess_execution_eligibility()` 要求：

- `score_status=scored`；
- `execution_state.eligible=true`；
- `main_net_inflow_yuan >= config`；
- Trend raw `>=0.3`；
- VWAP 有效；
- 价格在 VWAP 上，或 I14 为 `cautious_hold`；
- I14 不是 `watch`。

资金门槛读取 `config/setting.json`，当前为 500 万元。比较始终使用人民币数值字段。

`execution_state` 在 Compute Pool 完成报价和技术补全后，由
`mapping.intraday_contract.execution_state()` 生成。双池构建直接使用该字段，
mapper base 再调用同一纯函数复算；存储值与复算值不一致时中断。该字段归确定性代码
所有，LLM 不得创建、修改或覆盖。

VWAP/I14 分流规则：

| 状态 | 结果 |
|---|---|
| `price >= VWAP` | 可继续竞争执行池。 |
| `i14_exemption=watch` | 只进入观察池。 |
| `i14_exemption=cautious_hold` | 可进入执行池，最终方向最高为谨慎持有。 |
| 跌破 VWAP 且无 I14 豁免 | 只进入观察池。 |
| VWAP 缺失或 `<=0` | 只进入观察池。 |

执行候选按原分数/代码排序取最多 30，不按 tier 过滤、不用观察股填充。观察集合先放
scored observations（按分数/代码），再放 unscored observations（按
QuickScore/代码），截取前 30；原因统计基于截断前全集。

每只观察股包含全部 `observation_reasons`、固定优先级选出的
`primary_observation_reason`、`score_status` 和可用原始证据。主原因优先级为：

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

## 8. Theme Support Shadow

Mapper base 从同一 `theme_ranking.json` 附加：

- primary theme、member role、membership weight；
- core heat、diffusion heat、theme rank；
- 或明确 `available=false` 与缺失原因。

Shadow 不进入评分、floor、rank、池归属或执行角色，也不得被复制到 annotations。

## 9. Reasoning 与发布

`intraday_mapper.annotations.v3` 分为：

- `executable_annotations`：显式写 Direction、Tradeability、
  `execution_role`、`execution_condition` 与 T+1 计划；
- `observation_annotations`：只写观察摘要、复核条件、风险说明。

两个数组必须精确覆盖 base 对应池且互斥。精确覆盖只表示每只股票均已完成判断，
不表示全部推荐。外置规则由 LLM 以自然语言应用；Python 不解析规则语义，也不能把
observation 升级为 executable。

稳定文件名直接写 V3，不提供 V1/V2 生产兼容层：

| 文件 | Schema |
|---|---|
| `intraday_mapper.base.json` | `intraday_mapper_base.v2` |
| `intraday_mapper.annotations.json` | `intraday_mapper_annotations.v3` |
| `intraday_mapper.json` | `intraday_mapper.v3` |
| `overnight_strategy.json` | `intraday_overnight_strategy.v3` |

最终投影：

```text
executable + primary + actionable Direction       → recommendations
executable + alternative/watch + Direction=观望   → eligible_watchlist
observation pool                                  → observations
```

Observation 视图不包含 Direction、Tradeability、执行角色、止损或 T+1 执行计划。HTML 只有在
JSON validator 通过后生成，并分区展示三类视图、数据质量和 Theme Shadow。

LLM 完成逐股判断后必须横向比较，赋予 `primary|alternative|watch`。候选规则不得
影响 Direction、execution role 或 T+1 计划；实际应用的正式规则进入
`rules_applied`。策略只输出定性的 `risk_posture`，不得输出个股或总仓位百分比、
金额或手数。

## 10. 发布不变量

- `executable_pool` 与 `observation_pool` 互斥，各自最多 30 只且允许为空；
- 执行池所有股票必须已评分并通过全部确定性执行资格；
- 不可执行股票不得用于填满执行池；
- `rank` 只在完整 Scored Pool 中生成，池过滤后不重新排名；
- annotations 必须精确覆盖 base 的两个池；
- recommendations 精确等于所有 primary，eligible watchlist 精确等于所有
  alternative/watch；
- `risk_posture=zero`、没有 primary、recommendations 为空三者等价；
- observation 注释和最终视图不得包含任何可行动交易字段；
- selection pools、mapper、annotations、strategy 任一验证失败均禁止发布；
- 数据完整但执行池为空属于成功业务结果，输出零 recommendations 和
  `risk_posture=zero`。

## 11. 当前命令

```bash
uv run --frozen ashare-pilot automation intraday run \
  --date YYYY-MM-DD \
  --compute-pool-size 120 \
  --executable-size 30 \
  --observation-size 30

uv run --frozen ashare-pilot strategy overnight validate-selection --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday build-mapper-base --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday validate-annotations --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday build-mapper --date YYYY-MM-DD
uv run --frozen ashare-pilot mapping intraday validate-mapper --date YYYY-MM-DD
uv run --frozen ashare-pilot strategy overnight build --date YYYY-MM-DD
uv run --frozen ashare-pilot strategy overnight validate --date YYYY-MM-DD
uv run --frozen ashare-pilot strategy overnight render-report --date YYYY-MM-DD
```

## 12. 本期边界

当前合同保留三路召回顺序、QuickScore 公式与权重、`source_pool` 单标签语义和默认
Compute Top 120。本期不包含：

- 通用 `run_id`、原子发布、输入输出哈希或旧缓存隔离；
- QuickScore 调参、`source_pool` 多标签或 concept leads 第四路召回；
- Theme Ranking 进入生产评分；
- 统一最低 `overnight_score`；
- I10/I14 数值标定、收益率/胜率上线门槛；
- learned rule 的新增、升级或退役；
- 旧 JSON 数据迁移或旧 Schema 兼容。
