"""Tests for the analysis service functions."""

import math

import pytest

from app.services.analysis import (
    AnalysisError,
    InsufficientDataError,
    InvalidWindowError,
    daily_returns,
    historical_volatility,
    simple_moving_average,
    total_return_pct,
)

CLOSES = [100.0, 110.0, 99.0, 121.0]


def test_daily_returns_computes_simple_percentage_changes():
    returns = daily_returns(CLOSES)
    assert len(returns) == len(CLOSES) - 1
    assert returns[0] == pytest.approx(0.10)
    assert returns[1] == pytest.approx(-0.10)
    assert returns[2] == pytest.approx(121.0 / 99.0 - 1)


def test_daily_returns_raises_when_there_is_only_one_price():
    with pytest.raises(InsufficientDataError, match="at least 2"):
        daily_returns([100.0])


def test_daily_returns_raises_on_a_zero_previous_close():
    with pytest.raises(AnalysisError, match="closing price of 0"):
        daily_returns([0.0, 10.0])


def test_simple_moving_average_averages_the_most_recent_window():
    assert simple_moving_average(CLOSES, 2) == pytest.approx((99.0 + 121.0) / 2)
    assert simple_moving_average(CLOSES, 4) == pytest.approx(sum(CLOSES) / 4)


def test_simple_moving_average_uses_only_the_trailing_window():
    assert simple_moving_average([1.0, 1.0, 1.0, 10.0], 1) == pytest.approx(10.0)


def test_simple_moving_average_rejects_a_window_below_one():
    with pytest.raises(InvalidWindowError, match="at least 1"):
        simple_moving_average(CLOSES, 0)


def test_simple_moving_average_rejects_an_insufficient_window():
    with pytest.raises(InsufficientDataError, match="needs 5 observations"):
        simple_moving_average(CLOSES, 5)


def test_historical_volatility_reports_daily_and_annualized_figures():
    result = historical_volatility(CLOSES, 3)
    assert result.window == 3
    assert result.observations == 3
    assert result.annualization_factor == 252

    expected_daily = math.sqrt(
        sum(
            (value - sum(daily_returns(CLOSES)) / 3) ** 2
            for value in daily_returns(CLOSES)
        )
        / 2
    )
    assert result.daily_volatility == pytest.approx(expected_daily)
    assert result.annualized_volatility == pytest.approx(
        expected_daily * math.sqrt(252)
    )


def test_historical_volatility_rejects_a_window_below_two():
    with pytest.raises(InvalidWindowError, match="at least 2"):
        historical_volatility(CLOSES, 1)


def test_historical_volatility_rejects_an_insufficient_window():
    with pytest.raises(InsufficientDataError, match="needs 5 daily returns"):
        historical_volatility(CLOSES, 5)


def test_total_return_pct_is_measured_from_first_to_last_close():
    assert total_return_pct([100.0, 125.0]) == pytest.approx(25.0)
    assert total_return_pct([100.0, 80.0]) == pytest.approx(-20.0)


def test_total_return_pct_needs_two_prices():
    with pytest.raises(InsufficientDataError, match="at least 2"):
        total_return_pct([100.0])
