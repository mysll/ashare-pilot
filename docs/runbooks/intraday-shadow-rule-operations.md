# 尾盘影子规则后续操作手册

> 适用合同：`intraday_shadow_rule_validation.v1`
> 当前规则：`ISR-S001 v1`
> 当前状态：仅验证，不产生推荐，不影响正式策略

## 一、平时需要做什么

正常情况下不需要每天手工操作。

只要原有的14:30尾盘分析流水线正常运行，系统就会在正式 Compute/Score 完成后，
自动刷新当天的影子规则合同：

```text
research/intraday-shadow/{日期}/shadow_rule_validation.json
```

影子任务是非阻断任务。即使它执行失败，也不会阻止正式 mapper、
`overnight_strategy.json` 或尾盘报告发布。

日常只需确保：

1. 交易日的14:30尾盘流水线正常运行；
2. 不修改当前 `ISR-S001 v1` 的条件和标签；
3. 不根据影子合同里的股票进行交易；
4. 不手工把影子结论写入 `memory/INTRADAY_RULES.md`。

## 二、影子合同中的股票应该如何理解

合同中的 `pending_matches` 只是“规则在当日14:30命中的待验证样本”。

它们不是：

- 买入推荐；
- 正式观察池；
- 仓位建议；
- 第二天必涨预测；
- 允许下单的交易信号。

下一交易日产生完整14:30缓存后，系统才会把待验证样本转为
`verified_matches`，并记录：

- T+1开盘收益；
- T+1截至14:30最高收益；
- T+1的14:30标记收益；
- 是否达到“盘中冲高1%”主验证目标。

`T+1 high` 命中只代表盘中出现过价格机会，不代表真实成交，也不代表持有到
14:30可以盈利。

## 三、手动补跑

### 1. 补跑完整尾盘流水线

当日14:30任务没有运行或运行失败时：

```bash
uv run --frozen ashare-pilot automation intraday run --date YYYY-MM-DD
```

运行完成后，确认以下文件存在：

```text
.cache/intraday/YYYY-MM-DD/compute_pool_enriched.json
.cache/intraday/YYYY-MM-DD/all_stocks_cache.json
research/intraday-shadow/YYYY-MM-DD/shadow_rule_validation.json
```

### 2. 只补跑影子合同

如果正式尾盘缓存已经完整，只是影子合同缺失：

```bash
uv run --frozen ashare-pilot review intraday shadow build \
  --as-of YYYY-MM-DD --replace
```

### 3. 校验合同

```bash
uv run --frozen ashare-pilot review intraday shadow validate \
  research/intraday-shadow/YYYY-MM-DD/shadow_rule_validation.json
```

正常结果包含：

```json
{"valid": true}
```

## 四、什么时候复查

### 每新增5个前瞻触发日

这里的“5个触发日”不是简单经过5个交易日，而是 `ISR-S001` 实际筛出至少一只股票的
5个独立交易日。

达到后进行一次阶段复查。可以直接提出：

```text
复查影子规则 ISR-S001 的最新表现
```

阶段复查主要检查：

- 前瞻触发交易日数；
- 股票级冲高1%命中率；
- 市场日等权命中率；
- 相对同池基线的命中率提升；
- T+1开盘收益；
- 扣除假设成本后的T+1 14:30标记收益；
- 是否被单日大量样本或少数异常股票主导；
- 强市、弱市和轮动市下是否表现一致。

阶段复查不修改规则，只判断是否继续收集。

### 累计至少10个前瞻触发日

达到10个独立前瞻触发日后，进行第一次完整评审。

当前门槛：

| 指标 | 门槛 |
|------|------|
| 前瞻触发交易日 | ≥10日 |
| 股票级主标签命中率 | ≥75% |
| 相对同池基线命中率提升 | ≥10个百分点 |
| 扣成本后的T+1标记平均收益 | ≥0% |

合同状态的含义：

| 状态 | 处理 |
|------|------|
| `awaiting_prospective_evidence` | 样本不足，继续收集 |
| `continue_observation` | 样本达到要求但门槛未全部通过；继续观察或设计新版本 |
| `review_ready` | 门槛全部通过，可进行人工研究评审，但仍不能自动转为正式策略 |

