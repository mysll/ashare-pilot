# A-Share Pilot：Agent 初始化与安装指南

本文供首次接管仓库的 Agent 使用。目标是把一台新机器上的全新 checkout 初始化到
“CLI 可运行、Cookie 可用、主题库可查询、memory 可从零生长、OpenCode 可执行任务”的状态。

所有命令都应从仓库根目录执行。正式运行入口统一为：

```bash
uv run --frozen ashare-pilot <capability> ...
```

`uv` 是唯一必需的 Python 环境管理器。不要要求用户全局安装 Python，不要手动激活
虚拟环境，也不要把 `mise`、`python` 或仓库旧脚本作为生产入口。

## 1. 初始化原则

Agent 必须遵守以下顺序：

1. 检查系统依赖。
2. 检查仓库完整性，尤其是 `config/`。
3. 选择当前操作系统的 uv 项目环境。
4. 同步锁定依赖。
5. 创建本地状态目录并初始化不含策略的 memory 骨架。
6. 首次构建主题库。
7. 执行验收命令。
8. 只有全部验收通过后，才启动分析或定时任务。

Agent 无法执行交互式步骤；Cookie 初始化需用户手动完成，详见文件末尾的后续步骤章节。

初始化过程中不得删除用户已有的 `.cookie`、`memory/`、`predict/`、`intraday/`、
`operation/` 或 `data/theme-library/`。这些目录可能包含不可从代码重建的运行状态。

## 2. 系统依赖

### 2.1 必需依赖

| 依赖 | 用途 | 要求 |
|---|---|---|
| Git | 获取和更新仓库 | 能执行 `git --version` |
| uv | 下载托管 Python、创建虚拟环境、同步依赖、运行 CLI | 能执行 `uv --version` |
| 网络访问 | 下载 Python/依赖并访问行情、新闻和主题数据源 | 首次同步和数据更新时必需 |

安装 uv：

PowerShell：

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

Bash：

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

安装后重新打开终端，再执行：

```bash
uv --version
```

仓库通过 `.python-version` 固定 Python `3.12.13`。如果目标机没有该版本，uv 会自动
下载托管 Python；不要额外安装或修改系统 Python。平台条件依赖也会由项目自动安装。

### 2.2 按功能安装的依赖

| 依赖 | 何时需要 |
|---|---|
| Google Chrome | 执行 `update_cookie.bat`、登录或人机验证时 |
| OpenCode Desktop | 人工使用项目 Skills 时 |
| `opencode` CLI | 运行 `auto.bat`、`auto.sh` 或 `automation scheduler run` 时；必须位于 `PATH` |
| Node.js / pnpm | 仅在选择通过 npm 安装或维护 OpenCode CLI 时 |
| mise | 可选的开发快捷工具；不是 Skills 或生产运行依赖 |

如果只运行 `ashare-pilot` CLI，不需要 Node.js、pnpm 或 mise。

## 3. 获取仓库并检查完整性

```bash
git clone <repository-url> ashare-pilot
cd ashare-pilot
```

Agent 必须确认以下受版本控制的入口存在：

```text
pyproject.toml
uv.lock
.python-version
AGENTS.md
opencode.json
src/ashare_pilot/
config/cron-tasks.json
config/trading-calendar.json
config/trading-scope.json
config/themes/theme-config.json
config/themes/theme-library-config.json
.opencode/agents/
.opencode/commands/
.agents/skills/
resources/schemas/
resources/templates/
data/theme-library/
```

其中 `pyproject.toml` 和 `config/` 是工作区识别的硬条件。任何一个缺失都应停止初始化并
修复 checkout；不得用空目录或临时 JSON 伪造配置。

CLI 默认从当前目录向父目录查找工作区。若必须从仓库外运行，使用以下任一种方式：

```bash
uv run --project /path/to/ashare-pilot --frozen ashare-pilot --workspace /path/to/ashare-pilot --version
```

或者设置 `ASHARE_PILOT_WORKSPACE` 为仓库绝对路径。

## 4. 创建虚拟环境并同步依赖

所有运行方式统一使用仓库默认环境 `.venv`。不需要手动激活虚拟环境，也不要设置
`UV_PROJECT_ENVIRONMENT`；`uv sync` 和 `uv run` 会自动创建或使用 `.venv`：

```bash
uv sync --frozen
uv run --frozen ashare-pilot --version
```

如果当前 shell 已激活其他虚拟环境，应先清除 `VIRTUAL_ENV`，或通过一个未激活虚拟环境的
新终端执行上述命令。需要在同一 checkout 中维护多个平台环境属于高级用法，由使用者自行
为相应入口设置 `UV_PROJECT_ENVIRONMENT`，不属于本指南的默认配置。

## 5. 创建本地状态目录

