#FetchSoldListingsService.py
import os
import requests
from dotenv import load_dotenv
from cachetools import TTLCache
import base64
import time

load_dotenv()

EBAY_APP_ID = os.getenv("EBAY_APP_ID") # Need to upgrade to dev program key to get higher rate limit
EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
EBAY_MARKETPLACE = os.getenv("EBAY_MARKETPLACE", "EBAY_US")

# Cache up to 256 searches, each cached for 15 minutes
_cache = TTLCache(maxsize=256, ttl=900)

# App token cache
_app_token = None
_app_token_expiry = 0

# Simple runtime metrics
api_call_count = 0
cache_hits = 0
cache_misses = 0
last_rate_limit_headers = {}

# Search ebay for sold listings of a given card name. Get metadata including sold price and dates.
''' 
def fetch_sold_listings(card_name, year=None, card_set=None, language=None, limit=25):
    global api_call_count, cache_hits, cache_misses, last_rate_limit_headers
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
        cache_hits += 1
        cached = _cache[cache_key]
        return cached[:limit]

    cache_misses += 1

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
        api_call_count += 1
        response = requests.get(url, params=params)
        # Capture headers (rate limit info) for diagnostics
        try:
            last_rate_limit_headers = dict(response.headers)
        except Exception:
            last_rate_limit_headers = {}
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
'''


def _get_app_token():
    """Fetch and cache an OAuth app access token (client_credentials)."""
    global _app_token, _app_token_expiry
    if _app_token and time.time() < _app_token_expiry - 30:
        return _app_token
    if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
        raise RuntimeError("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET must be set in .env to use Catalog API")
    auth = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {"Content-Type": "application/x-www-form-urlencoded", "Authorization": f"Basic {auth}"}
    data = {"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope/commerce.catalog.readonly"}
    resp = requests.post(url, headers=headers, data=data)
    resp.raise_for_status()
    body = resp.json()
    token = body.get("access_token")
    expires_in = int(body.get("expires_in", 3600))
    _app_token = token
    _app_token_expiry = time.time() + expires_in
    return _app_token


def search_catalog_products(card_name, year=None, card_set=None, language=None, limit=10):
    """Search the eBay Catalog product_summary for matching products and return summaries."""
    # Build keywords
    keywords = [card_name]
    if year:
        keywords.append(str(year))
    if card_set:
        keywords.append(card_set)
    if language:
        keywords.append(language)
    q = " ".join([k for k in keywords if k])
    cache_key = f"catalog:{q.lower()}:{limit}"
    if cache_key in _cache:
        return _cache[cache_key]

    token = _get_app_token()
    url = "https://api.ebay.com/commerce/catalog/v1_beta/product_summary/search"
    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKETPLACE,
        "Content-Type": "application/json"
    }
    params = {"q": q, "limit": str(limit)}
    resp = requests.get(url, headers=headers, params=params)
    try:
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        # Return empty on errors
        return []
    data = resp.json()
    products = []
    for p in data.get("productSummaries", []):
        products.append({
            "title": p.get("title"),
            "epid": p.get("epid"),
            "brand": p.get("brand"),
            "gtin": p.get("gtin"),
            "mpn": p.get("mpn"),
            "image": p.get("image", {}).get("imageUrl"),
            "productHref": p.get("productHref"),
            "productWebUrl": p.get("productWebUrl"),
        })

    _cache[cache_key] = products
    return products

# uvicorn app.main:app --reload
# Testing: curl "http://127.0.0.1:8000/PricingService?card_name=Charizard&limit=25"