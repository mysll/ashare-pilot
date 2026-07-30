# ADR-0008：Intraday 影子规则验证合同

- 状态：Accepted
- 日期：2026-07-30
- 范围：14:30 历史截面规则的独立、前瞻、非推荐验证
- 关联：[ADR-0004 双池合同](0004-intraday-selection-pools-contract.md)

## 背景

项目已经积累约一个月的 14:30 Compute Pool 快照，可以研究哪些当时可见特征与
T+1 表现有关。但若直接从“次日上涨股票”反推条件、再把同一时期当作验证集，会
产生幸存者偏差和选择污染。现有 `overnight_strategy.json` 也不应读取尚未经过
前瞻验证的研究规则。

## 决策

新增 `intraday_shadow_rule_validation.v1`，默认发布到：

```text
research/intraday-shadow/{as_of_date}/shadow_rule_validation.json
```

合同只有研究和验证语义：

- `mode` 固定为 `VALIDATION_ONLY`；
- 禁止 Direction、Tradeability、RiskSeverity、仓位、买卖或订单字段；
- `strategy_consumption_allowed=false`；
- `formal_rule_update_allowed=false`；
- `recommendation_generation_allowed=false`；
- `automatic_promotion_allowed=false`。

任何 shadow 构建失败均为非阻断事件，不影响 mapper、正式隔夜策略或人类板报。

## T+1 配对与标签

- T 日入场基准为 `compute_pool_enriched.price` 的 14:30 快照；
- 只允许配对日历定义的精确下一交易日；
- 缺少精确 T+1 缓存时标记无效，禁止跳到下一个可用缓存日；
- T+1 开盘、截至缓存时点最高价和标记价取自下一交易日
  `all_stocks_cache.json`；
- 标记价不是正式收盘价，最高价命中也不代表真实成交。

当前首版规则的主标签是“T+1 截至 14:30 的最高价相对 T 日 14:30 快照价
达到 +1%”。开盘收益和 T+1 14:30 标记收益为辅助标签。

## 历史校准与前瞻证据

规则版本必须声明 `frozen_on`：

- `source_date <= frozen_on` 只算 `calibration`，不得宣称样本外有效；
- `source_date > frozen_on` 才算 `prospective`；
- 修改任一条件、标签或门槛必须增加规则版本，并重置前瞻证据；
- 每个 dated contract 是追加快照，不应改写成新的历史结论。

即使前瞻门槛全部满足，合同也只能进入 `review_ready`，不得自动进入
`memory/INTRADAY_RULES.md`。正式规则仍受 `RULE_GOVERNANCE.md` 管理。

## 持续运行

Intraday compute/scoring 成功后，自动化流水线非阻断地执行：

```bash
uv run --frozen ashare-pilot review intraday shadow build \
  --as-of YYYY-MM-DD --replace
```

独立校验：

```bash
uv run --frozen ashare-pilot review intraday shadow validate \
  research/intraday-shadow/YYYY-MM-DD/shadow_rule_validation.json
```

当前规则配置位于 `config/intraday-shadow-rules.json`。至少每新增 5 个前瞻市场日
复核一次；达到配置的最小前瞻日数后才评价门槛。
