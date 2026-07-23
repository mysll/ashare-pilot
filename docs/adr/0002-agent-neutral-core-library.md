# ADR-0002：Agent 无关的 Python 核心工程

- 状态：Accepted
- 日期：2026-07-21
- 修订：2026-07-22（第二阶段完成统一 CLI 切换）
- 范围：`.opencode/lib/`、`.opencode/scripts/`、`.opencode/skills/*/scripts/`
- 关联：[术语表](../glossary.md)
- 实施方案：[核心工程实施计划](../core-refactor-plan.md)

## 背景

当前 Python 实现分散在 `.opencode/lib/`、`.opencode/scripts/` 和各个
`.opencode/skills/*/scripts/` 目录。大量模块通过修改 `sys.path` 互相调用，
使通用 Python 能力依附于 OpenCode 和具体 Skill 的物理目录。

现有 Skill 功能流本身不需要改造成 Python 工作流引擎。问题在于 Skill 调用的
Python 脚本不是项目级公共实现，因此 Codex 或其他 Agent 难以复用同一套功能流。

## 已确认决策

项目将在仓库根级建立一个工程化、Agent 无关的 Python 核心工程。现有
`.opencode/lib/`、`.opencode/scripts/` 和 `.opencode/skills/*/scripts/` 中的
Python 实现迁入该工程，并按照业务功能而不是 Skill 名称划分模块。

现有 `.opencode` Skill 的功能、步骤、LLM 职责和 JSON 合同保持不变，所有 Python
调用统一切换到项目公共入口。Agent 仍然编排 Skill 中声明的步骤；本次重构不把
功能流改造成由 Python 核心掌握的工作流状态机。

核心工程不是按原 Skill 目录一对一复制的脚本集合。数据源、行情访问、技术
计算、主题库、策略合同、校验、渲染和自动化等能力应形成可导入的功能模块，
消除运行代码中的 `sys.path` 修改和对 `.opencode` 路径的依赖。

### 包布局

Python 核心工程采用标准 `src` 布局，导入命名空间为 `ashare_pilot`：

```text
src/
└── ashare_pilot/
```

不使用含义过于宽泛的 `core` 作为 Python 包名。`pyproject.toml` 负责声明该包
及其安装、测试和命令入口；调用者不应依靠仓库当前目录或手工修改模块搜索路径。

产品名称为 **A-Share Pilot**，发行包名和 CLI 均为 `ashare-pilot`。`Pilot`
表示 A 股 Agent 决策领航，不表示无人值守自动交易。

### 一级功能边界

`ashare_pilot` 按业务能力划分以下一级模块：

| 模块 | 职责 |
|------|------|
| `market_data` | 数据源、行情抓取、缓存和交易日历。 |
| `news` | 新闻抓取与规范化。 |
| `indicators` | 技术指标与派生特征。 |
| `themes` | 概念数据、主题库与主题排名。 |
| `mapping` | 候选池、证据整理与 mapper 合同。 |
| `strategy` | 早盘和隔夜策略的确定性计算、组装与校验。 |
| `operations` | 盘中操作状态与决策计算。 |
| `review` | 验证、复盘与回测。 |
| `automation` | 调度和规则治理检查。 |

校验器、HTML 渲染器和 JSON 组装器跟随其所属业务模块放置。项目不建立承接
无明确归属代码的全局 `utils`、`validators` 或 `scripts` 包。

### 公共命令接口

核心工程对 Agent 和人工调用者提供统一的 `ashare-pilot` CLI，并通过
`python -m ashare_pilot` 提供等价入口。命令按业务能力组织，例如：

```text
ashare-pilot market-data quote ...
ashare-pilot themes query ...
ashare-pilot mapping daily prepare ...
ashare-pilot strategy daily finalize ...
```

Skill 不直接执行 `src/ashare_pilot/` 内的文件路径，也不依赖内部模块布局。
Python 模块同时保留可导入 API，供单元测试和其他程序调用。

### 两阶段迁移

迁移采用旁路建设，不对正在运行的 OpenCode 工作流做原地修改：

