---
name: daily-strategy
description: Prepare, reason over, validate, and publish the selected-only daily_strategy.v2 Step 3 contract.
---

# Daily Strategy Step 3

Step 3 是唯一的日策略 Reasoning 层。Python 负责验证、投影、提示、Trade Profile 基线、观察池补全和发布；portfolio-manager 负责最终 regime、选股代码与顺序、Direction、RiskSeverity 应用、评级、规则匹配和执行计划。

## 不可变约束

- 所有 `mapper.strategy_view.json.candidates[]` 必须完整、同序进入 LLM 输入；禁止 top-N 预筛。
- LLM 不读取完整 `mapper.json`、`pool_indicators.json` 或 `news.json`。
- Python 的 `direction_base_hint`、`risk_severity_base_hint`、`profile_base` 仅为 advisory，不是最终决策。
- 最终主列表限制：`strong-sector/neutral <= 10`、`weak <= 7`、`panic <= 5`。
- 最终选股代码和顺序、Direction、评级与 RiskSeverity 应用均归 LLM；Python 不重排合法选择。
- 每个入选股必须写非空 `reasoning.source_basis`，只能使用输入中真实的主题、role tag 与 canonical `news#id`。
- A 股新仓必须是 T+1 条件计划，最早执行时间不得早于 `09:35:05`；保持人工确认，不做自动买入。
- `strategy.json`、`daily_report.html` 是正式产物；`.strategy_llm_input.json`、`strategy.draft.json`、`step3_timing.json` 是非合同工作流产物。
- Step 3 不直接写 `memory/daily/INDEX.md`；盘后 verification 工作流拥有记忆更新。

## 唯一执行序列

先运行：

```bash
uv run --frozen ashare-pilot strategy daily prepare --date YYYY-MM-DD
```

portfolio-manager 的热阶段只读取：

- `predict/YYYY-MM-DD/.strategy_llm_input.json`
- `.agents/skills/daily-strategy/references/strategy-selection-rubric.md`
- `.agents/skills/daily-strategy/references/strategy-output-contract.md`
- `memory/RULES.md`（存在时）
- `memory/SHARED_RULES.md`（存在时）

零历史项目中缺少这两个文件表示尚无已学习规则；继续基于当日合同推理，不得预先生成或
虚构历史规则。

按 rubric 扫描全部候选，只对最终入选股做深推理，并写：

- `predict/YYYY-MM-DD/strategy.draft.json`

然后运行：

```bash
uv run --frozen ashare-pilot strategy daily finalize --date YYYY-MM-DD
```

编排器能够测得 portfolio-manager 墙钟时间时必须传入：

```bash
uv run --frozen ashare-pilot strategy daily finalize \
  --date YYYY-MM-DD --llm-duration <measured_seconds>
```

未传时仅记录 `mtime_estimate`，该次 `step3_timing.json` 不具备 Gate D 统计资格。

finalize 校验草稿的输入哈希、候选和证据归属，按最终 regime 重算 Trade Profile，应用带理由的白名单 overrides，补齐全部未选候选观察行，验证 `daily_strategy.v2`，再发布 JSON 与 HTML。

## 失败与重试

- prepare 失败：修复源合同或重新执行 Step 2；不得手改紧凑输入绕过覆盖校验。
- 草稿校验失败：portfolio-manager 只修正 `strategy.draft.json`，重新运行 finalize；修正会重录 `strategy_llm` 指纹和 retry count。
- 哈希不匹配：重新读取当前 `.strategy_llm_input.json` 并完整重写草稿，不得沿用旧草稿。
- profile override 非白名单、无理由或与仓位/T+1矛盾：删除或修正 override；finalize 不静默修复。
- `step3_timing.json` 写入失败仅告警，不得使策略合同失效。

## 上线门槛

- Gate A：真实冻结投影保持候选、主题、分数、Pattern、风险和证据等价。
- Gate B：真实冻结 draft 确定性回放与 expected strategy slice 完全一致。
- Gate C：validator、观察池覆盖和 HTML 渲染全部通过。
- 2026-07-09 是缺少 canonical `news.json` 的 legacy 超大池样本，只用于候选覆盖回归，不伪造证据。
- Gate D 只接受 `gate_d_eligible=true` 的真实运行；累计至少五次后才能报告 P95 或宣称达到 4–6 分钟目标。

## 回滚

若新链路在 live shadow 中出现实质决策漂移，保留已发布正式合同，停止工作流切换并恢复上一版 Step 3 指令；不要重写历史 `strategy.json`。冻结回放使用 `uv run --frozen ashare-pilot strategy daily compare-shadow --mode frozen`；live shadow 使用 `--mode live --report-only`。在五次 Gate D 样本完成前保持此回滚路径。
