# A股早盘推荐与二次确认系统开发实施文档

> 文档类型：Engineering Plan  
> 版本：v1  
> 日期：2026-07-11  
> 上位设计：[`morning-recommendation-system-spec.md`](morning-recommendation-system-spec.md)  
> 涉及 Skill：`daily-market-analysis`、`daily-strategy`、`intraday-operation-guide`

## 实施状态（2026-07-11）

已完成：

- P0-A 完整 K 线选择、首根 K 与最新完整 K 分离；
- P0-B 三指数 `regime_live` 与 `global_action`；
- P0-C 机械类别上限、定性仓位档位单调降级、T+1 控制；
- `operation_snapshot.v3`、`operation_decision.v2` 及验证器；
- `daily_strategy.v3` 定性仓位校验；
- P2 `--slot`、09:35/09:40 多快照、原子 latest 写入；
- P2 类别状态迁移和策略池主题确认；
- `--quotes-fixture`、`--intraday-fixture-dir`、`--no-network` 离线回放入口；
- 2026-07-08～10 回归场景和端到端离线测试。

当前测试：daily-strategy 6 项，intraday-operation-guide 28 项。

Review修复：

- v3 `portfolio_limits` 已传播到盘中快照，并按总参与只数、单主题只数和相关标的数量统一限制；
- v3 个股 `t1_risk_plan` 原样投影到 `t1_controls.t1_exit_plan`；
- 盘前时间使用`datetime.time.fromisoformat`做语义校验，v3执行层遇到非法时间直接失败，不再静默回退。
- 增加迟到交付闸门：09:40无前序快照最高B且 `WATCH_ONLY`；09:45及以后无前序快照只允许C/D；09:45有09:40前序时才允许继续评估B→A。

仍待完成：

- 接入真实、可追溯的市场宽度数据；
- 使用后续运行自动保存的原始 09:35/09:40 响应建立真实历史 fixture；
- 主题确认从策略池扩展到 Theme Library 有界核心成员；
- 独立调度 09:35/09:40 任务；
- 前向执行日志与增量回测。

---

## 1. 文档目的

本文档负责把产品 Spec 转换成可提交代码的开发任务，重点说明：

- 修改哪些文件；
- 新增哪些脚本；
- 函数和数据结构如何设计；
- `daily_strategy.v1` 如何迁移到 v2；
- 如何排除未完成的 5 分钟 K 线；
- 如何计算市场级交易闸门；
- 如何保证 A/B/C/D 和仓位不可越权；
- 如何处理 A 股 T+1；
- 如何构造离线 fixture 和回放测试；
- 每个开发切片如何验收和提交。

本文档不是产品说明，不重新讨论为什么需要二次确认。业务目标与原则以上位 Spec 为准。

---

## 2. 当前代码基线

### 2.1 盘前阶段

| 文件 | 当前职责 |
|---|---|
| `.agents/skills/daily-market-analysis/SKILL.md` | 编排新闻、mapper、strategy 三阶段 |
| `.agents/skills/daily-strategy/SKILL.md` | 指导 LLM 生成 `strategy.json` |
| `.agents/skills/daily-strategy/scripts/validate_strategy_json.py` | 只接受 `daily_strategy.v1` |
| `.agents/skills/daily-strategy/scripts/compute_trade_profile.py` | 生成交易画像、锚点和仓位建议 |
| `.agents/skills/daily-strategy/scripts/render_daily_report_html.py` | 渲染盘前报告 |

### 2.2 二次确认阶段

| 文件 | 当前职责 | 已知问题 |
|---|---|---|
| `.agents/skills/intraday-operation-guide/SKILL.md` | 指导 A/B/C/D 人工操作卡生成 | 市场级确认不够结构化 |
| `.agents/skills/intraday-operation-guide/scripts/build_operation_snapshot.py` | 读取策略、mapper、行情和分时，计算逐股 flags | 使用最新返回 K 线，未排除未完成 K；首根 K 语义错误；无机械类别 |
| `.opencode/lib/fetch/fetch_stock.py` | 提供批量报价和单股分时接口 | 不负责 K 线完整性判断 |

### 2.3 下游消费者

变更 `strategy.json` 时必须回归：

| 消费者 | 风险 |
|---|---|
| `render_daily_report_html.py` | 新字段应兼容，不应破坏 v1 页面 |
| `build_operation_snapshot.py` | 当前硬编码只接受 v1 |
| `daily-trading-review/scripts/generate_verification_json.py` | 解析股票、市场状态和 profile |
| `daily-trading-review/scripts/entry_band_shadow_backtest.py` | 依赖 verification，而非直接依赖全部新字段 |
| `intraday-operation-guide/SKILL.md` | 输入和输出合同必须同步更新 |

---

## 3. 开发策略

### 3.1 先修正确性，再升级 schema

