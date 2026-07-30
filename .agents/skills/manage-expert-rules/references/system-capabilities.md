# Expert Rule System Capabilities

This document is a closed whitelist for `manage-expert-rules`. A datum,
decision-time availability, comparison, or action not listed here is
unsupported. Do not infer support from general market knowledge or substitute
proxy metrics.

## Global boundaries

| Capability | Support |
|---|---|
| Consumers | `DAILY_STRATEGY`, `OVERNIGHT_STRATEGY` only |
| Trading scope | `sh` and `sz`; excludes `sh688*` and `bj*` |
| Position expression | `WATCH_ONLY`, `LIGHT`, `STANDARD` only |
| Automated order placement | Unsupported |
| Account cash, holdings, shares, lots, or numeric exposure | Unsupported |
| Same-day sale of a newly opened A-share position | Unsupported |
| Expert Rule effectiveness statistics | Unsupported in V1 |
| Operation Guide adjustments | Unsupported |

Simple comparisons are supported when every operand is an explicitly listed
field available to the same consumer: equality, set membership, greater/less
than, range, and boolean checks. Do not construct a new technical indicator,
multi-day aggregation, or proxy factor unless the exact derived field is
listed.

Missing or null data never satisfies a numeric or boolean condition. A rule
that depends on a field which can be missing must state whether to exclude the
case or take a conservative supported action.

## DAILY_STRATEGY data

Decision time is the pre-market Step 3 run. The canonical LLM input is
`predict/{date}/.strategy_llm_input.json`
(`strategy_llm_input.tmp.v3`). Price and technical inputs are based on the
previous close unless the field explicitly says otherwise.

### Market and theme fields

| Meaning | Canonical path |
|---|---|
| Advisory regime | `market_inputs.regime_hint` |
| Index code/name/open/change | `market_inputs.indices.<code>.{code,name,open,percent}` |
| Index fetch failure | `market_inputs.index_fetch_failed` |
| Board allow/exclude policy | `market_inputs.market_state.board_policy` |
| Dominant theme name/heat | `market_inputs.market_state.dominant_themes[].{name,final_heat}` |
| Financing flow | `market_inputs.market_state.financing_flow` (may be null) |
| Market risk flags | `market_inputs.market_state.risk_flags[]` |
| Theme rank/name/heat/direction | `themes[].{rank,name,final_heat,attention_direction}` |
| Theme evidence references | `themes[].evidence_refs[]` |

### Candidate fields

| Meaning | Canonical path |
|---|---|
| Stock identity | `candidates[].{code,name}` |
| Primary/source themes | `candidates[].primary_theme`, `source_themes` when present |
| Role tags | `candidates[].role_tags` plus `candidate_defaults.role_tags` |
| Composite and component scores | `candidates[].scores.{composite,tech,theme_heat,news_impact,auction,money_flow}` |
| Score confidence exceptions | `candidates[].confidence_exceptions` |
| Advisory direction/risk | `candidates[].direction_base_hint`, `risk_severity_base_hint`, `risk_type[]` |
| Pattern states | `candidates[].pattern.{auction,heat,leader,rotation,volume}` |
| Previous-close price source | `candidates[].strategy_inputs.{price,price_source}` |
| ATR and ATR percent | `candidates[].strategy_inputs.{atr,atr_pct}` |
| Moving averages | `candidates[].strategy_inputs.{ma5,ma20}` |
| 20-day high/low | `candidates[].strategy_inputs.{high20,low20}` |
| Previous limit-up context | `candidates[].profile_inputs.{board_streak,yesterday_limit_up}` |
| Profile baseline | `profile_bases[candidates[].profile_ref]` |
| Canonical news references | `evidence_sets[candidates[].evidence_ref]` and `news_evidence[]` |

### DAILY_STRATEGY actions

The Reasoning layer may:

- select `panic|weak|neutral|strong-sector` regime;
- select and order candidates within the contract limits;
- set selected-stock `direction`, `rating`, `entry_profile`, `anchor`,
  qualitative `position_tier`, and `entry_setup`;
- exclude an unselected input candidate using `exclusion_overrides`;
- apply only the documented profile and plan override fields in
  `daily-strategy/references/strategy-output-contract.md`;
