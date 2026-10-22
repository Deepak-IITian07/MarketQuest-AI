"""Tests for the sample market data loader."""

from datetime import date
from pathlib import Path

import pytest

from app.services import market_data
from app.services.market_data import (
    DataValidationError,
    SymbolNotFoundError,
    get_latest_price,
    get_latest_prices,
    get_price_history,
    get_symbols,
    load_price_bars,
    normalize_symbol,
)

FIXTURES = Path(__file__).parent / "fixtures"
TINY_DATASET = FIXTURES / "tiny_dataset.csv"
INVALID_DATASET = FIXTURES / "invalid_dataset.csv"
MISSING_COLUMNS_DATASET = FIXTURES / "missing_columns.csv"
DUPLICATE_DATASET = FIXTURES / "duplicate_dataset.csv"


def test_load_price_bars_reads_every_row_of_the_sample_dataset():
    bars = load_price_bars()
    assert len(bars) == 120
    assert {bar.symbol for bar in bars} == {
        "DEMOBANK",
        "DEMOENERGY",
        "DEMOPHARMA",
        "DEMOTECH",
    }


def test_load_price_bars_keeps_ohlcv_values_intact():
    bar = next(
        bar
        for bar in load_price_bars()
        if bar.symbol == "DEMOBANK" and bar.date == date(2026, 9, 7)
    )
    assert bar.open == 858.88
    assert bar.high == 866.64
    assert bar.low == 846.57
    assert bar.close == 854.10
    assert bar.volume == 360237


def test_get_symbols_is_sorted_and_upper_case():
    symbols = get_symbols()
    assert symbols == sorted(symbols)
    assert all(symbol.isupper() for symbol in symbols)
    assert "DEMOTECH" in symbols


def test_get_price_history_is_ordered_oldest_first():
    history = get_price_history("DEMOTECH")
    assert len(history) == 30
    assert [bar.date for bar in history] == sorted(bar.date for bar in history)
    assert history[0].date == date(2026, 9, 7)


def test_get_price_history_accepts_lowercase_symbol():
    history = get_price_history("demotech")
    assert history[0].symbol == "DEMOTECH"


def test_get_price_history_raises_for_unknown_symbol():
    with pytest.raises(SymbolNotFoundError) as excinfo:
        get_price_history("NOPE")
    assert "NOPE" in str(excinfo.value)
    assert excinfo.value.available


def test_get_latest_price_returns_the_most_recent_bar():
    latest = get_latest_price("DEMOTECH")
    assert latest == get_price_history("DEMOTECH")[-1]
    assert latest.date == max(bar.date for bar in get_price_history("DEMOTECH"))


def test_get_latest_prices_covers_every_symbol():
    latest = get_latest_prices()
    assert set(latest) == set(get_symbols())
    assert all(bar.close > 0 for bar in latest.values())


def test_normalize_symbol_trims_and_upper_cases():
    assert normalize_symbol("  demotech ") == "DEMOTECH"


def test_load_price_bars_rejects_a_file_that_does_not_exist(tmp_path):
    with pytest.raises(DataValidationError, match="not found"):
        load_price_bars(tmp_path / "nope.csv")


def test_load_price_bars_rejects_an_inconsistent_ohlc_row():
    with pytest.raises(DataValidationError, match="high"):
        load_price_bars(INVALID_DATASET)


def test_load_price_bars_rejects_a_file_with_missing_columns():
    with pytest.raises(DataValidationError, match="missing required column"):
        load_price_bars(MISSING_COLUMNS_DATASET)


def test_load_price_bars_rejects_duplicate_observations():
    with pytest.raises(DataValidationError, match="duplicate observation"):
        load_price_bars(DUPLICATE_DATASET)


def test_load_price_bars_rejects_a_file_with_no_rows(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text("date,symbol,open,high,low,close,volume\n", encoding="utf-8")
    with pytest.raises(DataValidationError, match="no price rows"):
        load_price_bars(empty)


def test_load_price_bars_rejects_a_non_numeric_price(tmp_path):
    broken = tmp_path / "broken.csv"
    broken.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-05,BAD,not-a-number,105.00,99.00,104.00,10\n",
        encoding="utf-8",
    )
    with pytest.raises(DataValidationError, match="not a number"):
        load_price_bars(broken)


def test_tiny_dataset_loads_and_has_one_symbol():
    bars = load_price_bars(TINY_DATASET)
    assert len(bars) == 3
    assert get_symbols(TINY_DATASET) == ["TINY"]
    with pytest.raises(SymbolNotFoundError):
        get_price_history("DEMOTECH", TINY_DATASET)


def test_clear_cache_drops_the_loaded_dataset():
    market_data.clear_cache()
    assert len(load_price_bars()) == 120
    market_data.clear_cache()