开发顺序固定为：

```text
P0-A  K线时间正确性
P0-B  市场级确认与机械闸门
P0-C  类别/仓位/T+1输出约束
P1    strategy.json v2
P2    多快照状态机与主题宽度
P3    前向回测和规则治理
```

原因：当前最危险的问题发生在二次确认脚本。如果先扩大盘前 schema，会增加迁移面，却不能立刻解决未完成 K 线和错误 A 类建议。

### 3.2 每个切片必须保持可运行

- 每个切片独立提交；
- 每次修改后保留旧命令可运行；
- schema 迁移期间读取端兼容 v1/v2；
- 新产物先并行写入，不立即删除旧文件名；
- fixture 测试不访问网络；
- 实时 smoke test 只用于补充，不作为唯一验收。

### 3.3 不修改数据源返回语义

不要在 `.opencode/lib/fetch/fetch_stock.py` 内把某根 K 线标记为完成，因为数据源接口本身不知道调用者的交易日期、时区和快照槽位。

K 线完整性筛选放在 `intraday-operation-guide` 层。

---

## 4. 目标文件结构

第一阶段允许保留单文件实现；完成 P0 后建议结构如下：

```text
.agents/skills/intraday-operation-guide/
├── SKILL.md
├── scripts/
│   ├── build_operation_snapshot.py
│   ├── build_operation_decision.py
│   ├── validate_operation_snapshot.py
│   ├── validate_operation_decision.py
│   ├── operation_models.py
│   ├── operation_time.py
│   ├── market_confirmation.py
│   └── mechanical_classification.py
└── tests/
    ├── fixtures/
    │   ├── 2026-07-08/
    │   ├── 2026-07-09/
    │   └── 2026-07-10/
    ├── test_completed_bars.py
    ├── test_market_confirmation.py
    ├── test_mechanical_classification.py
    ├── test_position_caps.py
    ├── test_t1_semantics.py
    └── test_snapshot_validation.py
```

如果项目暂不引入 `pytest`，测试可先使用 Python 标准库 `unittest`。不要为了测试框架增加不必要依赖。

---

## 5. P0-A：K 线时间正确性

### 5.1 修改文件

```text
.agents/skills/intraday-operation-guide/scripts/build_operation_snapshot.py
.agents/skills/intraday-operation-guide/tests/test_completed_bars.py
```

### 5.2 时间模型

新增常量：

```python
MARKET_TZ = ZoneInfo("Asia/Shanghai")
MORNING_OPEN = time(9, 30)
MORNING_CLOSE = time(11, 30)
AFTERNOON_OPEN = time(13, 0)
AFTERNOON_CLOSE = time(15, 0)
BAR_MINUTES = 5
```

所有内部时间使用带时区的 `datetime`。输出使用 ISO 8601：

```text
2026-07-13T09:35:08+08:00
```

不要继续使用无时区的：

```text
2026-07-13 09:35:08
```

### 5.3 新增函数

建议先放在 `build_operation_snapshot.py`，稳定后移入 `operation_time.py`。

```python
def parse_exchange_datetime(value: Any, trade_date: date) -> datetime | None:
    """Parse provider bar time into Asia/Shanghai aware datetime."""


def infer_bar_interval(
    raw_bar_time: datetime,
    scale_minutes: int,
    provider_time_semantics: str,
) -> tuple[datetime, datetime]:
    """Return (bar_start, bar_end)."""


def is_completed_bar(bar_end: datetime, snapshot_time: datetime) -> bool:
    return bar_end <= snapshot_time


def select_completed_bars(
    raw_bars: list[dict[str, Any]],
    snapshot_time: datetime,
    scale_minutes: int = 5,
) -> list[dict[str, Any]]:
    """Normalize, sort, deduplicate, and exclude incomplete/future bars."""


def get_first_session_bar(
    completed_bars: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the completed 09:30-09:35 bar only."""


def get_latest_completed_bar(
    completed_bars: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Return the most recent completed bar."""
```

### 5.4 先确认数据源时间语义

当前样本表现为：09:36 快照拿到 `09:40:00`。实现前必须用保存的原始响应确认新浪分时字段代表：

- K 线开始时间；或
- K 线结束时间；或
- 当前聚合桶标签。

不要根据字段名称猜测。

fixture 中必须保存：

```text
raw_intraday_response.json
snapshot_time.txt
expected_completed_bars.json
```

如果 `09:40:00` 表示 09:35～09:40 的聚合桶结束标签，则 09:36 必须排除。

### 5.5 重写 K 线 flags

当前 `compute_kline_flags(klines)` 改为：

```python
def compute_kline_flags(
    raw_klines: list[dict[str, Any]],
    snapshot_time: datetime,
    trade_date: date,
) -> dict[str, Any]:
```

返回结构：