## 五、什么时候可以修改规则

在首轮10个前瞻触发日完成前，不修改：

- 涨幅区间；
- VWAP偏离区间；
- 日内位置门槛；
- 换手率门槛；
- T+1主标签；
- 成本假设；
- 验证通过门槛。

如果修改任何一项：

1. 将规则版本从 `v1` 升级为 `v2`；
2. 写清修改原因和旧版结果；
3. 更新 `frozen_on`；
4. 新版本的前瞻证据从零开始；
5. 旧版合同保留，不改写历史。

规则配置文件：

```text
config/intraday-shadow-rules.json
```

不要为了让历史结果更漂亮而反复调整阈值。历史数据只能用于提出下一版假设，
不能同时充当新版本的样本外验证。

## 六、什么时候可以考虑进入正式规则

`review_ready` 不等于可以实盘。

只有完成以下步骤后，才可以讨论是否进入正式规则治理：

1. 前瞻门槛全部通过；
2. 检查收益没有被少数交易日或个股主导；
3. 检查T+1冲高是否存在现实可执行的退出窗口；
4. 如需验证09:45或其他退出时间，补充分钟行情；
5. 读取 `memory/RULE_GOVERNANCE.md`；
6. 完成与现有 Ixx/Rxx 规则的碰撞检查；
7. 由人工明确批准进入候选或观察生命周期。

在人工批准前，禁止：

- 修改正式隔夜评分；
- 修改 mapper；
- 修改 `overnight_strategy.json` 生成逻辑；
- 把影子股票加入正式推荐；
- 把影子证据计入正式规则胜率。

## 七、异常处理

### 合同没有生成

依次检查：

1. 当日 `.cache/intraday/{date}/compute_pool_enriched.json` 是否存在；
2. 当日 `market_breadth.json` 是否存在；
3. 正式尾盘 Compute/Score 是否成功；
4. 手动执行影子构建命令；
5. 再执行合同校验命令。

### 某个历史日被排除

查看合同中的：

```text
dataset.excluded_pairs
```

常见原因：

- `exact_t_plus_1_cache_missing`：缺少精确下一交易日缓存；
- `t_plus_1_market_cache_too_small`：下一交易日全市场缓存不完整；
- `t_plus_1_match_ratio_too_low`：股票匹配覆盖不足；
- `compute_pool_too_small`：T日候选池不完整；
- `market_up_ratio_missing`：市场广度缺失。

被排除的交易日不能手工改成成功样本，也不能跳到更晚日期替代T+1。

### 校验失败

不要手工删除字段来强行通过。保留错误输出并检查：

- Schema版本；
- `mode` 是否仍为 `VALIDATION_ONLY`；
- 是否意外出现推荐、方向、仓位或订单字段；
- `primary_success` 是否与T+1最高收益一致；
- 是否存在同日同股票重复证据。

## 八、建议的固定工作节奏

| 时间 | 操作 |
|------|------|
| 每个交易日14:30后 | 正常运行尾盘流水线，无需查看影子股票 |
| 影子任务异常时 | 手动补跑并校验合同 |
| 每新增5个触发日 | 做一次阶段复查，不改规则 |
| 累计10个触发日 | 做第一次完整评审 |
| 门槛未通过 | 继续观察，或冻结旧版后设计v2 |
| 状态为 `review_ready` | 启动人工研究评审，仍不自动进入正式策略 |

## 九、相关文件

| 文件 | 用途 |
|------|------|
| `config/intraday-shadow-rules.json` | 当前影子规则、标签和门槛 |
| `resources/schemas/intraday_shadow_rule_validation.v1.schema.json` | 合约Schema |
| `research/intraday-shadow/{date}/shadow_rule_validation.json` | 每日验证快照 |
| `docs/adr/0008-intraday-shadow-rule-validation-contract.md` | 架构与隔离边界 |
| `memory/RULE_GOVERNANCE.md` | 未来若进入正式规则时的治理要求 |
