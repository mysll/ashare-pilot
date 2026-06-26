#!/usr/bin/env python3
"""
Financial news aggregator — Multi-source news fetching
"""
import hashlib
import json
import re
import sys
import time
import urllib.parse
from datetime import datetime
from typing import Any

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
TIMEOUT = 20


def _cls_sign(params: dict[str, str]) -> str:
    sp = urllib.parse.urlencode(sorted(params.items()))
    sha1 = hashlib.sha1(sp.encode()).hexdigest()
    return hashlib.md5(sha1.encode()).hexdigest()

def fetch_thepaper() -> list[dict[str, str]]:
    """澎湃新闻热门"""
    resp = requests.get(
        "https://cache.thepaper.cn/contentapi/wwwIndex/rightSidebar",
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("hotNews", []):
        items.append({
            "title": k.get("name", ""),
            "url": f"https://www.thepaper.cn/newsDetail_forward_{k.get('contId', '')}",
            "source": "The Paper",
        })
    return items[:20]


def fetch_cls() -> list[dict[str, str]]:
    """财联社电报（实时快讯）"""
    base_params = {"app": "CailianpressWeb", "name": "telegraph", "os": "web", "sv": "8.7.9"}
    sign = _cls_sign(base_params)
    base_params["sign"] = sign
    resp = requests.get(
        "https://www.cls.cn/api/cache",
        params=base_params,
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("roll_data", []):
        if k.get("is_fad"):
            continue
        items.append({
            "title": k.get("title") or k.get("brief", ""),
            "url": f"https://www.cls.cn/detail/{k.get('id', '')}",
            "source": "CLS",
        })
    return items[:30]


EM_HEADERS = {"User-Agent": UA, "Referer": "https://data.eastmoney.com/"}


def fetch_eastmoney() -> list[dict[str, str]]:
    """东方财富 — 财经要闻"""
    resp = requests.get(
        "https://np-listapi.eastmoney.com/comm/web/getFastNewsList",
        params={
            "client": "web",
            "biz": "web_home_flash",
            "fastColumn": "",
            "sortEnd": "",
            "pageSize": "30",
            "req_trace": str(int(time.time() * 1000)),
        },
        headers=EM_HEADERS,
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("fastNewsList", []):
        items.append({
            "title": k.get("title", ""),
            "url": k.get("url", ""),
            "source": "Eastmoney",
            "desc": k.get("summary", ""),
        })
    return items[:30]


# ─── 宏观层 ────────────────────────────────────────────────

def fetch_wallstreetcn() -> list[dict[str, str]]:
    """华尔街见闻 — 实时快讯"""
    resp = requests.get(
        "https://api-one-wscn.awtmt.com/apiv1/content/lives",
        params={"channel": "global-channel", "limit": "30"},
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("items", []):
        title = k.get("title") or k.get("content_text", "")
        title = re.sub(r"<[^>]+>", "", title)[:120]
        items.append({
            "title": title,
            "url": f"https://wallstreetcn.com/live/{k.get('id', '')}",
            "source": "Wallstreet CN",
        })
    return items[:30]


# ─── 深度层 ────────────────────────────────────────────────

def fetch_jiemian() -> list[dict[str, str]]:
    """界面新闻 — 商业报道"""
    resp = requests.get(
        "https://m.jiemian.com",
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    import re
    items = []
    # 匹配文章链接
    pattern = r'<a[^>]+href="(https://m\.jiemian\.com/article/(\d+)\.html)"[^>]*>([^<]+)</a>'
    matches = re.findall(pattern, resp.text)
    seen = set()
    for url, aid, title in matches:
        if aid in seen:
            continue
        seen.add(aid)
        title = title.strip()
        if len(title) > 5:
            items.append({
                "title": title,
                "url": url,
                "source": "Jiemian",
            })
    return items[:30]


# ─── 情绪层 ────────────────────────────────────────────────

def fetch_xueqiu() -> list[dict[str, str]]:
    """雪球热帖"""
    session = requests.Session()
    session.headers.update({"User-Agent": UA})
    r1 = session.get("https://xueqiu.com/hq", timeout=TIMEOUT)
    r1.raise_for_status()

    resp = session.get(
        "https://stock.xueqiu.com/v5/stock/hot_stock/list.json",
        params={"size": "20", "_type": "10", "type": "10"},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    data = resp.json()
    items = []
    for k in data.get("data", {}).get("items", []):
        if k.get("ad"):
            continue
        pct = k.get("percent", 0)
        sign = "+" if pct > 0 else ""
        items.append({
            "title": f"{k.get('name', '')} ({sign}{pct}%)",
            "url": f"https://xueqiu.com/s/{k.get('code', '')}",
            "source": "Xueqiu",
        })
    return items[:20]



def fetch_all_news() -> dict[str, list[dict[str, str]]]:
    result = {}
    for name, fn in NEWS_SOURCES.items():
        try:
            result[name] = fn()
        except Exception as e:
            print(f"[WARN] {name} failed: {e}", file=sys.stderr)
            result[name] = []
    return result


# News source registry
NEWS_SOURCES: dict[str, Any] = {
    "hotspot": fetch_thepaper,
    "flash": fetch_cls,
    "finance": fetch_eastmoney,
    "macro": fetch_wallstreetcn,
    "sentiment": fetch_xueqiu,
    "jiemian": fetch_jiemian,
}


def format_brief(news: dict[str, list[dict[str, str]]]) -> str:
    """Format news as Markdown briefing"""
    lines = [f"# Daily Financial News Brief — {datetime.now().strftime('%Y-%m-%d %H:%M')}", ""]
    for category, items in news.items():
        if not items:
            continue
        lines.append(f"## {category}")
        for i, it in enumerate(items, 1):
            title = it.get("title", "").strip()
            source = it.get("source", "")
            url = it.get("url", "")
            desc = it.get("desc", "")
            line = f"{i}. [{title}]({url})"
            if desc:
                line += f" — {desc[:80]}"
            lines.append(line)
        lines.append("")
    return "\n".join(lines)


def main():
    """Main entry point"""
    import argparse

    # Ensure stdout uses UTF-8 encoding (fixes Windows console display)
    sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Aggregate financial news from multiple sources")
    parser.add_argument("-o", "--output", help="Output file path (default: stdout)")
    parser.add_argument("-j", "--json", action="store_true", help="Output JSON format")
    parser.add_argument(
        "-s", "--sources", nargs="*", choices=list(NEWS_SOURCES.keys()),
        help="Specify news sources (default: all)"
    )
    args = parser.parse_args()

    sources = {k: NEWS_SOURCES[k] for k in args.sources} if args.sources else NEWS_SOURCES
    news = {}
    for name, fn in sources.items():
        try:
            news[name] = fn()
        except Exception as e:
            print(f"[WARN] {name} failed: {e}", file=sys.stderr)
            news[name] = []

    output = json.dumps(news, ensure_ascii=False, indent=2) if args.json else format_brief(news)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()

