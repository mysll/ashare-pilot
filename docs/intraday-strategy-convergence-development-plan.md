# Intraday 策略组合收敛开发计划

- 版本：1.1
- 日期：2026-07-28
- 状态：Implemented
- 前置合同：[Intraday 双池选股最终开发计划](intraday-stock-selection-final-development-plan.md)
- 领域语言：[Intraday 选股领域术语表](intraday-stock-selection-glossary.md)
- 当前实现：[当前 Intraday 选股、评分与过滤流程](current-intraday-stock-selection.md)

## 1. 背景

双池 V2 已经确定性地区分：

```text
Executable Pool
  数据、评分和基础执行资格均通过

Observation Pool
  确定性不可执行或关键评分数据不完整
```

但 Reasoning 到最终策略之间仍缺少显式的“组合收敛”语义。当前流程容易把
`Tradeability=Watch` 批量写成可行动 Direction，再由构建器全部投影到
`recommendations`。这会产生以下问题：

- Executable 被误解为最终推荐；
- Watch 被误解为谨慎买入；
- 主选和替代标的同时进入推荐；
- 外置规则的文字结论与最终名单可能矛盾；
- `position_plan` 和 `position_cap` 使用账户无关的百分比，无法保证至少可以买入
  一手，形成虚假精确；
- HTML 忠实放大上游语义问题，但无法判断哪些股票只是备选。

本计划只修复 Reasoning 之后的组合收敛与最终投影，不修改双池计算、评分公式、
执行资格或任何外置经验规则。

## 2. 已确认的架构决策

### 2.1 外置规则完全由 LLM 负责

`memory/INTRADAY_RULES.md` 和 `memory/SHARED_RULES.md` 中的规则保持自然语言：

- LLM 阅读规则；
- LLM 判断是否触发；
- LLM 处理规则冲突与优先级；
- LLM 决定规则如何影响 Direction、执行角色、风险和 T+1 计划；
- LLM 在发布前自查规则结论与最终名单是否一致。

Python 不得：

- 解析 I20 或任何具体规则的自然语言；
- 根据主题关系替 LLM 执行去重；
- 硬编码任何规则编号的语义；
- 验证候选规则、正式规则或规则生命周期；
- 根据 `rules_applied` 自动修改、删除或升级股票；
- 引入机器可读规则注册表作为本期前置条件。

`rules_applied` 继续作为 LLM 推理审计字段，代码只验证它是字符串数组，不解释其
内容。

### 2.2 不输出个股仓位百分比

在缺少以下账户信息时，策略不得输出个股仓位百分比、金额或手数：

- 可用现金；
- 已有持仓；
- 当前成交价；
- A 股整手约束；
- 单笔最大风险金额；
- 账户级剩余风险预算。

因此本期删除账户无关的：

- 个股百分比仓位；
- `position_pct` 设想；
- “单只 0.25% / 0.5%”等文案；
- 精确总仓位百分比；
- 根据百分比推导推荐数量的方案。

真实手数只能由未来独立的账户执行层计算，不属于当前预测合同。

### 2.3 用执行角色表达组合收敛

对 Executable Pool 中每只股票，LLM 在完成个股判断后必须再赋予一个执行角色：

| `execution_role` | 含义 | 最终视图 |
|---|---|---|
| `primary` | 本轮最终主选，满足执行条件时可以行动 | `recommendations` |
| `alternative` | 替代方案，不与对应主选同时执行 | `eligible_watchlist` |
| `watch` | 合格但本轮不执行 | `eligible_watchlist` |

执行角色不改变：

- Scoreability；
- OvernightScore；
- rank / rank_tier；
- execution_state；
- Executable / Observation 池归属。

### 2.4 不设置统一推荐数量上限

本期不新增“最多推荐 N 只”的硬编码策略，因为该数量属于市场状态和外置规则共同
决定的 Reasoning 结果。

系统只要求：

- `primary` 是 LLM 完成组合收敛后的最终同时执行集合；
- 替代方案不得伪装成主选；
- Watch 不得批量自动变成推荐；
- LLM 发布前完成外置规则和最终名单的一致性自查。

## 3. 目标语义

### 3.1 四个层次必须分离

