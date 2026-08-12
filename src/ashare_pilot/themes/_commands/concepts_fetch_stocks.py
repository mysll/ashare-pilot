#!/usr/bin/env python3
"""Fetch stocks for each concept board from East Money.

Supports resume: skips already-fetched concepts, retries previously failed ones.
Each concept is stored as a separate file: cache/stocks/BK0917.json

Concepts listed under ``member_fetch_partial_ok`` in theme-config.json may be
accepted as complete with the already-fetched subset when the fetch fails
partway (e.g. repeatedly failing boards). Their ``reported_total`` is then set
to the fetched count, a ``fetch_note`` records the partial_ok acceptance, and
the run continues instead of stopping.

Usage:
    python fetch_concept_stocks.py
    python fetch_concept_stocks.py -q          # quiet: skip summary table
    python fetch_concept_stocks.py --concept BK0917
    python fetch_concept_stocks.py --top 10
    python fetch_concept_stocks.py --retry-failed
    python fetch_concept_stocks.py --reset
    python fetch_concept_stocks.py --json
"""

import argparse
import io
import json
import random
import sys
import time
from pathlib import Path

from ashare_pilot.themes.datasource import EastMoneyConceptSource
from ashare_pilot.themes.fetch_settings import (
    DEFAULT_CONCEPT_MEMBER_PAGE_SIZE,
    load_concept_request_delay,
    load_fetch_page_sizes,
    load_first_page_only,
)
from ashare_pilot.themes.runtime import theme_cache_path, theme_config_path

CACHE_DIR = theme_cache_path()
STOCKS_DIR = CACHE_DIR / "stocks"
FAILED_FILE = CACHE_DIR / "concept_stocks_failed.json"
CHECKPOINT_DIR = CACHE_DIR / "concept-stock-checkpoints"
PROGRESS_FILE = CACHE_DIR / "concept_stocks_progress.json"
THEME_CONFIG_FILE = theme_config_path("theme-config.json")


def load_concepts():
    cache_path = CACHE_DIR / "concepts.json"
    if not cache_path.exists():
        print(f"Error: {cache_path} not found. Run fetch_concepts.py first.")
        sys.exit(1)
    with open(cache_path, "r", encoding="utf-8") as f:
        return json.load(f)


def concept_cache_path(code):
    return STOCKS_DIR / f"{code}.json"


