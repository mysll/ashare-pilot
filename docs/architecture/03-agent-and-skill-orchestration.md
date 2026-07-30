# Agent 与 Skill 编排

## 1. 两类控制面

OpenCode 提供两类版本化定义：

- `.opencode/commands/*.md`：用户和调度器可调用的 slash command；
- `.opencode/agents/*.md`：专业角色、模型、温度和行为边界。

`.agents/skills/*/SKILL.md` 是具体工作流协议。Command 只选择顶层 Skill，顶层
Skill 再规定是否以及如何分派专业 Agent。

## 2. 专业角色

| 角色 | 类型 | 主要职责 | 禁止事项 |
|---|---|---|---|
| `sector-analyst` | 感知 | 新闻到主题、产业链与 taxonomy 对齐 | 最终方向和交易建议 |
| `equity-analyst` | 感知 | 候选池、资格、技术/资金状态、主题统计 | Direction、RiskSeverity |
| `market-microstructure-analyst` | 感知 | 指数、宽度、资金、盘面结构 | 评分和交易结论 |
| `macro-strategist` | 上下文 | 政策、宏观、流动性与情绪 | 最终组合决策 |
| `portfolio-manager` | 推理 | Direction、RiskSeverity、角色、执行计划 | 重做上游事实计算 |
| `performance-analyst` | 复盘 | 结果验证、归因、规则和 memory 更新 | 篡改原策略或事后拟合 |

日线 Step 1/2 使用轻量感知角色，Step 3 使用 `portfolio-manager`。14:30 流程
先由盘面和股票感知角色检查 Compute 产物，再由 `portfolio-manager` 形成 annotations。

## 3. 所有权模型

### 3.1 Python 所有

- 数值行情、指标、资金流和评分；
- 股票/主题成员关系和交易范围；
- 候选池成员、排序、硬过滤与数据质量状态；
- schema、固定字段、哈希、时间和正式合同组装；
- 校验、HTML 渲染和发布。

### 3.2 LLM 感知角色所有

- 被 Skill 明确授权的语义 annotations；
- 对 Compute 产物的一致性检查和可读解释；
- 缺失或异常的文字说明。

### 3.3 Portfolio Manager 所有

- 最终市场状态推理；
- Direction、RiskSeverity、交易角色和顺序；
- 定性仓位意图、执行条件和 T+1 计划；
- 正式规则的语义应用与审计说明。

LLM 不能修改 Python 所有的事实；Python 也不能在合法输出上替代 LLM 重新选择
最终股票和顺序。

## 4. 编排协议

顶层 Skill 通常执行以下模式：

```text
1. Python prepare / compute
2. 向指定 Agent 传递日期、输入路径和输出路径
3. Agent 只读紧凑输入并写 annotations/draft
4. Python validate
5. 必要时按 Skill 限制修复一次
6. Python finalize + validate + render
```

Agent 间不传递自由文本作为机器合同。下游必须重新读取已验证 JSON。顶层编排器
不得把大段 JSON、公式或 validator 错误塞入初始分派 prompt；Skill 会规定精确的
路径协议。

## 5. 信任边界

| 边界 | 验证方式 |
|---|---|
| 网络响应进入核心 | 数据源解析、数量和字段检查 |
| LLM annotations/draft 进入核心 | 专用 validator、exact coverage、枚举和证据归属 |
| 确定性中间产物进入下游 | schema/日期/来源检查与测试保证 |
| 正式合同发布 | 最终 validator 成功后写入 |
| learned rule 进入推理 | governance 状态和引用检查 |

验证失败时，Agent 只能修复自己拥有的字段。不得手改 Compute 数值、池成员、评分、
schema 或内容哈希绕过失败。

## 6. Command 到 Skill

| Command | 顶层 Skill | 主要正式输出 |
|---|---|---|
| `/daily-analysis` | `daily-market-analysis` | `predict/{date}/strategy.json` |
| `/operation-guide` | `intraday-operation-guide` | `operation_guide.html` + manifest |
| `/intraday-analysis` | `intraday-market-analysis` | `overnight_strategy.json` |
| `/daily-review` | `daily-trading-review` | daily verification + memory |
| `/intraday-review` | `intraday-trading-review` | intraday verification + memory |

## 7. 扩展原则

新增能力时优先判断它属于确定性核心、感知还是推理。新公式进入 Python；新语义
字段必须有明确 owner 和 validator；新角色只有在权限或认知边界确实不同于现有
角色时才增加。不要为每个 Skill 创建同名 Python 包。