```text
Executable Pool
  确定性具备执行资格
        ↓
Tradeability
  LLM 对个股交易质量的判断
        ↓
Execution Role
  LLM 完成组合比较后的主选 / 备选 / 观察
        ↓
Final View
  recommendations / eligible_watchlist
```

禁止以下快捷推导：

```text
Executable → Recommendation
Watch → 谨慎持有
A/B Tier → primary
高分 → 自动 primary
```

### 3.2 Tradeability、Direction 与执行角色

本合同明确：

```text
Actionable Direction
  = 持有偏多 | 持有 | 谨慎持有

Non-actionable Direction
  = 观望
```

`谨慎持有` 属于 Actionable Direction。因此 `Watch + primary + 谨慎持有`
是合法组合，但 `Watch + primary + 持有/持有偏多` 不合法。

基础合同关系：

| Tradeability | 允许的角色 | 允许的 Direction |
|---|---|---|
| `Suitable` | primary / alternative / watch | primary 可行动；其余观望 |
| `Watch` | primary / alternative / watch | primary 只能谨慎持有；其余观望 |
| `Extended` | watch | 观望 |
| `Avoid` | watch | 观望 |

此外：

- 每个 `executable_annotations[]` 都必须显式提供 `execution_role`；
- `execution_role` 不允许缺失、为 `null` 或由其他字段默认推导；
- `i14_exemption=cautious_hold` 的 primary Direction 最高为 `谨慎持有`；
- `primary` 必须通过确定性 `execution_state.eligible=true`；
- `alternative` 和 `watch` 必须使用 `stop_loss_basis=not_applicable`；
- `primary` 必须使用可解析的确定性止损 basis；
- Observation Pool 不得出现 `execution_role`。

这些是通用合同语义，不包含任何外置经验规则。

### 3.3 主选与备选

LLM 负责识别替代关系，并通过自然语言说明：

```json
{
  "code": "sh601398",
  "execution_role": "alternative",
  "direction": "观望",
  "execution_condition": "仅在主选银行股失去执行条件时重新评估，不与主选同时执行"
}
```

本期不增加 Python 可执行的互斥组，也不让代码判断哪些股票属于同一主题。替代关系
属于 LLM 的组合推理结果。

### 3.4 RiskSeverity 与 RiskPosture

两个字段属于不同层次：

| 字段 | 含义 | 不表示 |
|---|---|---|
| `risk_severity` | 市场或个股的风险程度判断：low / medium / high / critical。 | 是否已经形成最终主选。 |
| `risk_posture` | LLM 完成组合收敛后的整体执行姿态：zero / very_light / light / normal。 | 仓位百分比、金额、手数或推荐数量。 |

`risk_posture` 的定性含义：

| 值 | 含义 |
|---|---|
| `zero` | 本轮没有主选，不执行。 |
| `very_light` | 极度谨慎，只保留严格筛选后的主选。 |
| `light` | 谨慎参与。 |
| `normal` | 按常规条件执行。 |

通用一致性合同：

```text
risk_posture=zero
  ⇔ 没有 execution_role=primary
  ⇔ recommendations 为空
```

空 Executable Pool 必须输出 `risk_posture=zero`。Executable Pool 非空但 LLM
最终全部设为 `alternative/watch` 时，也必须输出 `risk_posture=zero`。Builder
不得静默修正不一致的姿态；validator 应拒绝并要求重新生成 annotations。

## 4. 目标数据合同

本次删除字段并改变最终投影语义，属于 breaking change。稳定文件名保持不变，
Reasoning 相关 Schema 升级：

| 文件 | 当前 | 目标 |
|---|---|---|
| `selection_pools.json` | `intraday_selection_pools.v1` | 不变 |
| `intraday_mapper.base.json` | `intraday_mapper_base.v2` | 不变 |
| `intraday_mapper.annotations.json` | `intraday_mapper_annotations.v2` | `intraday_mapper_annotations.v3` |
| `intraday_mapper.json` | `intraday_mapper.v2` | `intraday_mapper.v3` |
| `overnight_strategy.json` | `intraday_overnight_strategy.v2` | `intraday_overnight_strategy.v3` |

