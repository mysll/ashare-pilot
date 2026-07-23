# ADR-0003：盘中主题证据链与成员分层

- 状态：Accepted
- 日期：2026-07-23
- 范围：概念成分股抓取、主题库成员模型、盘中主题排名、mapper 主题合同
- 关联：[术语表](../glossary.md)
- 实施清单：[盘中主题证据链实施清单](../intraday-theme-evidence-implementation.md)

## 背景

盘中隔夜流程在 14:30 使用已发布主题库中的成员关系，将当天
ComputePool 的涨幅和资金数据聚合为主题排名。主题关系通常来自上一版、常见为
前一交易日收盘后构建的数据；盘中流程不会重新抓取概念成员。

2026-07-23 排查发现：

- 日科化学被列为“AI算力”领涨股，中岩大地被列为“PCB/被动元件”领涨股。
- 两只股票的代码、名称和东方财富概念归属没有串位。日科化学确有算力、液冷
  相关业务；中岩大地因拟收购 PCB 刀具企业而进入 PCB 概念。
- 问题在于盘中排名把所有主题成员视为同等有效，并将涨幅最高成员直接称为
  主题领涨股，未区分产业核心、合格成员与边缘关系。
- 概念成分股接口请求每页 200 条，但实际快照最多返回 100 条。当前代码以
  `len(page) < requested_page_size` 判断结束，使大型概念停在第一页。本地
  495 个概念缓存中有 171 个恰好 100 只，没有任何概念超过 100 只。
- 当前 `fetch-stocks` 在分页中途失败时可能返回部分结果，外层又可能把这些结果
  保存为已完成概念；存在失败概念时命令也没有可靠返回非零退出码，因此批处理的
  “失败后不 build”保护可能失效。
- 主题库构建过程已经为所有通过 eligibility 的成员计算 purity、industry 和
  candidate 分数，但只持久化各 Top N 列表中的分数，其他计算结果被丢弃。
- `intraday_mapper.base.json` 只有聚合主题排名，没有全池股票的确定性主题关系；
  LLM 因而把“沪市主板、深市主板、创业板”写入 `sector`。

## 核心业务边界

主题能力是数据与感知层，不负责决定买哪只股票。

14:30 的数据模型为：

```text
上一版已发布主题关系 × 今日 14:30 ComputePool 行情 = 今日主题观察
```

主题层负责成员关系、成员质量、主题聚合及证据传递。是否优先主线、寻找溢出轮动、
选择独立行情、判断封板可交易性和形成最终仓位，属于策略与执行层。

本 ADR 不修改：

- `overnight_score` 及其选股权重；
- 热门主题如何影响策略；
- 封板、尾盘成交和仓位规则；
- intraday LLM 的方向、风险和 T+1 推理规则。

## 已确认决策

### 1. 概念成分股分页与断点续传

分页指单个东方财富概念板块内部的股票成员分页，由
`ashare-pilot themes concepts fetch-stocks` 负责。

- 按接口实际分页能力逐页获取，直到抓取数量达到接口报告的 `total`。
- 每页成功后保存该概念的分页 checkpoint 和已去重成员。
- 默认模式下，失败概念从失败页继续；已完成概念跳过；未开始概念从第一页开始。
- `--reset` 清除概念成员缓存和分页 checkpoint，所有概念从第一页重新抓取。
- 断点仅服务于当天收盘后的同一轮全量更新。当天必须完成，不设计跨日续传或
  checkpoint 日期保护。
- 任一概念仍未完成时，`fetch-stocks` 返回非零退出码。
- 抓取失败时不执行 `themes library build`，当前已发布主题库保持不变。
- 本次不迁移旧成员缓存状态；新机制上线后直接执行一次 `--reset` 全量抓取。
- 继续使用现有涨跌幅排序，不为跨日恢复改成股票代码排序。

完成条件同时包括：

- 所有目标概念均完成；
- 每个概念抓取数量等于接口报告的 `total`；
- 分页合并后股票代码无重复；
- 不存在失败页或待续传 checkpoint；
- 命令以退出码 0 结束。

### 2. 主题成员三层模型

成员身份统一为：

| `member_role` | 定义 |
|---|---|
| `core` | `anchor=true`，或 `industry_score >= leader_threshold`。 |
| `qualified` | 通过现有 eligibility，但未达到 `core` 条件。 |
| `edge` | 未通过 eligibility 的原始主题成员。 |

本期不引入 `event` 标签。事件型关系如果未通过 eligibility，会自然落入 `edge`。

构建时必须：

- 为所有主题成员持久化 eligibility 结果和 `member_role`；
- 为所有 qualified/core 成员持久化已经计算出的完整评分；
- 不再因为成员未进入 pure/industry/candidate Top N 就丢弃其评分；
- 保留现有 pure、industry、candidate 展示列表及限制。

阈值和权重继续集中在 `config/themes/theme-library-config.json`，不新增独立的
盘中主题排名配置文件。

### 3. 成员聚合权重

`core_heat` 的成员权重：

```text
core      = 1.0
qualified = clamp(purity_score × 0.01, 0, 1)
edge      = 0
```

