# Daily Theme 迁移至 Step 1 重构方案

**版本：** v2

**日期：** 2026-07-29

**状态：** Proposed

**范围：** `daily-market-analysis` Step 1 / Step 2、Daily Theme 合同与耗时观测

**关联：** `daily-news-brief`、`daily-stock-mapping`、`daily-strategy`

## 1. 决策摘要

将 Daily Theme 的所有权从 Step 2 迁移到 Step 1，并同时重构 Theme
生成方式：

1. Step 1 由 `sector-analyst` 子代理黑盒执行；
2. Step 1 顺序完成新闻抓取、Theme 证据准备、LLM 语义注释和 Python
   确定性组装；
3. LLM 不再直接编写完整 `themes.json`；
4. Step 2 改由 `equity-analyst` 执行，只负责主题股票池、技术数据、个股
   语义标注和 Mapper；
5. `themes.json` 直接升级为 `daily_themes.v2`，所有生产者、消费者、
   validator、fixture 和文档在同一变更中完成切换；
6. 删除 `daily_themes.v1`、旧Theme CLI、旧公共API、旧Skill规则和全部
   compatibility reader/writer，不提供双写、委托或运行时开关；
7. 流程仍在 09:20 启动，不将新闻或 Theme 工作提前到 09:20 之前。

目标流程：

```text
Step 1: sector-analyst
news fetch
  -> news.json + news.md
  -> Python theme evidence
  -> LLM theme annotations
  -> Python finalize + validate
  -> themes.json

Step 2: equity-analyst
themes.json
  -> prepare stock universe/indicators
  -> LLM mapper annotations
  -> Python finalize + validate
  -> mapper.strategy_view.json

Step 3: portfolio-manager
mapper.strategy_view.json
  -> strategy draft
  -> Python finalize + validate
  -> strategy.json + daily_report.html
```

仅把当前 `theme_llm` 原样移动到 Step 1 不属于本方案，因为那只会改变
耗时归属，不会降低总耗时或提高正确性。

## 2. 当前问题

### 2.1 Step 1 缺少明确派发合同

当前 Step 1 只有 Agent 名称和任务清单，没有 Step 2、Step 3 已经具备的
固定 `Action`、精确 prompt 和黑盒边界。主编排容易直接执行新闻命令，
导致 `macro-strategist` 没有被派发。

同时，`news fetch --output-dir` 已经确定性生成 `news.json` 和 `news.md`。
如果没有额外语义任务，Step 1 子代理接近空壳。

### 2.2 Theme LLM 职责过载

当前 LLM 对每个主题同时负责：

- 新闻相关性与匹配置信度；
- market action、emotion、capital、policy、catalyst 判断；
- news density；
- direction coefficient；
- Base Heat 和 Final Heat 运算；
- status 与 rank；
- `matched_concepts`、evidence 和完整 JSON 装配。

其中 news density、系数换算、公式、状态和排序均为确定性工作。

2026-07-29 冻结产物中：

| 指标 | 数值 |
|------|-----:|
| Theme 输入行 | 21 |
| Theme-News 关系 | 53 |
| `.theme_evidence_input.json` | 21,419 bytes |
| `themes.json` | 13,567 bytes / 447 lines |
| evidence 到 themes 实际区间 | 约 133.8 秒 |
| Python Step 2 prepare | 约 7.6 秒 |

### 2.3 Theme evidence 丢失匹配来源

Python 使用 Theme Library 的 name、alias、keyword、concept 完成召回，
但当前临时输入只保留：

```json
{"name": "主题名", "items": [...]}
```

LLM 无法直接知道：

- 命中了哪个 term；
- term 属于 name、alias、keyword 还是 concept；
- 哪些 concepts 实际命中；
- 新闻是强匹配还是宽松召回。

随后又要求 LLM 计算 confidence 和 `matched_concepts`，造成不必要的
二次推断。

### 2.4 无效上下文

2026-07-29 的 `unmatched_high_priority` 有 40 条，紧凑序列化后约占
Theme evidence 业务负载的 36.9%。当前规则禁止用这些行创建主题或
重新查询 Theme Library，因此它们没有 Theme LLM 消费者。