不为新生成文件提供 V2 写入兼容层。历史 V1/V2 文件仅作为磁盘归档和 fixture
证据保留，不批量迁移，也不承诺由正式复盘 Skill 读取。本期不实现 V1/V2 生产
复盘兼容路径；如需重新分析历史文件，使用一次性人工流程。

### 4.1 `intraday_mapper.annotations.v3`

```json
{
  "schema_version": "intraday_mapper_annotations.v3",
  "date": "YYYY-MM-DD",
  "market_assessment": {
    "regime_hint": "string",
    "tomorrow_expectation": "string",
    "risk_severity": "low|medium|high|critical",
    "reasoning_trace": "string"
  },
  "executable_annotations": [
    {
      "code": "sh600000",
      "tradeability": "Suitable|Watch|Extended|Avoid",
      "direction": "持有偏多|持有|谨慎持有|观望",
      "execution_role": "primary|alternative|watch",
      "trading_strategy": "趋势跟随|回调布局|强势接力|防御布局",
      "risk_severity": "low|medium|high|critical",
      "expected_premium": "string",
      "key_reason": "string",
      "execution_condition": "string",
      "t_plus_1_plan": {
        "auction_condition": "string",
        "open_strategy": "string",
        "stop_loss_basis": "day_low|ma5|ma10|ma20|not_applicable",
        "take_profit": "string"
      },
      "rules_applied": [],
      "reasoning_trace": "string"
    }
  ],
  "observation_annotations": [
    {
      "code": "sz000001",
      "observation_summary": "string",
      "watch_condition": "string",
      "risk_note": "string"
    }
  ],
  "strategy": {
    "risk_posture": "zero|very_light|light|normal",
    "execution_principle": "string",
    "risk_control": ["string"],
    "execution_window": "14:50-14:57"
  }
}
```

变更：

- 新增 `execution_role`；
- `position_plan` 替换为 `execution_condition`；
- `position_cap` 替换为定性的 `risk_posture` 和 `execution_principle`；
- 不增加任何仓位百分比、金额或手数字段；
- `rules_applied` 保持自然语言规则的审计引用，不进入代码决策。

### 4.2 `intraday_mapper.v3`

Mapper 继续将 annotation 合并到对应 executable stock 的 `reasoning`，不改变
Compute 所有权。新增/替换的 Reasoning 字段原样进入：

- `execution_role`；
- `execution_condition`；
- `risk_posture`；
- `execution_principle`。

不得把 `execution_role` 写入 Observation Pool。

### 4.3 `intraday_overnight_strategy.v3`

```json
{
  "schema_version": "intraday_overnight_strategy.v3",
  "date": "YYYY-MM-DD",
  "market_assessment": {},
  "strategy": {
    "risk_posture": "very_light",
    "execution_principle": "弱市只保留完成组合比较后的主选，替代标的不同时执行",
    "risk_control": [],
    "execution_window": "14:50-14:57"
  },
  "data_quality": {},
  "recall_quality": {},
  "recommendations": [],
  "eligible_watchlist": [],
  "observations": []
}
```

最终投影：

```text
Executable
  + execution_role=primary
  + actionable Direction
    → recommendations

Executable
  + execution_role in {alternative, watch}
  + Direction=观望
    → eligible_watchlist

Observation Pool
    → observations
```

## 5. LLM 组合收敛流程

更新 `intraday-strategy` Skill，要求一次 Reasoning 严格按以下顺序执行。

### 5.1 阶段 A：读取事实与规则

完整读取：

- `intraday_mapper.base.json`；
- `memory/INTRADAY_RULES.md`；
- `memory/SHARED_RULES.md`。

确认：

- Compute 字段只读；
- 双池归属只读；
- 外置规则保持自然语言，由 LLM 语义应用；
- 候选规则不得影响 Direction、角色、最终名单或 T+1 执行计划；
- 不得新增、升级、退役或改写规则。

### 5.2 阶段 B：逐股判断

对每只 executable stock 分别完成：

- Tradeability；
- 初步 Direction 倾向；
- Expected Premium；
- RiskSeverity；
- T+1 风险与止损 basis；
- 实际应用的规则引用。

此阶段不得直接把所有 Watch 设为 `primary`。

### 5.3 阶段 C：横向组合比较

在完整 executable 集合中进行横向比较：

