from __future__ import annotations

import json
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

from ashare_pilot.mapping._commands.intraday.validate_annotations import validate
from ashare_pilot.mapping.intraday_contract import attach_theme_evidence, primary_theme
from ashare_pilot.themes._commands import (
    concepts_fetch_stocks,
    dashboard,
    library_build,
    ranking,
)
from ashare_pilot.themes.datasource import ConceptStocksFetchResult, EastMoneyConceptSource
from ashare_pilot.themes.fetch_settings import load_fetch_page_sizes, load_first_page_only


ROOT = Path(__file__).resolve().parents[2]


def api_stock(index: int) -> dict:
    code = f"{index:06d}"
    return {"f12": code, "f13": 0, "f14": f"样本{index}", "f20": 1, "f21": 1}


def api_concept(index: int) -> dict:
    return {
        "f12": f"BK{index:04d}",
        "f13": 90,
        "f14": f"概念{index}",
        "f2": 1,
        "f3": 1,
        "f62": 1,
    }


def source_with_pages(monkeypatch: pytest.MonkeyPatch, pages: dict[int, dict | None]):
    source = EastMoneyConceptSource(min_interval=0, max_interval=0)
    calls = []

    def fetch(_url, _headers, page_label="", callback=None):
        page = int(page_label.rsplit("p", 1)[1])
        calls.append(page)
        return pages.get(page)

    monkeypatch.setattr(source, "_fetch_page_with_retry", fetch)
    monkeypatch.setattr("ashare_pilot.themes.datasource.time.sleep", lambda _seconds: None)
    return source, calls


def response(total: int, rows: list[dict]) -> dict:
    return {"rc": 0, "data": {"total": total, "diff": rows}}


def test_concept_members_fetches_all_browser_sized_pages(monkeypatch: pytest.MonkeyPatch):
    source, calls = source_with_pages(monkeypatch, {
        1: response(150, [api_stock(i) for i in range(50)]),
        2: response(150, [api_stock(i) for i in range(50, 100)]),
        3: response(150, [api_stock(i) for i in range(100, 150)]),
    })
    checkpoints = []
    result = source.fetch_concept_stocks("BK0001", on_page=checkpoints.append)
    assert result.status == "complete"
    assert result.total == len(result.stocks) == 150
    assert len({row["code"] for row in result.stocks}) == 150
    assert calls == [1, 2, 3]
    assert [item.next_page for item in checkpoints] == [2, 3, 4]


def test_concept_board_list_uses_both_browser_endpoints(
    monkeypatch: pytest.MonkeyPatch,
):
    source = EastMoneyConceptSource(min_interval=0, max_interval=0)
    concepts = [api_concept(index) for index in range(75)]
    captured = []

    def fetch(url, headers, page_label=""):
        query = parse_qs(urlparse(url).query)
        captured.append((query, headers, page_label))
        page = int(query["pn"][0])
        start = (page - 1) * 50
        return response(75, concepts[start : start + 50])

    monkeypatch.setattr(source, "_fetch_page_with_retry", fetch)
    result = source.fetch_concept_sectors(resume=False)

    assert len(result) == 75
    assert [item[2] for item in captured] == ["1", "2"]
    for query, headers, _page_label in captured:
        assert query["pz"] == ["50"]
        assert query["fid"] == ["f62"]
        assert query["fs"] == ["m:90+t:3"]
        assert query["ut"] == ["8dec03ba335b81bf4ebdf7b29ec27d15"]


