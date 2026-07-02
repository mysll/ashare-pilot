---
name: daily-news-brief
description: Aggregate financial news from multiple sources to generate daily briefings. Trigger this skill when users need financial news, market highlights, policy updates, investment sentiment, or request news briefings and market flashes.
---

# Daily Financial News Brief

Aggregate multiple financial news sources into a structured news briefing.

## Quick Start

```bash
python scripts/fetch_news.py
```

By default, outputs Markdown format briefing to stdout.

## Command Arguments

| Argument | Description |
|----------|-------------|
| `-o, --output <file>` | Output to file |
| `-j, --json` | Output JSON format |
| `-s, --sources <names>` | Specify news sources (multiple allowed) |

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

## Usage Examples

```bash
# Output to file
python scripts/fetch_news.py -o brief.md

# Get specific sources only
python scripts/fetch_news.py -s flash finance

# JSON format output
python scripts/fetch_news.py -j -o news.json
```

## Output Format

Default Markdown format:

```markdown
# Daily Financial News Brief — 2025-04-01 10:30

## flash
1. [Title](URL) — Summary...
2. ...

## finance
1. [Title](URL)
```