- 哪些股票可以作为本轮主选；
- 哪些只是主选失效时的替代；
- 哪些虽合格但本轮不执行；
- 外置规则是否要求收紧、互斥、去重或归零；
- 市场判断、风险姿态和主选集合是否一致。

随后统一写入：

- `execution_role`；
- 最终 Direction；
- `execution_condition`。

### 5.4 阶段 D：发布前自查

LLM 在写 annotations 前必须自查：

```text
[ ] Executable 精确覆盖只表示完成判断，不表示全部推荐
[ ] 每个 primary 都是本轮最终同时执行集合的一部分
[ ] alternative/watch 全部为观望
[ ] Watch 没有被批量等同于谨慎持有
[ ] Avoid/Extended 全部为 watch + 观望
[ ] 候选规则没有影响 Direction、execution_role 或执行计划
[ ] rules_applied 只记录本轮实际应用的正式规则
[ ] 已声明应用的外置规则与最终主选/备选关系没有矛盾
[ ] execution_condition 与 execution_role 一致
[ ] 风险姿态、风险控制文字与最终主选集合一致
[ ] 不包含个股仓位百分比、金额或手数
```

这一步由 LLM 完成，Python 不解析规则语义。

## 6. 代码层通用校验

代码只验证 Schema 和不依赖外置规则的合同一致性。

### 6.1 Annotation 校验

修改：

```text
src/ashare_pilot/mapping/_commands/intraday/validate_annotations.py
src/ashare_pilot/mapping/intraday_contract.py
```

新增通用检查：

- 每个 executable annotation 必须显式存在 `execution_role`；
- `execution_role` 不允许为 `null`，且必须属于
  `primary|alternative|watch`；
- `primary` 必须具有可行动 Direction；
- `alternative/watch` 必须为 `观望`；
- `Watch + primary` 的 Direction 只能是 `谨慎持有`；
- `Avoid/Extended` 只能是 `watch + 观望`；
- `primary` 必须使用非 `not_applicable` 止损 basis；
- `alternative/watch` 必须使用 `not_applicable`；
- `execution_condition` 必须为非空字符串；
- annotations 禁止出现 `position_pct`、仓位金额或手数字段；
- Observation annotations 禁止出现 `execution_role` 和
  `execution_condition`；
- `risk_posture` 必须属于固定枚举；
- `execution_principle` 必须为非空字符串；
- 没有 `primary` 时 `risk_posture` 必须为 `zero`；
- 存在 `primary` 时 `risk_posture` 不得为 `zero`；
- 空 executable pool 时必须输出 `risk_posture=zero`。

明确不检查：

- I20 是否触发或是否正确应用；
- 任意规则编号是否属于正式或候选区；
- 主题是否应当去重；
- primary 数量是否符合某条经验规则；
- LLM 的自然语言规则推理是否正确。

### 6.2 Mapper 校验

修改：

```text
src/ashare_pilot/mapping/_commands/intraday/validate_mapper.py
```

要求：

- 合并后的 reasoning 与 annotations 完全一致；
- Compute-owned 字段未被覆盖；
- `execution_role` 只存在于 executable reasoning；
- observation reasoning 不包含执行字段；
- annotation coverage 继续精确覆盖双池。

### 6.3 Strategy 校验

修改：

```text
src/ashare_pilot/strategy/_commands/overnight/validate.py
```

要求：

- recommendations 代码集合精确等于 mapper 中所有 `primary`；
- eligible_watchlist 精确等于 mapper 中所有 `alternative/watch`；
- recommendations 每只均为可行动 Direction；
- eligible_watchlist 每只均为 `观望`；
- recommendations 为空时 `risk_posture` 必须为 `zero`；
- recommendations 非空时 `risk_posture` 不得为 `zero`；
- 两个视图互斥并精确覆盖 executable pool；
- observations 精确覆盖 observation pool；
- 最终投影字段与 mapper 完全一致；
- 输出中不存在被移除的账户无关仓位字段。

## 7. 构建与展示改造

### 7.1 Strategy Builder

修改：

```text
src/ashare_pilot/strategy/_commands/overnight/build.py
```

从当前：

```text
actionable Direction → recommendations
```

改为：

