# 开盘操作确认

## 1. 职责

`intraday-operation-guide` 将当天 `daily_strategy.v3` 条件计划与开盘后的真实行情
合并，生成 A/B/C/D 人工操作分类。它不是新的选股流程，也不下单。

必需输入：

- `predict/{date}/strategy.json`；
- `predict/{date}/mapper.json`。

规则输入为 `memory/RULES.md` 和 `memory/SHARED_RULES.md`，只能用于收紧分类或
补充谨慎说明。

## 2. 状态感知入口

调用者始终运行同一个入口：

```bash
uv run --frozen ashare-pilot operations guide run --date YYYY-MM-DD
```

Runner 根据上海市场时间和已验证的 immutable snapshots 自动决定模式，不要求用户
指定“首次确认”“二次确认”或“再次确认”。

## 3. 时间与状态

| 状态 | 行为 |
|---|---|
| 09:35:10 前启动 | 同一进程等待 09:35，完成后自动等待并执行 09:40 |
| 有有效 09:35，且 09:40 已到 | 用 09:35 作为 predecessor 执行 `SECOND_CONFIRMATION` |
| 首次启动在 09:40:10–09:45:09 | 先做迟到初次确认，再于 09:45 跟进 |
| 已有完整有效确认链 | 使用最新 eligible snapshot 做 `RECHECK` |
| 开盘窗口后仍无有效链 | `LATE_OBSERVE_ONLY` |

Runner 会等待期望的完整 5 分钟 K 线真正发布，不能把正在形成的 bar 当成已完成 bar。

## 4. 迟到策略

| 首个可用快照 | 上限 |
|---|---|
| 09:35 | 正常首次确认 |
| 09:40 且无 predecessor | `WAIT_SECOND_CONFIRMATION`，最高 B，仓位为零 |
| 09:45 且有 09:40 predecessor | 可进行合法 B→A |
| 09:45 以后且无 predecessor | `OBSERVE_ONLY`，最高 C/D |

迟到属于 delivery confirmation，不等同于市场本身走弱。市场确认和交付确认必须
分别保存在合同中。

## 5. Snapshot 构建

Snapshot 读取策略中的股票和执行约束、mapper 中的 MA/ATR/High20，批量抓取：

- 上证、深证、科创等市场指数；
- 策略股票实时行情；
- 当日 5 分钟 K 线。

确定性计算包括：

- `regime_live`、`regime_confirmed` 和 `global_action`；
- 固定首根 09:30–09:35 bar；
- 最新已完成 bar；
- MA、ATR、VWAP、量价、冲高回落和数据警告；
- 主题确认、状态迁移、分类上限；
- 总持仓数、主题数和相关标的数等组合限制。

Snapshot schema 为 `intraday_operation_snapshot.v3`。

## 6. Decision 与 A/B/C/D

Decision 从已验证 snapshot 确定性生成，schema 为
`intraday_operation_decision.v2`。

| 类别 | 含义 | 人工动作 |
|---|---|---|
| A | 当前满足参与条件 | 无个人持仓冲突时可人工参与 |
| B | 等待确认 | 触发条件前不买 |
| C | 只观察 | 可在后续 recheck 恢复至 B，不能直接跳 A |
| D | 放弃/回避 | 当日不参与 |

`global_action` 是组合级硬闸：

| 值 | 约束 |
|---|---|
| `NORMAL` | 机械上允许 A |
| `SELECTIVE` | 只有个股确认通过才可 A，`STANDARD` 降为 `LIGHT` |
| `WAIT` | 全部最高 B |
| `NO_NEW_BUY` | 全部最高 C/D |

LLM 或人类说明可以保持或降级决定，不能突破
`decision_guardrails.max_allowed_class`。

## 7. Immutable 链与原子权威

每次正式运行保存 timestamp/slot 命名的 immutable snapshot、decision 和 HTML。
`lineage` 记录 predecessor、chain root 和 SHA-256。已有 `0935`、`0940` 文件不得
覆盖；重复运行写新的时间戳产物。

`operation_run.latest.json` 是匹配三件套的原子权威，包含：

- snapshot 路径和 hash；
- decision 路径和 hash；
- HTML 路径和 hash。

`operation_snapshot.latest.json`、`operation_decision.latest.json` 和无版本 HTML
只是便利投影，不能单独证明跨文件一致性。

## 8. 验证与渲染

```bash
uv run --frozen ashare-pilot operations snapshot validate \
  operation/YYYY-MM-DD/operation_snapshot.latest.json
uv run --frozen ashare-pilot operations decision validate \
  operation/YYYY-MM-DD/operation_decision.latest.json
uv run --frozen ashare-pilot operations guide render \
  --date YYYY-MM-DD \
  --decision operation/YYYY-MM-DD/operation_decision.latest.json \
  --snapshot operation/YYYY-MM-DD/operation_snapshot.latest.json \
  --output operation/YYYY-MM-DD/operation_guide.html
```

Live 校验必须严格检查引用和 hash；`--portable` 只用于 predecessor 已被有意移除的
迁移归档。
