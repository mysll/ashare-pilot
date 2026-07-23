# Mapper semantic phase

Load only after `uv run --frozen ashare-pilot mapping daily prepare` writes `.mapper_annotation_input.json`.

- Emit every target candidate code exactly once.
- Use each candidate's `source_themes`, `direct_news_refs`, and `theme_news_refs` to select only matching rows from top-level `news_evidence`.
- `news_relevance` is mandatory and candidate-specific; include confidence and canonical evidence or a concise trace.
- A `NewsDirect` tag must retain its canonical direct `news#id`; never guess a reference that is absent from the input.
- Emit `major_event` only for a named company-level discrete event.
- Emit `anomaly` only for a mandatory trigger or genuine structural anomaly.
- Emit `pattern` only for reviewed dimensions that override the script-owned default.
- Do not emit themes, membership, Direction, RiskSeverity, trade levels, or repetitive default prose.