```text
execution_role=primary + actionable Direction
  → recommendations

execution_role=alternative|watch + Direction=观望
  → eligible_watchlist
```

构建器不得：

- 根据分数自动改角色；
- 根据 rank tier 自动改角色；
- 根据主题自动去重；
- 根据外置规则自动改名单；
- 生成或推算仓位。

### 7.2 HTML

修改：

```text
src/ashare_pilot/strategy/_commands/overnight/render_report.py
```

保持当前已恢复的中文决策终端布局，不重新设计模板。只调整语义展示：

- 顶部数量继续使用 `len(recommendations)`；
- recommendation 显示“主选”；
- eligible watchlist 区分“备选”和“观察”；
- 删除个股仓位百分比；
- 删除精确总仓位百分比；
- 展示定性 `risk_posture`；
- 展示 `execution_condition`；
- alternative 明确显示“暂不执行，仅作为替代”；
- Watch 不再被统一翻译为“谨慎买入”；
- 页面不展示 `rank_tier`；
- 页面不增加“交易板”列。

HTML 继续只消费已通过 validator 的 JSON，不包含额外策略判断。

## 8. 兼容与下游调整

需要同步修改的 Skill 和文档：

```text
.agents/skills/intraday-market-analysis/SKILL.md
.agents/skills/intraday-strategy/SKILL.md
.agents/skills/intraday-trading-review/SKILL.md
docs/current-intraday-stock-selection.md
docs/intraday-stock-selection-glossary.md
docs/intraday-stock-selection-final-development-plan.md
```

其中：

- `intraday-trading-review/SKILL.md` 当前明确只接受
  `intraday_overnight_strategy.v2` 和 `intraday_mapper.v2`，必须升级为只接受
  V3，并按 primary / alternative / watch 提取复盘口径；
- `intraday-market-analysis/SKILL.md` 和 `intraday-strategy/SKILL.md` 负责更新
  V3 发布与生成说明；
- `src/ashare_pilot/review/` 当前不读取 intraday strategy JSON，本期无预期代码
  改动，只需确认没有新增耦合；
- `src/ashare_pilot/automation/_commands/intraday.py` 当前只编排到
  `selection_pools.json`，不生成 mapper/strategy，本期不修改其 Schema 逻辑。

下游复盘口径：

- recommendation 只评估 `primary`；
- alternative 单独记录替代观察结果，不计为实际推荐；
- watch 继续作为机会成本观察；
- 新生成文件只写 V3；
- 正式复盘 Skill 升级后只接受 V3；
- 历史 V1/V2 只保留为归档和 fixture，不进入生产复盘路径。

必须在发布 V3 前同步更新 `intraday-trading-review/SKILL.md` 的硬编码 Schema
要求，禁止先发布 V3、后修复复盘 Skill。

## 9. 测试计划

### 9.1 Annotation 单元测试

新增或更新：

```text
tests/unit/test_intraday_mapper_v2.py
```

测试用例：

1. Suitable + primary + 持有：通过；
2. Watch + primary + 谨慎持有：通过；
3. Watch + primary + 持有：失败；
4. Watch + alternative + 观望：通过；
5. Watch + watch + 观望：通过；
6. alternative + 可行动 Direction：失败；
7. watch + 可行动 Direction：失败；
8. Avoid + primary：失败；
9. Extended + alternative：失败；
10. primary + `not_applicable` 止损：失败；
11. alternative/watch + 可执行止损 basis：失败；
12. Observation 出现 execution role：失败；
13. `position_pct` 或手数字段出现：失败；
14. 缺失 execution role：失败；
15. `execution_role=null`：失败；
16. 非法 risk posture：失败；
17. 空 executable + `risk_posture=zero`：通过；
18. 空 executable + 非 zero posture：失败；
19. executable 非空但全部 alternative/watch + `zero`：通过；
20. 有 primary + `zero`：失败。

实施时将测试文件按目标 Schema 重命名为 V3，避免测试名称继续暗示 V2。

### 9.2 Strategy 投影测试

更新：

```text
tests/unit/test_overnight_strategy_v2.py
```

覆盖：

