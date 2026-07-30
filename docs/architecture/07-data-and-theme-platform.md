# 数据与主题平台

## 1. 行情数据模块

`ashare_pilot.market_data` 将数据源、运行时工作区、交易范围和命令适配分离。

主要数据源：

| 数据源 | 主要用途 |
|---|---|
| 东方财富 | 全市场快照、资金流、龙虎榜、融资融券、概念和盘中统计 |
| 新浪 | 实时报价、全市场列表和部分分时数据 |
| 搜狐 | 默认历史日 K |
| 腾讯 | 报价补充/兼容数据 |

具体数据源选择与 fallback 位于 `_datasources/`。外部接口不是内部稳定合同，调用者
应使用 `market_data.api` 或 CLI。

## 2. HTTP 与认证

全局 HTTP 配置来自 `config/setting.json`，当前支持代理。东方财富 Cookie 存在
仓库根 `.cookie`，由 Windows Chrome 登录流程或可信备份生成；核心 CLI 不从
`.env` 读取凭据。

Cookie、网络响应和 cache 都不得作为 LLM 可补写的数据。认证或数据完整性失败应
由数据命令显式报告。

## 3. 缓存

| 路径 | 内容 | 可重建性 |
|---|---|---|
| `.cache/kline/` | 单股历史 K 线 | 可重建 |
| `.cache/intraday/{date}/` | 同日盘中 Compute 快照 | 可重建但运行内必须保持同一快照 |
| `.cache/theme-library/` | 主题抓取过程状态 | 可重建/续跑 |

盘中缓存虽然可重建，但同一次 14:30 工作流只能 Compute once，避免不同时间点的
数据被混合成一个策略合同。

## 4. 指标模块

`ashare_pilot.indicators` 提供 SMA、EMA、VWMA、RSI、MACD、Bollinger、ATR 等计算。
单股命令消费历史 K 线；pool 命令只为受控候选池批量补充指标。

日线和盘中流程都禁止用 `market-data stocks all` 作为预市场候选抓取捷径。全市场
能力用于专门的市场快照，不用于逐股技术计算。

## 5. 交易范围

`config/trading-scope.json` 是唯一交易范围配置：

- `sh*`、`sz*` 可进入范围；
- `sh688*` 和 `bj*` 排除；
- HK、US、期货不进入日线与隔夜候选；
- overrides 可表达未来的个别例外。

Scan、mapping、selection 和 operations 必须使用相同的范围解析逻辑，不能各自维护
前缀副本。

## 6. 持久主题库

`data/theme-library/` 建立 Theme → Concept → Stock 的离线知识：

```text
data/theme-library/
├── concepts/       东方财富概念及成员缓存
├── themes/         按主题聚合的成员与评分
├── stocks/         股票反向索引
├── index/          concept/stock/theme 查询索引
├── aliases/        关键词和主题别名
└── metadata/       构建版本与统计
```

`config/themes/theme-config.json` 定义主题、概念、别名、权重和 anchors；
`theme-library-config.json` 定义 coverage、角色和 purity/leader/candidate 评分参数。

## 7. 构建顺序

```bash
uv run --frozen ashare-pilot themes concepts fetch -q
uv run --frozen ashare-pilot themes concepts fetch-stocks
uv run --frozen ashare-pilot themes library build
```

概念成员支持按页 checkpoint 和续跑。任一概念未完整抓取时不能构建并替换当前主题库。
全量重置仅在明确需要时使用 `fetch-stocks --reset`。

## 8. 成员角色

主题成员分为：

| 角色 | 含义 |
|---|---|
| `core` | anchor 或达到产业 leader 阈值 |
| `qualified` | 通过 eligibility，但未达到 core |
| `edge` | 原始概念成员但未通过 eligibility |

角色描述股票与主题关系强弱，不等于股票投资质量。edge 仍可能因市场行为进入观察或
策略池，但不能代表主题核心强度。

## 9. 两种动态主题视图

### 9.1 日线新闻主题

日线 Step 1 使用新闻证据和离线 taxonomy，发布 `daily_themes.v2`。它回答“隔夜
催化映射到哪些可投资主题”。

### 9.2 盘中自底向上主题

14:30 流程使用上一版已发布主题成员关系乘以当日 Compute Pool 行情，发布
`intraday_theme_ranking.v2`。它回答“今天真实交易的股票共同指向哪些主题”。

盘中同时区分核心热度与边缘扩散，记录 `core_leader`、`momentum_leader`、
contributors 和全池 `stock_themes`。新闻主题和盘中主题不能相互替代。

## 10. 查询接口

```bash
uv run --frozen ashare-pilot themes query list --json
uv run --frozen ashare-pilot themes query theme <name> --json
uv run --frozen ashare-pilot themes query candidates <theme> --json
uv run --frozen ashare-pilot themes query stock <codes> --roles --json
uv run --frozen ashare-pilot themes query stats
```