def test_concept_board_list_resumes_versioned_checkpoint(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    concepts = [api_concept(index) for index in range(75)]

    first = EastMoneyConceptSource(
        min_interval=0,
        max_interval=0,
        state_dir=tmp_path,
    )

    def first_fetch(url, _headers, page_label=""):
        page = int(parse_qs(urlparse(url).query)["pn"][0])
        if page == 2:
            return None
        start = (page - 1) * 50
        return response(75, concepts[start : start + 50])

    monkeypatch.setattr(first, "_fetch_page_with_retry", first_fetch)
    with pytest.raises(RuntimeError, match="page 2 failed"):
        first.fetch_concept_sectors()

    state_path = tmp_path / "concepts_fetch_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    assert state["schema_version"] == "concept_fetch_state.v2"
    assert state["next_page"] == 2
    assert len(state["results"]) == 50

    second = EastMoneyConceptSource(
        min_interval=0,
        max_interval=0,
        state_dir=tmp_path,
    )
    resumed_pages = []

    def second_fetch(url, _headers, page_label=""):
        page = int(parse_qs(urlparse(url).query)["pn"][0])
        resumed_pages.append(page)
        start = (page - 1) * 50
        return response(75, concepts[start : start + 50])

    monkeypatch.setattr(second, "_fetch_page_with_retry", second_fetch)
    result = second.fetch_concept_sectors()

    assert len(result) == 75
    assert resumed_pages == [2]
    assert not state_path.exists()


def test_concept_members_resume_from_failed_page(monkeypatch: pytest.MonkeyPatch):
    first, first_calls = source_with_pages(monkeypatch, {
        1: response(75, [api_stock(i) for i in range(50)]),
        2: None,
    })
    partial = first.fetch_concept_stocks("BK0001")
    assert partial.status == "partial"
    assert partial.next_page == partial.failed_page == 2
    assert first_calls == [1, 2]

    second, second_calls = source_with_pages(monkeypatch, {
        2: response(75, [api_stock(i) for i in range(50, 75)]),
    })
    complete = second.fetch_concept_stocks(
        "BK0001",
        start_page=partial.next_page,
        initial_stocks=partial.stocks,
        known_total=partial.total,
    )
    assert complete.status == "complete"
    assert len(complete.stocks) == 75
    assert second_calls == [2]


def test_member_request_uses_validated_browser_contract(
    monkeypatch: pytest.MonkeyPatch,
):
    source = EastMoneyConceptSource(min_interval=0, max_interval=0)
    captured = {}

    def fetch(url, headers, page_label=""):
        captured["query"] = parse_qs(urlparse(url).query)
        captured["headers"] = headers
        captured["page_label"] = page_label
        return response(1, [api_stock(0)])

    monkeypatch.setattr(source, "_fetch_page_with_retry", fetch)
    result = source.fetch_concept_stocks("BK1749")

    assert result.status == "complete"
    assert captured["query"]["pz"] == ["50"]
    assert captured["query"]["pn"] == ["1"]
    assert captured["query"]["fid"] == ["f3"]
    assert captured["query"]["fs"] == ["b:BK1749"]
    assert captured["query"]["ut"] == ["8dec03ba335b81bf4ebdf7b29ec27d15"]
    assert captured["headers"]["user-agent"] in (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/146.0.0.0 Safari/537.36",
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:109.0) Gecko/20100101 Firefox/121.0",
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:109.0) Gecko/20100101 Firefox/121.0",
    )
    assert captured["page_label"] == "BK1749/p1"


def test_request_uses_raw_requests_get_without_session(
    monkeypatch: pytest.MonkeyPatch,
):
    source = EastMoneyConceptSource(min_interval=0, max_interval=0)
    source._last_request_time = 0.0
    source._request_count = 0

    captured = []

    class Resp:
        status_code = 200
        text = '{"rc": 0, "data": {"total": 1, "diff": []}}'

    def fake_get(url, *, headers, timeout, **kwargs):
        captured.append((url, headers))
        return Resp()

    monkeypatch.setattr(source._session, "get", fake_get)
    result = source._request_with_retry(
        "https://example.invalid/query",
        {"cookie": "must-not-appear-in-diagnostics"},
    )

    assert result == {"rc": 0, "data": {"total": 1, "diff": []}}
    assert len(captured) == 1
    assert captured[0][0] == "https://example.invalid/query"


def test_legacy_100_row_checkpoint_resumes_safely_at_50_rows(
    monkeypatch: pytest.MonkeyPatch,
):
    legacy, _legacy_calls = source_with_pages(monkeypatch, {
        1: response(150, [api_stock(i) for i in range(100)]),
    })
    legacy_page = legacy.fetch_concept_stocks(
        "BK0001",
        page_size=100,
        max_pages=1,
    )
    assert len(legacy_page.stocks) == 100
    assert legacy_page.next_page == 3
    assert legacy_page.current_page_size == 50

    resumed, resumed_calls = source_with_pages(monkeypatch, {
        3: response(150, [api_stock(i) for i in range(100, 150)]),
    })
    complete = resumed.fetch_concept_stocks(
        "BK0001",
        start_page=legacy_page.next_page,
        initial_stocks=legacy_page.stocks,
        known_total=legacy_page.total,
    )

    assert complete.status == "complete"
    assert len(complete.stocks) == 150
    assert resumed_calls == [3]


