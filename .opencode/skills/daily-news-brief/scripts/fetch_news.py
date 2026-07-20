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
from datetime import datetime, date, timedelta
from pathlib import Path
from typing import Any

import requests

UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
TIMEOUT = 20

_REMOVE_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f]")

def _clean(d: dict[str, str]) -> dict[str, str]:
    return {k: _REMOVE_CONTROL.sub("", v) if isinstance(v, str) else v for k, v in d.items()}


_TODAY = date.today()
_YESTERDAY = _TODAY - timedelta(days=1)

_DATE_IN_TEXT = re.compile(r"(\d{1,2})月(\d{1,2})日")


def _recent_text(summary: str) -> bool:
    """Check if dates mentioned in the summary text are within the last 2 days."""
    for m in _DATE_IN_TEXT.finditer(summary):
        try:
            d = date(_TODAY.year, int(m.group(1)), int(m.group(2)))
        except ValueError:
            continue
        if d > _TODAY:
            continue
        if d < _YESTERDAY:
            return False
    return True


def _recent_date(date_str: str) -> bool:
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y/%m%d"):
        try:
            d = datetime.strptime(date_str, fmt).date()
            return d in (_TODAY, _YESTERDAY)
        except ValueError:
            continue
    return False


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
        st = k.get("showTime", "")
        if st and not _recent_date(st[:10]):
            continue
        summary = k.get("summary", "")
        if summary and not _recent_text(summary):
            continue
        url = k.get("url") or k.get("jumpUrl") or ""
        code = k.get("code", "")
        if not url and code:
            url = f"https://finance.eastmoney.com/a/{code}.html"
        items.append({
            "title": k.get("title", ""),
            "url": url,
            "source": "Eastmoney",
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
        pct = k.get("percent")
        if pct is None:
            title = f"{k.get('name', '')} (—)"
        else:
            sign = "+" if pct > 0 else ""
            title = f"{k.get('name', '')} ({sign}{pct}%)"
        items.append({
            "title": title,
            "url": f"https://xueqiu.com/s/{k.get('code', '')}",
            "source": "Xueqiu",
        })
    return items[:20]



# ─── 政策层 ────────────────────────────────────────────────

def fetch_people_politics() -> list[dict[str, str]]:
    """人民网 — 政治新闻（通过主站抓取）"""
    resp = requests.get(
        "http://www.people.com.cn/",
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"
    items = []
    seen = set()
    pattern = r'<a[^>]*href=[\"\'](http://politics\.people\.com\.cn/n1/(\d{4})/(\d{4})/[^\"\']+)[\"\'][^>]*>([^<]{10,})</a>'
    for url, year, mmdd, title in re.findall(pattern, resp.text):
        title = title.strip()
        if title in seen:
            continue
        seen.add(title)
        date_str = f"{year}/{mmdd}"
        if not _recent_date(date_str):
            continue
        items.append({
            "title": title,
            "url": url,
            "source": "People.cn",
        })
    return items[:20]


def fetch_stcn() -> list[dict[str, str]]:
    """证券时报 — 资本市场新闻"""
    resp = requests.get(
        "https://www.stcn.com/",
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    items = []
    seen = set()
    pattern = r'<a[^>]+href=[\"\'](/article/detail/\d+\.html)[\"\'][^>]*>([^<]{8,})</a>'
    for url_path, title in re.findall(pattern, resp.text):
        title = title.strip()
        if title and title not in seen:
            seen.add(title)
            items.append({
                "title": title,
                "url": f"https://www.stcn.com{url_path}",
                "source": "STCN",
            })
    return items[:30]


def fetch_yicai() -> list[dict[str, str]]:
    """第一财经 — 综合财经新闻"""
    resp = requests.get(
        "https://www.yicai.com/",
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    items = []
    seen = set()
    for url_path in re.findall(r'href=[\"\'](/brief/\d+\.html)[\"\']', resp.text):
        full_url = f"https://www.yicai.com{url_path}"
        title_match = re.search(
            rf'<a[^>]+href=[\"\']{re.escape(url_path)}[\"\'][^>]*>.*?<b>(.*?)</b>',
            resp.text, re.DOTALL,
        )
        if title_match:
            title = re.sub(r'<[^>]+>', '', title_match.group(1)).strip()[:80]
            if title and title not in seen:
                seen.add(title)
                items.append({
                    "title": title,
                    "url": full_url,
                    "source": "Yicai",
                })
    if not items:
        pattern = r'<a[^>]+href=[\"\'](/news/\d+\.html)[\"\'][^>]*>([^<]{8,})</a>'
        for url_path, title in re.findall(pattern, resp.text):
            title = title.strip()
            if title and title not in seen:
                seen.add(title)
                items.append({
                    "title": title,
                    "url": f"https://www.yicai.com{url_path}",
                    "source": "Yicai",
                })
    return items[:30]


def fetch_21jingji() -> list[dict[str, str]]:
    """21世纪经济报道 — 深度财经"""
    resp = requests.get(
        "https://www.21jingji.com/",
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"
    items = []
    seen = set()
    pattern = r'<a[^>]+href=[\"\'](https?://m\.21jingji\.com/article/(\d{8})/[^\"\']+)[\"\'][^>]*title=[\"\']([^\"\']+)[\"\']'
    for url, yyyymmdd, title in re.findall(pattern, resp.text):
        title = title.strip()
        if not title or title in seen:
            continue
        if not _recent_date(yyyymmdd):
            continue
        seen.add(title)
        items.append({
            "title": title,
            "url": url,
            "source": "21Jingji",
        })
    return items[:30]


_SINA_IGNORE = {"股票", "新股", "港股", "美股", "基金", "期货", "外汇", "黄金", "债券",
                 "理财", "银行", "保险", "信托", "专栏", "博客", "数据", "视频", "直播",
                 "首页", "ESG", "医药", "会议", "免费试用", "买基金", "新浪财经APP",
                 "手机版", "环球股指", "投研中心", "黑猫投诉", "收藏", "设为书签"}


def fetch_sina() -> list[dict[str, str]]:
    """新浪财经 — 综合财经新闻"""
    resp = requests.get(
        "https://finance.sina.com.cn/",
        headers={"User-Agent": UA},
        timeout=TIMEOUT,
    )
    resp.raise_for_status()
    resp.encoding = "utf-8"
    items = []
    seen = set()
    pattern = r'<a[^>]+href=[\"\'](https?://finance\.sina\.com\.cn/[^\"\']+/\d{4}-\d{2}-\d{2}/doc-[^\"\']+\.shtml)[\"\'][^>]*>([^<]{10,})</a>'
    for url, title in re.findall(pattern, resp.text):
        title = re.sub(r'<[^>]+>', '', title).strip()
        if not title or title in seen:
            continue
        seen.add(title)
        items.append({
            "title": title,
            "url": url,
            "source": "Sina Finance",
        })
    return items[:30]


def fetch_all_news() -> dict[str, list[dict[str, str]]]:
    result = {}
    for name, fn in NEWS_SOURCES.items():
        try:
            result[name] = [_clean(it) for it in fn()]
        except Exception as e:
            print(f"[WARN] {name} failed: {e}", file=sys.stderr)
            result[name] = []
    return result


# News source registry
NEWS_SOURCES: dict[str, Any] = {
    "policy": fetch_people_politics,
    "hotspot": fetch_thepaper,
    "flash": fetch_cls,
    "finance": fetch_eastmoney,
    "macro": fetch_wallstreetcn,
    "sentiment": fetch_xueqiu,
    "stcn": fetch_stcn,
    "yicai": fetch_yicai,
    "21jingji": fetch_21jingji,
    "sina": fetch_sina,
}


def build_news_document(
    news: dict[str, list[dict[str, str]]], report_date: str | None = None
) -> dict[str, Any]:
    """Build the canonical flat news contract with globally increasing IDs."""
    now = datetime.now().astimezone()
    items: list[dict[str, Any]] = []
    next_id = 1
    for category, category_items in news.items():
        for source_item_no, item in enumerate(category_items, 1):
            items.append(
                {
                    "id": next_id,
                    "category": category,
                    "source_item_no": source_item_no,
                    "title": item.get("title", "").strip(),
                    "url": item.get("url", "").strip(),
                    "source": item.get("source", "").strip(),
                    "desc": item.get("desc", "").strip(),
                }
            )
            next_id += 1
    return {
        "schema_version": "daily_news.v1",
        "date": report_date or now.strftime("%Y-%m-%d"),
        "generated_at": now.isoformat(timespec="seconds"),
        "items": items,
    }


def format_brief(doc: dict[str, Any]) -> str:
    """Render the canonical news contract as Markdown."""
    lines = [f"# Daily Financial News Brief — {doc['date']}", ""]
    grouped: dict[str, list[dict[str, Any]]] = {}
    for item in doc.get("items", []):
        grouped.setdefault(str(item.get("category", "other")), []).append(item)
    for category, items in grouped.items():
        if not items:
            continue
        lines.append(f"## {category}")
        for it in items:
            title = it.get("title", "").strip()
            url = it.get("url", "")
            desc = it.get("desc", "")
            line = f"- `news#{it['id']}` [{title}]({url})"
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
    parser.add_argument("--date", help="Report date in YYYY-MM-DD (default: today)")
    parser.add_argument(
        "--output-dir",
        help="Write both news.md and canonical news.json to this directory",
    )
    parser.add_argument(
        "-s", "--sources", nargs="*", choices=list(NEWS_SOURCES.keys()),
        help="Specify news sources (default: all)"
    )
    args = parser.parse_args()
    if args.output_dir and (args.output or args.json):
        parser.error("--output-dir cannot be combined with --output or --json")
    if args.date:
        try:
            datetime.strptime(args.date, "%Y-%m-%d")
        except ValueError:
            parser.error("--date must be YYYY-MM-DD")

    sources = {k: NEWS_SOURCES[k] for k in args.sources} if args.sources else NEWS_SOURCES
    news = {}
    for name, fn in sources.items():
        try:
            news[name] = [_clean(it) for it in fn()]
        except Exception as e:
            print(f"[WARN] {name} failed: {e}", file=sys.stderr)
            news[name] = []

    doc = build_news_document(news, args.date)
    if args.output_dir:
        output_dir = Path(args.output_dir)
        output_dir.mkdir(parents=True, exist_ok=True)
        (output_dir / "news.json").write_text(
            json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        (output_dir / "news.md").write_text(
            format_brief(doc), encoding="utf-8", newline="\n"
        )
        print(f"OK: wrote {output_dir / 'news.json'}")
        print(f"OK: wrote {output_dir / 'news.md'}")
        return

    output = json.dumps(doc, ensure_ascii=False, indent=2) if args.json else format_brief(doc)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output)
    else:
        print(output)


if __name__ == "__main__":
    main()