1. 第一阶段只新增 `src/ashare_pilot/`、公共 CLI 及其测试。现有
   `.opencode/lib/`、`.opencode/scripts/`、`.opencode/skills/*/scripts/`
   和全部 Skill 内容保持原样，生产执行继续使用旧入口。
2. 新核心工程通过约定的等价性验收后，在单一切换中把现有 Skill、批处理、配置
   和命令文档改为调用公共 CLI，并删除旧 Python、重复测试与主题数据副本。

第一阶段不得为了复用而把旧脚本改成新核心的包装器，也不得提前调整 Skill
命令。旧链路是迁移期间的生产基线和行为参照。

### 双轨变更规则

第一阶段旁路建设期间，`.opencode` 中的旧实现仍是 OpenCode 生产权威版本，并按
以下规则控制分叉：

- 线上缺陷先在旧实现修复，以保证现有生产链路；同一修复必须同步到新核心，
  并在新核心增加对应回归测试。
- 原则上暂停向旧脚本加入新功能；只有无法等待切换的交易需求可以例外，且
  必须同时进入新核心。
- 新核心可以进行不改变外部行为的内部重构，但不得单方面改变现有 JSON 合同、
  计算语义或失败行为。

### 严格行为等价

本次迁移是行为保持重构，不包含策略、算法或数据合同升级：

- 相同的冻结输入必须产生相同的 JSON 合同和业务字段。
- 公共 CLI 的参数语义、退出码和错误条件必须与对应旧入口等价。
- 时间戳、绝对路径、请求耗时等非确定字段只有被明确列入验收白名单后才能忽略。
- 发现的旧逻辑缺陷先记录；修复必须作为独立变更，并按双轨规则同时进入新旧实现。

### 根级配置

新核心使用仓库根级 `config/` 作为项目配置目录，不再从 `.opencode/config/`
或某个 Skill 的 `scripts/` 目录读取配置。至少包含：

```text
config/
├── trading-scope.json
├── trading-calendar.json
├── cron-tasks.json
└── themes/
    ├── theme-config.json
    └── theme-library-config.json
```

第一阶段复制现有配置内容供等价验证；第二阶段切换后根级配置成为唯一权威副本，
`.opencode/config/` 重复副本删除。

### 依赖驱动的分批迁移

迁移不以 Skill 为单位复制目录，而按功能依赖从底向上推进：

1. 工程骨架、配置加载和统一 CLI。
2. `market_data`、`news`。
3. `indicators`、`themes`。
4. `mapping`。
5. `strategy`。
6. `operations`、`review`。
7. `automation`。

每一批必须完成公共 API、CLI 和等价性测试后才能进入下一批。批次边界可以根据
实际导入依赖细化，但不得退化为按 Skill 名称复制现有目录。

### 第二阶段启动门槛

第二阶段 Skill 适配以离线等价为充分门槛，不要求连续多个交易日进行生产影子运行。
离线验收必须覆盖：

- 旧命令与新 CLI 使用相同冻结输入或录制的外部响应。
- JSON 和文件产物去除已批准的非确定字段后严格相等。
- CLI 参数语义、标准输出、标准错误、退出码和失败条件等价。
- 各一级功能模块以及早盘、盘中、隔夜和复盘关键路径均有覆盖。

任何差异必须修复，或作为有理由、可审查的非确定字段进入白名单。测试通过后即可
开始第二阶段 Skill 适配；生产影子运行可以自愿执行，但不是强制门槛。

### 发布边界

本期核心工程是可安装的仓库内应用库。开发者和 Agent 可以通过 `uv sync` 或
`pip install -e .` 安装，并在 A-Share Pilot 项目工作区内使用统一 CLI 和
Python API。

“通用”在本期表示 Agent 无关，不表示项目无关。核心工程仍可依赖本仓库的根级
`config/`、`memory/`、`predict/`、`intraday/`、`operation/` 等数据约定，
不承诺作为脱离项目的 PyPI 通用交易库发布。

### 工作区定位