以下目录不属于可移植源码状态。部分命令能够按需创建它们，但新环境应先建立基础结构，
方便 Agent 检查权限和恢复数据。

Bash：

```bash
mkdir -p \
  .cache/intraday \
  .cache/kline \
  .cache/theme-library \
  data/theme-library \
  predict \
  intraday \
  operation \
  logs \
  memory/daily \
  memory/intraday
```

PowerShell：

```powershell
$directories = @(
  ".cache/intraday",
  ".cache/kline",
  ".cache/theme-library",
  "data/theme-library",
  "predict",
  "intraday",
  "operation",
  "logs",
  "memory/daily",
  "memory/intraday"
)
$directories | ForEach-Object { New-Item -ItemType Directory -Force $_ | Out-Null }
```

目录职责：

| 路径 | 内容 | 初始化方式 |
|---|---|---|
| `.cache/` | K 线、主题和盘中计算缓存 | 可创建空目录，命令自动填充 |
| `data/theme-library/` | 主题、概念、股票、别名、索引和元数据 | 首次主题库构建生成 |
| `predict/{date}/` | 盘前新闻、映射、策略和报告 | 日常流水线按日期生成 |
| `intraday/{date}/` | 盘中 mapper 和隔夜策略 | 盘中流水线按日期生成 |
| `operation/{date}/` | 盘中操作快照、决策和报告 | 操作指南命令生成 |
| `logs/` | 调度器及任务日志 | 调度器自动生成 |
| `memory/` | 描述骨架，以及 Agent 在运行和复盘中逐步形成的规则、表现与历史 | 初始化命令创建描述文件和空规则模板 |

### 5.1 从零建立 memory

`memory/` 被 Git 忽略，因为其中的业务状态不随源码分发。创建目录后执行幂等初始化：

```bash
uv run --frozen ashare-pilot automation memory init
```

该命令只补齐以下描述文件、空规则模板和索引文件：

```text
memory/MEMORY.md
memory/RULE_GOVERNANCE.md
memory/PERFORMANCE.md
memory/RULES.md
memory/SHARED_RULES.md
memory/INTRADAY_RULES.md
memory/daily/INDEX.md
memory/intraday/INDEX.md
memory/daily/
memory/intraday/
```

初始化内容来自 `resources/templates/memory/`。其中：

- `MEMORY.md` 描述 memory 目录、复盘流程和查询入口；
- `RULE_GOVERNANCE.md` 描述未来规则如何从证据产生，但不包含策略规则；
- `PERFORMANCE.md` 提供零样本统计说明，不填写虚构胜率；
- 三个规则文件只包含标题、治理链接和空表头，不包含规则 ID、交易条件或历史结论；
- 两个 `INDEX.md` 只包含空表头，等待首个真实复盘追加。

命令绝不覆盖任何已经存在的 memory 文件。重复执行时已有文件显示为 `KEPT`。

不要复制示例规则，也不要创建占位规则。规则模板没有数据行表示“尚无历史经验”。Agent
首次运行时依据当日事实、业务合同和 Skills 完成分析，不得声称存在历史验证过的规则。

memory 按真实运行结果自然生长：

1. 首次盘前或盘中分析生成 `predict/{date}/` 或 `intraday/{date}/`，不向空模板预写规则。
2. 收盘后复盘将当日事实写入 `memory/daily/{date}/` 或 `memory/intraday/{date}/`。
3. Agent 根据复盘更新 `PERFORMANCE.md` 和索引，并在有真实候选时更新适用的规则文件。
4. 单日发现只能作为候选或观察记录，不能伪装成已验证策略。
5. 后续运行读取对应规则模板；没有规则数据行的作用域视为没有已积累规则。

如果不是全新项目，而是继续已有项目，则保留并读取现有 `memory/`。初始化流程不得覆盖、
回滚或自动重建其中内容。

初始化后即可执行治理检查，确认三个空模板符合结构和容量约束：

```bash
uv run --frozen ashare-pilot automation rules check
```

## 6. 首次构建主题库

必须按以下顺序执行，后一步依赖前一步输出：

```bash
uv run --frozen ashare-pilot themes concepts fetch -q -v
uv run --frozen ashare-pilot themes concepts fetch-stocks --reset
uv run --frozen ashare-pilot themes library build --clean
```

也可直接运行全量批处理，它会先更新 Cookie：

```powershell
.\update_theme.bat
```

如果概念或成分股抓取因网络问题中断，应重新执行相同步骤；抓取支持续跑。不要跳过概念列表
直接构建一个空主题库。

日常只更新成分股和索引时，可使用：

```powershell
.\update_theme_stock.bat
```

构建后验收：

```bash
uv run --frozen ashare-pilot themes query stats
uv run --frozen ashare-pilot themes query list --json
```