### 2.5 完整 Theme 合同没有被完整验证

当前 `validate-themes` 没有验证：

- subscores 是否齐全、类型和范围是否正确；
- news density 是否与接受的新闻证据一致；
- emotion coefficient 是否与主题注意力方向一致；
- Base Heat、Final Heat 和 Policy Bonus 公式；
- status 阈值；
- rank 连续性和排序；
- evidence 是否来自当日 `news.json`；
- Theme 名称是否与 evidence 输入一致。

2026-07-29 的产物存在 density、status 和排序不一致，但仍通过验证。

### 2.6 Skill 上下文过大

当前 `daily-stock-mapping/SKILL.md` 为 895 行、约 46.9 KB。Theme
阶段之后约 28.7 KB 的股票池、指标和 Mapper 规则在 Theme 推理时已经
进入上下文。

Theme 和股票层拆分后，两类子代理只加载各自所需规则。

## 3. 目标与非目标

### 3.1 目标

- Step 1 必须真正通过指定子代理执行；
- Theme 语义判断只读取紧凑、完备、可追踪的输入；
- Python 负责全部确定性计算、排序、状态推导和正式合同装配；
- `daily_themes.v2` 成为唯一正式Theme合同；
- 所有下游直接读取v2字段，不保留v1兼容分支；
- Step 2 只保留一个 Mapper LLM 阶段；
- 每个 LLM 阶段由拥有该产物的子代理自行验证和最多修复一次；
- 主编排只做存在性 gate 和子代理派发，不编辑 Step 1/2/3 产物；
- 09:20 后启动，整体仍以 09:35 前发布为目标。

### 3.2 非目标

- 不调整模型、temperature 或 reasoning 等级；
- 不改变 `daily_strategy.v3`；
- 不改变 Theme Library 的持久化结构或主题成员关系；
- 不引入 09:20 前预抓新闻；
- 不在本次重构中并发请求高风险市场数据接口；
- 不把 Theme 分析强制加入所有独立的 `daily-news-brief` 请求。

## 4. 新的步骤与 Agent 边界

### 4.1 Step 1：News and Theme Perception

**Agent：** `sector-analyst`

选择 `sector-analyst` 的原因：

- Theme taxonomy、行业映射和主题证据判断属于 sector perception；
- 新闻抓取本身是确定性命令，不需要单独占用 macro LLM；
- `macro-strategist` 保留用于独立宏观、政策和跨市场分析，不再作为
  Daily Step 1 的空壳执行器。

Step 1 精确派发格式：

```text
Load skills `daily-news-brief` and `daily-theme-extraction` and execute in order.

Date: {YYYY-MM-DD}

Outputs:
- predict/{YYYY-MM-DD}/news.json
- predict/{YYYY-MM-DD}/news.md
- predict/{YYYY-MM-DD}/themes.json
```

主编排禁止内联新闻、Theme 输入、公式或 validator 错误。

Step 1 内部顺序：

1. `themes daily prepare --fetch-news` 在同一进程内拉取新闻并生成
   Theme LLM 临时输入；
2. LLM 写精简 Theme annotations；
3. `themes daily publish` 在内存中校验 annotations、计算并完整校验
   正式合同，通过后原子发布 `themes.json`；
4. 若 annotations 校验失败，由同一 Step 1 子代理修复一次并重新运行
   `publish`；
5. 第二次 annotation 失败或任何确定性合同错误均停止，不进入 Step 2。

`news.md` 使用脚本生成的可读层。Daily pipeline 不再要求 LLM
重新组织 `news.md`，避免增加与机器合同无关的耗时。

### 4.2 Step 2：Stock Mapping

**Agent：** `equity-analyst`

Step 2 精确派发格式：

