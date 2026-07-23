# Agent 无关 Python 核心工程实施计划

- 状态：Completed
- 日期：2026-07-21
- 关联：[ADR-0002](adr/0002-agent-neutral-core-library.md)
- 映射：[Python 核心工程迁移映射](core-refactor-migration-map.md)

## 目标

在不修改现有 `.opencode` 生产链路的前提下，新增 `src/ashare_pilot`，把分散
Python 实现按业务能力重构为可安装、可导入、可由任意 Agent 调用的核心工程。

本计划覆盖第一阶段旁路建设及经再次授权的第二阶段切换。第二阶段已于
2026-07-22 完成。

## 不可变约束

1. 第一阶段不修改 `.opencode` 内的运行代码、测试和 Skill。
2. 不改变交易公式、JSON 合同、排序、默认值和失败语义。
3. 新能力必须同时提供公共 Python API 和统一 CLI。
4. 新代码不得修改 `sys.path`，不得通过源码位置猜测工作区。
5. 每批迁移必须先通过离线等价测试，再开始依赖它的下一批。
6. 旧实现仍是生产权威；线上修复按 ADR-0002 的双轨规则同步。

## 目标骨架

```text
config/
data/theme-library/
resources/
  schemas/
  templates/
src/ashare_pilot/
  __init__.py
  __main__.py
  cli/
  workspace.py
  errors.py
  market_data/
  news/
  indicators/
  themes/
  mapping/
  strategy/
  operations/
  review/
  automation/
tests/
  unit/
  cli/
  equivalence/
  fixtures/
  tools/
```

具体模块可在功能包内部继续拆分，但不得新增无明确职责的全局 `utils` 包。

## Batch 1：工程骨架

### 交付

- 配置 Hatchling 的 `src` 包发现和 `ashare-pilot` console script。
- 增加 pytest 开发依赖和根级测试目录。
- 实现 `ASharePilotError` 基础异常。
- 实现 Workspace 解析优先级：CLI → 环境变量 → 向上查找 → 明确失败。
- 建立可分模块注册的 argparse 命令树和 `python -m ashare_pilot` 等价入口。
- 复制根级配置，但不删除或改写旧配置。
- 项目版本保持在 `0.1.x`；正式切换时再发布 `1.0.0`。

### 验收

- editable install 后两个 CLI 入口可用。
- 从仓库根、子目录和显式临时工作区定位一致。
- CLI 全局帮助、未知命令和工作区错误有测试。
- 现有生产命令不受影响。

## Batch 2：Market Data 与 News

### 交付

- 迁移数据源、行情、历史数据、市场宽度、资金流、排行、Cookie 与交易日历。
- 迁移新闻抓取与规范化。
- HTTP、时间、Cookie 和文件边界可在测试中替换。
- 建立本批公共 API 和迁移映射中的 CLI。

### 验收

- 使用录制响应比较新旧 JSON、CSV、文本和错误行为。
- K 线缓存、前复权、股票代码前缀和回退源行为等价。
- 新闻 ID、排序、去重和双产物写入等价。

## Batch 3：Indicators 与 Themes

### 交付

- 迁移指标计算、池指标抓取和盘中技术富化。
- 迁移概念抓取、主题库构建/查询、概念面板和主题排名。
- 复制主题持久数据到 `data/theme-library/`，临时数据使用根级 `.cache`。
- 建立根级主题配置读取。

### 验收

- 指标缺失值、权重归一化、排序和精度严格等价。
- 主题查询、候选股顺序、索引和动态市场视图等价。
- 新实现不读取 `.opencode/skills/theme-library`。

## Batch 4：Mapping

### 交付

- 迁移早盘主题证据、股票池、mapper 组装、验证、投影和计时。
- 迁移盘中扫描池、ComputePool 富化和 intraday mapper 合同。
- 抽取 daily/intraday 共享的合同与组装逻辑，但不强行合并不同语义。

### 验收

- 使用冻结 themes、annotations、行情和指标输入比较全部中间/最终 JSON。
- 校验错误顺序、错误文本、内容哈希和候选顺序等价。
- Step 2 perception 与 Step 3 reasoning 边界不改变。

## Batch 5：Strategy

### 交付

- 迁移早盘 prepare/finalize、Trade Profile、选择规范化、验证和 HTML 渲染。
- 迁移隔夜评分、策略合同、验证和 HTML 渲染。
- LLM 仍只通过现有 JSON 产物参与，核心工程不接管 Agent 编排。

### 验收

- 冻结 LLM draft 和 mapper 输入产生完全等价的正式策略合同。
- 评分、买入区间、止损、目标、观察池补全和渲染语义等价。
- HTML 在批准的非确定字段白名单之外等价。

## Batch 6：Operations 与 Review

### 交付

- 迁移盘中快照、机械分类、市场/主题确认、状态转移、仓位和操作指引。
- 迁移早盘验证及 entry band/quality 回测。

### 验收

- 完成 K 线、迟到策略、幂等写入和状态转移场景等价。
- 回测样本选择、收益计算、分组统计和输出等价。

## Batch 7：Automation

### 交付

- 迁移规则治理检查、交易日调度器和盘中 pipeline runner。
- 调度器使用根级配置和 Workspace，不绑定 OpenCode 的源码目录。
- 实际 Agent 命令仍维持旧生产配置，直到第二阶段。

### 验收

- dry-run、once、交易日、TP1、超时、排队、日志和 Ctrl+C 语义等价。
- 规则治理的 ID、容量、生命周期和引用检查等价。

## 全局离线验收

每个旧入口至少包含：

- 正常输入样本；
- 边界或缺失数据样本；
- 一个预期失败样本；
- CLI 参数、退出码和标准流断言；
- 规范化后产物等价断言。

网络入口必须使用录制响应，不在等价测试中访问外部服务。非确定字段白名单集中
维护，并要求每个字段附理由；不得在单个测试中随意删除差异。

## 第二阶段切换条件

只有满足以下条件后才可请求第二阶段授权：

- 迁移映射中的旧入口全部覆盖；
- 所有新 CLI 和公共 API 可安装并通过测试；
- 新核心对 `.opencode` 的运行时路径引用为零；
- 根级配置和主题数据可独立支撑离线流程；
- 全部旧测试和新测试通过；
- ADR-0002 的待决策项已经关闭并转为 Accepted。

第二阶段在单一变更中更新 Skill、批处理、配置、AGENTS.md 和其他命令文档，
删除旧 Python、旧重复测试与主题数据副本，不保留长期兼容 wrapper。切换后版本
为 `1.0.0`，根级 `src/`、`config/`、`data/` 和 `tests/` 为权威实现与数据位置。
