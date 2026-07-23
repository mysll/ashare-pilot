# 盘中主题证据链实施清单

- 版本：1.0
- 日期：2026-07-23
- 范围：ADR-0003 的代码、合同、测试和全量重建步骤
- 关联：[ADR-0003](adr/0003-intraday-theme-evidence-contract.md)、[术语表](glossary.md)

## 实施原则

- 按“抓取完整性 → 主题成员模型 → 动态排名 → mapper 合同”的顺序实施。
- 主题层只提供数据，不修改隔夜选股策略。
- 确定性字段只允许 Python 构建器生成，LLM 只能消费和解释。
- 今天的新主题库通过一次 `--reset` 全量抓取生成，不迁移旧缓存状态。

## 第一阶段：概念成分股分页

涉及：

- `src/ashare_pilot/themes/datasource.py`
- `src/ashare_pilot/themes/_commands/concepts_fetch_stocks.py`
- `.cache/theme-library/` 中的分页 checkpoint
- `update_theme.bat`
- `update_theme_stock.bat`

任务：

- [ ] 将单概念成员抓取改为真正的多页循环，使用接口报告的 `total` 判断完成。
- [ ] 定义单概念分页结果，明确区分 complete、partial 和 failed，禁止用非空列表
      隐式表示成功。
- [ ] 每页成功后保存累计去重成员、下一页和接口 total。
- [ ] 默认模式从失败页继续，已完成概念跳过。
- [ ] `--reset` 清除成员缓存和分页 checkpoint，所有概念从第一页开始。
- [ ] 任一概念未完成时，命令返回非零退出码。
- [ ] 确认两个更新批处理只在 `fetch-stocks` 返回 0 后执行 library build。
- [ ] 全部完成后清理失败状态和分页 checkpoint。

完成标准：

- 超过100只成员的概念能保存完整成员。
- 中间页失败不会发布部分概念。
- 默认重跑从失败页继续。
- `--reset` 重跑从第一页开始并覆盖所有概念。
- 存在失败概念时批处理不会执行 build。

## 第二阶段：主题成员模型

涉及：

- `config/themes/theme-library-config.json`
- `src/ashare_pilot/themes/_commands/library_build.py`
- `data/theme-library/themes/*.json`
- `data/theme-library/stocks/*.json`
- `data/theme-library/index/*.json`

任务：

- [ ] 在配置中增加 member role 阈值和 core/qualified/edge 聚合参数。
- [ ] 保留所有通过 eligibility 成员的完整评分，不在 Top N 截断前丢弃。
- [ ] 为每个主题成员生成 `eligible` 和 `member_role`。
- [ ] core 使用 anchor 或 `industry_score >= leader_threshold`。
- [ ] qualified 使用现有 eligibility。
- [ ] 其余原始主题成员标为 edge。
- [ ] 在主题文件、股票文件及所需索引中传递角色和评分。
- [ ] `library_version` 使用成功构建日期 `YYYY-MM-DD`。
- [ ] 保留现有 pure、industry、candidate Top N 查询行为。

完成标准：

- 日科化学在 AI算力关系中具有确定角色和现有 purity 分。
- 中岩大地在 PCB/被动元件关系中为 edge。
- Top N 之外的 qualified 成员仍保留完整评分。
- 查询 API 能返回成员角色，但不改变既有查询用途。

## 第三阶段：盘中主题排名

涉及：

- `src/ashare_pilot/themes/_commands/ranking.py`
- `.cache/intraday/{date}/theme_ranking.json`
- `config/themes/theme-library-config.json`

任务：

- [ ] 从配置读取 core、qualified、edge 的聚合权重。
- [ ] 计算 `core_heat`，只使用 core 和 qualified。
- [ ] 计算 `diffusion_heat`，只使用 edge。
- [ ] 生成 core 优先、qualified 兜底的 `core_leader`。
- [ ] 生成允许 edge 的 `momentum_leader`。
- [ ] 资金项只取消分子绝对值，保留原归一化结构。
- [ ] 删除旧 `heat` 字段和所有读取兼容。
- [ ] 按 core_heat、diffusion_heat、主题名称排序并保留 Top 15。
- [ ] 输出 `library_version`、`membership_as_of` 和 `market_as_of`。
- [ ] 为 Top 15 输出 contributors。
- [ ] 为 ComputePool 全股票输出紧凑的 `stock_themes`。
- [ ] 保持持续性固定10分和领涨幅度绝对值逻辑不变。