```text
Load skill `daily-stock-mapping` and execute.

Date: {YYYY-MM-DD}

Inputs:
- predict/{YYYY-MM-DD}/news.json
- predict/{YYYY-MM-DD}/themes.json

Outputs:
- predict/{YYYY-MM-DD}/theme_stocks.extra.json (optional)
- predict/{YYYY-MM-DD}/theme_stocks.universe.json
- predict/{YYYY-MM-DD}/theme_stocks.base.json
- predict/{YYYY-MM-DD}/theme_stocks.json
- predict/{YYYY-MM-DD}/mapper.annotations.json
- predict/{YYYY-MM-DD}/mapper.json
- predict/{YYYY-MM-DD}/mapper.strategy_view.json
```

Step 2 不再：

- 生成 `.theme_evidence_input.json`；
- 生成或修复 Theme annotations；
- 编写 `themes.json`；
- 记录 `theme_llm` 耗时；
- 加载 Theme heat 的完整语义 rubric。

Step 2 直接消费 Step 1 已原子发布的 `daily_themes.v2`；不再重复运行
Step 1 validator，也不由 Step 2 或主编排修改 Step 1 产物。

### 4.3 Step 3：策略职责不变，Theme读取同步升级

Step 3 继续由 `portfolio-manager` 黑盒执行 `daily-strategy`。
策略决策职责和 `daily_strategy.v3` 不变，但所有直接读取
`themes.json` 的 strategy prepare、finalize 和 report renderer 必须在
同一变更中改为只接受 `daily_themes.v2`。任何v1输入均fail closed。

## 5. Skill 结构

### 5.1 保持 `daily-news-brief` 通用

`daily-news-brief` 继续只定义：

- 新闻源；
- `news fetch` 命令；
- `daily_news.v1`；
- `news.md` 可读格式。

独立请求新闻简报时不自动运行 Theme 分析。

### 5.2 新增 `daily-theme-extraction`

新增：

```text
.agents/skills/daily-theme-extraction/
  SKILL.md
  references/
    theme-semantics-rubric.md
```

`SKILL.md` 只包含：

- prepare -> annotations -> finalize 的执行顺序；
- 临时输入和注释输出路径；
- 一次修复规则；
- 禁止读取项；
- timing 记录要求。

语义评分细节只放在 `theme-semantics-rubric.md`。Skill 不包含股票池、
技术指标、Mapper 或 Step 3 规则。

### 5.3 收缩 `daily-stock-mapping`

删除或迁出：

- Theme Extraction 全章；
- `themes.json` LLM 输出示例；
- Theme policy/catalyst/heat 计算规则；
- `theme_llm` timing 指令。

保留：

- `themes.json` 输入 gate；
- Theme Library 到股票池的确定性成员关系；
- indicators、filters、mapper annotations 和 finalize；
- Step 2 -> Step 3 合同。

## 6. Theme 临时合同

### 6.1 Python 输入：`.theme_evidence_input.json`

升级临时 schema：

```json
{
  "schema_version": "theme_evidence_input.tmp.v2",
  "date": "YYYY-MM-DD",
  "themes": [
    {
      "name": "AI算力",
      "matched_concepts": ["算力", "数据中心"],
      "evidence": [
        {
          "refs": ["news#12", "news#48"],
          "category": "flash",
          "source": "财联社",
          "title": "算力中心供配电架构迎革新",
          "desc": "...",
          "matches": [
            {"kind": "alias", "term": "算力中心"},
            {"kind": "concept", "term": "数据中心"}
          ]
        }
      ],
      "market_signals": {
        "available": false,
        "trace": "no structured theme market signal"
      }
    }
  ]
}
```

规则：

- `name` 必须直接来自 Theme Library；
- `matches[].kind` 只允许 `name`、`alias`、`keyword`、`concept`；
- `matched_concepts` 由 Python 从实际命中关系生成；
- 相同标题可合并，但必须保留全部 canonical `news#id`；
- 不再写 `unmatched_high_priority`；
- 不包含 Theme Library 全量主题、股票候选、Mapper 或 strategy 字段；
- 若已有单快照主题市场信号，可由 Python写入 `market_signals`；
- 不允许 Theme LLM 为获取 market action 读取未来的 Step 2 产物。

### 6.2 LLM 输出：`.theme_annotations.json`

