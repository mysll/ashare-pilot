# 规则治理

本文只定义未来规则如何从真实复盘中产生，不包含任何预置交易策略。

## 1. 分类

| 类型 | 含义 | 是否属于经验策略 |
|---|---|:---:|
| `CONTRACT` | 数据字段、接口和计算所有权 | 否 |
| `RISK_POLICY` | 风险边界、仓位上限和不可交易条件 | 是 |
| `EMPIRICAL` | 对未来结果的条件预测 | 是 |
| `REFERENCE` | 指向其他文件中的唯一规则正文 | 否 |
| `RETIRED` | 已退出执行的历史规则摘要 | 否 |

## 2. 从零开始

- 初始化时不存在 `RULES.md`、`INTRADAY_RULES.md` 和 `SHARED_RULES.md`。
- 没有真实复盘证据时不得创建策略规则。
- 第一次出现的模式只能记录为候选，并明确证据日期和待验证条件。
- 同一交易日多只股票属于同一个市场日证据，不能重复计数升级规则。

## 3. 生命周期

| 状态 | 含义 | 是否执行 |
|---|---|:---:|
| 候选 | 单日或证据不足的观察 | 否 |
| 观察中 | 已预注册并等待独立未来样本 | 受规则自身约束 |
| 有效 | 达到预注册证据门槛 | 是 |
| 休眠 | 当前缺少适用条件 | 否 |
| 待退役 | 连续失败，等待审查 | 否 |
| 已退役 | 被替代或确认失效 | 否 |

候选进入观察中前必须记录：触发条件、排除条件、适用市场状态、预测期限、成功/失败/中性
标准、对照动作、规则动作、最大风险和初始证据引用。

## 4. 证据口径

每次验证至少区分：

```text
rule_id / branch_id
date
eligible
triggered
regime_at_decision
symbols
prediction_horizon
baseline_action
rule_action
outcome              # positive / negative / neutral / invalid
pnl_or_avoided_loss
opportunity_cost
evidence_ref
notes
```

- 条件未满足记为 `not_triggered`，不得计入成功率。
- 数据缺失或口径错误记为 `invalid`。
- 中性结果单独统计，不得算作正向。
- 详细证据留在 verification，规则文件只保留摘要和回链。

## 5. 执行优先级

1. 数据质量与交易可行性。
2. 硬风控和退出。
3. 市场状态门控。
4. 标的资格与主题暴露。
5. 入场、仓位和止损参数。
6. 评分与排序偏好。

同层冲突时优先采用证据更充分且风险更低的动作；仍无法决定时输出
`NO_TRADE_CONFLICT`，不得临时发明豁免。

## 6. 文件归属

- Morning 候选和规则：`memory/RULES.md`
- Intraday/T+1 候选和规则：`memory/INTRADAY_RULES.md`
- 跨时段候选和规则：`memory/SHARED_RULES.md`
- Morning 证据：`memory/daily/{date}/verification.md`
- Intraday 证据：`memory/intraday/{date}/intraday_verification.md`

规则文件首次创建后应包含“可执行规则族”“候选规则（不执行、不计容量）”和退役审计区，
并链接回本文件。规则编号必须稳定且不能在多个文件中重复定义 canonical 正文。