```json
{
  "data_warning": [],
  "snapshot_time": "2026-07-13T09:40:05+08:00",
  "completed_bar_count": 2,
  "first_bar": {
    "bar_start": "2026-07-13T09:30:00+08:00",
    "bar_end": "2026-07-13T09:35:00+08:00",
    "is_complete": true,
    "open": 10.0,
    "high": 10.2,
    "low": 9.95,
    "close": 10.15,
    "volume": 100000,
    "red_flag": false,
    "close_position": 0.8
  },
  "latest_completed_bar": {
    "bar_start": "2026-07-13T09:35:00+08:00",
    "bar_end": "2026-07-13T09:40:00+08:00",
    "is_complete": true,
    "price_strength_confirmed": true,
    "volume_multiple": 1.6
  }
}
```

删除顶层含混字段：

```text
latest_bar_time
first_bar_red_flag
```

兼容期间可以保留 deprecated 投影，但内部判断只能使用嵌套新字段。

### 5.6 成交量比较修正

当前实现用“当前最新 K 与前 5 根平均”比较。开盘早期样本数不足，且开盘首根天然放量，容易失真。

P0 最低实现：

```python
def recent_volume_baseline(completed_bars: list[dict], exclude_latest=True) -> float | None:
    # 至少 2 根历史完整 bar 才生成 recent baseline
```

输出额外字段：

```json
{
  "volume_baseline_kind": "recent_completed_bars",
  "volume_baseline_sample_n": 3,
  "volume_multiple": 1.42,
  "volume_confirmed": false
}
```

如果样本不足：

```json
{
  "volume_multiple": null,
  "volume_confirmed": null,
  "data_warning": ["volume_baseline_insufficient"]
}
```

不得把 `null` 当作 `false` 后再声称“缩量确认”。

P2 再加入“昨日同期 5 分钟量”基线。

### 5.7 单元测试

至少覆盖：

```python
def test_093459_has_no_first_completed_bar(): ...
def test_093505_includes_only_first_bar(): ...
def test_093600_excludes_094000_bucket(): ...
def test_094005_includes_second_bar(): ...
def test_first_bar_flag_never_uses_latest_bar(): ...
def test_duplicate_provider_bars_are_deduplicated(): ...
def test_future_date_bar_is_rejected(): ...
def test_lunch_break_is_not_counted_as_bar(): ...
```

### 5.8 验收命令

```bash
python -m unittest discover \
  -s .agents/skills/intraday-operation-guide/tests \
  -p 'test_completed_bars.py'
```

验收标准：

- 09:36 回放不再读取 `09:40` 未完成桶；
- 首根 K 和最新完整 K 可以不同；
- 没有完整 K 时明确输出 warning，而不是猜测。

---

## 6. P0-B：市场级确认与全局闸门

### 6.1 修改文件

```text
.agents/skills/intraday-operation-guide/scripts/build_operation_snapshot.py
.agents/skills/intraday-operation-guide/scripts/market_confirmation.py
.agents/skills/intraday-operation-guide/tests/test_market_confirmation.py
```

### 6.2 指数抓取

复用现有接口：

```python
fetch_stocks(["sh000001", "sz399001", "sh000688"])
```

不要逐个调用。

标准化函数：

```python
INDEX_CODES = ("sh000001", "sz399001", "sh000688")


def normalize_index_quotes(
    quotes: list[dict[str, Any]],
    snapshot_time: datetime,
) -> tuple[dict[str, Any], list[str]]:
    """Validate quote code, time, price, open and yestclose."""
```

每个指数输出：

```json
{
  "code": "sz399001",
  "open_pct": -0.35,
  "current_pct": -0.62,
  "quote_time": "2026-07-13T09:40:01+08:00",
  "lag_seconds": 4,
  "valid": true
}
```

### 6.3 `regime_live` 最低版本

P0 不引入复杂模型，先实现透明、可测试的规则函数：

```python
REGIME_ORDER = {
    "panic": 0,
    "weak": 1,
    "neutral": 2,
    "strong-sector": 3,
}


def classify_live_regime(
    sh_pct: float,
    sz_pct: float,
    kcb_pct: float,
    regime_prior: str,
) -> tuple[str, list[str]]:
    ...
```

建议初始规则：

1. 深证 `<= -1.5%`：`weak`，若其他指数同步重挫可为 `panic`；
2. 深证 `<= -0.5%`：最高 `neutral`；
3. 深证 `< -0.3%` 且 prior 为 strong：至少降一级；
4. 科创强、深证弱：标记结构性背离，不能为全局 strong；
5. 三指数方向基本一致且主题强，才允许 `strong-sector`；
6. 数据不足不输出强市。

阈值先集中定义，不散落在分支中：

```python
@dataclass(frozen=True)
class RegimeThresholds:
    preopen_recheck_pct: float = -0.3
    downgrade_pct: float = -0.5
    weak_pct: float = -1.5
    panic_pct: float = -2.5
    divergence_pct: float = 1.5
```

