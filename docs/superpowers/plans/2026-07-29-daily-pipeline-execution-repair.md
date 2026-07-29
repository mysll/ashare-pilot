# 早盘流水线执行纠偏与耗时治理方案

**日期：** 2026-07-29
**状态：** 设计已确认，待实施
**范围：** `daily-market-analysis` Step 2 / Step 3 编排、热阶段输入、
语义合同、失败重试与耗时观测
**关联记录：** `docs/time.md`

本方案是对以下既有性能方案的真实运行纠偏，不推翻已经落地的
Compute → Perception → Reasoning、紧凑输入和确定性组装架构：

- `docs/superpowers/plans/2026-07-14-daily-step2-performance-final.md`
- `docs/superpowers/plans/2026-07-15-daily-step3-performance-optimization.md`

---

## 1. 背景与基线

2026-07-29 早盘任务于 09:20:00 启动，正式策略于 09:37:02 发布：

| 阶段 | 完成时间 | 墙钟耗时 |
|---|---:|---:|
| Step 1 新闻 | 09:20:40 | 约 41 秒 |
| Step 2 映射 | 09:29:18 | 约 8 分 38 秒 |
| Step 3 策略 | 09:37:02 | 约 7 分 43 秒 |
| **全流程** | **09:37:02** | **约 17 分 02 秒** |

运行约束已经确认：

1. 任务必须在 09:20 启动，不能通过提前抓取新闻或提前执行主题分析
   规避耗时问题。
2. 09:20 后竞价数据才进入本工作流认可的稳定窗口。
3. 首要交付目标是稳定在 09:35 前发布正式策略；09:30 保留为进一步
   优化目标。
4. 不以界面显示的 `Thought` 时间代替阶段墙钟时间。

2026-07-29 的可见 `Thought` 与真实耗时差异明显：

| 阶段 | 可见 Thought 合计 | 实际墙钟 |
|---|---:|---:|
| Step 2 | 约 1 分 48 秒 | 约 8 分 38 秒 |
| Step 3 | 约 2 分 07 秒 | 约 7 分 43 秒 |

缺失时间主要位于子代理执行、长 JSON 输出、重复读取、校验失败、修改及
重新发布，而不是本地 Python 计算。

---

## 2. 已确认问题

### 2.1 Step 2 主编排接管了子代理工作

原 `daily-market-analysis` Step 2 同时包含：

- `Agent: sector-analyst` 的说明性标签；
- `Action: Load skill daily-stock-mapping` 的当前代理动作；
- “两个 LLM semantic stages”的内部 V5 说明；
- 面向当前执行者的完整命令序列；
- 未绑定接收者的通用 Prompt。

主编排因此加载了 `daily-stock-mapping`，执行主题证据构建、读取完整新闻、
查询主题列表并写入 `themes.json`。当天只有
`mapper.annotations.json` 写入阶段明确显示为 `Sector-Analyst Agent`。

### 2.2 LLM 热阶段重复读取完整数据

目标输入本应是：

| 热阶段 | 唯一业务输入 |
|---|---|
| Theme LLM | `.theme_evidence_input.json` |
| Mapper Annotation LLM | `.mapper_annotation_input.json` |
| Strategy LLM | `.strategy_llm_input.json` + 策略 rubric / memory |

当天实际额外读取了：

- Theme 阶段：完整 `news.json`、分页新闻、完整主题列表；
- Mapper 阶段：`theme_stocks.json`、`pool_indicators.json`；
- Strategy 阶段：再次查看 `mapper.strategy_view.json`。

这些读取扩大上下文，又重新引入紧凑输入已经消除的信息重复。

### 2.3 `anomaly` 精简合同不完整

完整 `daily-stock-mapping` 技能规定 `anomaly` 是自然语言字符串，但精简
`mapper-semantics-rubric.md` 只说明何时输出，没有明确：

```text
anomaly: string|null
```

当天子代理将其写成 `{type, confidence, trace}` 对象，和 `pattern` /
`major_event` 的结构混淆，导致第一次 `finalize` 失败。

技能声明 `anomaly <= 50` 字符，验证器当前允许 80 字符，也存在合同漂移。

### 2.4 Blanket R2/P2 校验产生误报

当天 20 个候选具有以下共同特征：

- `direct_news_refs` 全部为空；
- 只有主题级 `theme_news_refs`；
- 紧凑输入只有 7 条新闻证据；
- 新闻证据只有标题，没有正文位置或名单位置。