新增非正式中间合同：

```json
{
  "schema_version": "daily_theme_annotations.v1",
  "date": "YYYY-MM-DD",
  "themes": [
    {
      "name": "AI算力",
      "accepted_refs": ["news#12"],
      "confidence": 82,
      "attention_direction": "bullish",
      "market_action": 65,
      "emotion_raw": 80,
      "capital": 45,
      "policy_tier": "none",
      "policy_polarity": "neutral",
      "policy_ref": null,
      "catalyst": null,
      "reason": "算力催化与正向市场表现一致"
    }
  ]
}
```

LLM 只拥有以下语义字段：

| 字段 | 所有者 | 说明 |
|------|--------|------|
| `accepted_refs` | LLM | 从该主题输入 evidence 的 canonical refs 中选择 |
| `confidence` | LLM | 对接受证据与主题关系的整体置信度 |
| `attention_direction` | LLM | `bullish/mixed/panic/neutral/unknown` |
| `market_action` | LLM | 依据已提供新闻/结构化市场信号分档 |
| `emotion_raw` | LLM | 方向无关的关注度 |
| `capital` | LLM | 无有效资本证据时必须为45 |
| `policy_tier` | LLM | `none/local/ministry/state_council/national_strategy` |
| `policy_polarity` | LLM | `bullish/neutral/bearish` |
| `policy_ref` | LLM | 非 `none` 时必须来自 accepted refs |
| `catalyst` | LLM | 合格催化类型和 canonical evidence，默认null |
| `reason` | LLM | 简短可审计说明 |

LLM 不输出：

- `rank`；
- `status`；
- `heat`；
- `news_density`；
- `emotion_coefficient`；
- `base`；
- policy bonus数值或乘法结果；
- `matched_concepts`；
- 完整 `themes.json`。

## 7. Python 正式组装规则

新增一个共享的 Theme finalizer，负责从 v2 evidence 和 annotations
生成唯一正式合同 `daily_themes.v2`。不生成v1投影。

### 7.1 Evidence 与 coverage

- 每个 evidence 输入主题必须恰好有一条 annotation；
- annotation 不得增加输入中不存在的主题；
- `accepted_refs` 必须是该主题 evidence 内 canonical refs 的子集；
- 重复标题组按一个 distinct evidence 计算 density；
- confidence `<60` 的主题仍写入 `themes.json`，但强制
  `status="discarded"`，不再使用“discard”表示删除整行；
- `matched_concepts` 由接受证据对应的 Python match provenance 生成。

### 7.2 确定性计算

```text
emotion_coefficient:
  bullish -> 1.0
  mixed   -> 0.8
  panic   -> 0.5
  neutral -> 0.8
  unknown -> 0.8

news_density = min(distinct_accepted_evidence_count, 10) / 10 * 100

base =
  market_action * 0.45
  + emotion_raw * emotion_coefficient * 0.30
  + news_density * 0.15
  + capital * 0.10

policy_bonus:
  none              -> 0
  local             -> 2
  ministry          -> 5
  state_council     -> 8
  national_strategy -> 10

policy_coefficient:
  bullish -> 1.0
  neutral -> 0.5
  bearish -> 0.0

final_heat = base + policy_bonus * policy_coefficient
```

Catalyst：

- LLM只声明合格的 catalyst 和 evidence；
- Python先计算 `policy_adjusted_heat = base + policy_bonus *
  policy_coefficient`；
- 有合格catalyst时执行
  `final_heat = max(policy_adjusted_heat, 57)`，不额外增加catalyst分值；
- 每日最多2个 catalyst promotion；
- 超过2个时按 `policy_adjusted_heat`、confidence、主题名稳定排序取前2个。

所有舍入逻辑必须集中在一个 Python 函数中，并由单元测试锁定；Skill、
validator 和 renderer 不重复实现公式。

### 7.3 Status 与 rank

确定性顺序：

```text
sort key:
  final_heat DESC
  confidence DESC
  name ASC
```

状态：

