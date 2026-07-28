# Intraday 选股系统评估与修改意见

- 版本：1.0
- 日期：2026-07-27
- 范围：14:30 尾盘隔夜流水线的召回、评分、过滤、分层、可交易性；不含权重数值标定实验
- 关联：[当前 Intraday 选股、评分与过滤流程](current-intraday-stock-selection.md)、[盘中主题证据链 ADR](adr/0003-intraday-theme-evidence-contract.md)、[盘中主题证据链实施清单](intraday-theme-evidence-implementation.md)
- 状态：已实施并由 [ADR-0004](adr/0004-intraday-selection-pools-contract.md)
  取代；本文仅保留历史问题与决策来源，不作为当前生产契约

## 1. 结论摘要

当前系统是**可审计、可回放、边界清楚的工程化选股漏斗**，不是单层“总分过线即推荐”模型。Compute 与 Reasoning 分工正确：分数/档位/执行态由 Python 独占，LLM 只写语义与仓位，发布前有强校验。

相对历史问题（VWAP 字段错误、涨幅硬杀导致空池、百分位无绝对地板），设计已明显收敛。剩余问题主要是**策略合同断层**，而非“再调几个权重”：

1. Theme Continuity 名实不符，主题热度不进分；
2. 资金流 partial 对绝对地板不 fail-closed；
3. 封板/不可交易标的占 Opportunity Pool 名额后再观望；
4. 相对 A/B/C 在弱质量日仍可能显得“好看”，最终安全高度依赖规则与校验器。

**总评：工程成熟度高，策略闭环未完成。** 优先修合同与 fail-closed，再谈权重标定。

## 2. 现状优点（应保留）

| 能力 | 说明 | 修改时约束 |
|------|------|------------|
| 五层串联 | 广域召回 → 评分前硬过滤 → 九维相对分 → 绝对地板与 A/B/C → Reasoning/发布校验 | 不合并回单层黑箱打分 |
| 相对分 + 绝对地板 | 缓解“全池再差也有 A” | 地板只能收紧或明确降级，不可删除后无替代 |
| I10 / I11 / I13 / I14 | 弱市资金缩放、异常替换、极弱零仓、VWAP 豁免 | 改行为必须同步 INTRADAY Contract |
| `execution_state` Python 独占 | 封板、涨停价、板块资格不可被 annotation 覆盖 | 不把 eligible 交给 LLM |
| 单次快照缓存 | `.cache/intraday/{date}/` 固定中间 JSON | 禁止同日多阶段混用不同时刻行情 |
| 调参分层（现状文档 §11） | 改哪一层、同步哪些文档/测试清晰 | 本提案的变更也按层登记 |

## 3. 问题清单与修改意见

优先级：

- **P0**：直接扭曲排序或可交易池质量，应先做；
- **P1**：容量/安全/可解释性；
- **P2**：文档与注释漂移、次要公式细节。

### 3.1 P0-A：Theme Continuity 名实不符

**现状**

- 九维中 Theme 权重 18%。
- raw 实际为：`source_pool` 等级（limit_up / turnover / gain_range）+ 个股主力净流入 sigmoid。
- `theme_ranking.json`（core_heat / diffusion_heat）**不进入** `overnight_score`。
- ADR-0003 明确暂不修改 overnight 权重与“主题如何影响策略”。

**风险**

- 感知层有主题、选股层无主题 → 主线溢价无法进入排序；
- 规则/LLM 若按“Theme Continuity = 主题延续”解释分数，会系统性误读；
- 与“隔夜 alpha ≈ 主线延续 + 个股质量”的产品叙事不一致。

**修改意见（二选一，禁止第三种：LLM 临时加分）**

#### 方案 A（推荐）：确定性接入主题证据

在评分前为每只股票计算只读字段，例如：

```text
theme_support_raw =
    f(primary_theme.core_heat 或 rank,
      membership_tier: core|qualified|edge,
      member weight)
```

再并入 Theme Continuity raw，建议形态：

```text
ThemeRaw =
    SourceProxy × α
  + ThemeSupport × (1 − α)
```

约束：

- α 初始可取 0.4～0.6，必须写死在代码与 Contract，禁止运行时由 LLM 改；
- 无主题归属或 ranking 缺失时：ThemeSupport 用中性值（如 0.5）并记 `theme_support_missing`，**不要**静默当 0 或当 1；
- 不改变 ADR 的“主题层不决定买卖”：主题只影响排序证据，方向/仓位仍由规则与校验决定；
- 若采纳，需修订 ADR-0003 的“不修改 overnight_score”边界，或另开 ADR 说明例外范围。

#### 方案 B：改名并降权叙事

若短期不接 ranking：

- 将维度展示名改为 `SourceCapitalProxy`（或同等语义）；
- 同步 `INTRADAY_RULES` I02、`intraday-strategy` SKILL、本现状文档；
- 明确 Theme Ranking 仅解释与交叉验证，**不得**被 Reasoning 当作已计入总分的证据。

**验收**