### 6.4 `global_action`

```python
GLOBAL_ACTIONS = {"NORMAL", "SELECTIVE", "WAIT", "NO_NEW_BUY"}


def compute_global_action(
    regime_live: str,
    data_warnings: list[str],
    index_states: dict[str, Any],
    snapshot_slot: str,
) -> tuple[str, list[str]]:
    ...
```

P0 规则：

| 条件 | global_action |
|---|---|
| 指数报价缺失或严重过期 | `WAIT` |
| `panic` | `NO_NEW_BUY` |
| `weak` | `NO_NEW_BUY` |
| 指数明显背离 | `SELECTIVE` |
| `neutral` | `SELECTIVE` |
| `strong-sector` 且数据完整 | `NORMAL` |

`NO_NEW_BUY` 是硬闸门：所有股票的 `max_allowed_class` 最高为 C。

### 6.5 市场宽度接口

当前仓库没有稳定的全市场宽度脚本时，P0 不得临时调用全量 5500 股抓取。

实现顺序：

1. P0：三指数确认；
2. P1/P2：接入已有可用的板块/市场快照源；
3. 如果宽度不可用，输出：

```json
{
  "breadth": null,
  "data_warnings": ["market_breadth_unavailable"],
  "global_action": "SELECTIVE"
}
```

不要伪造上涨家数，也不要为了补宽度违反 daily pipeline 的性能约束。

### 6.6 快照顶层变更

```json
{
  "schema_version": "intraday_operation_snapshot.v2",
  "date": "2026-07-13",
  "generated_at": "2026-07-13T09:40:05+08:00",
  "snapshot_slot": "09:40",
  "market_confirmation": {
    "regime_prior": "strong-sector",
    "regime_live": "weak",
    "regime_confirmed": "weak",
    "regime_changed": true,
    "indices": {},
    "breadth": null,
    "global_action": "NO_NEW_BUY",
    "reasons": ["sz399001_below_-0.5"],
    "data_warnings": ["market_breadth_unavailable"]
  }
}
```

### 6.7 测试

```python
def test_strong_prior_is_downgraded_when_sz_open_weak(): ...
def test_kcb_strength_cannot_override_sz_weakness(): ...
def test_missing_index_quote_forces_wait(): ...
def test_weak_regime_forces_no_new_buy(): ...
def test_neutral_regime_is_selective(): ...
def test_market_breadth_missing_never_yields_normal(): ...
```

### 6.8 历史验收

用 2026-07-10 保存的指数/个股数据重放：

- 盘前 `regime_prior=strong-sector`；
- 开盘后深证走弱；
- 预期 `regime_changed=true`；
- `global_action` 至少降为 `SELECTIVE`，满足弱市阈值时为 `NO_NEW_BUY`；
- 不得保留原操作指南中的扩大仓位 A 类。

---

## 7. P0-C：机械分类、定性仓位档位与 T+1

### 7.1 新增模块

```text
.agents/skills/intraday-operation-guide/scripts/mechanical_classification.py
.agents/skills/intraday-operation-guide/scripts/build_operation_decision.py
.agents/skills/intraday-operation-guide/scripts/validate_operation_decision.py
```

### 7.2 数据模型

```python
CLASS_RANK = {"D": 0, "C": 1, "B": 2, "A": 3}


@dataclass
class PositionTiers:
    morning: str
    market_adjusted: str
    signal_adjusted: str
    portfolio_adjusted: str
    final: str


@dataclass
class MechanicalDecision:
    mechanical_class: str
    max_allowed_class: str
    class_reasons: list[str]
    hard_blocks: list[str]
    position_tier: PositionTiers
```

### 7.3 机械分类函数

```python
def compute_mechanical_decision(
    strategy: dict[str, Any],
    stock_snapshot: dict[str, Any],
    market_confirmation: dict[str, Any],
    snapshot_time: datetime,
) -> MechanicalDecision:
    ...
```

判断顺序必须固定：

```text
1. schema/date/code/data hard block
2. morning direction/profile block
3. global_action cap
4. earliest/latest entry time
5. pre-entry invalidations
6. theme cap（P2 前可为 unknown）
7. stock price/volume/VWAP/anchor signals
8. qualitative position tier downgrade
9. mechanical class
```

### 7.4 类别规则伪代码

```python
if severe_data_error or strategy_direction in {"看空"}:
    return D

if global_action == "NO_NEW_BUY":
    return min(signal_class, C)

if now < earliest_entry_time:
    return min(signal_class, B)

if pre_entry_invalidation_triggered:
    return D

if high_open_fade and first_bar.red_flag:
    return D

if extended_from_anchor:
    return min(signal_class, C)

if all_required_confirmations:
    return A

if thesis_valid_and_one_machine_trigger_exists:
    return B

return C
```

