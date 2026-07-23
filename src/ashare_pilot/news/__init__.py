"""News acquisition and normalization."""

from ashare_pilot.news.api import fetch_daily_news, write_news_outputs
from ashare_pilot.news.fetch import build_news_document, format_brief

__all__ = [
    "build_news_document",
    "fetch_daily_news",
    "format_brief",
    "write_news_outputs",
]