- 同池回放：主题 core 成员相对 edge/无主题，在其它维相近时排序方向符合预期（方案 A）；
- 或文档/规则全文不再出现“Theme Continuity = 主题热度”的错误表述（方案 B）；
- 单元测试锁定 raw 公式与缺失行为。

**建议改动位置**

- `strategy/_commands/overnight/score.py`（raw / breakdown 字段名）
- 主题字段来源：mapper base 或 enrich 阶段的确定性主题合同
- `memory/INTRADAY_RULES.md` I02 Contract
- `.agents/skills/intraday-strategy/SKILL.md`

---

### 3.2 P0-B：资金流 partial 放宽绝对地板

**现状**

- 绝对地板要求主力净流入 `> 0`。
- `threshold_reached` 且未返回：明确资金地板失败。
- `partial` 且未覆盖：**不**把缺失当 0，也**不**执行该票的资金净流入地板。
- 全池 `unavailable`：跳过资金地板 + warning。

**风险**

- 未覆盖票可凭其它百分位维度进入 Top 30；
- 样本日（2026-07-27 缓存）partial 覆盖 100/120，地板失败 33 仍能凑满 30；
- 属于非 fail-closed，与“绝对质量”语义冲突。

**修改意见**

按数据质量分支，收紧为：

| `money_flow_quality` | 未覆盖 / 缺失股票行为 |
|----------------------|------------------------|
| `complete` | 维持：无流入或 ≤0 → `floor_pass=false` |
| `threshold_reached` | 维持：未达门槛 → 资金地板失败 |
| `partial` | **新增**：未覆盖 → `floor_pass=false`，`floor_reason=money_flow_uncovered`；或进入机会池必须 `degraded=true` 且 Reasoning 最高 Watch |
| `unavailable` | 维持跳过资金地板，但机会池默认 `degraded=true`，I 类规则倾向全观望（与空池降级一致） |

推荐默认：**partial 未覆盖 = 地板失败**（真正 fail-closed）。若担心空池，使用已有 degraded 路径，而不是静默放行。

**验收**

- fixture：partial 覆盖 80/120 时，未覆盖票不得出现在非 degraded 的 opportunity_pool；
- unavailable 时输出 warning + degraded 标记可测；
- 冻结回放对比 Top 30 变动可解释（仅资金覆盖相关）。

**建议改动位置**

- `strategy/_commands/overnight/score.py` 绝对地板逻辑
- 资金流 enrich 的 quality 字段契约（若需更细粒度 per-stock coverage flag）

---

### 3.3 P1-A：封板 / 不可交易占坑

**现状**

- 涨停/封板不在评分前硬过滤；
- 可占 A/B/C 与 Top 30；
- mapper base 生成 `execution_state` 后强制观望；
- skill 文档仍写“先剔除不可交易再评分”，与实现不符。

**风险**

- 可交易候选被挤出 30 名额；
- 展示上 A 档很多，可下单很少。

**修改意见**

在 **Opportunity Pool 截断之前** 增加可交易优先策略（不必从评分池物理删除，以便审计）：

```text
排序键：
  1. execution_eligible 或 provisional_tradable 降序（可交易优先）
  2. overnight_score 降序
截断 Top N
```

实现要点：

- 在 score 之后、或 build opportunity 时，用与 `execution_state` **同一套**封板/涨停价规则做 `provisional_eligible`（避免两套涨停算法）；
- 封板票仍可保留在 scored 全量列表供解释，但**默认不占** opportunity 名额；
- 若可交易不足 N：允许用封板填满并全部标记观望，同时 `pool_warning=sealed_padding`。

**验收**

- 构造 15 只封板高分 + 20 只可交易中分：Top 30 应优先 20 只可交易；
- 校验器行为不变：封板仍只能观望；
- 更新 skill：删除或改写“先剔除再评分”为“评分后按可交易优先截断”。

**建议改动位置**

- opportunity pool 构建（`score.py` 或 overnight build 前序）
- 与 `execution_state()` 共享涨停/封板纯函数
- `.agents/skills/intraday-strategy/SKILL.md`、相关 perception skill 表述

---

### 3.4 P1-B：相对档位与绝对质量偏松

**现状**

- A/B/C 为池内名次百分比，无 75/60/45 固定分线；
- 地板仅：主力 `> 0`、Trend raw `≥ 0.3`；
- 样本最高分约 66～70 仍有 A；C 常被 A/B 占满。

**风险**

- 弱质量日 UI/层级仍“好看”；
- 安全依赖 I13 与 LLM 规则，分数本身不表达“值不值得做”。

**修改意见（可叠加，建议先做小步）**

1. **机会池绝对分可选门槛**（配置化，默认可先关闭或设低）  
   例如 `min_overnight_score_for_opportunity`；低于门槛的 A 仍可保留在 scored 列表，但不进 opportunity，或强制 `degraded`。

2. **收紧 Trend 地板**  
   无技术数据时 Trend raw 从 0.5 改为 **0.2 或缺失失败**（见 3.6），避免“缺数据反而过线”。

3. **档位展示与 tradeability 解耦加强**  
   报告/HTML 明确：`rank_tier` ≠ 可买；主展示以 `tradeability` + `execution_state.eligible` 为准（多为文档与渲染，不一定改分）。