def load_concept(code):
    path = concept_cache_path(code)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_concept(code, data):
    STOCKS_DIR.mkdir(parents=True, exist_ok=True)
    with open(concept_cache_path(code), "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_theme_configuration():
    with open(THEME_CONFIG_FILE, "r", encoding="utf-8") as f:
        value = json.load(f)
    return value if isinstance(value, dict) else {}


def load_member_fetch_exclusions():
    value = load_theme_configuration().get("member_fetch_exclusions", {})
    return value if isinstance(value, dict) else {}


def load_member_fetch_partial_ok():
    """Names/codes of concepts allowed to be accepted as complete on partial fetch.

    ``member_fetch_partial_ok`` in theme-config.json is a list of concept names
    (or codes). A dict shape (name -> reason) is also accepted for symmetry with
    ``member_fetch_exclusions``.
    """
    value = load_theme_configuration().get("member_fetch_partial_ok", [])
    if isinstance(value, dict):
        value = list(value.keys())
    if not isinstance(value, list):
        return set()
    return {str(item) for item in value if item}


def is_partial_ok(code, name, partial_ok):
    """Whether a concept may be accepted partial, matching by name or code."""
    return name in partial_ok or code in partial_ok


def accept_partial_as_complete(code, name, result):
    """Mark a partial-ok concept complete with the fetched subset as the total.

    Writes a ``complete`` marker whose ``reported_total`` equals the fetched
    count so ``get_cached_codes`` treats the concept as cached on later runs.
    A ``fetch_note`` records the acceptance for traceability.
    """
    count = len(result.stocks)
    save_concept(code, {
        "concept_code": code,
        "concept_name": name,
        "status": "complete",
        "reported_total": count,
        "stock_count": count,
        "stocks": result.stocks,
        "fetch_note": (
            f"partial_ok: accepted {count} of {result.total or '?'} stocks "
            f"after {result.error or result.status} "
            f"(page {result.failed_page or result.next_page})"
        ),
        "fetch_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    clear_checkpoint(code)


def referenced_concept_names(config):
    names = set()
    for theme in config.get("themes", {}).values():
        if isinstance(theme, dict):
            names.update(
                name for name in theme.get("concepts", [])
                if isinstance(name, str) and name
            )
    return names


def save_ignored_concept(concept, reason):
    code = concept["code"]
    save_concept(code, {
        "concept_code": code,
        "concept_name": concept["name"],
        "status": "ignored",
        "ignore_reason": reason,
        "reported_total": 0,
        "stock_count": 0,
        "stocks": [],
        "fetch_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    clear_checkpoint(code)


def checkpoint_path(code):
    return CHECKPOINT_DIR / f"{code}.json"


def load_checkpoint(code, page_size=DEFAULT_CONCEPT_MEMBER_PAGE_SIZE):
    path = checkpoint_path(code)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        return None
    checkpoint_page_size = value.get(
        "page_size",
        DEFAULT_CONCEPT_MEMBER_PAGE_SIZE,
    )
    if checkpoint_page_size != page_size:
        print(
            f"  Ignoring incompatible {code} checkpoint: page size changed "
            f"from {checkpoint_page_size} to {page_size}.",
            flush=True,
        )
        path.unlink()
        return None
    return value


def load_checkpoint_any(code):
    """Load checkpoint regardless of page_size — used during adaptive fetches."""
    path = checkpoint_path(code)
    if not path.exists():
        return None
    with open(path, "r", encoding="utf-8") as f:
        value = json.load(f)
    if not isinstance(value, dict):
        return None
    return value


def save_checkpoint(code, result, page_size=DEFAULT_CONCEPT_MEMBER_PAGE_SIZE):
    CHECKPOINT_DIR.mkdir(parents=True, exist_ok=True)
    value = {
        "schema_version": "concept_stock_checkpoint.v3",
        "concept_code": code,
        "page_size": page_size,
        "status": result.status,
        "last_completed_page": max(0, result.next_page - 1),
        "next_page": result.next_page,
        "total": result.total,
        "fetched_count": len(result.stocks),
        "failed_page": result.failed_page,
        "error": result.error,
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        "stocks": result.stocks,
    }
    with open(checkpoint_path(code), "w", encoding="utf-8") as f:
        json.dump(value, f, ensure_ascii=False, indent=2)


def clear_checkpoint(code):
    path = checkpoint_path(code)
    if path.exists():
        path.unlink()
    if CHECKPOINT_DIR.exists() and not any(CHECKPOINT_DIR.iterdir()):
        CHECKPOINT_DIR.rmdir()


def get_cached_codes(valid_ignored_names=None):
    if not STOCKS_DIR.exists():
        return set()
    valid_ignored_names = set(valid_ignored_names or ())
    complete = set()
    for path in STOCKS_DIR.glob("*.json"):
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        if (
            value.get("status") == "ignored"
            and value.get("concept_name") in valid_ignored_names
            and value.get("stock_count") == 0
            and value.get("reported_total") == 0
            and value.get("stocks") == []
        ) or (
            value.get("status") == "complete"
            and value.get("stock_count") == value.get("reported_total")
            and len(value.get("stocks", [])) == value.get("reported_total")
            and len({s.get("code") for s in value.get("stocks", []) if isinstance(s, dict)}) == value.get("reported_total")
        ):
            complete.add(path.stem)
    return complete


def load_all_cached():
    if not STOCKS_DIR.exists():
        return {}
    result = {}
    for f in STOCKS_DIR.glob("*.json"):
        with open(f, "r", encoding="utf-8") as fh:
            result[f.stem] = json.load(fh)
    return result


def load_failed():
    if not FAILED_FILE.exists():
        return []
    with open(FAILED_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_failed(failed):
    if failed:
        CACHE_DIR.mkdir(parents=True, exist_ok=True)
        with open(FAILED_FILE, "w", encoding="utf-8") as f:
            json.dump(failed, f, ensure_ascii=False, indent=2)
    elif FAILED_FILE.exists():
        FAILED_FILE.unlink()


def save_progress(**values):
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    progress = {
        "schema_version": "concept_stocks_progress.v1",
        "updated_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        **values,
    }
    with open(PROGRESS_FILE, "w", encoding="utf-8") as f:
        json.dump(progress, f, ensure_ascii=False, indent=2)


def clear_progress():
    if PROGRESS_FILE.exists():
        PROGRESS_FILE.unlink()


def next_page_for(code, page_size=DEFAULT_CONCEPT_MEMBER_PAGE_SIZE):
    checkpoint = load_checkpoint(code, page_size)
    if not checkpoint:
        return 1
    try:
        return max(1, int(checkpoint.get("next_page", 1)))
    except (TypeError, ValueError):
        return 1


def fetch_one(
    source,
    code,
    name,
    *,
    page_size=DEFAULT_CONCEPT_MEMBER_PAGE_SIZE,
    max_pages=None,
):
    checkpoint = load_checkpoint_any(code) or {}
    checkpoint_pz = checkpoint.get("page_size")
    effective_init_pz = checkpoint_pz if checkpoint_pz == 50 else page_size

    def persist(result):
        sz = getattr(result, "current_page_size", effective_init_pz)
        save_checkpoint(code, result, sz)

    result = source.fetch_concept_stocks(
        code,
        page_size=effective_init_pz,
        start_page=checkpoint.get("next_page", 1),
        initial_stocks=checkpoint.get("stocks", []),
        known_total=checkpoint.get("total"),
        on_page=persist,
        max_pages=max_pages,
    )
    if result.status != "complete":
        save_checkpoint(code, result, page_size)
        return result
    unique_codes = {
        stock.get("code")
        for stock in result.stocks
        if isinstance(stock, dict) and stock.get("code")
    }
    if result.total is None or len(result.stocks) != result.total or len(unique_codes) != result.total:
        save_checkpoint(code, result, page_size)
        return type(result)(
            status="partial",
            stocks=result.stocks,
            total=result.total,
            next_page=result.next_page,
            failed_page=result.failed_page,
            error="completion_validation_failed",
        )
    save_concept(code, {
        "concept_code": code,
        "concept_name": name,
        "status": "complete",
        "reported_total": result.total,
        "stock_count": len(result.stocks),
        "stocks": result.stocks,
        "fetch_time": time.strftime("%Y-%m-%d %H:%M:%S"),
    })
    clear_checkpoint(code)
    return result


def main(argv=None):
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Fetch stocks for concept boards")
    parser.add_argument("--concept", help="Fetch stocks for a specific concept code (e.g., BK0917)")
    parser.add_argument("--top", type=int, default=0, help="Limit number of concept boards to fetch")
    parser.add_argument("--retry-failed", action="store_true", help="Only retry previously failed concepts")
    parser.add_argument("--force-complete", action="store_true", help="Mark checkpoints as complete and move to stocks, skipping further pages")
    parser.add_argument("--reset", action="store_true", help="Delete cache and start fresh")
    parser.add_argument("--json", action="store_true", help="Output as JSON")
    parser.add_argument("-o", "--output", metavar="FILE", help="Save output to file")
    parser.add_argument("-v", "--verbose", action="store_true", help="Show detailed progress and retry messages")
    parser.add_argument("-q", "--quiet", action="store_true", help="Suppress summary table output, only show progress")
    args = parser.parse_args(argv)

    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        _concept_page_size, member_page_size = load_fetch_page_sizes(
            THEME_CONFIG_FILE
        )
        first_page_only = load_first_page_only(THEME_CONFIG_FILE)
        delay_min, delay_max = load_concept_request_delay(THEME_CONFIG_FILE)
        partial_ok = load_member_fetch_partial_ok()
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        print(f"Error: invalid theme fetch settings: {exc}", file=sys.stderr)
        return 1

    if args.reset:
        if STOCKS_DIR.exists():
            import shutil
            shutil.rmtree(STOCKS_DIR)
        if CHECKPOINT_DIR.exists():
            import shutil
            shutil.rmtree(CHECKPOINT_DIR)
        if FAILED_FILE.exists():
            FAILED_FILE.unlink()
        clear_progress()
        if (CACHE_DIR / "concept_stocks.json").exists():
            (CACHE_DIR / "concept_stocks.json").unlink()
        print("Cleared cache and failed list.")

    if args.force_complete:
        if not CHECKPOINT_DIR.exists() or not any(CHECKPOINT_DIR.iterdir()):
            print("No checkpoints found.")
            return 0

        concepts = load_concepts()
        concept_name_map = {c["code"]: c["name"] for c in concepts}

        checkpoints = sorted(CHECKPOINT_DIR.glob("*.json"))
        if args.concept:
            checkpoints = [p for p in checkpoints if p.stem == args.concept]

        if not checkpoints:
            print("No matching checkpoints found.")
            return 0

        failed = {item["code"]: item for item in load_failed()}
        processed = 0
        for cp in checkpoints:
            with open(cp, "r", encoding="utf-8") as f:
                data = json.load(f)
            code = data.get("concept_code", cp.stem)
            name = concept_name_map.get(code, code)
            stocks = data.get("stocks", [])
            save_concept(code, {
                "concept_code": code,
                "concept_name": name,
                "status": "complete",
                "reported_total": len(stocks),
                "stock_count": len(stocks),
                "stocks": stocks,
                "fetch_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            clear_checkpoint(code)
            failed.pop(code, None)
            print(f"  {code} {name}: {len(stocks)} stocks -> completed")
            processed += 1

        save_failed(list(failed.values()))
        clear_progress()
        print(f"\nForce-completed {processed} concept(s).")
        return 0

    source = EastMoneyConceptSource(
        requests_per_minute=15,
        min_interval=delay_min,
        max_interval=delay_max,
        verbose=args.verbose,
    )

    if args.concept:
        print(f"Fetching stocks for concept {args.concept}...")
        concept = next((c for c in load_concepts() if c.get("code") == args.concept), {})
        result = fetch_one(
            source,
            args.concept,
            concept.get("name", args.concept),
            page_size=member_page_size,
            max_pages=1 if first_page_only else None,
        )
        stocks = result.stocks
        print(f"Fetched {len(stocks)} stocks ({result.status}).")
        if first_page_only and stocks:
            save_concept(args.concept, {
                "concept_code": args.concept,
                "concept_name": concept.get("name", args.concept),
                "status": "complete",
                "reported_total": len(stocks),
                "stock_count": len(stocks),
                "stocks": stocks,
                "fetch_time": time.strftime("%Y-%m-%d %H:%M:%S"),
            })
            clear_checkpoint(args.concept)
        elif result.status != "complete":
            if stocks and is_partial_ok(
                args.concept,
                concept.get("name", args.concept),
                partial_ok,
            ):
                accept_partial_as_complete(
                    args.concept,
                    concept.get("name", args.concept),
                    result,
                )
                print(
                    f"Partial accepted ({len(stocks)} stocks), "
                    "marked complete (partial_ok)."
                )
            else:
                print(f"Fetch incomplete at page {result.failed_page or result.next_page}: {result.error}", file=sys.stderr)
                return 1

        if args.json:
            output_str = json.dumps(stocks, ensure_ascii=False, indent=2)
        else:
            lines = [f"Concept: {args.concept}", f"Stocks: {len(stocks)}", ""]
            lines.append(f"{'Code':<10} {'Name':<12} {'Price':>8} {'Chg%':>8} {'MV(亿)':>12}")
            lines.append("-" * 60)
            for s in stocks[:50]:
                price = s.get("price", "-")
                chg = s.get("change_pct", "-")
                mv = s.get("total_mv", 0)
                mv_str = f"{mv / 100000000:.1f}" if mv else "-"
                lines.append(f"{s['code']:<10} {s['name']:<12} {price!s:>8} {chg!s:>7}% {mv_str:>12}")
            if len(stocks) > 50:
                lines.append(f"  ... and {len(stocks) - 50} more")
            output_str = "\n".join(lines)

        if args.output:
            with open(args.output, "w", encoding="utf-8", newline="") as f:
                f.write(output_str)
            print(f"Saved to {args.output}")
        elif not args.quiet:
            print(output_str)
        return 0

    concepts = load_concepts()
    theme_config = load_theme_configuration()
    exclusions = load_member_fetch_exclusions()
    conflicts = sorted(set(exclusions) & referenced_concept_names(theme_config))
    if conflicts:
        print(
            "Error: member_fetch_exclusions contains theme-referenced concepts: "
            + ", ".join(conflicts),
            file=sys.stderr,
        )
        return 1
    ignored_concepts = [
        concept for concept in concepts
        if concept.get("name") in exclusions
    ]
    for concept in ignored_concepts:
        save_ignored_concept(concept, exclusions[concept["name"]])
    ignored_codes = {concept["code"] for concept in ignored_concepts}

    cached_codes = get_cached_codes(exclusions)
    failed = [
        item for item in load_failed()
        if item.get("code") not in ignored_codes
        and item.get("code") not in cached_codes
    ]
    save_failed(failed)
    failed_codes = set(f["code"] for f in failed)

    if args.retry_failed:
        todo = [c for c in concepts if c["code"] in failed_codes]
        if not todo:
            print("No failed concepts to retry.")
            return 0
        print(f"Retrying {len(todo)} previously failed concepts...")
    else:
        todo = [c for c in concepts if c["code"] not in cached_codes or c["code"] in failed_codes]

    if args.top > 0:
        todo = todo[:args.top]

    total = len(todo)
    already = len(cached_codes) - len(failed_codes & cached_codes)
    print(
        f"Concepts: {len(concepts)} total, {len(ignored_codes)} ignored, "
        f"{already} cached, {len(failed_codes)} failed, {total} to fetch"
    )

    if total == 0:
        print("All concepts already fetched. Use --reset to start fresh.")
        return 0

    concept_by_code = {concept["code"]: concept for concept in todo}
    failed_by_code = {
        item["code"]: item
        for item in failed
        if item.get("code") in concept_by_code
    }

    pending = [concept for concept in todo if concept["code"] not in cached_codes]
    total_pending = len(pending)

    for position, concept in enumerate(pending, 1):
        code = concept["code"]
        name = concept["name"]
        remaining = total_pending - position
        save_progress(
            status="fetching",
            round_page=None,
            round_position=position,
            round_size=total_pending,
            current_concept={"code": code, "name": name},
            completed_count=len(cached_codes),
            remaining_count=remaining,
            total_concepts=len(concepts),
        )
        print(
            f"[{position}/{total_pending}] "
            f"Fetching {name} ({code})...",
            flush=True,
        )

        try:
            result = fetch_one(
                source,
                code,
                name,
                page_size=member_page_size,
                max_pages=1 if first_page_only else None,
            )
            if result.error or result.failed_page is not None:
                if result.stocks and is_partial_ok(code, name, partial_ok):
                    accept_partial_as_complete(code, name, result)
                    failed_by_code.pop(code, None)
                    save_failed(list(failed_by_code.values()))
                    cached_codes.add(code)
                    action = "completed_partial_ok"
                    print(
                        f"  Partial accepted ({len(result.stocks)}/{result.total or '?'} "
                        "stocks), marked complete (partial_ok)."
                    )
                else:
                    clear_checkpoint(code)
                    failure = {
                        "code": code,
                        "name": name,
                        "error": result.error or result.status,
                        "failed_page": result.failed_page or result.next_page,
                        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    }
                    failed_by_code[code] = failure
                    save_failed(list(failed_by_code.values()))
                    save_progress(
                        status="failed",
                        round_page=None,
                        round_position=position,
                        round_size=total_pending,
                        current_concept={"code": code, "name": name},
                        completed_count=len(cached_codes),
                        remaining_count=remaining,
                        total_concepts=len(concepts),
                        error=failure["error"],
                    )
                    print(
                        f"  Incomplete ({len(result.stocks)}/{result.total or '?'}), "
                        f"checkpoint cleared: {failure['error']}."
                    )
                    print("  Stopping now so the caller can refresh the cookie and resume.")
                    return 1
            else:
                failed_by_code.pop(code, None)
                save_failed(list(failed_by_code.values()))
                if first_page_only:
                    save_concept(code, {
                        "concept_code": code,
                        "concept_name": name,
                        "status": "complete",
                        "reported_total": len(result.stocks),
                        "stock_count": len(result.stocks),
                        "stocks": result.stocks,
                        "fetch_time": time.strftime("%Y-%m-%d %H:%M:%S"),
                    })
                    clear_checkpoint(code)
                    cached_codes.add(code)
                    action = "completed"
                    print(f"  First page saved: {len(result.stocks)} stocks (done).")
                elif result.status == "complete":
                    cached_codes.add(code)
                    action = "completed"
                    print(f"  Complete: {len(result.stocks)} stocks.")
                else:
                    action = "page_complete"
                    print(
                        f"  Partial: "
                        f"{len(result.stocks)}/{result.total or '?'} stocks cached."
                    )
            save_progress(
                status="in_progress",
                last_action=action,
                round_page=None,
                round_position=position,
                round_size=total_pending,
                current_concept={"code": code, "name": name},
                completed_count=len(cached_codes),
                remaining_count=remaining,
                total_concepts=len(concepts),
            )

            if remaining > 0:
                delay = random.uniform(delay_min, delay_max)
                print(f"  Waiting {delay:.1f}s...", flush=True)
                time.sleep(delay)

        except KeyboardInterrupt:
            failure = {
                "code": code,
                "name": name,
                "error": "interrupted",
                "failed_page": 0,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            failed_by_code[code] = failure
            save_failed(list(failed_by_code.values()))
            save_progress(
                status="interrupted",
                round_page=None,
                round_position=position,
                round_size=total_pending,
                current_concept={"code": code, "name": name},
                completed_count=len(cached_codes),
                remaining_count=remaining,
                total_concepts=len(concepts),
            )
            print("\n\nInterrupted! Progress saved. Run again to continue.")
            return 130
        except Exception as exc:
            failure = {
                "code": code,
                "name": name,
                "error": str(exc),
                "failed_page": 0,
                "time": time.strftime("%Y-%m-%d %H:%M:%S"),
            }
            failed_by_code[code] = failure
            save_failed(list(failed_by_code.values()))
            save_progress(
                status="failed",
                round_page=None,
                round_position=position,
                round_size=total_pending,
                current_concept={"code": code, "name": name},
                completed_count=len(cached_codes),
                remaining_count=remaining,
                total_concepts=len(concepts),
                error=str(exc),
            )
            print(f"  Error: {exc}")
            return 1

    all_failed = list(failed_by_code.values())
    save_failed(all_failed)
    clear_progress()

    cached_codes = get_cached_codes(exclusions)
    total_stocks = sum((load_concept(c) or {}).get("stock_count", 0) for c in cached_codes)
    cached_count = len(cached_codes) - len([f for f in all_failed if f["code"] in cached_codes])
    print(f"\nDone! Cached: {cached_count}, Failed: {len(all_failed)}, Total stocks: {total_stocks}")

    if all_failed:
        print(f"Failed concepts ({len(all_failed)}):")
        for f in all_failed[:10]:
            print(f"  {f['code']} {f['name']} - {f['error']}")
        if len(all_failed) > 10:
            print(f"  ... and {len(all_failed) - 10} more")
        print(f"Run with --retry-failed to retry them.")

    all_data = load_all_cached()
    if args.json:
        output_str = json.dumps(
            {k: {"concept_name": v["concept_name"], "stock_count": v["stock_count"]} for k, v in all_data.items()},
            ensure_ascii=False,
            indent=2,
        )
    else:
        lines = []
        lines.append(f"{'Concept Code':<12} {'Concept Name':<20} {'Stocks':>8}")
        lines.append("-" * 45)
        for code, data in sorted(all_data.items(), key=lambda x: x[1]["stock_count"], reverse=True):
            lines.append(f"{code:<12} {data['concept_name']:<20} {data['stock_count']:>8}")
        output_str = "\n".join(lines)

    if args.output:
        with open(args.output, "w", encoding="utf-8", newline="") as f:
            f.write(output_str)
        print(f"Saved to {args.output}")
    elif not args.quiet:
        print(output_str)
    return 1 if all_failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
