"""
Test suite for the Pokemon Card Price Comparator API.
Uses mock eBay data so tests work without hitting the real API.
"""
import pytest
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

# ── Mock eBay data ───────────────────────────────────────────────────────────
MOCK_EBAY_RESPONSE = {
    "findCompletedItemsResponse": [{
        "searchResult": [{
            "item": [
                {
                    "title": ["Charizard VMAX 020/189"],
                    "sellingStatus": [{
                        "currentPrice": [{"__value__": "45.00"}],
                        "sellingState": ["EndedWithSales"]
                    }],
                    "listingInfo": [{
                        "endTime": ["2026-03-10T14:30:00.000Z"]
                    }]
                },
                {
                    "title": ["Charizard EX 006/165"],
                    "sellingStatus": [{
                        "currentPrice": [{"__value__": "30.00"}],
                        "sellingState": ["EndedWithSales"]
                    }],
                    "listingInfo": [{
                        "endTime": ["2026-03-08T10:15:00.000Z"]
                    }]
                },
                {
                    "title": ["Charizard V 017/189"],
                    "sellingStatus": [{
                        "currentPrice": [{"__value__": "20.00"}],
                        "sellingState": ["EndedWithSales"]
                    }],
                    "listingInfo": [{
                        "endTime": ["2026-03-05T08:00:00.000Z"]
                    }]
                },
                {
                    "title": ["Charizard GX Best Offer"],
                    "sellingStatus": [{
                        "currentPrice": [{"__value__": "100.00"}],
                        "sellingState": ["EndedWithBestOffer"]
                    }],
                    "listingInfo": [{
                        "endTime": ["2026-03-01T12:00:00.000Z"]
                    }]
                },
                {
                    "title": ["Charizard Base Set"],
                    "sellingStatus": [{
                        "currentPrice": [{"__value__": "55.00"}],
                        "sellingState": ["EndedWithSales"]
                    }],
                    "listingInfo": [{
                        "endTime": ["2026-02-28T16:45:00.000Z"]
                    }]
                },
            ]
        }]
    }]
}

MOCK_EMPTY_RESPONSE = {
    "findCompletedItemsResponse": [{
        "searchResult": [{
            "item": []
        }]
    }]
}


def mock_ebay_get(url, params=None):
    """Mock requests.get to return fake eBay data."""
    class MockResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return MOCK_EBAY_RESPONSE
    return MockResponse()


def mock_ebay_get_empty(url, params=None):
    """Mock requests.get to return empty eBay data."""
    class MockResponse:
        status_code = 200
        def raise_for_status(self):
            pass
        def json(self):
            return MOCK_EMPTY_RESPONSE
    return MockResponse()


# ── /PricingService tests ────────────────────────────────────────────────────

@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_pricing_service_returns_price(mock_get):
    resp = client.get("/PricingService?card_name=Charizard&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert data["card_name"] == "charizard"
    assert data["price"].startswith("$")
    print(f"  ✅ PricingService → {data}")


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_pricing_service_with_fee(mock_get):
    resp = client.get("/PricingService?card_name=Charizard&fee=0.7&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    # With fee=0.7, price should be less than full price
    price_val = float(data["price"].replace("$", ""))
    assert price_val > 0
    print(f"  ✅ PricingService (fee=0.7) → {data}")


# ── /CardInformationService tests ────────────────────────────────────────────

@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_card_info_returns_stats(mock_get):
    resp = client.get("/CardInformationService?card_name=Charizard&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    assert "min" in data
    assert "max" in data
    assert "mean" in data
    assert "trend" in data
    assert data["min"] <= data["max"]
    assert data["min"] <= data["mean"] <= data["max"]
    print(f"  ✅ CardInformationService → min=${data['min']}, max=${data['max']}, mean=${data['mean']:.2f}, trend={data['trend']}")


# ── /pastsoldlisting tests ──────────────────────────────────────────────────

@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_past_sold_listings_returns_data(mock_get):
    resp = client.get("/pastsoldlisting?card_name=Charizard&limit=10")
    assert resp.status_code == 200
    data = resp.json()
    listings = data["listings"]
    assert len(listings) > 0
    # Each listing should have price and date
    for listing in listings:
        assert "price" in listing
        assert "date" in listing
        assert listing["price"] > 0
    print(f"  ✅ pastsoldlisting → {len(listings)} listings returned")


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_past_sold_listings_skips_best_offer(mock_get):
    resp = client.get("/pastsoldlisting?card_name=Charizard&limit=10")
    data = resp.json()
    prices = [l["price"] for l in data["listings"]]
    # The $100 Best Offer listing should NOT be in results
    assert 100.0 not in prices
    print(f"  ✅ Best Offer ($100) correctly skipped → prices: {prices}")


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_past_sold_listings_respects_limit(mock_get):
    resp = client.get("/pastsoldlisting?card_name=Charizard&limit=2")
    data = resp.json()
    assert len(data["listings"]) == 2
    print(f"  ✅ Limit respected → requested 2, got {len(data['listings'])}")


# ── /pricechart tests ───────────────────────────────────────────────────────

@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_price_chart_returns_png(mock_get):
    resp = client.get("/pricechart?card_name=Charizard&limit=10")
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "image/png"
    # PNG files start with these magic bytes
    assert resp.content[:4] == b'\x89PNG'
    print(f"  ✅ pricechart → PNG image returned ({len(resp.content)} bytes)")


# ── 404 tests (no results) ──────────────────────────────────────────────────

@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get_empty)
def test_pricing_service_404_when_no_listings(mock_get):
    resp = client.get("/PricingService?card_name=FakeCard123")
    assert resp.status_code == 404
    print(f"  ✅ PricingService returns 404 for no results")


@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get_empty)
def test_card_info_404_when_no_listings(mock_get):
    resp = client.get("/CardInformationService?card_name=FakeCard123")
    assert resp.status_code == 404
    print(f"  ✅ CardInformationService returns 404 for no results")


# ── Cache tests ──────────────────────────────────────────────────────────────

@patch("app.services.ebay._cache", {})
@patch("app.services.ebay.requests.get", side_effect=mock_ebay_get)
def test_cache_prevents_duplicate_api_calls(mock_get):
    # First call hits the API
    client.get("/pastsoldlisting?card_name=Charizard&limit=5")
    # Second call should use cache
    client.get("/pastsoldlisting?card_name=Charizard&limit=3")
    # eBay API should only be called once
    assert mock_get.call_count == 1
    print(f"  ✅ Cache works → 2 requests but only {mock_get.call_count} eBay API call")