4. **不建议**立刻恢复固定 75/60/45 作为唯一分档（与已收敛的 rank_tier 语义冲突）；若需要绝对语义，用 floor / min_score，而不是改 A 的百分比定义。

**验收**

- 配置开关下回放：弱分日 opportunity 变少或 degraded 增多，而不是 silent 满 30 个 A/B；
- I02 Contract 写清 rank_tier 与绝对门槛关系。

---

### 3.5 P1-C：板块过滤双轨

**现状**

- Scan Pool：排除前缀，无 override；
- mapper `execution_state`：最长前缀 + override。

**风险**

- 早期被删的票无法被后续 override 恢复。

**修改意见**

- 抽公共 `trading_scope.is_in_scope(code) -> bool`，Scan 与 execution 共用；
- 或 Scan 阶段改为“标记 out_of_scope”而非物理删除，最终以 execution 为准（更可审计，池子略大）。

**验收**

- 对 `trading-scope.json` 含 override 的 fixture：Scan 与 execution 结论一致。

---

### 3.6 P2：次要公式与文档漂移

| 项 | 意见 |
|----|------|
| 技术缺失 Trend=0.5 | 改为缺失分位中性但 **floor 失败**，或 raw=0.2；禁止“缺数据更易过地板” |
| I14 判断顺序 | 文档写清业务意图：小偏离+高 QS → 更严 `watch`；若业务要“越好越宽松”，需改判定表并测 |
| QuickScore Momentum | 7%～9% 与涨停同落 0.3 是否合理：若保留 limit_up 高 MarketAlign，应在注释写明“有意”；否则为 7%～9% 单独档 |
| amount 未进 QuickScore | 可选：用 log(amount) 替换或补充 TurnoverCapacity，避免只靠换手率 |
| Scan 注释四路 vs 三路 | 改代码注释与 skill 为三路，或恢复 concept leads 并写清优先级 |
| score.py / CLI 仍写 V1.1 五维 | 统一为 V1.2 九维 |
| 主题 Continuation 固定 10 | 仍属 ADR 暂缓；接 Theme 进分时不要依赖该假维度 |
| confidence 不参与排序 | 可保持；若 partial/unavailable，建议在 opportunity 元数据暴露 `confidence` 供 Reasoning 降级 |

## 4. 建议实施顺序

```text
阶段 0  文档对齐（P2 漂移）
        - 三路召回、V1.2 九维、rank_tier ≠ tradeability、封板时机
        - 不改行为，降低 LLM 合同误读

阶段 1  P0-B 资金 partial fail-closed
        - 行为变更小、收益明确、易测

阶段 2  P1-A 可交易优先截断 Opportunity
        - 与 execution_state 共用纯函数
        - 直接改善“能下单的池子”

阶段 3  P0-A 主题进分（方案 A）或改名（方案 B）
        - 方案 A 需 ADR 边界修订 + 主题字段合同稳定
        - 方案 B 可与阶段 0 合并，作为 A 的前置

阶段 4  P1-B/P1-C 绝对门槛配置化 + trading scope 统一
        - 有前向验证后再收紧默认阈值
```

原则：

- **先 fail-closed 与占坑，再主题进分，最后调权重**；
- 任何公式/门槛变更同步：`INTRADAY_RULES` Contract、相关 SKILL、单元测试、冻结回放、[现状文档](current-intraday-stock-selection.md)、本文状态。

## 5. 明确不做（本提案范围外）

- 用 LLM 改 `overnight_score` / tier / 止损价 / execution_state；
- 恢复涨幅硬杀 6% 一类与召回目标对打的过滤器；
- 无回放数据的大规模权重搜索；
- 把主题层做成“自动下单决策层”；
- 一次 PR 同时大改九维权重 + 主题接入 + 地板（不可归因）。

## 6. 成功标准

系统在行为上满足：

1. **名实一致**：Theme 维要么真用主题证据，要么改名且规则不再误读；
2. **数据降级可预期**：partial/unavailable 不会静默抬高不可信票；
3. **机会池以可交易为先**：封板不无声占满 Top N；
4. **相对排序 + 绝对质量**：A 仍表示相对名次，但进机会池有可配置的绝对约束与 degraded 语义；
5. **文档 = 代码**：召回路数、权重版本、过滤时机与 skill 一致。

## 7. 与现状风险表对照

| 现状文档 §10 | 本提案 |
|--------------|--------|
| 1 Theme 名实不符 | §3.1 P0-A |
| 2 资金 partial 放宽地板 | §3.2 P0-B |
| 4 板块过滤双轨 | §3.5 P1-C |
| 5 封板后观望占坑 | §3.3 P1-A |
| 6 I14 顺序 | §3.6 |
| 7 技术缺失不保守 | §3.4 / §3.6 |
| 8–11 文档漂移 | 阶段 0 + §3.6 |

## 8. 修订记录

| 版本 | 日期 | 说明 |
|------|------|------|
| 1.0 | 2026-07-27 | 初版：基于 current-intraday-stock-selection v1.1 的评估与修改意见 |
