---
name: daily-news-brief
description: Aggregate financial news from multiple sources to generate daily briefings. Trigger this skill when users need financial news, market highlights, policy updates, investment sentiment, or request news briefings and market flashes.
---

# Daily Financial News Brief

Aggregate multiple financial news sources into a structured news briefing.

## Quick Start

```bash
uv run --frozen ashare-pilot news fetch
```

By default, outputs Markdown format briefing to stdout. The daily workflow must
use `--output-dir` so the same fetch writes both canonical `news.json` and
readable `news.md`.

## Command Arguments

| Argument | Description |
|----------|-------------|
| `-o, --output <file>` | Output to file |
| `-j, --json` | Output JSON format |
| `-s, --sources <names>` | Specify news sources (multiple allowed) |
| `--date <YYYY-MM-DD>` | Set the report date |
| `--output-dir <dir>` | Write both `news.json` and `news.md` |

## News Sources

| Source | Provider | Content Type |
|--------|----------|--------------|
| policy | People.cn Politics | Policy updates & political news |
| hotspot | The Paper Hot News | Social highlights |
| flash | CLS Telegraph | Real-time flashes |
| finance | Eastmoney | Financial news |
| macro | Wallstreet CN | Macro insights |
| sentiment | Xueqiu Hot Stocks | Market sentiment |
| stcn | Securities Times | Capital market & regulatory news |
| yicai | Yicai (China Business News) | Comprehensive financial news |
| 21jingji | 21st Century Business Herald | In-depth financial reporting |
| sina | Sina Finance | Comprehensive financial news |

## Usage Examples

```bash
# Daily workflow output (required)
uv run --frozen ashare-pilot news fetch --date 2026-07-10 --output-dir predict/2026-07-10

# Get specific sources only
uv run --frozen ashare-pilot news fetch -s flash finance

# JSON format output
uv run --frozen ashare-pilot news fetch -j -o news.json
```

## Canonical JSON Contract

`news.json` is the machine source of truth. It uses schema `daily_news.v1` and
a flat `items` array. Integer IDs are assigned globally in fetch order and are
continuous from `1` to `N`. All downstream news evidence must use
`news#<id>`. Category-local pointers, Markdown line pointers, and Markdown
ranges are forbidden. `news.md` may be reorganized by an LLM and is never a
machine evidence source.

```json
{
  "schema_version": "daily_news.v1",
  "date": "2026-07-10",
  "generated_at": "2026-07-10T09:20:00+08:00",
  "items": [
    {
      "id": 1,
      "category": "policy",
      "source_item_no": 1,
      "title": "Example",
      "url": "https://example.com/1",
      "source": "Example Source",
      "desc": ""
    }
  ]
}
```

## Markdown Output Format

Default Markdown format:

```markdown
# Daily Financial News Brief — 2025-04-01 10:30

## flash
- `news#1` [Title](URL) — Summary...

## finance
- `news#21` [Title](URL)
```