统一采用 R2 在这种输入下可能是正确结果。P1/P2 也缺少足够的
`headline/body/list` 位置信息进行候选级区分。

当前验证器只要不少于 5 个候选全部为 R2/P2 就直接阻断发布，没有检查
输入是否确实同质。最终修复通过人为制造 R2/P1、R1/P2、R3/P2 差异通过
校验，其中部分差异缺乏输入证据。

### 2.5 校验错误没有一次性修复

第一次 Mapper `finalize` 同时返回：

- 三个 `anomaly` 类型错误；
- Blanket R2/P2 错误。

执行过程只修改了三个 `anomaly`，在已知 R2/P2 错误仍存在时再次运行
`finalize`，产生一次必然失败的重复尝试。

### 2.6 Step 3 的 `max_holding_days` 是无效合同字段

`max_holding_days` 当前只被：

1. `validate_strategy.py` 强制校验为 1–20；
2. `mechanical_classification.py` 原样复制；
3. `validate_snapshot.py` 检查是否存在。

它没有用于：

- 交易分类；
- 买入或卖出判断；
- 到期退出；
- 持仓提醒；
- 日报或盘中操作指南展示。

当天三只 `WATCH_ONLY` 股票按“不建仓”语义输出 0，验证器要求改成 1，
产生了一次没有业务价值的失败。

同一 `t1_risk_plan` 中的 `overnight_risk`、`gap_up_action`、
`flat_open_action`、`gap_down_action` 会进入操作指南，仍有实际用途，不在
删除范围内。

### 2.7 重试和 LLM 耗时记录失真

- `step2_timing.json` 缺少 `theme_llm` 和
  `mapper_annotation_llm`，`complete_same_run=false`。
- Step 3 实际发生一次草稿修复，但
  `validation_retry_count=0`。
- Step 3 没有传入实测 `--llm-duration`，使用
  `mtime_estimate`，`gate_d_eligible=false`。
- 当前记录无法区分首轮生成、校验、修复和重新发布耗时。

---

## 3. 锁定设计决策

### 3.1 启动时间不变

- `daily-analysis` 继续于 09:20 触发。
- 不新增提前新闻、提前主题或提前计算任务。
- 所有性能改进必须来自 09:20 后的热路径压缩。

### 3.2 Step 2 由 `sector-analyst` 完整自闭环

主编排只通过命名 Prompt 调用 `sector-analyst`。

`sector-analyst` 在同一次生命周期内负责：

```text
load daily-stock-mapping
→ build-theme-evidence
→ themes.json
→ validate-themes
→ prepare
→ mapper.annotations.json
→ finalize
→ 必要时修复并重试
→ mapper.strategy_view.json
```

主编排不加载 Step 2 技能，不执行 Step 2 命令，不读取或修改 Step 2
中间产物。

### 3.3 Step 3 由 `portfolio-manager` 完整自闭环

主编排只通过命名 Prompt 调用 `portfolio-manager`。

`portfolio-manager` 在同一次生命周期内负责：

```text
load daily-strategy
→ strategy daily prepare
→ 读取紧凑输入和规则
→ strategy.draft.json
→ strategy daily finalize
→ 必要时修复并重试
→ strategy.json + daily_report.html
```

主编排不运行 Step 3 `prepare` / `finalize`，不读取或修改
`strategy.draft.json`，也不处理 validator 错误。

### 3.4 校验与修复属于各自子代理

- 子代理必须在退出前完成本步骤的校验闭环。
- 一次校验失败后，必须处理返回的完整错误集合。
- 只允许一次语义修复重试；第二次仍失败则由该子代理报告失败并停止。
- 主编排不接管中间合同修复。

### 3.5 删除 `max_holding_days`

- 从新生成的 `daily_strategy.v3` 合同中删除。
- 历史 JSON 中存在该字段时忽略，不重写历史产物。
- 不增加 `WATCH_ONLY` 特例或占位值。

### 3.6 不用差异化假数据满足校验器

- 验证器不得要求 LLM 在同质证据上制造 R/P 差异。
- 语义校验必须由实际输入能力驱动。
- 缺少候选级位置证据时，不把 P1/P2 差异作为发布条件。

---

## 4. 目标编排

```text
/daily-analysis (general orchestrator)
    |
    +-- Step 1: news fetch
    |
    +-- sector-analyst
    |     `-- complete daily-stock-mapping workflow
    |
    `-- portfolio-manager
          `-- complete daily-strategy workflow
