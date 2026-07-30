# ADR-0005：Memory 专家规则系统

- 状态：Accepted
- 日期：2026-07-30
- 范围：`memory/` 规则治理与策略推理
- 关联：[术语表](../glossary.md)

## 背景

现有 Memory 规则由复盘发现并按证据生命周期治理。系统尚不能明确表达“由专家
直接授权生效”的规则，也没有表达专家规则的正式领域模型。

专家规则不能被误建模为一条跳过门槛的 learned rule。两者的生效依据不同：
learned rule 依靠累计证据晋级，专家规则依靠人工授权生效。

## 已确认决策

### 专家规则的生效依据

专家规则是人工授权的执行规则，不是等待系统验证的市场假设。它不经过 learned
rule 的“候选 → 观察中 → 有效”准入流程，也不以历史样本数、命中率或累计经济
效果作为生效门槛。

### 生命周期所有权

专家规则的增加和删除只能由人工执行。系统不得自动创建、删除、停用或修改专家
规则。

人工删除采用物理删除：规则从当前专家规则集中直接移除，不建立 `RETIRED`
墓碑，不保存规则版本、删除人、删除原因或规则级审计历史。

删除不回写历史产物。已有 `strategy.json`、操作快照和 verification 文件保持
原样，即使其中仍引用已删除的 `E` 系列 ID。删除同时移除当前规则正文及该规则
的当前数据。

规则格式无效、必要数据不可用或更高层系统硬约束阻止执行时，系统可以 fail
closed，并记录该次未执行及原因，但这不改变专家规则本身的生命周期状态。

### 统一命名

本领域统一使用“专家规则（Expert Rule）”，不在文件、规则 ID、CLI 或领域对象中
使用 `HUMAN`：

| 元素 | 命名 |
|------|------|
| Canonical 文件 | `memory/EXPERT_RULES.md` |
| 规则 ID | `E001` 起的稳定编号 |
| CLI 命令组 | `ashare-pilot automation rules expert` |
| 领域对象 | `ExpertRule` |

### 冲突优先级

规则冲突先比较决策层级，再比较规则来源，不能用专家来源越级绕过高层约束：

1. 数据有效性、交易范围、不可成交状态和 Schema 合法性等系统不可变约束最高；
2. 继续遵循硬风控、regime、标的资格、入场仓位、评分排序的现有决策层级；
3. 仅在同一决策层级内，专家规则优先于 learned rule；
4. 两条专家规则同层冲突时，优先条件更具体的规则；
5. 仍无法消解时输出 `NO_TRADE_CONFLICT`，停止相关交易建议并提示人工处理。

### 适用范围

专家规则保存在同一 canonical 文件中，并通过 `applies_to` 列表显式路由到实际
消费者：

- `DAILY_STRATEGY`
- `OVERNIGHT_STRATEGY`

一条规则可以指定一个或两个消费者；两者全部指定即表示两个策略流程均适用。专家规则不
使用含义容易漂移的 `MORNING`、`INTRADAY` 或 `SHARED` scope。未列入
`applies_to` 的消费者不得读取或执行该规则。

`OPERATION_GUIDE` 不属于 V1 专家规则消费者，不读取也不执行专家规则。

### 表达与写入边界

专家规则正文使用自然语言，不建设机器表达式 DSL。每条规则使用结构化元数据承载
稳定 ID、名称、适用消费者和决策层级，条件、排除条件与动作使用清晰的自然语言。

V1 最小合同为：

| 字段 | 约束 |
|------|------|
| `id` | CLI 自动分配的 `E` 系列稳定编号 |
| `name` | 简短规则名 |
| `applies_to` | `DAILY_STRATEGY`、`OVERNIGHT_STRATEGY` 或两者 |
| `decision_layer` | `RISK_CONTROL`、`REGIME`、`ELIGIBILITY`、`ENTRY_POSITION`、`RANKING` |
| `condition` | 自然语言触发条件 |
| `exclusions` | 自然语言排除条件列表，允许空列表 |
| `action` | 自然语言执行动作 |

合同不包含状态、版本、作者、时间、证据或评价字段。

系统提供直接 CLI，用于校验并原子化增加、删除和列出专家规则。CLI 是唯一写入
入口；Skill 和 Agent 不直接编辑 canonical 文件。

主要使用方式是一套专家规则管理 Skill：

1. LLM 通过逐步提问理解人工需求；
2. LLM 判断当前系统的数据和接口能力是否支持该需求；
3. LLM 补齐规则的适用范围、决策层级、条件、排除条件和动作；
4. LLM 向人工展示完整规则并取得确认；
5. 只有确认后，LLM 才调用 CLI 写入规则。

Skill 负责语义访谈和规则成文，CLI 只负责确定性校验与持久化，不让 CLI 猜测自然
语言含义。

能力检查必须覆盖条件所需数据、数据在目标决策时点的可用性，以及动作是否有对应
系统接口。例如规则要求“量比大于 1.5”，但系统没有合适的量比数据源时，Skill
必须反馈当前系统不支持该规则，不得调用 CLI，不得假定字段存在，也不得降级为
含义不同的代理指标。

### 系统能力说明书

系统能力以一份供专家规则管理 Skill 读取的自然语言说明书维护。说明书记录当前
可用数据、数据来源、决策时点可用性、适用消费者和可执行动作。系统能力变化时，
对说明书和 Skill 做增量维护。