- record actually applied `E` IDs in `rules_applied`;
- make a supported action more conservative.

It may not invent stocks, themes, role tags, news evidence, exact future
prices, numeric position sizing, order quantities, fixed execution times, or
same-day sell instructions.

### DAILY_STRATEGY known unsupported data

- Intraday/current volume ratio (`量比`) at the pre-market decision time.
- Live current price, live VWAP, live turnover, live money flow, or completed
  intraday bars.
- MA10 as a usable daily Step 3 input.
- Level-2 order book, queue size, bid/ask depth, personal positions, and
  account balances.
- Raw news content not present in the compact input; canonical `news#id`
  references alone do not provide arbitrary missing facts.

## OVERNIGHT_STRATEGY data

Decision time is the approximately 14:30 intraday overnight run. Canonical
Reasoning inputs include `intraday/{date}/intraday_mapper.base.json`,
`selection_pools.json`, and `theme_ranking.json`.

### Market and theme fields

| Meaning | Canonical path |
|---|---|
| Market breadth | `market.breadth.{total,up_count,down_count,flat_count,up_ratio,limit_up_count,limit_down_count,timestamp,partial}` |
| Index quote | `market.indices[].{code,name,price,open,yestclose,high,low,volume,amount,percent,time}` |
| Concept performance/capital/breadth/momentum | `market.concept_dashboard.themes.*.{performance,capital,breadth,momentum,composite,details}` |
| Published theme ranking and contributors | `themes` and `theme_ranking.json` fields present in the run |

### Executable stock fields

| Meaning | Canonical path |
|---|---|
| Identity and snapshot quote | `executable_stocks[].{code,name,price,change_pct,change_amt}` |
| Volume, amount, swing, turnover | `executable_stocks[].{volume,amount,swing,turnover}` |
| Current volume ratio | `executable_stocks[].volume_ratio` |
| Intraday OHLC, volume, amount, VWAP | `executable_stocks[].enriched.real_time.{price,open,high,low,yestclose,volume,amount,vwap}` |
| Main/sized money flow | `executable_stocks[].enriched.money_flow` |
| MA and Bollinger fields | `executable_stocks[].technicals.{status,ma5,ma10,ma20,ma60,boll_mid,boll_ub,boll_lb,boll_zone,ma_alignment,above_ma5}` |
| Trade feasibility facts | `executable_stocks[].execution_state` and `execution_eligibility` |
| Deterministic score/rank | `overnight_score`, `score_trace`, `confidence`, `rank`, `rank_tier`, `tier`, `trend_raw` |
| Theme identity/support | `market_board`, `primary_theme`, `themes[]`, `theme_support_shadow` |

`volume_ratio` is supported only for `OVERNIGHT_STRATEGY` when present in the
14:30 mapper. It is not a supported `DAILY_STRATEGY` field.

### OVERNIGHT_STRATEGY actions

The Reasoning layer may:

- author the market assessment and `zero|very_light|light|normal` risk posture;
- set executable-stock `tradeability`, `direction`, `execution_role`,
  `trading_strategy`, `risk_severity`, `expected_premium`, `key_reason`, and
  `execution_condition`;
- choose a supported T+1 stop-loss basis and write qualitative auction/open/
  take-profit text;
- keep an executable stock as primary, alternative, or watch subject to
  existing invariants;
- record actually applied `E` IDs in `rules_applied`;
- make a supported action more conservative.

It may not modify quote facts, scores, ranks, tiers, pool membership,
execution eligibility, themes, deterministic stop-loss price, or numeric
position sizing. Observation-pool stocks cannot be promoted into executable
roles.

### OVERNIGHT_STRATEGY known unsupported data

- Future T+1 auction, open, high, low, close, or realized return at decision
  time.
- Level-2 order book, queue size, bid/ask depth, personal positions, and
  account balances.
- Any field absent or null in the current mapper run.
- Automated order placement or account-level sizing.

## Maintenance

When a system change adds, removes, renames, or changes the timing of a
capability, update only the affected entries in this document and the Skill
workflow if needed. The Expert Rule CLI does not read or validate this
reference.