- confidence `<60`：`discarded`；
- Final Heat `>=55`：进入 tradeable 候选；
- tradeable 只保留排序前20个，溢出主题为 `discarded`；
- `40 <= Final Heat <55` 且
  `attention_direction == bullish OR market_action >=50`：`watch`；
- 其他：`discarded`。

最终 `rank` 按上述稳定顺序从1连续编号。v1的
`themes[].direction` 字段被删除，只保留语义明确的
`themes[].attention_direction`。它是“主题注意力方向”，不是 Step 3
的股票/策略 `Direction`。

### 7.4 正式合同：`daily_themes.v2`

```json
{
  "schema_version": "daily_themes.v2",
  "date": "YYYY-MM-DD",
  "themes": [
    {
      "rank": 1,
      "name": "AI算力",
      "status": "tradeable",
      "confidence": 82,
      "attention_direction": "bullish",
      "score": {
        "market_action": 65,
        "emotion_raw": 80,
        "emotion_coefficient": 1.0,
        "news_density": 20,
        "capital": 45,
        "base_heat": 61,
        "policy": {
          "tier": "none",
          "polarity": "neutral",
          "bonus": 0,
          "coefficient": 0.5,
          "evidence_ref": null
        },
        "final_heat": 61
      },
      "catalyst": null,
      "matched_concepts": ["算力", "数据中心"],
      "evidence_refs": ["news#12"],
      "reason": "算力催化与正向市场表现一致"
    }
  ]
}
```

v1字段删除映射：

| v1字段 | v2处理 |
|--------|--------|
| `heat` | 删除；唯一值为 `score.final_heat` |
| `direction` | 删除；改为 `attention_direction` |
| `subscores` | 删除；改为结构化 `score` |
| `subscores.base` | 改为 `score.base_heat` |
| `subscores.policy_bonus` | 改为 `score.policy.bonus` |
| `subscores.policy_polarity` | 改为 `score.policy.polarity` |
| `evidence` 字符串 | 删除；改为 `evidence_refs` 数组 |

禁止为旧字段保留别名、重复投影或fallback读取。正式合同只保存一份
Final Heat、一份注意力方向和一组结构化证据引用。

### 7.5 下游合同同步升版

Theme字段会继续投影到股票池、Mapper和Step 3输入，因此直接受影响的
正式合同必须同时升版：

| 当前合同 | 新合同 | Theme投影 |
|----------|--------|-----------|
| `daily_themes.v1` | `daily_themes.v2` | 完整正式Theme合同 |
| `daily_theme_stocks_universe.v1` | `daily_theme_stocks_universe.v2` | `name/rank/final_heat/attention_direction/evidence_refs` |
| `daily_theme_stocks_base.v1` | `daily_theme_stocks_base.v2` | 同上 |
| `daily_theme_stocks.v1` | `daily_theme_stocks.v2` | 同上 |
| `daily_mapper_base.v1` | `daily_mapper_base.v2` | 同上 |
| `daily_mapper.v1` | `daily_mapper.v2` | 同上 |
| `daily_strategy_input.v1` | `daily_strategy_input.v2` | 同上 |

下游紧凑投影统一为：

```json
{
  "name": "AI算力",
  "rank": 1,
  "final_heat": 61,
  "attention_direction": "bullish",
  "evidence_refs": ["news#12"]
}
```

投影使用 `final_heat` 是下游合同自己的字段，不是对v1顶层 `heat` 的
兼容。所有上述v1 schema validator、reader、fixture和示例与
`daily_themes.v1` 一起删除。`daily_mapper_annotations.v1` 不含Theme
投影字段，可保持版本不变；`daily_strategy.v3` 的策略决策合同也不因
输入Theme字段重命名而升版。

## 8. 验证合同

### 8.1 `publish` 的 annotation gate

必须一次收集全部错误：

- schema/date；
- 输入主题 coverage、重复、额外主题；
- score范围和 enum；
- accepted refs 的归属；
- policy tier、polarity、policy ref 一致性；
- catalyst 类型、证据和每日数量；
- reason 类型与最大长度。

### 8.2 `publish` 的正式合同 gate