不要使用自由文本包含关系判断盘前不买条件作为唯一实现。P0 可保留规则映射，P1 应把关键条件结构化进 `preopen_plan`。

### 7.5 定性仓位档位

```python
def compute_position_tiers(
    morning_tier: str,
    global_action: str,
    mechanical_class: str,
    data_warning_count: int,
) -> PositionTiers:
    ...
```

建议降档规则：

| 条件 | 档位处理 |
|---|---|
| `NORMAL` | 保持盘前档位 |
| `SELECTIVE` | `STANDARD→LIGHT`，`LIGHT→WATCH_ONLY` |
| `WAIT` | `WATCH_ONLY` |
| `NO_NEW_BUY` | `WATCH_ONLY` |
| A | 保持当前档位 |
| B/C/D | `WATCH_ONLY`，未触发前不形成可执行意图 |
| 非严重 data warning | 至少降一级，不允许增加 |

核心 invariant：

```python
rank(final) <= rank(portfolio_adjusted) <= rank(signal_adjusted)
<= rank(market_adjusted) <= rank(morning)
```

任何违反都由 validator 报错。

### 7.6 `operation_decision.json`

`build_operation_decision.py` 输入：

```bash
uv run --frozen ashare-pilot operations decision build \
  --snapshot operation/2026-07-13/operation_snapshot_0940.json \
  --output operation/2026-07-13/operation_decision_0940.json
```

第一版由脚本直接使用 `mechanical_class` 作为 `final_class`。如果仍保留 LLM 调整，则 LLM 写 annotations，再由脚本合并：

```text
operation_decision.base.json
operation_decision.annotations.json
operation_decision.json
```

推荐采用后一种结构，延续项目现有 base/annotations/final 模式，避免 LLM 直接手写完整机器合同。

annotations 只允许：

```json
{
  "code": "sz000977",
  "requested_class": "B",
  "reason": "量能未确认，保守降级",
  "trigger_text": "完整5分钟K放量站稳VWAP"
}
```

合并器校验：

```python
CLASS_RANK[requested_class] <= CLASS_RANK[max_allowed_class]
```

### 7.7 T+1 字段

单股决策必须输出：

```json
{
  "pre_entry_invalidation": {
    "machine_condition": "price < 40.50",
    "display": "买入前跌破40.50则取消"
  },
  "post_entry_t_risk_alert": {
    "machine_condition": "price < 40.50",
    "display": "成交后若跌破40.50，标记为T+1高风险仓"
  },
  "t1_exit_plan": {
    "gap_up": "...",
    "flat_open": "...",
    "gap_down": "..."
  }
}
```

validator 检查禁止词不能简单全局扫描“止损”，因为历史规则和风险说明可能合理出现。应检查结构：

- `same_day_sell_action` 必须不存在或为 null；
- 新仓操作字段不得为 `SELL`；
- `pre_entry_invalidation` 必须明确是成交前；
- 卖出动作只允许在 `t1_exit_plan`。

### 7.8 Skill 文档更新

修改 `.agents/skills/intraday-operation-guide/SKILL.md`：

- 快照命令增加 `--slot`；
- 先验证 snapshot，再生成 decision；
- Markdown 只读取 final decision；
- 强调 LLM 只能降级；
- 删除“失效即离场”这类可能被理解为 T 日卖出的表述；
- 增加已成交/未成交两种卡片模板；
- 09:35 前禁止 A；
- `NO_NEW_BUY` 下禁止 A/B。

---

## 8. P1：`strategy.json` v2 迁移

### 8.1 修改文件

```text
.agents/skills/daily-market-analysis/SKILL.md
.agents/skills/daily-strategy/SKILL.md
.agents/skills/daily-strategy/scripts/validate_strategy_json.py
.agents/skills/daily-strategy/scripts/render_daily_report_html.py
.agents/skills/intraday-operation-guide/scripts/build_operation_snapshot.py
.agents/skills/daily-trading-review/scripts/generate_verification_json.py
```

### 8.2 合同切换策略

- validator 只接受 `daily_strategy.v3`；
- 新运行只生成定性 `position_tier`；
- 不读取、不迁移、不回填旧数值仓位合同；
- 回测样本从 v3 启用日期重新起算，避免合同变化混合。

### 8.3 v3 定性计划

```python
preopen_plan = {
    "decision": "CONDITIONAL",
    "earliest_entry_time": "09:35:05",
    "latest_entry_time": "10:00:00",
    "requires_first_bar": True,
    "requires_market_confirmation": True,
    "requires_theme_confirmation": True,
    "entry_setup": map_profile_to_setup(stock),
    "pre_entry_invalidations": [stock.get("no_buy_condition")],
}
```

