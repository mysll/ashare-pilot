# Python 核心与 CLI

## 1. 工程形态

项目采用标准 `src` 布局，发行包和命令名均为 `ashare-pilot`：

```text
pyproject.toml
src/ashare_pilot/
├── cli/
├── market_data/
├── news/
├── indicators/
├── themes/
├── mapping/
├── strategy/
├── operations/
├── review/
└── automation/
```

Python 版本要求为 3.12 及以上，运行依赖保持精简：`requests`、
`websocket-client`，Windows 额外安装 `tzdata`。测试依赖为 `pytest`。

## 2. 工作区解析

`ashare_pilot.workspace.resolve_workspace()` 按以下优先级解析根目录：

1. 全局参数 `--workspace PATH`；
2. 环境变量 `ASHARE_PILOT_WORKSPACE`；
3. 从当前目录逐级向上查找。

候选目录必须同时含有 `pyproject.toml` 和 `config/`。显式路径无效时直接失败，
不会静默回退。`Workspace` 提供 `config_dir`、`resources_dir`、`data_dir` 和
`cache_dir`，业务代码应接收显式工作区，而不是从源码物理位置猜根目录。

## 3. CLI 组装

`ashare_pilot.cli.app` 使用标准库 `argparse`。`cli.registry` 依次注册九个能力：

| 能力 | 职责 |
|---|---|
| `market-data` | 实时/历史行情、宽度、资金流、榜单、认证 |
| `news` | 新闻抓取与规范化 |
| `indicators` | 单股指标和候选池指标 |
| `themes` | 概念抓取、主题库、日线主题、盘中排名 |
| `mapping` | 日线与盘中 mapper 合同 |
| `strategy` | 日线和隔夜策略合同 |
| `operations` | 开盘操作快照、决策和生命周期 |
| `review` | 日线验证与回测 |
| `automation` | 调度、memory、规则检查、盘中 Compute |

命令结构遵循：

```text
ashare-pilot <capability> [<context>] <action>
```

叶子命令保留独立参数解析器；顶层只解析工作区和命令路由。`python -m
ashare_pilot` 与安装后的命令使用同一入口。

## 4. 主要命令树

```text
market-data
  quote | history | breadth | special
  stocks all
  money-flow [board]
  ranking concepts|turnover
  pool limit-up
  auth update-cookie
indicators
  calculate
  pool fetch|enrich
themes
  concepts fetch|fetch-stocks
  library build
  query
  dashboard build
  ranking compute
  daily prepare|publish
mapping
  daily prepare|finalize|validate-*|build-*|compare-regression
  intraday build-scan-pool|enrich-compute-pool|build-mapper*|validate-*
strategy
  daily prepare|finalize|validate|render-report|compare-shadow|...
  overnight score|validate-selection|build|validate|render-report
operations
  snapshot build|validate
  decision build|validate
  guide run|render
review
  daily verify|backtest-entry-band|backtest-entry-quality
automation
  scheduler run
  memory init
  rules check
  intraday run
```

完整参数以对应命令的 `--help` 为准，架构文档不复制所有叶子参数。

## 5. 模块内部结构

每个能力通常包含：

- `api.py`：面向程序调用的公共函数；
- `cli.py`：命令注册与适配；
- `_commands/`：叶子命令实现；
- 领域模块：合同、算法、数据源或状态机。

公共 API 接收普通 Python 参数和显式 `Workspace`。CLI 负责参数、输出格式和退出码，
不应承载业务公式。

## 6. 错误与副作用

顶层捕获 `ASharePilotError` 并以退出码 2 输出清晰错误。叶子命令的合同校验失败
同样必须非零退出。文件写入由所属模块负责，正式发布命令应先完成内存组装和验证，
再写正式产物。

网络、时间和文件系统是主要外部边界。公共 API 通过显式工作区、可替换数据源或
冻结输入支持离线测试。调用者不得依赖 `_commands` 中未导出的内部函数作为稳定 API。

## 7. 公共 API 边界

当前 `api.py` 暴露的代表性能力包括：

- `market_data`: quotes、history、breadth、money flow、榜单；
- `news`: fetch 和双格式写出；
- `indicators`: 历史数据加指标计算；
- `themes`: 查询、排名、Dashboard 和概念抓取；
- `mapping`: mapper 构建、合并和校验；
- `strategy`: 日线 finalize、隔夜 build/validate/render；
- `operations`: snapshot/decision/validate/render；
- `review`: verification 和回测解析；
- `automation`: memory、规则、调度配置和盘中管线。

`api.py` 是可导入边界；JSON 文件和 CLI 是 Agent/人工运行边界。
