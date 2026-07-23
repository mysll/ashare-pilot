from __future__ import annotations

import os
import time
from math import ceil
from pathlib import Path

import pytest

from ashare_pilot.themes.datasource import EastMoneyConceptSource, load_cookie


LIVE_ENABLED = os.environ.get("ASHARE_LIVE_EASTMONEY") == "1"
CONCEPT_CODE = os.environ.get("ASHARE_LIVE_CONCEPT", "BK1749")
@pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="set ASHARE_LIVE_EASTMONEY=1 to run the East Money pagination probe",
)
def test_browser_shaped_concept_pagination_completes_without_rate_limit() -> None:
    """Probe a known multi-page board without reading or writing fetch checkpoints."""
    cookie = load_cookie()
    assert cookie, ".cookie does not contain EASTMONEY_COOKIE"

    page_states = []
    source = EastMoneyConceptSource(
        requests_per_minute=15,
        min_interval=3.0,
        max_interval=5.0,
        verbose=True,
    )

    def record_page(result):
        page_states.append(result)
        print(
            f"page={len(page_states)} fetched={len(result.stocks)} "
            f"total={result.total} next_page={result.next_page}",
            flush=True,
        )

    result = source.fetch_concept_stocks(CONCEPT_CODE, on_page=record_page)

    assert result.status == "complete", result.error
    assert result.total is not None and result.total > 50
    assert len(result.stocks) == result.total
    assert len({stock["code"] for stock in result.stocks}) == result.total
    assert len(page_states) == ceil(result.total / 50)


@pytest.mark.skipif(
    not LIVE_ENABLED,
    reason="set ASHARE_LIVE_EASTMONEY=1 to run the East Money board-list probe",
)
def test_browser_shaped_concept_board_list_matches_full_catalog(
    tmp_path: Path,
) -> None:
    cookie = load_cookie()
    assert cookie, ".cookie does not contain EASTMONEY_COOKIE"

    source = EastMoneyConceptSource(
        requests_per_minute=15,
        min_interval=3.0,
        max_interval=5.0,
        verbose=True,
        state_dir=tmp_path,
    )
    concepts = None
    for attempt in range(1, 4):
        try:
            concepts = source.fetch_concept_sectors(resume=True)
            break
        except RuntimeError as exc:
            print(f"attempt={attempt} interrupted: {exc}", flush=True)
            if attempt == 3:
                raise
            time.sleep(5)

    assert concepts is not None
    assert len(concepts) > 400
    assert len({concept["code"] for concept in concepts}) == len(concepts)
    assert all(concept["code"].startswith("BK") for concept in concepts)
    assert all(concept["name"] for concept in concepts)