`position_tier` 只允许 `WATCH_ONLY|LIGHT|STANDARD`，不得附带百分比。

### 8.4 validator 结构

重构为：

```python
def validate_v3(doc, errors): ...
def validate_portfolio_limits(doc, errors): ...
def validate_preopen_plan(stock, index, errors): ...
def validate_t1_plan(stock, index, errors): ...
```

CLI 增加：

```bash
python .../validate_strategy_json.py predict/2026-07-13/strategy.json
python .../validate_strategy_json.py predict/2026-07-13/strategy.json
```

validator 只接受 `daily_strategy.v3`。

### 8.5 下游兼容

`render_daily_report_html.py`：

- 展示“最早入场时间”“需要开盘确认”“T+1 风险”和定性仓位档位；
- 不从 HTML 反向解析数据。

`generate_verification_json.py`：

- 读取 `position_tier`，不记录数值仓位；
- 增加记录 strategy schema version；
- 增加确认槽位和执行决策关联字段，但允许为空。

---

## 9. P2：多快照状态机

### 9.1 CLI

`build_operation_snapshot.py` 增加：

```text
--slot auto|09:35|09:40|09:45
--as-of ISO_DATETIME       # fixture/replay only
--quotes-fixture PATH      # tests/replay only
--intraday-fixture-dir PATH
--no-network               # fixture 缺失即失败
```

生产命令：

```bash
uv run --frozen ashare-pilot operations snapshot build \
  --date 2026-07-13 \
  --slot 09:35 \
  -o operation/2026-07-13/operation_snapshot_0935.json
```

回放命令：

```bash
uv run --frozen ashare-pilot operations snapshot build \
  --date 2026-07-10 \
  --slot 09:40 \
  --as-of 2026-07-10T09:40:05+08:00 \
  --quotes-fixture .agents/skills/intraday-operation-guide/tests/fixtures/2026-07-10/quotes_0940.json \
  --intraday-fixture-dir .agents/skills/intraday-operation-guide/tests/fixtures/2026-07-10/intraday \
  --no-network \
  -o /tmp/operation_snapshot_2026-07-10_0940.json
```

### 9.2 文件写入

生产时：

```text
operation/{date}/operation_snapshot_0935.json
operation/{date}/operation_snapshot_0940.json
operation/{date}/operation_snapshot_0945.json
operation/{date}/operation_snapshot.latest.json
```

使用原子写：

```python
def atomic_write_json(path: Path, doc: dict[str, Any]) -> None:
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(...)
    temp.replace(path)
```

### 9.3 迁移函数

```python
ALLOWED_TRANSITIONS = {
    "A": {"A", "B", "C", "D"},
    "B": {"A", "B", "C", "D"},
    "C": {"C", "D"},
    "D": {"D"},
}


def validate_transition(
    previous: dict[str, Any],
    current: dict[str, Any],
    strategy: dict[str, Any],
) -> list[str]:
    ...
```

C→A 只有 `preopen_plan.allow_reassessment=true` 时允许。

每只股票输出：

```json
{
  "previous_class": "B",
  "current_class": "A",
  "transition": "B_TO_A",
  "transition_reasons": ["second_bar_confirmed", "above_vwap"]
}
```

### 9.4 调度

不要把 09:35 和 09:40 两次运行硬编码进 `daily-market-analysis` 的长任务中。盘前任务和确认任务应独立调度：

```text
09:20 daily-market-analysis
09:35 intraday-operation-guide --slot 09:35
09:40 intraday-operation-guide --slot 09:40
```

原因：

- 避免盘前任务长时间 sleep；
- 失败可独立重试；
- 日志和 SLA 独立；
- 操作层不需要保持 LLM 会话存活。

如果仍使用现有 cron daemon，应增加可配置多任务，而不是在脚本中 `sleep`。

---

## 10. P2：主题确认数据

### 10.1 原则

- 不抓全市场 5500 只股票；
- 只抓当日 strategy 涉及主题的核心/候选成员；
- 使用 Theme Library 映射；
- 每个主题限制成员数量；
- 对数据缺失明确降级。

### 10.2 数据结构

```python
def build_theme_member_codes(
    strategy: dict[str, Any],
    mapper: dict[str, Any],
    max_codes_per_theme: int = 10,
) -> dict[str, list[str]]:
    ...


def compute_theme_confirmation(
    theme: str,
    member_quotes: list[dict[str, Any]],
    core_codes: set[str],
) -> dict[str, Any]:
    ...
```

指标：

- `member_advance_ratio`；
- `member_above_vwap_ratio`；
- `core_confirmation_ratio`；
- `leader_above_vwap`；
- `open_to_current_fade_pct`；
- `valid_member_n`；
- `expected_member_n`。

最低样本：

```text
valid_member_n < 3 → UNKNOWN
```

主题状态先用规则表，不在 P2 引入模型训练。

---