在现有浅层校验上增加：

- Theme 名称属于 evidence 输入且唯一；
- 每个正式主题恰好对应一个 annotation；
- `matched_concepts` 与 Python provenance 一致；
- `evidence_refs` 全部存在于当日 `news.json`；
- `attention_direction`/coefficient映射；
- news density；
- policy bonus；
- Base Heat 和 Final Heat；
- catalyst floor；
- confidence `<60` 的 discarded约束；
- status 阈值和 tradeable上限；
- rank 连续、唯一且顺序正确；
- 至少一个 tradeable主题的现有 gate。

校验公式必须调用 finalizer 的共享函数，禁止复制第二套公式。

## 9. CLI 与代码布局

新增 Daily Theme 命令组：

```bash
uv run --frozen ashare-pilot themes daily prepare --date YYYY-MM-DD --fetch-news
uv run --frozen ashare-pilot themes daily publish --date YYYY-MM-DD
```

两个业务命令自动记录真实阶段耗时、artifact、count 和 validation
retry。不提供公开的独立 validator、finalizer 或 Step 1 timing 命令；
Agent/LLM 不得手工估算或填写 duration、count、artifact path、
validation retry。

建议代码布局：

```text
src/ashare_pilot/themes/_commands/daily/
  evidence.py
  publish.py
  validate_annotations.py
  finalize.py
  validate.py
  timing.py
  contract.py
```

同一原子变更中直接删除：

```text
ashare-pilot mapping daily build-theme-evidence
ashare-pilot mapping daily validate-themes
ashare_pilot.mapping.build_theme_evidence
```

`themes daily prepare/finalize/validate` 是唯一入口。不得保留旧命令
别名、公共API wrapper、deprecated提示、自动schema迁移或v1 reader。
所有仓库内调用者必须在同一提交中切换完成。

## 10. Timing 归属

### 10.1 新增 `step1_timing.json`

```json
{
  "schema_version": "daily_step1_timing.v1",
  "date": "YYYY-MM-DD",
  "stages": {
    "news_fetch": {},
    "theme_prepare": {},
    "theme_llm": {},
    "theme_finalize": {}
  }
}
```

每个阶段记录：

- duration；
- 输入/输出路径；
- bytes；
- modified_at；
- sha256；
- count；
- validation retry count。

`news_fetch`、`theme_prepare` 和 `theme_finalize` 使用命令内墙钟计时；
`theme_llm` 使用 evidence 产物写入至 annotations 产物写入并完成校验的
时间差。所有 count 和 retry 均由程序从产物及校验状态推导，禁止由LLM
事后补写。

只有同一次 artifact-linked run 的阶段才计算 Step 1 total。

### 10.2 收缩 `step2_timing.json`

Step 2 total stages 改为：

```text
prepare
mapper_annotation_llm
finalize
```

`themes.json` 作为 Step 2 prepare 的上游指纹，不再把 `theme_llm` 记在
Step 2。`indicators` 和 `market_views` 继续作为 prepare 的子阶段诊断。

### 10.3 Pipeline 总耗时

总编排报告应使用：

```text
Step 1 total + Step 2 total + Step 3 total
```

不得通过把 Theme 从 Step 2 移到 Step 1 来掩盖总耗时。验收同时比较
单阶段和09:20至最终发布的端到端 wall time。

## 11. 文件级实施清单

### Phase A：冻结基线

- 固定 2026-07-29 Theme evidence、themes和下游投影 fixture；
- 增加当前错误回放：density、status、rank；
- 记录主题数、接受新闻数、tradeable/watch/discarded数量；
- 记录现有 theme LLM 133.8秒基线。
- 将需要保留的冻结fixture直接重建为v2；历史v1产物仅作归档，不作为
  新代码可读取输入。

### Phase B：Theme Python 合同

- 新增 v2 evidence builder；
- 输出 match kind、term、matched concepts；
- 删除 `unmatched_high_priority`；
- 新增 annotation validator；
- 新增 Theme finalizer；
- 新增只接受 `daily_themes.v2` 的正式 themes validator；
- 增加公式、阈值、排序、证据和coverage测试。

