"""Tests for the market data and analysis HTTP endpoints."""

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.core.config import get_settings
from app.services import market_data
from main import app

client = TestClient(app)

FIXTURES = Path(__file__).parent / "fixtures"
TINY_DATASET = FIXTURES / "tiny_dataset.csv"


@pytest.fixture()
def tiny_dataset(monkeypatch: pytest.MonkeyPatch):
    """Point the market data service at a 3-row dataset for the duration of a test."""
    settings = get_settings().model_copy(
        update={
            "data_dir": str(TINY_DATASET.parent),
            "sample_prices_file": TINY_DATASET.name,
        }
    )
    monkeypatch.setattr(market_data, "get_settings", lambda: settings)
    market_data.clear_cache()
    yield TINY_DATASET
    market_data.clear_cache()


def test_health_endpoint_still_works():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"


def test_symbols_endpoint_lists_symbols_with_latest_prices():
    response = client.get("/market/symbols")
    assert response.status_code == 200
    body = response.json()

    assert body["data_source"] == "synthetic_demo"
    assert body["count"] == 4
    symbols = {entry["symbol"]: entry for entry in body["symbols"]}
    assert set(symbols) == {"DEMOBANK", "DEMOENERGY", "DEMOPHARMA", "DEMOTECH"}
    assert symbols["DEMOTECH"]["observations"] == 30
    assert symbols["DEMOTECH"]["latest_close"] > 0
    assert symbols["DEMOTECH"]["latest_date"] == "2026-10-16"


def test_prices_endpoint_returns_the_full_history():
    response = client.get("/market/prices/DEMOTECH")
    assert response.status_code == 200
    body = response.json()

    assert body["symbol"] == "DEMOTECH"
    assert body["count"] == 30
    assert body["currency"] == "INR"
    assert body["data_source"] == "synthetic_demo"

    first = body["prices"][0]
    assert first["date"] == "2026-09-07"
    assert set(first) == {"date", "open", "high", "low", "close", "volume"}


def test_prices_endpoint_is_case_insensitive():
    assert client.get("/market/prices/demotech").status_code == 200


def test_prices_endpoint_returns_404_for_an_unknown_symbol():
    response = client.get("/market/prices/NOTLISTED")
    assert response.status_code == 404
    assert "NOTLISTED" in response.json()["detail"]


def test_returns_endpoint_returns_one_return_per_price_pair():
    response = client.get("/market/returns/DEMOTECH")
    assert response.status_code == 200
    body = response.json()

    assert body["symbol"] == "DEMOTECH"
    assert body["count"] == 29
    assert body["returns"][0]["date"] == "2026-09-08"
    assert isinstance(body["returns"][0]["return_pct"], float)


def test_returns_endpoint_returns_404_for_an_unknown_symbol():
    assert client.get("/market/returns/NOTLISTED").status_code == 404


def test_analysis_endpoint_returns_a_summary():
    response = client.get("/market/analysis/DEMOTECH")
    assert response.status_code == 200
    body = response.json()

    assert body["symbol"] == "DEMOTECH"
    assert body["observations"] == 30
    assert body["sma_window"] == 20
    assert body["sma"] > 0
    assert body["volatility"]["window"] == 20
    assert body["volatility"]["observations"] == 20
    assert body["volatility"]["annualization_factor"] == 252
    assert body["volatility"]["annualized_volatility"] > 0
    assert body["data_source"] == "synthetic_demo"


def test_analysis_endpoint_honours_a_custom_sma_window():
    response = client.get("/market/analysis/DEMOTECH?sma_window=5&volatility_window=10")
    assert response.status_code == 200
    body = response.json()
    assert body["sma_window"] == 5
    assert body["volatility"]["window"] == 10
    assert body["volatility"]["observations"] == 10


def test_analysis_endpoint_rejects_a_window_below_one():
    response = client.get("/market/analysis/DEMOTECH?sma_window=0")
    assert response.status_code == 422


def test_analysis_endpoint_rejects_a_non_numeric_window():
    response = client.get("/market/analysis/DEMOTECH?sma_window=abc")
    assert response.status_code == 422


def test_analysis_endpoint_rejects_a_volatility_window_below_two():
    response = client.get("/market/analysis/DEMOTECH?volatility_window=1")
    assert response.status_code == 422


def test_analysis_endpoint_returns_404_for_an_unknown_symbol():
    assert client.get("/market/analysis/NOTLISTED").status_code == 404


def test_analysis_endpoint_returns_400_when_the_window_exceeds_the_sample(tiny_dataset):
    response = client.get("/market/analysis/TINY")
    assert response.status_code == 400
    detail = response.json()["detail"]
    assert "20" in detail
    assert "3" in detail


def test_analysis_endpoint_succeeds_when_the_window_fits_the_sample(tiny_dataset):
    response = client.get("/market/analysis/TINY?sma_window=3&volatility_window=2")
    assert response.status_code == 200
    body = response.json()
    assert body["symbol"] == "TINY"
    assert body["observations"] == 3
    assert body["sma"] == pytest.approx((104.0 + 102.0 + 108.0) / 3)
    assert body["volatility"]["observations"] == 2


def test_returns_endpoint_returns_400_when_there_are_too_few_prices(tiny_dataset):
    response = client.get("/market/returns/TINY")
    assert response.status_code == 200
    assert response.json()["count"] == 2