```

主编排只保留：

- 步骤顺序；
- 命名子代理 Prompt；
- 输入和正式输出路径。

内部命令、LLM 阶段、validator、修复逻辑和计时归各叶子技能所有。

---

## 5. 实施任务

### Task 1 — 完成主编排黑盒化

**修改：**

- `.agents/skills/daily-market-analysis/SKILL.md`

**Step 2：**

- 保留 `Agent`、`Action`、`sector-analyst prompt`、`Outputs`；
- 删除内部 V5 note 和命令序列；
- Prompt 只包含日期、输入和预期输出路径。

**Step 3：**

- 改成与 Step 2 对称的 `portfolio-manager` 完整工作流；
- 删除主编排中的 `strategy daily prepare`、热阶段读文件清单、
  `strategy daily finalize` 和失败修复说明；
- Prompt 改为 `Load skill daily-strategy and execute`。

**验收：**

- 运行日志中 Step 2 全部动作属于 `sector-analyst`；
- Step 3 全部动作属于 `portfolio-manager`；
- general orchestrator 不出现 Step 2/3 中间文件的 Read/Write/Edit；
- general orchestrator 不运行 Step 2/3 的 prepare/finalize。

> Step 2 主编排精简已经在当前工作区完成；Step 3 尚待实施。

### Task 2 — 收紧 Step 2 热阶段读取合同

**修改：**

- `.agents/skills/daily-stock-mapping/SKILL.md`
- `.agents/skills/daily-stock-mapping/references/theme-evidence-rubric.md`
- `.agents/skills/daily-stock-mapping/references/mapper-semantics-rubric.md`

**Theme LLM：**

- 确定性 `build-theme-evidence` 可读取 `news.json` 和主题库；
- LLM 写 `themes.json` 时只读：
  - `.theme_evidence_input.json`
  - `theme-evidence-rubric.md`
- 删除 LLM 阶段重新查询完整主题列表、重新扫描完整新闻的说明。

**Mapper Annotation LLM：**

- LLM 只读：
  - `.mapper_annotation_input.json`
  - `mapper-semantics-rubric.md`
- 禁止读取 `theme_stocks.json`、`pool_indicators.json`、完整新闻或 Mapper。

**验收：**

- 日志中两个热阶段没有多余文件读取；
- `themes.json` 和 `mapper.annotations.json` 仍通过现有合同校验；
- 紧凑输入候选覆盖和证据引用不降低。

### Task 3 — 修复 `anomaly` 合同

**修改：**

- `.agents/skills/daily-stock-mapping/SKILL.md`
- `.agents/skills/daily-stock-mapping/references/mapper-semantics-rubric.md`
- `src/ashare_pilot/mapping/_commands/daily/validate_annotations.py`
- 相关 Mapper 合同测试

**锁定格式：**

```text
anomaly: string|null
```

统一最大长度为 50 字符。`pattern` 和 `major_event` 继续使用结构化对象。

**验收：**

- 对象型 `anomaly` 在精简 rubric 层面已明确禁止；
- 51 字符失败，50 字符通过；
- 缺少真实异常时允许省略或为 null；
- 不要求输出重复默认描述。

### Task 4 — 将 R2/P2 检查改成证据感知

**修改：**

- `src/ashare_pilot/mapping/_commands/daily/validate_annotations.py`
- 必要时修改：
  - `src/ashare_pilot/mapping/_commands/daily/prepare.py`
  - Mapper annotation input builder
- Mapper validator 单元测试和 2026-07-29 冻结输入测试

**第一阶段：立即消除误报**

- 删除“全部 R2/P2 必然失败”的硬规则；
- 同质证据下统一 R2/P2 只产生 warning；
- 存在 `direct_news_refs` / `NewsDirect` 却全部按主题级处理时才报错；
- 不以“输出必须多样化”作为正确性条件。

**第二阶段：补足证据能力**

如果仍需严格校验 P：

- 紧凑证据增加可确定的 `mention_location`：
  `headline|body|list|absent`；
- P 值由该字段校验，而不是由候选间差异推断；
- 无法确定位置时允许 `unknown` 或不做 P 多样性校验。

**验收：**

- 2026-07-29 全部无 direct refs 的候选不会因统一 R2 阻断；
- 带 `NewsDirect` 的冻结样本若错误输出 R2 会失败；
- validator 不再诱导无证据的 R1/R3/P1 差异。

### Task 5 — 子代理内部执行完整错误修复

**修改：**

- `.agents/skills/daily-stock-mapping/SKILL.md`
- `.agents/skills/daily-strategy/SKILL.md`

**规则：**

1. 首次 validator 返回完整错误集合；
2. 子代理一次性修复全部错误；
3. 计入一次 validation retry；
4. 重跑 finalize；
5. 第二次失败则停止，不继续循环。

**验收：**

- 不再出现“已知仍有错误但先重跑”的流程；
- 日志中每次修复明确对应完整错误集合；
- 主编排不读取或编辑草稿/注释。

### Task 6 — 删除 `max_holding_days`

**修改：**

- `.agents/skills/daily-strategy/references/strategy-output-contract.md`
- `src/ashare_pilot/strategy/_commands/daily/validate_strategy.py`
- `src/ashare_pilot/operations/mechanical_classification.py`
- `src/ashare_pilot/operations/_commands/validate_snapshot.py`
- `docs/morning-recommendation-system-spec.md`
- 相关单元、等价和冻结测试

**处理：**

- 新策略不再输出该字段；
- validator 不再要求 1–20；
- operations 快照不再复制或要求该字段；
- 历史输入中出现该字段时作为未知额外字段忽略；
- 保留其余四个 T+1 场景字段。

**验收：**

- 全仓库运行代码不再消费或要求 `max_holding_days`；
- `WATCH_ONLY` 不再因持有天数失败；
- operation guide 的四个 T+1 场景字段保持不变；
- 不重写历史 `strategy.json`。

### Task 7 — Step 3 热阶段读取与输出收敛

**修改：**

- `.agents/skills/daily-strategy/SKILL.md`
- `.agents/skills/daily-strategy/references/strategy-selection-rubric.md`
- `.agents/skills/daily-strategy/references/strategy-output-contract.md`
- 如有需要，修改
  `src/ashare_pilot/strategy/_commands/daily/llm_input.py`

**处理：**

- `portfolio-manager` 只读取：
  - `.strategy_llm_input.json`
  - 两个策略 reference；
  - `RULES.md`、`SHARED_RULES.md`；
- 不直接读取 `mapper.strategy_view.json`、完整 Mapper、指标或新闻；
- 所有候选仍完整进入紧凑输入；
- 只对最终入选股输出深度推理；
- 删除 `max_holding_days` 后同步缩小草稿。

**验收：**

- Strategy 热阶段没有越界读取；
- 候选集合和顺序与 Step 2 输出一致；
- 正式策略仍由最终入选股和确定性观察池组成；
- 策略质量字段不因压缩而缺失。

### Task 8 — 修复计时和重试观测

**修改：**

- `src/ashare_pilot/mapping/_commands/daily/timing.py`
- `src/ashare_pilot/strategy/_commands/daily/timing.py`
- 两个技能中的 timing 调用说明
- timing 单元测试

**Step 2 必须记录：**

- `theme_llm`；
- `prepare`；
- 嵌套 `indicators`；
- `mapper_annotation_llm`；
- `finalize`；
- 每个语义阶段的输入/输出字节和 validation retry。

**Step 3 必须记录：**

- `prepare`；
- `strategy_llm`；
- `finalize`；
- 草稿修复次数；
- 最终被 `finalize` 消费的 draft 指纹。

**共同要求：**

- 使用子代理内部的阶段开始/结束时间，不使用 UI `Thought`；
- 修复后重新绑定最终产物指纹；
- `complete_same_run` 必须真实反映同一次运行；
- 实测 LLM 时长可用时不得退化成 `mtime_estimate`；
- validator 尝试次数和错误摘要可审计；
- timing 写入失败不影响正式交易合同。

**验收：**

- 正常运行 `complete_same_run=true`；
- Step 3 实际修复一次时 `validation_retry_count=1`；
- `gate_d_eligible` 与真实计时方法一致；
- `total_recorded_seconds` 可与日志墙钟核对。

---

## 6. 测试方案

### 6.1 单元测试

至少覆盖：

1. `anomaly` 的 string/null/长度边界；
2. 同质主题证据允许统一 R2；
3. `NewsDirect` 被错误降为主题级时失败；
4. `max_holding_days` 缺失时策略和快照通过；
5. 历史输入含该额外字段时保持兼容；
6. Step 2 / Step 3 retry count 正确；
7. 上游重跑后 timing 下游阶段正确失效；
8. 最终正式 JSON 和 HTML 正常发布。

建议运行：

```bash
uv run --frozen pytest \
  tests/unit/test_batch4_daily_contract.py \
  tests/unit/test_batch5_daily_contract.py \
  tests/unit/test_batch5_validate_strategy.py \
  tests/equivalence/test_batch5_strategy.py