说明书采用封闭白名单语义：只有明确列出的能力才视为支持，未列出的数据、时点或
动作一律视为当前不支持。每项数据能力注明实际来源文件或 JSON 字段和适用消费者；
每项动作注明可影响的合同字段及不可突破的上层约束。说明书可以列出“量比”等典型
不支持项，以帮助 Skill 给出明确反馈。

能力判断完全由 Skill 中的 LLM 完成。CLI 不读取能力说明书，不判断自然语言条件
是否有数据支持，也不判断动作是否有接口支持；CLI 只处理结构校验和持久化。

### 直接 CLI 旁路

直接调用 CLI 是受信任的专家旁路。调用者被视为已经自行确认系统能力，因此 CLI
允许写入未经过 Skill 语义审查的规则。CLI 的帮助和写入结果必须明确提示：直接
写入绕过语义与能力检查，推荐优先使用 Skill。

CLI 仍须拒绝结构不完整、枚举非法、ID 冲突或无法安全持久化的输入，但这些检查
不代表系统支持规则语义。

CLI 命令表面为：

```text
automation rules expert list [--json]
automation rules expert show E001 [--json]
automation rules expert validate --input rule.json
automation rules expert add --input rule.json [--dry-run]
automation rules expert remove E001 [--yes]
```

`add` 和 `validate` 同时支持 `--name`、`--applies-to`、
`--decision-layer`、`--condition`、`--exclusion`、`--action`，供人工直接
调用。Skill 使用 JSON 输入，避免 shell 对自然语言引号和换行的错误处理。所有
写操作使用原子替换。

删除时，Skill 必须先 `show` 完整规则并取得明确确认，再调用 `remove --yes`。
CLI 未收到 `--yes` 时只展示待删除规则并退出，不修改文件。执行删除后只打印被
删除的 ID，不保存正文或墓碑。

### Skill 布局

专家规则的推荐交互入口为项目 Skill：

```text
.agents/skills/manage-expert-rules/
├── SKILL.md
└── references/
    └── system-capabilities.md
```

Skill 名称为 `manage-expert-rules`。能力说明书放在 reference 中，由 Skill 在访谈
和能力判断时读取；CLI 不读取该文件。

### 写入前确认

Skill 写入前必须执行：

1. 完成访谈、能力检查及重复/冲突检查；
2. 生成结构化草案并调用 CLI `validate` 或 `add --dry-run`；
3. 展示规范化后的完整规则及逐项能力依据；
4. 获得用户对当前完整版本的明确确认；
5. 确认后才调用 CLI 执行持久化。

沉默、含糊回复或对任一字段的修改都不构成确认。字段变化后必须重新 dry-run、
重新展示并再次确认。

语义重复与冲突由 Skill 处理：

- 与现有专家规则语义重复时拒绝新增并指出已有 ID；
- 与现有专家规则冲突时不得自动覆盖，要求人工先删除旧规则或澄清适用条件；
- 与同层 learned rule 冲突时允许新增，但预览必须列出被覆盖的 learned-rule ID；
- 与更高决策层规则或系统硬约束冲突时拒绝新增。

CLI 不执行上述语义判断。

### 存在性生命周期

专家规则采用无状态、无版本模型：

- 规则存在于 `EXPERT_RULES.md` 时立即生效；
- 规则被物理删除后立即不存在；
- 不设置 `DRAFT`、`DISABLED` 或 `RETIRED` 状态；
- 不保存作者、审批人、版本或变更历史；
- 修改按“删除旧规则、重新新增”处理，分配新的 `E` 编号并重新确认；
- 未经确认的 Skill 草案只存在于当前对话，不写入 memory。

规则 ID 永不复用。`EXPERT_RULES.md` 保留仅用于分配编号的单调递增
`next_id`；删除规则不会回退计数器。该计数器不保存任何已删除规则内容。

### V1 不统计有效性

V1 不建设专家规则有效性统计，不创建 `EXPERT_RULE_STATS.json`，不生成评价
sidecar，也不要求规则定义评价期限或正向、负向、中性标准。后续若增加统计，
必须另行定义可取得的数据、评价口径和输出合同。

### 当前决策解释

V1 复用 `DAILY_STRATEGY` 和 `OVERNIGHT_STRATEGY` 现有的 `rules_applied`
字段记录实际命中的 `E` 系列 ID，并在对应 HTML 报告展示规则及其影响。未命中的
专家规则不记录。该信息只解释当前决策，不作为有效性统计。

全局 regime/风险姿态或候选排除没有独立 `rules_applied` 字段时，在现有
`market.notes`、`market_assessment.reasoning_trace`、`strategy.risk_control`
或 `exclusion_overrides[].reason` 中写入命中的 `E` ID，不新增 sidecar。

两个策略 Reasoning 流程在作出决策前读取 `EXPERT_RULES.md`，只选择
`applies_to` 包含自身的规则，并按本文确认的决策层级和冲突优先级执行。

### 初始化与治理检查

`automation memory init` 创建空的 `memory/EXPERT_RULES.md`，初始
`next_id=1`。`automation rules check` 校验文件结构、ID 唯一性、`next_id`
单调性、字段完整性、合法消费者与决策层级。

专家规则不计入 Morning/Shared/Intraday 的 `20/15/15` learned-rule 容量，
也不接受候选、观察、有效、休眠或退役状态。`RULE_GOVERNANCE.md` 增加独立专家
规则章节，并引用本 ADR 确认的冲突优先级。

V1 最多保留 20 条当前专家规则。达到上限后 CLI 拒绝新增，必须由人工删除现有
规则后才能继续添加。该容量与 learned-rule 配额相互独立。

## 待决策

当前没有未决的产品语义；实现细节在本 ADR 被确认后进入开发。