所有需要项目数据的公共 API 和 CLI 使用统一的工作区解析规则，优先级为：

1. CLI 全局参数 `--workspace`。
2. 环境变量 `ASHARE_PILOT_WORKSPACE`。
3. 从当前工作目录向上查找同时包含 `pyproject.toml` 和 `config/` 的目录。
4. 找不到时明确报错，不根据 Python 源文件的物理位置猜测项目根目录。

解析后的工作区应作为显式上下文传入业务模块。测试通过 `--workspace` 或对应
Python API 指向临时目录，避免读写真实生产产物。

### CLI 实现

统一 CLI 使用 Python 标准库 `argparse`，不为本次迁移引入 Typer、Click 等新
框架。命令通过分模块注册组成命令树，避免把所有解析逻辑集中到单个巨大文件。

叶子命令必须保持对应旧脚本的参数名称、默认值、输入语义和业务退出条件；统一
CLI 新增的上级命令路径不视为行为差异。`python -m ashare_pilot` 和安装后的
`ashare-pilot` 使用同一入口实现。

### 业务 API 与 CLI 分离

迁移时允许在严格行为等价约束下重组旧脚本内部结构：

- 业务模块以普通 Python 函数接收显式参数和已解析的工作区上下文。
- CLI 适配层只负责 `argparse`、调用业务 API、输出格式化和退出码映射。
- 网络、文件、时间等边界应在不改变行为的前提下可替换，以支持离线等价测试。
- 不要求为了形式统一而把现有 JSON 字典全部改写为 dataclass 或新的领域模型。

内部拆分不得改变计算公式、字段、排序、默认值、文件写入语义或异常处理结果。

### 测试工程

新核心的测试位于根级 `tests/`，按用途组织：

```text
tests/
├── unit/
├── cli/
├── equivalence/
└── fixtures/
```

新测试使用 `pytest`，并在 `pyproject.toml` 中声明为开发依赖。`pytest` 同时可以
执行现有的 `unittest.TestCase`。第一阶段不移动或修改 `.opencode` 内的旧测试；
新核心按迁移批次在根级建立覆盖。

### 冻结样本

离线等价样本采用最小、脱敏、版本化策略：

- 精简的外部响应、输入 JSON 和期望输出提交到 `tests/fixtures/`。
- Cookie、用户名、请求签名、机器绝对路径等敏感或环境相关内容必须移除。
- 不把完整 `.cache/`、`predict/` 或 `intraday/` 历史目录复制进测试树。
- 网络抓取能力使用录制的服务端响应体，让新旧实现消费同一输入，不在等价测试中联网。
- 每个样本记录来源日期、对应旧命令和覆盖场景。

### CLI 命名

公共命令遵循以下结构：

```text
ashare-pilot <capability> [<context>] <action>
```

CLI 名称使用 kebab-case，Python 模块和函数使用 snake_case。命令使用业务语言，
不机械保留旧文件的 `fetch_*`、`build_*` 前缀。每个旧 Python 入口必须在迁移
清单中映射到唯一新命令，示例包括：

```text
ashare-pilot market-data quote
ashare-pilot news fetch
ashare-pilot themes library build
ashare-pilot mapping daily prepare
ashare-pilot strategy daily finalize
ashare-pilot strategy overnight score
ashare-pilot operations snapshot build
ashare-pilot review daily verify
```

### Python 公共 API

每个一级能力只显式导出一组公共函数，例如：

```python
from ashare_pilot.market_data import fetch_quotes
from ashare_pilot.themes import query_theme
from ashare_pilot.mapping import prepare_daily_mapping
```

CLI 调用相同的公共函数。辅助解析、文件拼装和内部计算不从能力包的
`__init__.py` 导出，并视为可重构的内部实现。公共 API 受项目内版本和兼容
策略约束，内部实现不作兼容承诺。

### 错误与输出边界

公共业务 API 不调用 `sys.exit()`，也不直接把业务结果打印到 stdout。它返回
结构化结果，并通过统一的 `ASharePilotError` 异常层次表达可预期失败。

