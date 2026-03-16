#FetchSoldListingsService.py
import os
import requests
from dotenv import load_dotenv
from cachetools import TTLCache

load_dotenv()

EBAY_APP_ID = os.getenv("EBAY_APP_ID")

# Cache up to 256 searches, each cached for 15 minutes
_cache = TTLCache(maxsize=256, ttl=900)

# Search ebay for sold listings of a given card name. Get metadata including sold price and dates.


def fetch_sold_listings(card_name, year=None, card_set=None, language=None, limit=25):
    # Build keywords by combining all provided search terms
    keywords = [card_name]
    if year:
        keywords.append(str(year))
    if card_set:
        keywords.append(card_set)
    if language:
        keywords.append(language)

    # Build a cache key from the search parameters
    cache_key = " ".join(keywords).lower()

    # Return cached results if available (slice to requested limit)
    if cache_key in _cache:
        cached = _cache[cache_key]
        return cached[:limit]

    url = "https://svcs.ebay.com/services/search/FindingService/v1"
    headers = {"X-EBAY-SOA-OPERATION-NAME": "findCompletedItems"}
    params = {
        "OPERATION-NAME": "findCompletedItems",
        "SERVICE-VERSION": "1.0.0",
        "SECURITY-APPNAME": EBAY_APP_ID,
        "RESPONSE-DATA-FORMAT": "JSON",
        "keywords": " ".join(keywords),
        "itemFilter(0).name": "SoldItemsOnly",
        "itemFilter(0).value": "true",
        "paginationInput.entriesPerPage": "100"
    }

    try:
        response = requests.get(url, params=params)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"eBay API request failed: {e}")
        return []
    
    soldlistings = []
    
    # Parse eBay Finding API JSON response
    try:
        search_result = data.get('findCompletedItemsResponse', [{}])[0].get('searchResult', [{}])[0]
        items = search_result.get('item', [])
        for item in items:
            selling_status = item.get('sellingStatus', [{}])[0]
            # Skip Best Offer listings — the actual sold price is unknown
            selling_state = selling_status.get('sellingState', [None])[0]
            if selling_state == "EndedWithBestOffer":
                continue
            price_str = selling_status.get('currentPrice', [{}])[0].get('__value__')
            end_time = item.get('listingInfo', [{}])[0].get('endTime', [None])[0]
            if price_str:
                soldlistings.append({
                    "price": float(price_str),
                    "date": end_time 
                })
    except (IndexError, ValueError, KeyError):
        pass 

    # Cache all results (up to 100 from eBay) so different limit values reuse the same cache entry
    _cache[cache_key] = soldlistings

    return soldlistings[:limit]


# uvicorn app.main:app --reload
# Testing: curl "http://127.0.0.1:8000/PricingService?card_name=Charizard&limit=25"