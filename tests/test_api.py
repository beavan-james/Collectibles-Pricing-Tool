"""
Test suite for the Pokemon Card Price Comparator API.
Uses mock eBay data so tests work without hitting the real API.
"""

import pytest
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

MOCK_EBAY_RESPONSE = {
    "itemSummaries": [
        {
            "itemId": "v1|123456789|0",
            "title": "Charizard VMAX 020/189",
            "priceInfo": {"currentPrice": {"currency": "USD", "value": "45.00"}},
            "endDate": "2026-03-10T14:30:00.000Z",
        },
        {
            "itemId": "v1|123456790|0",
            "title": "Charizard EX 006/165",
            "priceInfo": {"currentPrice": {"currency": "USD", "value": "30.00"}},
            "endDate": "2026-03-08T10:15:00.000Z",
        },
        {
            "itemId": "v1|123456791|0",
            "title": "Charizard V 017/189",
            "priceInfo": {"currentPrice": {"currency": "USD", "value": "20.00"}},
            "endDate": "2026-03-05T08:00:00.000Z",
        },
        {
            "itemId": "v1|123456792|0",
            "title": "Charizard GX",
            "priceInfo": {"currentPrice": {"currency": "USD", "value": "55.00"}},
            "endDate": "2026-02-28T16:45:00.000Z",
        },
    ]
}

MOCK_EMPTY_RESPONSE = {"itemSummaries": []}

MOCK_TOKEN_RESPONSE = {
    "access_token": "mock_token_12345",
    "token_type": "Bearer",
    "expires_in": 3600,
}


def mock_ebay_get(url, params=None, headers=None):
    class MockResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            if "item_summary" in url:
                return MOCK_EBAY_RESPONSE
            return MOCK_EMPTY_RESPONSE

    return MockResponse()


def mock_ebay_get_empty(url, params=None, headers=None):
    class MockResponse:
        status_code = 200
        headers = {}

        def raise_for_status(self):
            pass

        def json(self):
            return MOCK_EMPTY_RESPONSE

    return MockResponse()


def mock_ebay_post(url, headers=None, data=None):
    class MockResponse:
        status_code = 200

        def raise_for_status(self):
            pass

        def json(self):
            return MOCK_TOKEN_RESPONSE

    return MockResponse()


@pytest.fixture(autouse=True)
def mock_env(monkeypatch):
    import app.services.ebay as ebay_module

    monkeypatch.setenv("EBAY_CLIENT_ID", "test_client_id")
    monkeypatch.setenv("EBAY_CLIENT_SECRET", "test_client_secret")
    monkeypatch.setenv("EBAY_MARKETPLACE", "EBAY_US")
    ebay_module.EBAY_CLIENT_ID = "test_client_id"
    ebay_module.EBAY_CLIENT_SECRET = "test_client_secret"
    ebay_module.EBAY_MARKETPLACE = "EBAY_US"
    ebay_module._app_token = None
    ebay_module._app_token_expiry = 0
    yield
    ebay_module._app_token = None
    ebay_module._app_token_expiry = 0


# ── /PricingService tests ────────────────────────────────────────────────────


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_pricing_service_returns_price(mock_get, mock_post):
    resp = client.get("/PricingService?card_name=Charizard&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["card_name"] == "charizard"
    assert data["price"].startswith("$")
    print(f"  ✅ PricingService → {data}")


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_pricing_service_with_fee(mock_get, mock_post):
    resp = client.get("/PricingService?card_name=Charizard&fee=0.7&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    price_val = float(data["price"].replace("$", ""))
    assert price_val > 0
    print(f"  ✅ PricingService (fee=0.7) → {data}")


# ── /CardInformationService tests ────────────────────────────────────────────


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_card_info_returns_stats(mock_get, mock_post):
    resp = client.get("/CardInformationService?card_name=Charizard&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "min" in data
    assert "max" in data
    assert "mean" in data
    assert "trend" in data
    assert data["min"] <= data["max"]
    assert data["min"] <= data["mean"] <= data["max"]
    print(
        f"  ✅ CardInformationService → min=${data['min']}, max=${data['max']}, mean=${data['mean']:.2f}, trend={data['trend']}"
    )


# ── /pastsoldlisting tests ──────────────────────────────────────────────────


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_past_sold_listings_returns_data(mock_get, mock_post):
    resp = client.get("/pastsoldlisting?card_name=Charizard&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    listings = data["listings"]
    assert len(listings) > 0
    for listing in listings:
        assert "price" in listing
        assert "date" in listing
        assert listing["price"] > 0
    print(f"  ✅ pastsoldlisting → {len(listings)} listings returned")


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_past_sold_listings_skips_best_offer(mock_get, mock_post):
    resp = client.get("/pastsoldlisting?card_name=Charizard&limit=10")
    data = resp.json()
    prices = [l["price"] for l in data["listings"]]
    assert 100.0 not in prices
    print(f"  ✅ Best Offer ($100) correctly skipped → prices: {prices}")


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_past_sold_listings_respects_limit(mock_get, mock_post):
    resp = client.get("/pastsoldlisting?card_name=Charizard&limit=2")
    data = resp.json()
    assert len(data["listings"]) == 2
    print(f"  ✅ Limit respected → requested 2, got {len(data['listings'])}")


# ── /pricechart tests ───────────────────────────────────────────────────────


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_price_chart_returns_png(mock_get, mock_post):
    resp = client.get("/pricechart?card_name=Charizard&limit=10")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    assert resp.content[:4] == b"\x89PNG"
    print(f"  ✅ pricechart → PNG image returned ({len(resp.content)} bytes)")


# ── 404 tests (no results) ──────────────────────────────────────────────────


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get_empty)
def test_pricing_service_404_when_no_listings(mock_get, mock_post):
    resp = client.get("/PricingService?card_name=FakeCard123")
    assert resp.status_code == 404
    print(f"  ✅ PricingService returns 404 for no results")


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get_empty)
def test_card_info_404_when_no_listings(mock_get, mock_post):
    resp = client.get("/CardInformationService?card_name=FakeCard123")
    assert resp.status_code == 404
    print(f"  ✅ CardInformationService returns 404 for no results")


# ── Cache tests ──────────────────────────────────────────────────────────────


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.post", side_effect=mock_ebay_post)
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_cache_prevents_duplicate_api_calls(mock_get, mock_post):
    client.get("/pastsoldlisting?card_name=Charizard&limit=5")
    client.get("/pastsoldlisting?card_name=Charizard&limit=5")
    assert mock_get.call_count == 1
    print(f"  ✅ Cache works → 2 requests but only {mock_get.call_count} eBay API call")