### Phase C：新增 Theme Skill

- 新增 `.agents/skills/daily-theme-extraction/SKILL.md`；
- 迁移 Theme rubric；
- 消除 policy freshness、confidence discard 和 Direction 命名冲突；
- 明确 LLM 只写 `.theme_annotations.json`；
- 明确一次修复由 Step 1 子代理自行完成。

### Phase D：Step 2 收缩

- 从 `daily-stock-mapping` 删除 Theme Extraction；
- 将输入改为 validated `themes.json + news.json`；
- Step 2 timing删除 `theme_llm`；
- `prepare` 不再创建 Theme evidence；
- `theme_stock_universe`、`theme_stock_base`、`theme_stocks`、
  `daily_contract` 和 Mapper投影全部直接读取
  `score.final_heat`、`attention_direction`、`evidence_refs`；
- 删除所有对v1 `heat`、`direction`、`subscores`、`evidence` 的读取。
- 同步输出 `daily_theme_stocks_universe.v2`、
  `daily_theme_stocks_base.v2`、`daily_theme_stocks.v2`、
  `daily_mapper_base.v2` 和 `daily_mapper.v2`。

### Phase E：下游全量切换

- 修改 `src/ashare_pilot/mapping/daily_contract.py`；
- 修改 `theme_stock_universe.py`、`theme_stock_base.py`、
  `theme_stocks.py` 及其validators；
- 修改 `mapper_base.py`、`mapper.py`、`validate_mapper.py`；
- 修改 `strategy_view.py` 并输出 `daily_strategy_input.v2`；
- 修改 daily strategy `llm_input.py`、`finalize.py`；
- 修改 daily `render_report.py`；
- 更新所有单元测试、CLI测试、fixture、文档示例和schema断言；
- 仓库全量搜索确认没有被替换的v1 schema或旧Theme字段消费者；
- 新代码遇到历史v1文件必须明确报错，不自动转换。

### Phase F：主编排切换

- Step 1 改为 `sector-analyst` exact prompt；
- Step 2 改为 `equity-analyst` exact prompt；
- Step 1 gate同时要求并验证 `news.json` 和 `themes.json`；
- 主编排不得修复任何 Step 1/2 artifact；
- 更新输出文件表和 Quick Reference；
- 更新 `.opencode/commands/daily-analysis.md` 的入口说明。

### Phase G：删除旧路径

- 删除旧 Theme Extraction 规则和 reference；
- 删除旧 Step 2 `theme_llm` timing分支；
- 删除旧 mapping CLI和公共Python API；
- 删除v1 validator、schema常量、测试fixture和示例；
- 确认没有 legacy Theme compatibility reader/writer、wrapper或字段fallback；
- 更新 docs、CLI帮助和公共API说明。

以上Phase是开发顺序，不是分批发布顺序。A-G完成并通过全量测试后作为
一个原子切换发布；禁止新旧合同混合部署。

## 12. 测试与回放

### 12.1 单元测试

- name/alias/keyword/concept match provenance；
- exact-title dedup和canonical refs保留；
- unmatched高优先新闻不进入hot input；
- annotation coverage和额外主题；
- accepted ref越界；
- direction coefficient；
- density、base、policy、heat；
- catalyst floor、policy不叠加和每日上限；
- confidence `<60` 强制 discarded；
- watch阈值；
- tradeable top20；
- rank稳定排序；
- 正式 evidence refs存在性；
- Step 2只接受 `daily_themes.v2`；
- 全部被替换的v1 schema和v1字段输入fail closed；
- 仓库内无旧CLI/API/字段fallback。

### 12.2 CLI测试

- `themes daily prepare --fetch-news`；
- `themes daily publish`；
- 旧的 `validate-annotations/finalize/validate` 不再公开；
- 缺少任一 Step 1 输入或正式输出 fail closed；
- 日期不一致 fail closed；
- annotation失败不覆盖现有 `themes.json`；
- 第二次 annotation validation失败后停止。

