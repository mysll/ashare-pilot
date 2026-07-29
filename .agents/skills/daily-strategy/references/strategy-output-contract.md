# Step 3 Decision Draft Contract

写入 `predict/YYYY-MM-DD/strategy.draft.json`。这是非合同、仅包含 LLM
决策的临时产物：

```json
{
  "schema_version": "daily_strategy_draft.tmp.v3",
  "date": "YYYY-MM-DD",
  "market": {
    "regime_prior": "panic|weak|neutral|strong-sector",
    "notes": "最终 regime 的简短理由"
  },
  "stocks": [],
  "exclusion_overrides": []
}
```

输入 SHA-256 由 Python `prepare` 写入 `.strategy_llm_input.sha256`，并由
`finalize` 校验。LLM 不得计算、复制或输出输入哈希，也不得在草稿中写
`source`。每次 `prepare` 后必须重新生成草稿，旧草稿不可复用。

LLM 不得输出以下 Python-owned 字段：

- 根级 `generated_at`、`portfolio_limits`；
- market 的 `requires_open_confirmation`、`stop_atr_multiplier`；
- stock 的 `name`、`horizon`、`entry_trigger`、`no_buy_condition`、
  `preopen_plan`、`t1_risk_plan`、`profile_trace`、`profile`。

## Selected stock

`stocks[]` 只含最终入选股，顺序即最终顺序。每行必须含：

```json
{
  "code": "sz000001",
  "sector": "仅多来源主题候选需要显式指定",
  "direction": "看多|偏多",
  "rating": "5★|4★|3★|2★|1★|—",
  "entry_profile": "趋势跟随|回调布局|强势接力|防御布局",
  "anchor": "MA5|MA10|MA20|OPEN|VWAP|首根5min|FLEX|无|—",
  "position_tier": "WATCH_ONLY|LIGHT|STANDARD",
  "entry_setup": "LIMIT_UP_CONT|MOMENTUM|FIRST_BAR_OR_PULLBACK|PULLBACK|DEFENSIVE|WATCH_ONLY",
  "rules_applied": ["Rxx"],
  "reasoning": {
    "source_basis": "真实主题/role/news依据",
    "direction_path": "最终 Direction 链路",
    "risk": "仅有实际风险判断时填写",
    "reread": "仅触发回读时填写",
    "override": "仅发生 override 时填写"
  },
  "profile_overrides": {},
  "plan_overrides": {}
}
```

单一来源主题候选省略 `sector`，Python 使用 `primary_theme`。多来源主题候选
必须显式选择输入中真实的来源主题。

`reasoning.source_basis` 与 `reasoning.direction_path` 必填；其余 reasoning
字段无内容时直接省略，不要写 `—`。每个 reasoning 字段及 market notes
最多 300 字。

不要写 `profile`；finalize 用最终 regime 重算。`profile_overrides` 每项格式：

```json
{"preferred_anchor":{"value":"MA5","reason":"R68强主线切换MA5"}}
```

白名单：`playbook`、`preferred_anchor`、`chase_policy`、`entry_window`、
`stop_policy`、`time_horizon`、`invalidation`、`note`、
`max_extension_atr`，以及只能取 Step 2 精确值或两位小数值的
`ref_ma20/ref_ma5/ref_high20`；`ref_ma10` 只能为 null，
`time_horizon` 必须保持 `T+1`。

标准执行计划由 Python 生成。确有个股例外时，`plan_overrides` 只允许：

- `entry_trigger`
- `no_buy_condition`
- `pre_entry_invalidations`
- `t1_risk_plan`

每项同样使用 `{"value": ..., "reason": "..."}`。不得 override 固定时间、
确认布尔值、T+1 horizon 或组合限制。

`position_tier`：

- `WATCH_ONLY`：仅观察，不形成新买入意图；
- `LIGHT`：轻仓意图，不代表固定百分比、金额、股数或手数；
- `STANDARD`：标准仓意图，不代表固定百分比、金额、股数或手数。

禁止输出 `position_budget`、`position_multiplier`、任何 exposure 百分比或
数值仓位上限。

`exclusion_overrides` 只能引用未入选且存在于输入中的候选，每个代码最多一次：

```json
{"code":"sh600000","reason":"明确且不误导的硬性排除理由"}
```

禁止输出 observation_pool、未选股推理、自动交易指令、
BuyLo/BuyHi/Stop/Target，或输入外的代码、主题、role、news 引用。
