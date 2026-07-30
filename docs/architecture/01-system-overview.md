# 系统总览

## 1. 系统定位

A-Share Pilot 是面向 A 股人工决策的 Agent 辅助系统。它将市场数据、新闻、主题
知识、确定性计算和受约束的 LLM 推理组合为三类产品：

1. 09:20 盘前日线策略；
2. 09:35/09:40 开盘后人工操作确认；
3. 14:30 尾盘隔夜 Alpha 策略。

系统不连接券商、不维护账户真实持仓、不自动下单。策略中的仓位只使用定性档位，
操作指南输出的是人工执行建议。

## 2. 总体分层

```text
用户 / 调度器
    │
    ▼
OpenCode Command
    │ 选择工作流
    ▼
Orchestrator Skill
    │ 分派专业角色、规定输入输出
    ├──────────────┐
    ▼              ▼
Analyst Agent      ashare-pilot CLI / Python API
语义感知与推理       抓取、计算、组装、校验、渲染、调度
    │              │
    └──── JSON 合同 ┘
           │
           ▼
predict/ intraday/ operation/ memory/
```

### 2.1 编排层

`.opencode/commands/` 提供用户入口，`.agents/skills/` 定义工作流顺序、角色分工、
允许读取的文件和失败策略。编排层不应复制确定性公式。

### 2.2 专业 Agent 层

Agent 负责无法完全代码化的语义判断。感知角色不能输出 Direction、
RiskSeverity 或交易建议；只有 `portfolio-manager` 可以形成最终策略推理。

### 2.3 确定性核心层

`src/ashare_pilot/` 是 Agent 无关的 Python 核心，负责：

- 数据源访问、缓存和规范化；
- 指标、评分、过滤和候选池；
- JSON 合同组装与验证；
- HTML 报告渲染；
- 调度、交易日和规则治理检查。

### 2.4 状态与知识层

- `config/`：版本控制内的权威配置；
- `data/theme-library/`：持久主题知识；
- `.cache/`：可重建的计算缓存；
- `predict/`、`intraday/`、`operation/`：按交易日发布的业务产物；
- `memory/`：由真实复盘生长的规则、表现和验证历史。

## 3. 核心依赖方向

业务依赖从数据向决策单向流动：

```text
market_data ─┬─> indicators ─┬─> mapping ─> strategy
             ├─> themes ─────┘
             └─> news ─> daily themes

daily strategy + live market ─> operations
strategy + actual results ────> review ─> memory
config + calendar + commands ─> automation
```

`operations` 消费日线策略但不反写策略；`review` 消费历史策略和真实结果但不重写
历史合同；memory 只在复盘流程中更新。

## 4. 三条业务链

| 链路 | 启动 | 正式机器合同 | 人类产物 |
|---|---|---|---|
| 盘前日线 | 09:20 | `predict/{date}/strategy.json` | `daily_report.html` |
| 开盘确认 | 按需，首个正式槽 09:35:10 | immutable snapshot/decision + run manifest | `operation_guide.html` |
| 尾盘隔夜 | 14:30 | `intraday_mapper.json`、`overnight_strategy.json` | `overnight_strategy.html` |

日线和尾盘策略分别在收盘后或 T+1 开盘后复盘，复盘结果进入 `memory/`。

## 5. 架构不变量

- 交易范围只有 `sh`、`sz`，排除 `sh688*` 和 `bj*`。
- JSON 是流水线步骤间的唯一机器合同；Markdown/HTML 只服务人类阅读。
- 外部数据和 LLM 输出在信任边界校验，失败时不得发布部分正式合同。
- Compute 生成的行情、指标、评分和池成员不得由 LLM 手工覆盖。
- 感知层不产生 Direction、RiskSeverity、仓位或买卖结论。
- 学习规则只能来自真实复盘；单日发现不能直接升级为可执行规则。
- 缺失数据必须显式降级、进入观察池或使流程失败，不得用虚构中性值掩盖。
- 历史已发布策略和 immutable 操作快照不得为了“修正结果”而重写。

## 6. 运行边界

Python 运行统一使用：

```bash
uv run --frozen ashare-pilot ...
```

工作区必须同时包含 `pyproject.toml` 和 `config/`。CLI、Skills 和调度器不依赖
手工激活虚拟环境，也不直接执行 `src/` 内部文件。