### 12.3 冻结回放

至少回放：

- 2026-07-29：21个Theme、多条重复新闻、panic和watch边界；
- 一个policy bullish/bearish分流日；
- 一个无policy、无capital信号日；
- 一个 catalyst候选超过2个的压力 fixture；
- 一个零tradeable主题的失败 fixture。

比较层次：

1. evidence召回覆盖；
2. LLM语义字段；
3. Python heat/status/rank；
4. selected tradeable themes；
5. theme stock universe；
6. mapper candidate pool；
7. Step 3 strategy input。

不要求新旧 LLM 分数逐字段完全相同，但任何 selected theme变化必须有
match provenance、accepted refs 和语义注释解释。

## 13. 验收标准

### 13.1 架构

- 主编排日志明确出现 Step 1 `sector-analyst` 子代理派发；
- Step 1 子代理一次完成 news和themes；
- Step 2 使用 `equity-analyst`；
- Step 2 不再生成或修复 `themes.json`；
- LLM 不再输出 rank、status、heat、base、density；
- Python 是正式 `themes.json` 的唯一装配者。

### 13.2 正确性

- `themes daily publish` 的 annotation 与正式合同 gates 均通过；
- heat公式、status和rank零容差一致；
- 所有 evidence 可解析到当日 `news.json`；
- 所有 Theme 名称来自 Theme Library；
- tradeable最多20个；
- Step 2、Step 3和renderer只消费新合同链；
- `themes -> theme_stocks -> mapper -> strategy_input` 的schema依次为
  v2且没有v1 reader；
- 仓库运行时代码不存在被替换的v1 schema、旧CLI、旧API或旧字段读取；
- v1历史文件不会被自动升级或静默接受。

### 13.3 性能

以相同冻结输入和相同执行环境比较：

- Theme hot input删除全部无消费者字段；
- Theme LLM输出字节数显著低于当前13.6KB；
- Theme LLM wall time目标：常态不超过60秒；
- Step 1 + Step 2总耗时低于重构前相同两步总耗时；
- 09:20启动后，完整策略以09:35前发布为最终验收目标。

性能目标不是正确性豁免。若首次回放超过60秒但合同和职责已经正确，
先保留架构，再根据 timing 数据继续压缩语义输入。

## 14. 原子切换与失败处理

本重构不提供运行时回滚路径：

- 不保留v1 producer或consumer；
- 不保留旧CLI、旧公共API、旧Skill分支；
- 不提供schema自动迁移；
- 不双写v1/v2；
- 不允许Step 1生产v2而Step 2/3仍读取v1字段；
- 不使用feature flag在新旧Theme流程之间切换。

发布必须是完整代码版本的原子切换。若发布前验收失败，继续在开发分支
修复，不部署部分改造；若发布后发现阻断问题，只能整体回退到上一个
代码版本并重新生成当日全套产物，禁止复用新旧schema混合的中间文件。

历史 `predict/{date}/themes.json` v1文件保留为不可变审计资料，但新CLI
不会读取、转换或覆盖它们。需要冻结回放时，测试fixture应提前显式
重建为v2，而不是在生产代码中加入迁移器。

## 15. 已锁定业务口径

本次完整整改直接采用以下口径，不保留旧行为分支：

1. 重复标题 density 按去重 evidence组计数，而不是按来源ID数计数；
2. confidence `<60` 保留正式行但标记 `discarded`；
3. tradeable超过20个时，溢出主题标记 `discarded`；
4. 删除 Theme `direction`，只保留 `attention_direction`，且不属于
   Step 3 `Direction`；
5. catalyst超过2个时由Python按稳定排序选择，不要求LLM返工；
6. Daily pipeline的 `news.md` 使用脚本输出，不再进行LLM重排。
7. `policy_tier != none` 必须引用当日、明确点名该主题的policy evidence；
   陈旧政策和仅作背景的政策统一按 `none`，不再保留矛盾的半加分解释。

这些口径必须同时写入 Theme skill、Python共享合同和测试，避免再次
出现文档、LLM输出与 validator 三套规则。
