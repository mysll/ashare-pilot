# 当前 Intraday 双池选股、评分与发布流程

- 版本：2.0
- 日期：2026-07-27
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
业务结果，最终发布零仓位与观察视图。

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
                       intraday_mapper.v2
                                      ↓
        recommendations / eligible_watchlist / observations
                                      ↓
             overnight_strategy.v2 + validated HTML
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

执行候选按原分数/代码排序取最多 30，不按 tier 过滤、不用观察股填充。观察集合先放
scored observations（按分数/代码），再放 unscored observations（按
QuickScore/代码），截取前 30；原因统计基于截断前全集。

## 8. Theme Support Shadow

Mapper base 从同一 `theme_ranking.json` 附加：

- primary theme、member role、membership weight；
- core heat、diffusion heat、theme rank；
- 或明确 `available=false` 与缺失原因。

Shadow 不进入评分、floor、rank、池归属或仓位，也不得被复制到 annotations。

## 9. Reasoning 与发布

`intraday_mapper.annotations.v2` 分为：

- `executable_annotations`：可写 Direction、Tradeability、仓位、T+1 计划；
- `observation_annotations`：只写观察摘要、复核条件、风险说明。

两个数组必须精确覆盖 base 对应池且互斥。Learned rules 只能把 executable
降级为观望，不能把 observation 升级为 executable。

最终投影：

```text
executable + actionable Direction → recommendations
executable + non-actionable       → eligible_watchlist
observation pool                  → observations
```

观察视图不包含 Direction、Tradeability、仓位、止损或 T+1 执行计划。HTML 只有在
JSON validator 通过后生成，并分区展示三类视图、数据质量和 Theme Shadow。

## 10. 当前命令

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