## 7. OpenCode 与自动调度

使用 OpenCode Desktop 时，它必须打开仓库根目录，并读取 `AGENTS.md`、`opencode.json` 和
`.agents/skills/`。Agent 执行业务命令时使用 `uv run --frozen ashare-pilot`，不得调用
已经迁移删除的 `.opencode/**/scripts/*.py`。

如需定时任务，先确认 OpenCode CLI 可被子进程找到：

```bash
opencode --version
uv run --frozen ashare-pilot automation scheduler run --dry-run
```

然后再启动：

批处理入口：

```powershell
.\auto.bat
```

Shell 入口：

```bash
./auto.sh
```

调度配置来自 `config/cron-tasks.json`，交易日和时区来自
`config/trading-calendar.json`。修改配置后必须重启调度器；停机期间错过的任务不会补跑。

## 8. 最终验收清单

Agent 应按顺序执行并记录退出码，不得只根据文件存在推断初始化成功：

```bash
uv --version
uv lock --check
uv run --frozen ashare-pilot --version
uv run --frozen ashare-pilot automation memory init
uv run --frozen ashare-pilot market-data quote sh600519 --json
uv run --frozen ashare-pilot themes query stats
uv run --frozen ashare-pilot automation scheduler run --dry-run
```

检查初始化生成的空规则模板：

```bash
uv run --frozen ashare-pilot automation rules check
```

开发或迁移验收时再运行完整测试：

```bash
uv run --frozen pytest -q
```

初始化完成必须同时满足：

- CLI 输出版本且退出码为 0；
- uv 锁文件与 `pyproject.toml` 一致；
- 行情查询返回结构化结果；
- 主题库统计可读取且不是空库；
- memory 描述文件、空规则模板和空索引已初始化，且没有预置或伪造策略规则；
- 规则治理检查通过；
- 调度 dry-run 能读取交易日历和任务配置；
- 所有项目入口都使用仓库默认的 `.venv`；
- `.cookie`、`memory/` 和运行产物没有进入 Git 暂存区。

## 9. 常见故障

### `No time zone found with key Asia/Shanghai`

环境依赖未同步。关闭已激活的其他虚拟环境，然后执行：

```bash
uv sync --frozen
```

### `Failed to hardlink files`

项目已在 `pyproject.toml` 中设置 `link-mode = "copy"`。若仍出现警告，确认当前命令是在
本仓库根目录运行，且没有使用 `--no-config`。

### 找不到工作区

确认当前目录或父目录同时包含 `pyproject.toml` 和 `config/`。从仓库外运行时传入
`--workspace` 或设置 `ASHARE_PILOT_WORKSPACE`。

### 找不到 `opencode`

 这只影响自动调度，不影响普通 `ashare-pilot` CLI。安装 OpenCode CLI、加入 `PATH`，
重新打开终端或桌面程序后再执行 dry-run。

## 10. 后续步骤：初始化 Cookie 与主题库

Agent 无法执行 `update_cookie.bat` — 该脚本打开 Chrome 浏览器后会阻塞终端等待用户
按 Enter 确认，Agent 无法完成这种终端交互。主题库构建也依赖有效 Cookie。

Agent 完成前述所有可自动化步骤（第 2–9 节）后，应提示用户手动执行以下操作：

### Cookie 初始化

东方财富认证状态保存在仓库根目录 `.cookie`，格式为：

```text
EASTMONEY_COOKIE=<cookie-string>
```

`.cookie` 含敏感信息，已被 Git 忽略。不得提交、打印或复制到日志和 Agent 回复中。

批处理入口：

```powershell
.\update_cookie.bat
```

Chrome 打开后完成登录或人机验证，返回终端按 Enter。成功标准是根目录生成非空 `.cookie`，
并且批处理输出 `Done`。

如果当前平台无法执行该批处理，应从受控凭据存储恢复 `.cookie`，或在能够执行批处理的
环境完成更新后安全传递该文件。不要让 Agent 在对话中索取 Cookie 内容。

当前核心 CLI 不会自动读取 `.env` 中的用户名和密码；不要把创建 `.env` 当作 Cookie
初始化的替代方案。

### 主题库构建

Cookie 就绪后，手动构建主题库。

全量批处理：

```powershell
.\update_theme.bat
```

仅更新成分股和索引：

```powershell
.\update_theme_stock.bat
```

或分步执行：

```bash
uv run --frozen ashare-pilot themes concepts fetch -q
uv run --frozen ashare-pilot themes concepts fetch-stocks
uv run --frozen ashare-pilot themes library build
```

### 完成验收

上述步骤完成后，Agent 可继续执行完整验收（行情查询、主题库统计、规则检查、调度 dry-run）。