## 11. 验证器实现

### 11.1 `validate_operation_snapshot.py`

CLI：

```bash
uv run --frozen ashare-pilot operations snapshot validate \
  operation/2026-07-13/operation_snapshot_0940.json
```

检查：

- schema；
- 日期和带时区时间；
- snapshot slot；
- source strategy/mapper；
- source run_id；
- 指数代码覆盖；
- quote lag；
- `global_action` 枚举；
- 股票代码唯一；
- strategy 股票全覆盖；
- K 线 `bar_end <= snapshot_time`；
- first bar 必须为 09:30～09:35；
- data warning 类型；
- mechanical class 枚举；
- position invariant；
- `NO_NEW_BUY` 下不存在 A/B 上限；
- hard block 对应 D；
- T+1 字段完整性。

### 11.2 `validate_operation_decision.py`

检查：

- source snapshot hash/path；
- final class 不超过 max allowed class；
- final position 不超过 snapshot cap；
- A 类有可执行条件；
- B 类恰好一个主要触发条件；
- C/D 无可执行仓位；
- 新仓无 T 日 SELL；
- 状态迁移合法；
- 所有文本股票代码和数值与机器字段一致。

### 11.3 输出码

统一：

| Exit code | 含义 |
|---:|---|
| 0 | 校验通过 |
| 1 | 合同或业务校验失败 |
| 2 | CLI 使用错误 |
| 3 | 输入缺失或无法读取 |

---

## 12. Fixture 与历史回放

### 12.1 fixture 内容

每个日期目录保存：

```text
fixtures/2026-07-10/
├── strategy.json
├── mapper.json
├── index_quotes_0935.json
├── index_quotes_0940.json
├── stock_quotes_0935.json
├── stock_quotes_0940.json
├── intraday/
│   ├── sz000977.json
│   └── ...
├── expected_snapshot_0935.json
├── expected_snapshot_0940.json
└── expected_decision_0940.json
```

fixture 应脱敏但不得修改影响计算的价格、时间和量。

### 12.2 三个历史场景

#### 2026-07-08

目标：验证早盘 strong-sector 判断与实际市场分化时能够降级。

#### 2026-07-09

目标：验证强市中系统仍能因为远离锚点、缺数据或无量把股票留在 B/C/D。

#### 2026-07-10

目标：验证市场反转能够关闭追涨，不再出现盘中层扩大仓位。

### 12.3 Golden file 注意事项

不要对整个 JSON 做脆弱的字符串全量比较。优先断言关键字段：

```python
self.assertEqual(snapshot["market_confirmation"]["global_action"], "NO_NEW_BUY")
self.assertLessEqual(CLASS_RANK[stock["max_allowed_class"]], CLASS_RANK["C"])
self.assertLessEqual(
    POSITION_TIER_RANK[stock["position_tier"]["final"]],
    POSITION_TIER_RANK[stock["position_tier"]["morning"]],
)
```

对 generated_at、路径和 reason 顺序使用归一化比较。

---

## 13. 回测与观测

### 13.1 新增事件记录

每次决策输出机器事件：

```json
{
  "date": "2026-07-13",
  "slot": "09:40",
  "code": "sz000977",
  "prior_class": "B",
  "final_class": "A",
  "position_max": 0.005,
  "market_regime": "neutral",
  "theme_state": "CONFIRMED",
  "triggered": true
}
```

可按日写普通 JSON 数组；只有未来变成事件流时再考虑 NDJSON。

### 13.2 日志字段

运行日志至少包含：

- run_id；
- snapshot slot；
- 开始/结束时间；
- 网络调用数量；
- 指数成功数；
- 个股成功数；
- 分时成功数；
- 数据 warning 数；
- A/B/C/D 数；
- global action；
- validator 结果；
- 总耗时。

### 13.3 性能预算

| 阶段 | 目标 |
|---|---:|
| 批量指数/股票报价 | ≤5 秒 |
| 10 只股票分时抓取 | ≤20 秒 |
| 计算与验证 | ≤2 秒 |
| LLM 卡片生成 | ≤30 秒 |
| 09:35 全流程 | ≤60 秒 |

后续可并行分时调用，但应设置并发上限，避免数据源限流。

---

## 14. 文档与合同同步

以下文件在对应切片中同步更新：

| 文件 | 更新内容 |
|---|---|
| `daily-market-analysis/SKILL.md` | 盘前只输出条件计划、v2 校验和 cutoff |
| `daily-strategy/SKILL.md` | v2 schema、T+1、preopen plan |
| `intraday-operation-guide/SKILL.md` | 多快照、机械上限、T+1 卡片 |
| `docs/entry-band-backtest-system.md` | 增加 09:35/09:40 确认组 |
| `docs/entry-band-backtest-tracking.md` | 记录正式启用日期和样本口径 |
| `docs/README.md` | 链接产品 Spec 与开发文档 |