1. primary 精确进入 recommendations；
2. alternative 精确进入 eligible_watchlist；
3. watch 精确进入 eligible_watchlist；
4. Observation 不携带执行字段；
5. 三个最终视图精确覆盖对应双池；
6. 构建结果被篡改后验证失败；
7. 空 executable pool 正常输出空推荐；
8. 空 executable pool 的 risk posture 必须为 zero；
9. 非空 executable 但无 primary 时 risk posture 必须为 zero；
10. 有 primary 时 risk posture 不得为 zero；
11. risk posture 正确投影；
12. 旧仓位字段不再出现在最终 JSON；
13. HTML 推荐数量等于 primary 数量。

实施时将测试文件按目标 Schema 重命名为 V3。

### 9.3 HTML 回归测试

必须验证：

- 保留既有中文决策终端的主要区块；
- 不显示 Rank Tier；
- 不显示交易板；
- 不显示个股百分比仓位；
- 不显示精确总仓位百分比；
- primary 显示为主选；
- alternative 显示为备选且暂不执行；
- watch 显示为观察；
- 空主选时明确显示“无合适执行候选”。

### 9.4 2026-07-28 场景回归

使用当天确定性 base 制作冻结 Reasoning 场景，验证合同能表达：

- 30 只 executable 全部完成注释；
- 只有完成组合收敛后的股票成为 primary；
- 同类股票可以表达主选和 alternative；
- 低分 Watch 可以保持 watch；
- risk posture 为弱市定性状态；
- 不出现个股百分比仓位。

注意：

- 自动化测试不得断言 I20 的具体结果；
- 自动化测试不得判断哪个银行股必须成为主选；
- 自动化测试不得检查候选规则生命周期；
- I20、候选规则和最终选股质量由 LLM 场景验收与人工复核确认。

## 10. 实施任务

### Task 0：冻结基线

- 保存当前 V2 单元测试结果；
- 提取 2026-07-28 最小回归 fixture；
- 记录当前推荐数、角色缺失和百分比仓位问题；
- 不修改 Compute、selection pools 或 mapper base。

验收：

- fixture 不依赖网络；
- 能稳定复现“Watch 被批量投影为 recommendation”的旧行为。

### Task 1：更新文档与 Schema 常量

- 更新领域术语；
- 定义 Execution Role；
- 将三个 Reasoning 相关 Schema 升级到 V3；
- 保持 selection pool v1 和 mapper base v2 不变；
- 明确删除的仓位字段和不兼容策略。

验收：

- 文档不再把 executable 或 Watch 等同推荐；
- 文档不再要求 LLM 输出百分比仓位；
- 文档明确外置规则只由 LLM处理。

### Task 2：先写失败测试

- 为 V3 annotations、mapper、strategy 增加 fixture；
- 写角色/方向/止损组合测试；
- 写三视图投影测试；
- 写禁止旧仓位字段测试；
- 写 HTML 语义测试。

验收：

- 新测试在旧实现上按预期失败；
- 失败原因集中在本计划字段和投影变化。

### Task 3：实现 Annotation 与 Mapper V3

- 更新合同常量；
- 合并 `execution_role` 和 `execution_condition`；
- 删除 `position_plan` 和 `position_cap`；
- 加入通用字段校验；
- 保持 Compute-owned 字段保护不变。

验收：

- V3 annotation/mapper 测试通过；
- 无任何 I20 或具体规则编号逻辑进入 Python。

### Task 4：实现 Strategy V3 投影

- 更新 builder；
- 更新 strategy validator；
- recommendations 按 primary 投影；
- eligible watchlist 按 alternative/watch 投影；
- 删除旧仓位字段。

验收：

- 三视图精确覆盖；
- role 和 Direction 不一致时失败；
- 构建器不做外置规则判断。

### Task 5：更新 LLM Skill

- 写入四阶段 Reasoning 流程；
- 写入发布前自查清单；
- 明确 Watch 不自动成为 primary；
- 明确替代标的必须观望；
- 明确候选规则不得影响执行结论；
- 明确不输出百分比、金额或手数；
- 保留所有外置规则自然语言处理权。

验收：

- Skill 不要求 Python 验证外置规则；
- Skill 不引入统一推荐数量上限；
- Skill 清楚区分精确注释覆盖与最终主选。