`diffusion_heat` 只使用 edge 成员：

```text
edge_diffusion_weight = clamp(theme_weight / 10, 0, 1)
```

比例、缩放值和上下限必须来自 `theme-library-config.json`，不得硬编码在排名实现中。

成员身份只描述股票与主题的关系强度，不描述股票本身的投资质量。edge 股票仍可
进入 ComputePool 或被策略选择；它只是不允许代表该主题的核心强度。

### 4. 双领涨股

主题排名同时输出：

- `core_leader`：优先从 core 成员中选择；ComputePool 中没有 core 时允许由
  qualified 兜底，并输出 `leader_role=qualified` 和 `leader_fallback=true`。
  edge 永远不能成为 `core_leader`。
- `momentum_leader`：从全部主题成员中选择当日涨幅最高者，可以是 edge。

这一区分保留市场对边缘事件股的炒作信号，同时不把它误称为产业核心领涨股。

### 5. 核心热度与扩散热度

删除旧 `heat` 字段，不保留兼容别名。

`core_heat` 与 `diffusion_heat` 使用相同的现有五维结构和权重：

| 维度 | 权重 |
|---|---:|
| 加权广度 | 20% |
| 领涨力 | 30% |
| 资金 | 25% |
| 加权平均动量 | 15% |
| 持续性 | 10% |

区别在于输入成员：

- `core_heat` 使用 core 和 qualified；
- `diffusion_heat` 只使用 edge；
- 两者分别使用对应的成员权重。

资金项保留原有跨主题最大绝对值归一化，只取消主题资金分子上的绝对值：

```text
capital_component = signed_theme_inflow / max_abs_theme_inflow × 25
```

净流入加分，净流出扣分。最终热度限制在 0–100。

本期明确暂不修改：

- 持续性固定加 10 分的旧逻辑；
- 领涨幅度使用绝对值的旧逻辑；
- 其他热度维度和权重。

主题排名按 `core_heat` 降序、`diffusion_heat` 降序、主题名称稳定排序。JSON 继续
只保存 Top 15 主题，不扩大主题排名数量。

### 6. 可审计的主题排名合同

`theme_ranking.json` 增加：

- `library_version`：主题库成功构建日期，格式 `YYYY-MM-DD`；
- `membership_as_of`：主题成员关系的构建日期；
- `market_as_of`：本次 ComputePool 行情快照时间；
- Top 15 主题的 `contributors`；
- ComputePool 全部股票的 `stock_themes`。

每个 contributor 至少包含：

- 股票代码和名称；
- `member_role`；
- 本次聚合使用的成员权重；
- purity、industry 等可用静态评分；
- 当日涨幅和主力净流入；
- 对 `core_heat`、`diffusion_heat`、`core_leader` 或
  `momentum_leader` 的贡献标识。

`stock_themes` 不受主题 Top 15 截断影响，但保持紧凑，只保存全池股票的确定性
主题关系和成员评分，不展开所有主题的排名详情。

### 7. mapper 主题字段

mapper 确定性生成并传递：

| 字段 | 含义 |
|---|---|
| `market_board` | 沪市主板、深市主板、创业板等交易板。 |
| `primary_theme` | 按确定性规则选择的主要投资主题。 |
| `themes` | 股票的完整主题关系、成员身份和评分。 |
| `sector` | 兼容字段，由构建器令其等于 `primary_theme`。 |

`primary_theme` 的稳定选择顺序为：

1. core 优先于 qualified，qualified 优先于 edge；
2. 同角色按 `industry_score`；
3. 再按 `purity_score`；
4. 再按主题成员权重；
5. 最后按主题名称稳定排序。

LLM annotations 不得编写或覆盖 `sector`、`market_board`、`primary_theme`、
`themes`、主题热度、领涨股和成员评分。

### 8. 验证边界

采用以下信任边界：

> 外部输入在入口验证；LLM 输出在信任边界验证；确定性代码输出由测试保证。

生产运行时验证：

- 东方财富分页完整性、数量、重复代码和失败状态；
- LLM 枚举、必填解释、交易不变量，以及禁止覆盖确定性主题字段。

不为确定性代码生成的 member_role、primary_theme、主题热度、领涨股和版本传递
增加重复运行时验证。它们由单元测试、性质测试和固定样例测试保证。

## 明确排除

本 ADR 不包括：

- 自动识别事件型主题关系；
- 跨日恢复概念成员分页；
- 保存全部主题排名；
- 兼容旧 `heat` 字段；
- 重写持续性或领涨力公式；
- 在主题层计算 `tradability`；
- 规定策略如何使用 `core_heat` 或 `diffusion_heat`；
- 修改个股隔夜评分、推荐阈值、方向和仓位。

## 结果

主题层将能准确表达“主题核心成员是否活跃”和“边缘成员是否扩散”，并为策略层
提供带版本、双时点和成员证据的事实合同。策略仍可选择热门主题内未充分上涨的
股票、主线溢出方向或非热门独立机会，但不再依赖 LLM 猜测个股主题，也不会让
低纯度事件股无条件代表整个主题。