```

根据实际修改文件补充 operations snapshot 和 timing 测试。

### 6.2 冻结回放

以 2026-07-29 的以下输入作为真实回放基线：

- `.theme_evidence_input.json`
- `.mapper_annotation_input.json`
- `.strategy_llm_input.json`

冻结回放至少验证：

- 不读取完整输入也能生成覆盖完整的语义输出；
- 统一主题级新闻关系不会触发误报；
- 删除 `max_holding_days` 不改变选股、方向、评级和其他 T+1 文本；
- prepare/finalize 的确定性输出保持稳定。

### 6.3 真实影子运行

至少积累 5 个交易日：

| 指标 | 要求 |
|---|---|
| 启动时间 | 09:20，不提前 |
| 正式策略发布时间 | 正常目标 ≤09:35 |
| Step 2 / Step 3 子代理归属 | 100% 正确 |
| 主编排中间文件读写 | 0 |
| 无效 validator 重跑 | 0 |
| Timing 完整运行 | 100% |
| 正式合同校验 | 100% 通过 |

在 5 次 `gate_d_eligible=true` 样本之前，不宣称达到稳定 P95。

---

## 7. 性能预算

09:20 至 09:35 共 900 秒，建议预算：

| 阶段 | 正常预算 |
|---|---:|
| Step 1 | ≤45 秒 |
| Step 2 | ≤6 分钟 |
| Step 3 | ≤6 分钟 |
| 交接与抖动余量 | ≥2 分 15 秒 |
| **总计** | **≤15 分钟** |

优化优先级：

1. 消除错误代理归属；
2. 消除完整文件重复读取；
3. 消除无依据的 validator 返工；
4. 删除无效输出字段；
5. 准确计时后再判断是否需要调整模型或进一步压缩输出。

本轮不以削减候选数量换取速度，不移动最终选股、Direction 或
RiskSeverity 的所有权。

---

## 8. 实施顺序

建议分为四组提交：

### Commit A — 编排归属

- 完成 Step 2 黑盒子代理编排；
- 将 Step 3 改为完整 `portfolio-manager` 子代理工作流；
- 不改变业务合同。

### Commit B — 合同正确性

- 明确 `anomaly`；
- 修复 Blanket R2/P2；
- 删除 `max_holding_days`；
- 更新测试和规范。

### Commit C — 热阶段输入

- 删除 Step 2 / Step 3 LLM 重复读取说明；
- 锁定三个紧凑输入边界；
- 加入冻结回放。

### Commit D — 观测与验收

- 完善 LLM、重试和 finalize 计时；
- 运行完整单元测试；
- 开始 5 日真实影子计时。

每组提交应独立通过测试，避免把编排、合同和观测修改混在一个不可回滚
变更中。

---

## 9. 回滚

1. 编排修改失败时，只回滚 `daily-market-analysis` 的 Agent/Prompt
   调度文本，不改写当天正式策略。
2. R/P validator 修改只影响发布门槛；若出现证据质量回退，恢复为 warning
   并保留审计，不恢复“强制多样化”。
3. 删除 `max_holding_days` 为向后兼容修改；旧文件多出的字段继续忽略。
4. 任何影子运行出现选股、Direction、评级或其他 T+1 行为漂移时，停止
   性能切换并用冻结回放定位，不重写历史输出。

---

## 10. 完成定义

全部满足后，本方案才算完成：

- Step 2 和 Step 3 各自由指定子代理完整自闭环；
- 主编排不执行、校验或修复两个步骤的中间合同；
- 三个 LLM 热阶段只读取规定的紧凑输入；
- `anomaly` 合同单一且一致；
- R/P 校验由证据驱动，不要求人为多样化；
- `max_holding_days` 从新合同和运行消费链删除；
- 每次失败只进行一次完整修复重试；
- Step 2 / Step 3 timing 能反映真实 LLM 和重试墙钟；
- 至少 5 个真实交易日形成可用的 Gate D 样本；
- 正常运行在 09:35 前发布正式策略。
