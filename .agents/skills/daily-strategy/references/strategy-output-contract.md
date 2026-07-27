# Step 3 Draft Output Contract

写入 `predict/YYYY-MM-DD/strategy.draft.json`。根结构：

```json
{
  "schema_version": "daily_strategy_draft.tmp.v2",
  "date": "YYYY-MM-DD",
  "generated_at": "ISO-8601",
  "source": {"strategy_input_sha256": "输入 source 要求的精确 canonical hash"},
  "market": {
    "regime_prior": "panic|weak|neutral|strong-sector",
    "requires_open_confirmation": true,
    "stop_atr_multiplier": 1.5,
    "notes": "最终 regime 理由"
  },
  "portfolio_limits": {
    "max_new_positions": 7,
    "max_theme_positions": 3,
    "max_correlated_names": 2
  },
  "stocks": [],
  "exclusion_overrides": []
}
```

`source.strategy_input_sha256` 必须是紧凑输入按 UTF-8、`sort_keys=true`、`separators=(",", ":")` canonical serialization 的 SHA-256。写草稿前运行下列命令取得精确值；旧草稿不可复用：

```bash
uv run --frozen ashare-pilot strategy daily build-llm-input --hash-only predict/YYYY-MM-DD/.strategy_llm_input.json
```

## Selected stock

`stocks[]` 只含最终入选股，顺序即最终顺序。每行必须含：

```json
{
  "code": "sz000001",
  "name": "示例",
  "sector": "输入中的 source theme",
  "direction": "看多|偏多",
  "rating": "5★|4★|3★|2★|1★|—",
  "entry_profile": "趋势跟随|回调布局|强势接力|防御布局",
  "anchor": "MA5|MA10|MA20|OPEN|VWAP|首根5min|FLEX|无|—",
  "entry_trigger": "非空",
  "no_buy_condition": "非空",
  "position_tier": "WATCH_ONLY|LIGHT|STANDARD",
  "horizon": "T+1",
  "preopen_plan": {
    "decision": "CONDITIONAL|WATCH_ONLY",
    "earliest_entry_time": "09:35:05",
    "latest_entry_time": "10:00:00",
    "requires_first_bar": true,
    "requires_market_confirmation": true,
    "requires_theme_confirmation": true,
    "entry_setup": "LIMIT_UP_CONT|MOMENTUM|FIRST_BAR_OR_PULLBACK|PULLBACK|DEFENSIVE|WATCH_ONLY",
    "pre_entry_invalidations": ["至少一项"]
  },
  "t1_risk_plan": {
    "overnight_risk": "非空",
    "gap_up_action": "非空",
    "flat_open_action": "非空",
    "gap_down_action": "非空",
    "max_holding_days": 2
  },
  "rules_applied": ["Rxx"],
  "profile_trace": "非空",
  "reasoning": {
    "source_basis": "真实主题/role/news依据",
    "direction_path": "最终Direction链路",
    "risk": "逐flag severity与应用",
    "reread": "触发新闻结果或—",
    "override": "规则/感知override或—"
  },
  "profile_overrides": {}
}
```

不要写 `profile`；finalize 用最终 regime 重算。`profile_overrides` 每项格式必须为：

```json
{"preferred_anchor":{"value":"MA5","reason":"R68强主线切换MA5"}}
```

白名单：`playbook`、`preferred_anchor`、`chase_policy`、`entry_window`、`stop_policy`、`time_horizon`、`invalidation`、`note`、`max_extension_atr`，以及只能取 Step 2 精确值或两位小数值的 `ref_ma20/ref_ma5/ref_high20`；`ref_ma10` 只能为 null。

`position_tier` 只属于 selected stock，不进入 profile 或 profile overrides：

- `WATCH_ONLY`：仅观察，不形成新买入意图；
- `LIGHT`：轻仓意图，不代表任何固定百分比、金额、股数或手数；
- `STANDARD`：标准仓意图，不代表任何固定百分比、金额、股数或手数。

禁止输出 `position_budget`、`position_multiplier`、任何 exposure 百分比或数值仓位上限。
profile 的 time horizon 必须与 stock 的 T+1 一致。无变化时使用空对象。

`exclusion_overrides` 只能引用未入选且存在于输入中的候选，每个代码最多一次：

```json
{"code":"sh600000","reason":"明确且不误导的硬性排除理由"}
```

禁止输出 observation_pool、完整 profile、未选股推理、自动交易指令、BuyLo/BuyHi/Stop/Target，或输入外的代码/主题/role/news 引用。

finalize 前的 draft validator 会直接检查上述全部 LLM-owned 字段、枚举、时间、T+1 风险计划、portfolio limits、source grounding 和 overrides；不能依赖 final strategy validator 延迟报错。