CLI 适配层负责 JSON、CSV、文本和文件输出，并把业务异常映射为对应旧命令
等价的错误文本与退出码。进度和诊断信息使用日志边界；机器可读输出不得混入
新的非数据文本。旧入口存在的特殊错误行为必须由等价测试锁定。

### Python 迁移范围

本次范围包括：

- `.opencode/lib/**/*.py`；
- `.opencode/scripts/*.py`；
- `.opencode/skills/*/scripts/*.py`。

第一阶段新测试写入根级 `tests/`；第二阶段删除旧目录内的重复测试。依赖旧实现的
等价测试保留为验收证据，在旧基线不存在时明确跳过；新核心的独立测试继续执行。
测试夹具生成器归入 `tests/tools/`，不进入生产包。

批处理文件、Skill 文档和配置不属于第一阶段 Python 代码迁移范围；第二阶段统一
改为调用 `ashare-pilot`。Agent 定义和业务生成产物不变。

### 主题库数据边界

主题库是解除 `.opencode` 运行依赖所必需的例外数据迁移。持久化数据提升到：

```text
data/theme-library/
├── aliases/
├── metadata/
├── concepts/
├── stocks/
├── themes/
└── index/
```

可重新抓取或计算的临时主题数据使用根级 `.cache/theme-library/`。第一阶段保留
Skill 目录内的旧数据并复制等价数据供新核心验证；第二阶段删除旧副本，根级
`data/theme-library/` 成为唯一持久数据源。数据内容和查询语义不变。

### 最小工程工具集

项目使用 Hatchling 构建 `src/ashare_pilot` 并安装 `ashare-pilot` 命令，使用
pytest 运行新测试和现有 unittest 测试。Python 要求维持 `>=3.12`，运行依赖
维持 `requests` 与 `websocket-client`。

本次重构不同时引入 Ruff、Mypy、Pydantic、新 CLI 框架或新 HTTP 框架。后续
如需采用，应作为独立工程决策处理。

### 固定资源

独立于可编辑配置的固定资源使用根级目录：

```text
resources/
├── schemas/
└── templates/
```

业务模块通过 Workspace 定位资源。现有内嵌 HTML 或 Schema 不为了目录形式而
强制拆分；只有形成独立文件的固定资源才进入该目录。固定资源不得继续放在
Agent Skill 目录，也不隐式绑定 Python 源文件路径。

### 版本策略

第一阶段旁路建设使用 `0.1.x` 版本，公共 API 可以随迁移批次在 ADR 约束内调整。
全部离线等价测试通过并完成第二阶段统一切换后发布 `1.0.0`。

从 `1.0.0` 开始，公共 CLI、各能力显式导出的 Python API 和 JSON 合同遵循语义
化版本规则。内部模块布局与未导出函数不构成兼容承诺。

### 第二阶段 Skill 适配原则

第二阶段获得明确授权后，修改 `.opencode/skills/` 下所有 Skill 对旧脚本的依赖，
统一使用新接口，并清理旧 Python、旧重复测试与主题数据副本。该切换已于
2026-07-22 完成。

## 已关闭决策

### 等价性测试矩阵与冻结样本

第一阶段最终验收以
[`docs/core-refactor-acceptance-matrix.md`](../core-refactor-acceptance-matrix.md)
为唯一入口矩阵。矩阵必须与迁移映射保持 68 个旧入口到 68 个新 CLI 的双向唯一
对应，并为每个入口记录正常、边界、失败、统一 CLI 和公共 API 证据。

冻结样本清单以 `tests/fixtures/manifest.json` 为权威副本。每个版本化 fixture 必须
记录来源日期、对应旧命令、覆盖场景和溯源说明；自动化测试保证 manifest 无漏项，
且不包含凭据、Cookie、请求签名或机器绝对路径。获准忽略的非确定字段集中维护在
`tests/equivalence/nondeterminism.py`，每个字段必须附具体理由。


## 实施约束

本 ADR 已于 2026-07-21 经确认接受；第二阶段于 2026-07-22 获得明确授权并完成。