### Task 6：更新 HTML

- 保持既有模板布局；
- 展示主选/备选/观察；
- 展示 execution condition；
- 展示定性风险姿态；
- 删除仓位百分比。

验收：

- HTML 与 JSON 角色完全一致；
- 无 Rank Tier 和交易板列；
- 无账户无关仓位数字。

### Task 7：更新 Skill、复盘口径与现状文档

- 更新 `intraday-market-analysis/SKILL.md` 的 V3 发布说明；
- 更新 `intraday-trading-review/SKILL.md`，只接受 V3；
- 更新复盘对 primary/alternative/watch 的读取说明；
- 明确历史 V1/V2 仅归档，不提供生产复盘兼容；
- 确认 Python review 代码不读取 intraday strategy JSON，无需修改；
- 确认 automation compute 编排不生成 mapper/strategy，无需修改；
- 更新现状文档和术语表。

验收：

- Reasoning 和发布 Skill 只写 V3；
- 复盘 Skill 只接受并正确读取 V3；
- Python review 与 compute automation 无无关改动；
- 历史 V1/V2 文件继续保留为归档和 fixture；
- alternative 不计入实际推荐绩效。

### Task 8：全量验证

依次执行：

```bash
uv run --frozen pytest tests/unit/test_intraday_mapper_v3.py
uv run --frozen pytest tests/unit/test_overnight_strategy_v3.py
uv run --frozen pytest tests/unit
uv run --frozen pytest tests/equivalence
```

使用冻结的 2026-07-28 base 重新生成 annotations 后执行：

```bash
uv run --frozen ashare-pilot mapping intraday validate-annotations --date 2026-07-28
uv run --frozen ashare-pilot mapping intraday build-mapper --date 2026-07-28
uv run --frozen ashare-pilot mapping intraday validate-mapper --date 2026-07-28
uv run --frozen ashare-pilot strategy overnight build --date 2026-07-28
uv run --frozen ashare-pilot strategy overnight validate --date 2026-07-28
uv run --frozen ashare-pilot strategy overnight render-report --date 2026-07-28
```

验收：

- 所有自动化测试通过；
- LLM 完成组合收敛；
- 主选、备选、观察语义清晰；
- 外置规则没有进入 Python；
- 没有个股或总体百分比仓位；
- HTML 与最终 JSON 一致。

## 11. 发布门槛

以下条件全部满足才能发布：

1. selection pools 和 mapper base 的代码与输出无变化；
2. V3 annotations 精确覆盖两个输入池；
3. 每个 executable 都有合法 execution role；
4. recommendations 只包含 primary；
5. eligible watchlist 只包含 alternative/watch；
6. Observation 不含执行字段；
7. 输出不含百分比仓位、金额或手数；
8. 外置规则没有进入代码解析或校验；
9. 2026-07-28 回归场景通过 LLM 自查和人工复核；
10. HTML 保持既有展示风格且忠实显示 V3；
11. 复盘 Skill 已升级为只接受 V3；
12. 历史 V1/V2 明确仅归档，不存在未实现的兼容承诺；
13. 单元测试与等价测试全部通过。

## 12. 回滚方案

如果 V3 发布后出现阻断：

- 停止写入 V3，不修改 selection pools 或 mapper base；
- 保留失败的 annotations 和 validator 输出用于诊断；
- 临时恢复 V2 Reasoning/strategy 生成路径；
- 不回滚 Compute、评分、双池或主题证据；
- 不把 V3 文件降写为伪 V2；
- 修复后从同一 mapper base 重新生成 Reasoning，无需重新抓取行情。

## 13. 明确非目标

本期不做：

- I20 或任何外置规则的代码化；
- 自然语言规则解析器；
- 规则生命周期代码校验；
- candidate rule ID 的 Python 拦截；
- 推荐数量硬上限；
- 个股仓位百分比；
- 总仓位百分比；
- 账户金额或手数估算；
- 自动下单；
- 账户管理；
- Compute Pool、Scoreability、评分权重或双池调整；
- HTML 全面重设计。

未来如果需要真实下单数量，应单独设计账户执行层，输入真实账户、价格、止损和
整手规则，由确定性代码计算可买手数，不能重新把仓位计算交给 LLM。