完成标准：

- edge 不能影响 core_heat 或成为 core_leader。
- edge 可以影响 diffusion_heat 和成为 momentum_leader。
- 净流出主题获得负资金分项。
- 排名合同能够直接解释日科化学和中岩大地的不同角色。

## 第四阶段：mapper 与报告合同

涉及：

- `src/ashare_pilot/mapping/_commands/intraday/mapper_base.py`
- `src/ashare_pilot/mapping/intraday_contract.py`
- `src/ashare_pilot/mapping/_commands/intraday/validate_annotations.py`
- `src/ashare_pilot/strategy/_commands/overnight/build.py`
- `src/ashare_pilot/strategy/_commands/overnight/render_report.py`
- `.agents/skills/intraday-strategy/SKILL.md`

任务：

- [ ] mapper base 从 theme_ranking 复制全池 stock_themes。
- [ ] 确定性生成 `market_board`、`primary_theme` 和 `themes`。
- [ ] `sector` 由构建器生成并等于 primary_theme。
- [ ] 删除 annotations 中 LLM 编写 sector 的合同。
- [ ] annotation validator 拒绝 LLM 提交任何确定性主题字段。
- [ ] overnight strategy 和 HTML 报告展示 primary_theme，交易板单独展示。
- [ ] 更新 Skill 文档，明确主题字段只读、来自确定性合同。
- [ ] 不修改 overnight_score、方向、仓位或 T+1 规则。

完成标准：

- 报告不再把“沪市主板/深市主板/创业板”显示为投资主题。
- LLM 无法覆盖主题归属。
- 中国铝业等股票能展示确定性的 primary_theme 和完整 themes。

## 测试

### 抓取与 CLI

- [ ] 单概念两页以上的完整抓取。
- [ ] 第2页失败后默认重跑从第2页继续。
- [ ] 第2页失败后 `--reset` 从第1页开始并重抓全部概念。
- [ ] 全部完成后默认重跑跳过已完成概念。
- [ ] 任一概念失败时 CLI 返回非零，批处理不进入 build。
- [ ] 分页合并去重并校验接口 total。

### 主题库

- [ ] core、qualified、edge 的配置边界。
- [ ] anchor 强制成为 core。
- [ ] qualified Top N 截断外仍保留评分。
- [ ] edge 不伪造 purity、industry 或 candidate 分数。

### 主题排名

- [ ] core 优先、qualified 兜底、edge 禁止成为 core_leader。
- [ ] momentum_leader 允许 edge。
- [ ] core 和 diffusion 成员集合互斥。
- [ ] 净流出产生负资金贡献。
- [ ] Top 15 截断不影响全池 stock_themes。
- [ ] 旧 heat 字段不存在。
- [ ] 双时点和 library_version 正确传递。

### mapper 与 LLM 边界

- [ ] primary_theme 的确定性排序稳定。
- [ ] sector 等于 primary_theme。
- [ ] market_board 与主题字段分离。
- [ ] annotations 出现 sector、primary_theme、themes 或主题分数时失败。
- [ ] 现有交易资格、方向和 T+1 不变量测试保持通过。

## 全量更新与验收

代码和离线测试通过后：

1. 在 Windows 更新 Cookie。
2. 执行 `update_theme_stock.bat`，由其使用 `--reset` 全量抓取概念成员。
3. 确认所有概念完成且命令退出码为 0。
4. 构建新主题库。
5. 查询日科化学、中岩大地、AI算力和 PCB/被动元件，核对成员角色。
6. 使用冻结的 2026-07-23 ComputePool 重建 theme_ranking。
7. 核对 core_leader、momentum_leader、core_heat、diffusion_heat 和 contributors。
8. 重建 mapper 与 HTML 报告，确认交易板和投资主题分离。

## 暂缓项

以下问题已经发现，但不在本次实施：

- 持续性固定10分；
- 领涨幅度使用绝对值；
- event 标签和公告证据；
- 跨日分页恢复；
- 主题层 tradability；
- 主题热度进入 overnight_score 的方式；
- 全量主题排名输出；
- 旧 heat 合同兼容。