def test_fetch_stocks_cli_failure_is_nonzero_and_does_not_publish(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cache = tmp_path / "cache"
    cache.mkdir()
    (cache / "concepts.json").write_text(
        json.dumps([
            {"code": "BK0001", "name": "样本概念"},
            {"code": "BK0002", "name": "不应继续请求"},
        ], ensure_ascii=False),
        encoding="utf-8",
    )
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(json.dumps({
        "fetch_settings": {
            "concept_member_page_size": 50,
            "concept_member_first_page_only": False,
        },
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(concepts_fetch_stocks, "THEME_CONFIG_FILE", config_path)
    monkeypatch.setattr(concepts_fetch_stocks, "CACHE_DIR", cache)
    monkeypatch.setattr(concepts_fetch_stocks, "STOCKS_DIR", cache / "stocks")
    monkeypatch.setattr(concepts_fetch_stocks, "FAILED_FILE", cache / "failed.json")
    monkeypatch.setattr(concepts_fetch_stocks, "CHECKPOINT_DIR", cache / "checkpoints")
    monkeypatch.setattr(concepts_fetch_stocks, "PROGRESS_FILE", cache / "progress.json")

    class FailedSource:
        calls = []

        def __init__(self, **_kwargs):
            pass

        def fetch_concept_stocks(self, code, **_kwargs):
            self.calls.append(code)
            return ConceptStocksFetchResult("failed", [], None, 1, 1, "request_failed")

    monkeypatch.setattr(concepts_fetch_stocks, "EastMoneyConceptSource", FailedSource)
    assert concepts_fetch_stocks.main(["-q"]) == 1
    assert FailedSource.calls == ["BK0001"]
    assert not (cache / "stocks" / "BK0001.json").exists()
    assert not (cache / "checkpoints" / "BK0001.json").exists()


def test_theme_fetch_page_sizes_are_configurable_and_validated(tmp_path: Path):
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(
        json.dumps({
            "fetch_settings": {
                "concept_board_page_size": 80,
                "concept_member_page_size": 100,
            }
        }),
        encoding="utf-8",
    )
    assert load_fetch_page_sizes(config_path) == (80, 100)

    config_path.write_text(
        json.dumps({
            "fetch_settings": {
                "concept_board_page_size": 101,
                "concept_member_page_size": 50,
            }
        }),
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="between 1 and 100"):
        load_fetch_page_sizes(config_path)


def test_member_checkpoint_is_discarded_when_configured_page_size_changes(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
):
    checkpoints = tmp_path / "checkpoints"
    checkpoints.mkdir()
    checkpoint = checkpoints / "BK0001.json"
    checkpoint.write_text(
        json.dumps({
            "schema_version": "concept_stock_checkpoint.v3",
            "concept_code": "BK0001",
            "page_size": 50,
            "next_page": 3,
            "stocks": [api_stock(0)],
        }),
        encoding="utf-8",
    )
    monkeypatch.setattr(concepts_fetch_stocks, "CHECKPOINT_DIR", checkpoints)

    assert concepts_fetch_stocks.load_checkpoint("BK0001", 100) is None
    assert not checkpoint.exists()


def test_fetch_stocks_reset_starts_page_one_then_completed_default_skips(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cache = tmp_path / "cache"
    (cache / "checkpoints").mkdir(parents=True)
    (cache / "stocks").mkdir()
    (cache / "concepts.json").write_text(
        json.dumps([{"code": "BK0001", "name": "样本概念"}], ensure_ascii=False),
        encoding="utf-8",
    )
    (cache / "checkpoints" / "BK0001.json").write_text(
        json.dumps({"next_page": 2, "total": 2, "stocks": [api_stock(0)]}),
        encoding="utf-8",
    )
    monkeypatch.setattr(concepts_fetch_stocks, "CACHE_DIR", cache)
    monkeypatch.setattr(concepts_fetch_stocks, "STOCKS_DIR", cache / "stocks")
    monkeypatch.setattr(concepts_fetch_stocks, "FAILED_FILE", cache / "failed.json")
    monkeypatch.setattr(concepts_fetch_stocks, "CHECKPOINT_DIR", cache / "checkpoints")
    monkeypatch.setattr(concepts_fetch_stocks, "PROGRESS_FILE", cache / "progress.json")
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(json.dumps({
        "fetch_settings": {"concept_member_page_size": 50},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(concepts_fetch_stocks, "THEME_CONFIG_FILE", config_path)
    starts = []

    class CompleteSource:
        def __init__(self, **_kwargs):
            pass

        def fetch_concept_stocks(self, *_args, **kwargs):
            starts.append(kwargs["start_page"])
            result = ConceptStocksFetchResult(
                "complete",
                [{"code": "sz000001", "name": "样本"}],
                1,
                2,
            )
            kwargs["on_page"](result)
            return result

    monkeypatch.setattr(concepts_fetch_stocks, "EastMoneyConceptSource", CompleteSource)
    assert concepts_fetch_stocks.main(["--reset", "-q"]) == 0
    assert starts == [1]
    assert not (cache / "checkpoints").exists()
    assert concepts_fetch_stocks.main(["-q"]) == 0
    assert starts == [1]


def test_sequential_resume_after_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cache = tmp_path / "cache"
    cache.mkdir()
    concepts = [
        {"code": "A", "name": "多页甲"},
        {"code": "B", "name": "单页乙"},
        {"code": "C", "name": "多页丙"},
        {"code": "D", "name": "单页丁"},
    ]
    (cache / "concepts.json").write_text(
        json.dumps(concepts, ensure_ascii=False), encoding="utf-8"
    )
    monkeypatch.setattr(concepts_fetch_stocks, "CACHE_DIR", cache)
    monkeypatch.setattr(concepts_fetch_stocks, "STOCKS_DIR", cache / "stocks")
    monkeypatch.setattr(concepts_fetch_stocks, "FAILED_FILE", cache / "failed.json")
    monkeypatch.setattr(concepts_fetch_stocks, "CHECKPOINT_DIR", cache / "checkpoints")
    monkeypatch.setattr(concepts_fetch_stocks, "PROGRESS_FILE", cache / "progress.json")
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(json.dumps({
        "fetch_settings": {"concept_member_page_size": 50},
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(concepts_fetch_stocks, "THEME_CONFIG_FILE", config_path)
    monkeypatch.setattr(concepts_fetch_stocks.time, "sleep", lambda _seconds: None)
    totals = {"A": 150, "B": 50, "C": 150, "D": 50}
    calls = []
    fail_once = {"C": True}

    class SequentialSource:
        def __init__(self, **_kwargs):
            pass

        def fetch_concept_stocks(
            self, code, *, start_page, initial_stocks, on_page, max_pages, **_kwargs
        ):
            calls.append((code, start_page))
            if code == "C" and start_page == 1 and fail_once["C"]:
                fail_once["C"] = False
                return ConceptStocksFetchResult(
                    "failed", initial_stocks, None, 1, 1, "request_failed",
                )
            total = totals[code]
            stocks = list(initial_stocks) + [
                {"code": f"sz{code}{index:05d}", "name": f"{code}{index}"}
                for index in range(len(initial_stocks), total)
            ]
            result = ConceptStocksFetchResult(
                "complete", stocks, total, 2,
            )
            on_page(result)
            return result

    monkeypatch.setattr(concepts_fetch_stocks, "EastMoneyConceptSource", SequentialSource)

    assert concepts_fetch_stocks.main(["--reset", "-q"]) == 1
    assert calls == [("A", 1), ("B", 1), ("C", 1)]
    progress = json.loads((cache / "progress.json").read_text(encoding="utf-8"))
    assert progress["status"] == "failed"
    assert progress["round_page"] is None
    assert progress["current_concept"]["code"] == "C"

    calls.clear()
    assert concepts_fetch_stocks.main(["-q"]) == 0
    assert calls == [("C", 1), ("D", 1)]
    assert not (cache / "progress.json").exists()
    assert not (cache / "checkpoints").exists()


def test_explicit_member_fetch_exclusions_skip_network_and_write_markers(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cache = tmp_path / "cache"
    cache.mkdir()
    concepts = [
        {"code": "BK0001", "name": "引用概念"},
        {"code": "BK1112", "name": "破净股"},
        {"code": "BK1672", "name": "破发股"},
    ]
    (cache / "concepts.json").write_text(
        json.dumps(concepts, ensure_ascii=False), encoding="utf-8"
    )
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(json.dumps({
        "themes": {"样本主题": {"concepts": ["引用概念"]}},
        "member_fetch_exclusions": {
            "破净股": "估值状态分类",
            "破发股": "发行状态分类",
        },
    }, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(concepts_fetch_stocks, "CACHE_DIR", cache)
    monkeypatch.setattr(concepts_fetch_stocks, "STOCKS_DIR", cache / "stocks")
    monkeypatch.setattr(concepts_fetch_stocks, "FAILED_FILE", cache / "failed.json")
    monkeypatch.setattr(concepts_fetch_stocks, "CHECKPOINT_DIR", cache / "checkpoints")
    monkeypatch.setattr(concepts_fetch_stocks, "PROGRESS_FILE", cache / "progress.json")
    monkeypatch.setattr(concepts_fetch_stocks, "THEME_CONFIG_FILE", config_path)
    monkeypatch.setattr(concepts_fetch_stocks.time, "sleep", lambda _seconds: None)
    calls = []

    class Source:
        def __init__(self, **_kwargs):
            pass

        def fetch_concept_stocks(
            self, code, *, start_page, initial_stocks, on_page, **_kwargs
        ):
            calls.append((code, start_page))
            result = ConceptStocksFetchResult(
                "complete",
                [{"code": "sz000001", "name": "样本"}],
                1,
                2,
            )
            on_page(result)
            return result

    monkeypatch.setattr(concepts_fetch_stocks, "EastMoneyConceptSource", Source)
    assert concepts_fetch_stocks.main(["--reset", "-q"]) == 0
    assert calls == [("BK0001", 1)]
    for code, name in (("BK1112", "破净股"), ("BK1672", "破发股")):
        marker = json.loads(
            (cache / "stocks" / f"{code}.json").read_text(encoding="utf-8")
        )
        assert marker["concept_name"] == name
        assert marker["status"] == "ignored"
        assert marker["stocks"] == []

    monkeypatch.setattr(library_build, "STOCKS_CACHE_DIR", cache / "stocks")
    monkeypatch.setattr(
        library_build,
        "MEMBER_FETCH_EXCLUSIONS",
        {"破净股": "估值状态分类", "破发股": "发行状态分类"},
    )
    loaded = library_build.load_concept_stocks()
    assert set(loaded) == {"BK0001", "BK1112", "BK1672"}
    assert concepts_fetch_stocks.get_cached_codes({"破净股", "破发股"}) == {
        "BK0001",
        "BK1112",
        "BK1672",
    }
    assert concepts_fetch_stocks.get_cached_codes() == {"BK0001"}


def test_dashboard_filters_member_fetch_exclusions_and_refills_top(
    monkeypatch: pytest.MonkeyPatch,
):
    concepts = [
        {
            "code": "BK0001",
            "name": "融资融券",
            "change_pct": "+3.00%",
            "net_inflow": "3.00",
            "up_count": 30,
            "down_count": 1,
        },
        {
            "code": "BK0002",
            "name": "主题甲",
            "change_pct": "+2.00%",
            "net_inflow": "2.00",
            "up_count": 20,
            "down_count": 2,
        },
        {
            "code": "BK0003",
            "name": "主题乙",
            "change_pct": "+1.00%",
            "net_inflow": "1.00",
            "up_count": 10,
            "down_count": 3,
        },
    ]
    requested = []

    class Source:
        def fetch_concept_ranking(self, *, top):
            requested.append(top)
            return concepts

    monkeypatch.setattr(dashboard, "_ds", Source())
    monkeypatch.setattr(
        dashboard,
        "load_member_fetch_exclusions",
        lambda: {"融资融券"},
    )
    monkeypatch.setattr(dashboard, "load_concept_to_stock", lambda: {})
    monkeypatch.setattr(dashboard, "load_lianban_set", lambda _mapping: set())
    monkeypatch.setattr(
        dashboard,
        "compute_momentum",
        lambda rows, *_args, **_kwargs: [
            {
                "raw": 0,
                "limit_up": 0,
                "first_board": 0,
                "continued_board": 0,
                "member_count": 0,
            }
            for _row in rows
        ],
    )

    result = dashboard.build_dashboard(top=2)

    assert requested == [3]
    assert result["meta"]["ranking_count"] == 2
    assert set(result["themes"]) == {"BK0002", "BK0003"}


def test_member_model_retains_all_qualified_scores_and_edge_has_none(
    monkeypatch: pytest.MonkeyPatch,
):
    cfg = library_build._load_library_config()
    cfg.update({
        "pure_limit": 1,
        "leader_limit": 1,
        "candidate_limit": 1,
        "leader_threshold": 101,
        "default_min_coverage": 60,
        "default_min_concepts": 2,
    })
    monkeypatch.setattr(library_build, "LIBRARY_CONFIG", cfg)
    theme_cfg = {
        "concepts": ["概念甲", "概念乙"],
        "concept_weights_override": {"概念甲": 1.0, "概念乙": 1.0},
        "anchors": ["sz000001"],
    }
    all_stocks = {
        "概念甲": [
            {"code": "sz000001", "name": "锚点", "total_mv": 4, "amount": 4},
            {"code": "sz000002", "name": "合格甲", "total_mv": 3, "amount": 3},
            {"code": "sz000003", "name": "合格乙", "total_mv": 2, "amount": 2},
            {"code": "sz000004", "name": "边缘", "total_mv": 1, "amount": 1},
        ],
        "概念乙": [
            {"code": "sz000002", "name": "合格甲", "total_mv": 3, "amount": 3},
            {"code": "sz000003", "name": "合格乙", "total_mv": 2, "amount": 2},
        ],
    }
    concept_info = {
        "概念甲": {"stock_count": 4},
        "概念乙": {"stock_count": 2},
    }
    pure, leaders, candidates, members, _weights, qualified_count = (
        library_build._compute_theme_scores(
            "样本主题", theme_cfg, ["概念甲", "概念乙"], all_stocks, concept_info
        )
    )
    by_code = {row["code"]: row for row in members}
    assert qualified_count == 3
    assert by_code["sz000001"]["member_role"] == "core"
    assert by_code["sz000002"]["member_role"] == "qualified"
    assert by_code["sz000003"]["member_role"] == "qualified"
    assert {"purity_score", "industry_score", "candidate_score"} <= by_code["sz000003"].keys()
    assert by_code["sz000004"] == {
        "code": "sz000004",
        "name": "边缘",
        "eligible": False,
        "member_role": "edge",
        "anchor": False,
        "theme_weight": 3.0,
    }
    assert len(pure) == len(leaders) == len(candidates) == 1
    cfg["leader_threshold"] = by_code["sz000002"]["industry_score"]
    rerun = library_build._compute_theme_scores(
        "样本主题", theme_cfg, ["概念甲", "概念乙"], all_stocks, concept_info
    )
    rerun_by_code = {row["code"]: row for row in rerun[3]}
    assert rerun_by_code["sz000002"]["member_role"] == "core"


def aggregation_config() -> dict[str, float]:
    return {
        "core_weight": 1.0,
        "qualified_purity_scale": 0.01,
        "qualified_weight_min": 0.0,
        "qualified_weight_max": 1.0,
        "edge_theme_weight_scale": 0.1,
        "edge_weight_min": 0.0,
        "edge_weight_max": 1.0,
    }


def test_dual_heat_leaders_signed_capital_and_full_stock_themes(
    monkeypatch: pytest.MonkeyPatch,
):
    monkeypatch.setattr(ranking, "_load_aggregation_config", aggregation_config)
    monkeypatch.setattr(ranking, "_library_metadata", lambda: ("2026-07-23", "2026-07-23"))
    data = {
        "enriched_time": "2026-07-23 14:31:36",
        "compute_pool": [
            {"code": "sz000001", "name": "核心", "quick_score": 3, "change_pct": "2%",
             "enriched": {"money_flow": {"main_net_inflow": "-2"}}},
            {"code": "sz000002", "name": "合格", "quick_score": 2, "change_pct": "5%",
             "enriched": {"money_flow": {"main_net_inflow": "-1"}}},
            {"code": "sz000003", "name": "边缘动量", "quick_score": 1, "change_pct": "10%",
             "enriched": {"money_flow": {"main_net_inflow": "10"}}},
        ],
        "stock_themes": {
            "sz000001": {"themes": [{"name": "主题甲", "member_role": "core", "eligible": True,
                                      "weight": 8, "purity_score": 80, "industry_score": 90}]},
            "sz000002": {"themes": [{"name": "主题甲", "member_role": "qualified", "eligible": True,
                                      "weight": 5, "purity_score": 50, "industry_score": 40}]},
            "sz000003": {"themes": [{"name": "主题甲", "member_role": "edge", "eligible": False,
                                      "weight": 2}]},
        },
    }
    doc = ranking.build_theme_ranking_document(data, pool_cutoff=3, top_n=15)
    theme = doc["theme_ranking"][0]
    assert "heat" not in theme
    assert theme["core_leader"]["code"] == "sz000001"
    assert theme["core_leader"]["leader_fallback"] is False
    assert theme["momentum_leader"]["code"] == "sz000003"
    assert theme["core_breakdown"]["capital"] < 0
    edge = next(row for row in theme["contributors"] if row["code"] == "sz000003")
    assert "core_heat" not in edge["contributions"]
    assert "diffusion_heat" in edge["contributions"]
    assert doc["market_as_of"] == "2026-07-23 14:31:36"
    assert set(doc["stock_themes"]) == {"sz000001", "sz000002", "sz000003"}


def test_top_15_does_not_truncate_stock_theme_relations(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setattr(ranking, "_load_aggregation_config", aggregation_config)
    monkeypatch.setattr(ranking, "_library_metadata", lambda: ("2026-07-23", "2026-07-23"))
    relations = [
        {"name": f"主题{index:02d}", "member_role": "edge", "eligible": False, "weight": 1}
        for index in range(16)
    ]
    data = {
        "compute_pool": [{"code": "sz000001", "name": "样本", "change_pct": "1%"}],
        "stock_themes": {"sz000001": {"themes": relations}},
    }
    doc = ranking.build_theme_ranking_document(data, pool_cutoff=1, top_n=15)
    assert len(doc["theme_ranking"]) == 15
    assert len(doc["stock_themes"]["sz000001"]["themes"]) == 16


def test_primary_theme_order_and_annotation_boundary():
    relations = [
        {"name": "边缘高分", "member_role": "edge", "industry_score": 100, "weight": 10},
        {"name": "合格", "member_role": "qualified", "industry_score": 99, "weight": 10},
        {"name": "核心乙", "member_role": "core", "industry_score": 80, "purity_score": 70, "weight": 8},
        {"name": "核心甲", "member_role": "core", "industry_score": 80, "purity_score": 70, "weight": 8},
    ]
    assert primary_theme(relations) == "核心乙"
    stock = attach_theme_evidence(
        [{"code": "sz300001", "name": "样本"}],
        {"sz300001": {"themes": relations}},
    )[0]
    assert stock["primary_theme"] == stock["sector"] == "核心乙"
    assert stock["market_board"] == "创业板"

    annotations = {
        "schema_version": "intraday_mapper_annotations.v1",
        "date": "2026-07-23",
        "market_assessment": {"reasoning_trace": "样本"},
        "stocks": [{"code": "sz300001", "sector": "创业板"}],
        "strategy": {},
    }
    errors = validate(annotations, "2026-07-23", {"sz300001"}, base={"stocks": []})
    assert any("deterministic theme field not allowed" in error for error in errors)


def test_frozen_20260723_theme_roles_and_mapper_separation(
    monkeypatch: pytest.MonkeyPatch,
):
    data = json.loads(
        (ROOT / "tests/fixtures/themes/adr0003_2026-07-23.json").read_text(encoding="utf-8")
    )
    monkeypatch.setattr(ranking, "_load_aggregation_config", aggregation_config)
    monkeypatch.setattr(ranking, "_library_metadata", lambda: ("2026-07-23", "2026-07-23"))
    doc = ranking.build_theme_ranking_document(data, pool_cutoff=3, top_n=15)
    ai = next(row for row in doc["theme_ranking"] if row["theme"] == "AI算力")
    pcb = next(row for row in doc["theme_ranking"] if row["theme"] == "PCB/被动元件")
    assert ai["core_leader"]["name"] == "日科化学"
    assert ai["core_leader"]["leader_role"] == "qualified"
    assert ai["core_leader"]["leader_fallback"] is True
    assert pcb["core_leader"] is None
    assert pcb["momentum_leader"]["name"] == "中岩大地"

    mapped = attach_theme_evidence(
        data["compute_pool"], doc["stock_themes"]
    )
    aluminum = next(row for row in mapped if row["code"] == "sh601600")
    assert aluminum["primary_theme"] == aluminum["sector"] == "有色金属"
    assert aluminum["market_board"] == "沪市主板"
    assert len(aluminum["themes"]) == 2


def test_load_first_page_only_defaults_to_false(tmp_path: Path):
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(
        json.dumps({"fetch_settings": {}}),
        encoding="utf-8",
    )
    assert load_first_page_only(config_path) is False


def test_load_first_page_only_reads_true(tmp_path: Path):
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(
        json.dumps({
            "fetch_settings": {
                "concept_member_first_page_only": True,
            }
        }),
        encoding="utf-8",
    )
    assert load_first_page_only(config_path) is True


def test_load_first_page_only_reads_false(tmp_path: Path):
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(
        json.dumps({
            "fetch_settings": {
                "concept_member_first_page_only": False,
            }
        }),
        encoding="utf-8",
    )
    assert load_first_page_only(config_path) is False


def test_load_first_page_only_handles_non_bool(tmp_path: Path):
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(
        json.dumps({
            "fetch_settings": {
                "concept_member_first_page_only": 1,
            }
        }),
        encoding="utf-8",
    )
    assert load_first_page_only(config_path) is True


def test_first_page_only_forces_complete_after_one_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cache = tmp_path / "cache"
    cache.mkdir()
    concepts = [
        {"code": "BK0001", "name": "多页概念"},
        {"code": "BK0002", "name": "单页概念"},
    ]
    (cache / "concepts.json").write_text(
        json.dumps(concepts, ensure_ascii=False), encoding="utf-8"
    )
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(
        json.dumps({
            "fetch_settings": {
                "concept_member_first_page_only": True,
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(concepts_fetch_stocks, "CACHE_DIR", cache)
    monkeypatch.setattr(concepts_fetch_stocks, "STOCKS_DIR", cache / "stocks")
    monkeypatch.setattr(concepts_fetch_stocks, "FAILED_FILE", cache / "failed.json")
    monkeypatch.setattr(concepts_fetch_stocks, "CHECKPOINT_DIR", cache / "checkpoints")
    monkeypatch.setattr(concepts_fetch_stocks, "PROGRESS_FILE", cache / "progress.json")
    monkeypatch.setattr(concepts_fetch_stocks, "THEME_CONFIG_FILE", config_path)
    monkeypatch.setattr(concepts_fetch_stocks.time, "sleep", lambda _seconds: None)
    calls = []

    class FirstPageSource:
        def __init__(self, **_kwargs):
            pass

        def fetch_concept_stocks(
            self, code, *, start_page, initial_stocks, on_page, max_pages, **_kwargs
        ):
            calls.append((code, start_page))
            total = 150 if code == "BK0001" else 50
            page_count = min(50, total - len(initial_stocks))
            stocks = list(initial_stocks) + [
                {"code": f"sz{code}{index:05d}", "name": f"{code}{index}"}
                for index in range(len(initial_stocks), len(initial_stocks) + page_count)
            ]
            complete = len(stocks) == total
            result = ConceptStocksFetchResult(
                "complete" if complete else "partial",
                stocks,
                total,
                start_page + 1,
            )
            on_page(result)
            return result

    monkeypatch.setattr(concepts_fetch_stocks, "EastMoneyConceptSource", FirstPageSource)
    assert concepts_fetch_stocks.main(["--reset", "-q"]) == 0
    assert calls == [("BK0001", 1), ("BK0002", 1)]

    cached = json.loads(
        (cache / "stocks" / "BK0001.json").read_text(encoding="utf-8")
    )
    assert cached["status"] == "complete"
    assert cached["stock_count"] == 50
    assert cached["reported_total"] == 50

    cached2 = json.loads(
        (cache / "stocks" / "BK0002.json").read_text(encoding="utf-8")
    )
    assert cached2["status"] == "complete"
    assert cached2["stock_count"] == 50

    assert not (cache / "checkpoints").exists()
    assert not (cache / "progress.json").exists()


def test_first_page_only_does_not_fetch_second_page(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    cache = tmp_path / "cache"
    cache.mkdir()
    concepts = [
        {"code": "BK0001", "name": "多页概念"},
        {"code": "BK0002", "name": "单页概念"},
    ]
    (cache / "concepts.json").write_text(
        json.dumps(concepts, ensure_ascii=False), encoding="utf-8"
    )
    config_path = tmp_path / "theme-config.json"
    config_path.write_text(
        json.dumps({
            "fetch_settings": {
                "concept_member_first_page_only": True,
            },
        }, ensure_ascii=False),
        encoding="utf-8",
    )
    monkeypatch.setattr(concepts_fetch_stocks, "CACHE_DIR", cache)
    monkeypatch.setattr(concepts_fetch_stocks, "STOCKS_DIR", cache / "stocks")
    monkeypatch.setattr(concepts_fetch_stocks, "FAILED_FILE", cache / "failed.json")
    monkeypatch.setattr(concepts_fetch_stocks, "CHECKPOINT_DIR", cache / "checkpoints")
    monkeypatch.setattr(concepts_fetch_stocks, "PROGRESS_FILE", cache / "progress.json")
    monkeypatch.setattr(concepts_fetch_stocks, "THEME_CONFIG_FILE", config_path)
    monkeypatch.setattr(concepts_fetch_stocks.time, "sleep", lambda _seconds: None)
    calls = []

    class FirstPageSource:
        def __init__(self, **_kwargs):
            pass

        def fetch_concept_stocks(
            self, code, *, start_page, initial_stocks, on_page, max_pages, **_kwargs
        ):
            assert max_pages == 1
            calls.append((code, start_page))
            total = 150
            page_count = min(50, total - len(initial_stocks))
            stocks = list(initial_stocks) + [
                {"code": f"sz{code}{index:05d}", "name": f"{code}{index}"}
                for index in range(len(initial_stocks), len(initial_stocks) + page_count)
            ]
            complete = len(stocks) == total
            result = ConceptStocksFetchResult(
                "complete" if complete else "partial",
                stocks,
                total,
                start_page + 1,
            )
            on_page(result)
            return result

    monkeypatch.setattr(concepts_fetch_stocks, "EastMoneyConceptSource", FirstPageSource)
    assert concepts_fetch_stocks.main(["--reset", "-q"]) == 0
    assert calls == [("BK0001", 1), ("BK0002", 1)]
    assert not any(start == 2 for _, start in calls)

    cached = json.loads(
        (cache / "stocks" / "BK0001.json").read_text(encoding="utf-8")
    )
    assert cached["status"] == "complete"
    assert cached["stock_count"] == 50