不要保留相互冲突的说明，例如一处写 `strategy.json v1`，另一处要求只生成 v2。

---

## 15. 推荐提交切片

### Commit 1：完整 K 线

```text
fix: use only completed intraday bars in operation guide
```

内容：时间解析、完整 K 线筛选、首根 K 修复、单元测试。

### Commit 2：市场闸门

```text
feat: add live market confirmation to operation snapshots
```

内容：三指数、regime live、global action、测试。

### Commit 3：机械类别与仓位

```text
feat: enforce operation class and position caps
```

内容：mechanical class、max allowed class、position invariant、decision validator。

### Commit 4：T+1 语义

```text
fix: separate pre-entry invalidation from T+1 exit handling
```

内容：新仓 T 日风险提示、T+1 计划、Skill 卡片更新。

### Commit 5：strategy v2

```text
feat: add conditional preopen plans to daily strategy
```

内容：v2 schema、validator、v1 投影、下游兼容。

### Commit 6：多快照状态机

```text
feat: track 0935 and 0940 operation decisions
```

内容：slot、原子写、迁移校验、latest 投影。

### Commit 7：主题确认与回放

```text
feat: add theme breadth confirmation and replay fixtures
```

内容：主题成员、宽度、历史 fixture、回放报告。

---

## 16. 各阶段验收清单

### P0-A

- [ ] 09:36 不读取 09:40 未完成 K；
- [ ] 首根 K 与最新 K 分离；
- [ ] 时间带 `+08:00`；
- [ ] K 线不足时输出 warning；
- [ ] 离线测试通过。

### P0-B

- [ ] 快照包含三指数；
- [ ] 输出 `regime_prior/regime_live/regime_confirmed`；
- [ ] 输出 `global_action`；
- [ ] 指数缺失自动 WAIT；
- [ ] 弱市自动 NO_NEW_BUY；
- [ ] 7 月 10 日回放能够降级。

### P0-C

- [ ] 每股有 mechanical/max class；
- [ ] LLM 不能升级；
- [ ] 仓位逐层递减；
- [ ] C/D 可执行仓位为 0；
- [ ] T 日新仓没有当日 SELL；
- [ ] snapshot 和 decision validator 通过。

### P1

- [ ] 新运行生成 v2；
- [ ] 历史 v1 可读；
- [ ] 所有股票有 preopen plan；
- [ ] 所有股票有 T+1 plan；
- [ ] review 和 HTML 不回归；
- [ ] 文档合同一致。

### P2

- [ ] 09:35/09:40 独立文件；
- [ ] 状态迁移合法；
- [ ] latest 文件原子更新；
- [ ] 主题数据不足明确 UNKNOWN；
- [ ] 可以离线重放三天样本。

---

## 17. 开发完成后的标准命令

### 盘前

```bash
/daily-market-analysis

uv run --frozen ashare-pilot strategy daily validate \
  predict/2026-07-13/strategy.json --require-v2
```

### 09:35

```bash
uv run --frozen ashare-pilot operations snapshot build \
  --date 2026-07-13 --slot 09:35 \
  -o operation/2026-07-13/operation_snapshot_0935.json

uv run --frozen ashare-pilot operations snapshot validate \
  operation/2026-07-13/operation_snapshot_0935.json

uv run --frozen ashare-pilot operations decision build \
  --snapshot operation/2026-07-13/operation_snapshot_0935.json \
  --output operation/2026-07-13/operation_decision_0935.json
```

### 09:40

```bash
uv run --frozen ashare-pilot operations snapshot build \
  --date 2026-07-13 --slot 09:40 \
  -o operation/2026-07-13/operation_snapshot_0940.json

uv run --frozen ashare-pilot operations decision validate \
  operation/2026-07-13/operation_decision_0940.json
```

### 测试

```bash
python -m unittest discover \
  -s .agents/skills/intraday-operation-guide/tests \
  -p 'test_*.py'

python -m py_compile \
  .agents/skills/intraday-operation-guide/scripts/*.py \
  .agents/skills/daily-strategy/scripts/validate_strategy_json.py
```

---

## 18. 首轮开发建议

首轮只实现 Commit 1～4，不立即升级 `strategy.json v2`：

1. 完整 K 线；
2. 首根 K 修复；
3. 三指数 live regime；
4. global action；
5. mechanical/max class；
6. 仓位上限；
7. T+1 风控表达；
8. 7 月 8～10 日 fixture 回放。

这组改动可以在继续读取 `daily_strategy.v1` 的情况下完成，风险最小，也最容易证明二次确认层是否真正减少错误开仓。

完成首轮并通过历史重放后，再进入 v2 合同迁移。否则盘前和盘中同时大改，一旦结果异常，很难区分是策略合同、实时确认还是数据时间口径造成的。
