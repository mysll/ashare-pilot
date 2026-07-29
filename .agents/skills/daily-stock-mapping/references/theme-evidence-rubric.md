# Theme evidence phase

Load only for the `themes.json` LLM stage.

- Theme names must resolve to Theme Library names, aliases, keywords, or concepts.
- Use `.theme_evidence_input.json`; every cited `news#id` must come from that
  compact input. Do not reopen canonical `news.json`/`news.md` or query the
  full Theme Library during this LLM phase.
- Heat, policy, catalyst, confidence, and direction follow the existing `daily_themes.v1` contract.
- `themes[].status` must use exactly one machine enum: `tradeable`, `watch`, or
  `discarded`. Never write `excluded`, `candidate`, `rejected`, or a display
  label; exclusion from a pool is behavior, while a discarded theme uses
  `status = "discarded"`.
- Do not inspect mapper candidates, technical indicators, or strategy fields in this phase.
