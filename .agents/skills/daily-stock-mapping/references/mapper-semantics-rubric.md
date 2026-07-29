# Mapper semantic phase

Load only after `uv run --frozen ashare-pilot mapping daily prepare` writes `.mapper_annotation_input.json`.

- Emit every target candidate code exactly once.
- Use each candidate's `source_themes`, `direct_news_refs`, and `theme_news_refs` to select only matching rows from top-level `news_evidence`.
- `news_relevance` is mandatory and candidate-specific; include confidence and canonical evidence or a concise trace.
- A `NewsDirect` tag must retain its canonical direct `news#id`; never guess a reference that is absent from the input.
- Emit `major_event` only for a named company-level discrete event.
- `anomaly` is exactly `string|null`, with a maximum length of 50 characters.
  Objects are forbidden. Emit it only for a mandatory trigger or genuine
  structural anomaly; otherwise omit it or use `null`.
- Emit `pattern` only for reviewed dimensions that override the script-owned default.
- Uniform R2/P2 is valid when all linked evidence is theme-level. A candidate
  with non-empty `direct_news_refs` or a `NewsDirect` role tag must not be
  labeled R2.
- Do not read `theme_stocks.json`, `pool_indicators.json`, full news, or any
  mapper artifact during this LLM phase.
- Do not emit themes, membership, Direction, RiskSeverity, trade levels, or repetitive default prose.
