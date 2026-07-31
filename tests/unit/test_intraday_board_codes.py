"""Canonical market-prefix handling for intraday stock records."""

from ashare_pilot.mapping._commands.intraday.scan_pool import (
    apply_board_filter,
)
from ashare_pilot.market_data._datasources.intraday import (
    EastMoneyIntradayDataSource,
)


def sina_item(symbol: str, change_pct: str = "9.72") -> dict:
    return {
        "symbol": symbol,
        "name": "样本",
        "trade": "10.00",
        "changepercent": change_pct,
        "pricechange": "0.88",
        "volume": "100",
        "amount": "1000",
        "amplitude": "1.0",
        "turnoverratio": "2.0",
        "high": "10.10",
        "low": "9.80",
        "open": "9.90",
        "settlement": "9.12",
        "mktcap": "10",
        "nmc": "8",
    }


def test_sina_bse_92_code_keeps_bj_prefix_and_board():
    source = EastMoneyIntradayDataSource()
    record = source._sina_to_stock_rec(sina_item("bj920284"))
    formatted = source._format_stock_item(record, include_board=True)

    assert record["market"] == 2
    assert formatted["code"] == "bj920284"
    assert formatted["board"] == "北交所"


def test_legacy_cached_92_row_is_normalized_to_bj():
    source = EastMoneyIntradayDataSource()
    legacy = source._sina_to_stock_rec(sina_item("sz920193"))

    assert legacy["market"] == 0
    assert source._to_full_code(legacy["code"], legacy["market"]) == "bj920193"
    assert source._classify_stock(legacy["code"], legacy["market"]) == "北交所"


def test_bse_92_uses_30_percent_limit_threshold():
    source = EastMoneyIntradayDataSource()

    assert source._is_limit_up(9.72, source._classify_stock("920284", 2)) is False
    assert source._is_limit_up(30.0, source._classify_stock("920284", 2)) is True


def test_normalized_bse_code_is_excluded_by_existing_scope_rule():
    source = EastMoneyIntradayDataSource()
    record = source._sina_to_stock_rec(sina_item("bj920284"))
    stock = source._format_stock_item(record)

    kept, removed = apply_board_filter([stock], {"bj", "sh688"})

    assert kept == []
    assert [item["code"] for item in removed] == ["bj920284"]


def test_shanghai_and_shenzhen_prefixes_are_unchanged():
    source = EastMoneyIntradayDataSource()

    assert source._to_full_code("600519", 1) == "sh600519"
    assert source._to_full_code("000001", 0) == "sz000001"
    assert source._classify_stock("688981", 1) == "科创板"
    assert source._classify_stock("300750", 0) == "创业板"
    assert source._classify_stock("301171", 0) == "创业板"
