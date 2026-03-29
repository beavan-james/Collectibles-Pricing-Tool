import os
import requests
from dotenv import load_dotenv
from cachetools import TTLCache
import base64
import time
from urllib.parse import urlencode

load_dotenv()

EBAY_CLIENT_ID = os.getenv("EBAY_CLIENT_ID")
EBAY_CLIENT_SECRET = os.getenv("EBAY_CLIENT_SECRET")
EBAY_MARKETPLACE = os.getenv("EBAY_MARKETPLACE", "EBAY_US")

_cache = TTLCache(maxsize=256, ttl=900)

_app_token = None
_app_token_expiry = 0

api_call_count = 0
cache_hits = 0
cache_misses = 0
last_rate_limit_headers = {}


def _get_app_token():
    global _app_token, _app_token_expiry
    if _app_token and time.time() < _app_token_expiry - 30:
        return _app_token
    if not EBAY_CLIENT_ID or not EBAY_CLIENT_SECRET:
        raise RuntimeError("EBAY_CLIENT_ID and EBAY_CLIENT_SECRET must be set in .env")
    auth = base64.b64encode(f"{EBAY_CLIENT_ID}:{EBAY_CLIENT_SECRET}".encode()).decode()
    url = "https://api.ebay.com/identity/v1/oauth2/token"
    headers = {
        "Content-Type": "application/x-www-form-urlencoded",
        "Authorization": f"Basic {auth}",
    }
    data = {
        "grant_type": "client_credentials",
        "scope": "https://api.ebay.com/oauth/api_scope",
    }
    resp = requests.post(url, headers=headers, data=data)
    resp.raise_for_status()
    body = resp.json()
    _app_token = body.get("access_token")
    _app_token_expiry = time.time() + int(body.get("expires_in", 3600))
    return _app_token


def fetch_sold_listings(card_name, year=None, card_set=None, language=None, limit=25):
    global api_call_count, cache_hits, cache_misses, last_rate_limit_headers

    keywords = [card_name]
    if year:
        keywords.append(str(year))
    if card_set:
        keywords.append(card_set)
    if language:
        keywords.append(language)
    q = " ".join([k for k in keywords if k])
    cache_key = f"sold:{q.lower()}:{limit}"
    if cache_key in _cache:
        cache_hits += 1
        return _cache[cache_key][:limit]

    cache_misses += 1
    api_call_count += 1

    token = _get_app_token()
    url = "https://api.ebay.com/buy/browse/v1/item_summary/search"

    filter_str = f"itemLocationCountryCode:[AE,AT,AU,BE,BG,CA,CH,CL,CZ,DE,DK,ES,FI,FR,GB,GR,HK,HU,ID,IE,IL,IN,IT,JP,KR,LI,LU,MY,MX,NL,NZ,PH,PL,PT,RU,SE,SG,TH,TW,US,VN,ZA],sort:endingSoonest"

    headers = {
        "Authorization": f"Bearer {token}",
        "X-EBAY-C-MARKETPLACE-ID": EBAY_MARKETPLACE,
    }
    params = {"q": q, "filter": filter_str, "limit": str(limit)}

    try:
        resp = requests.get(url, headers=headers, params=params)
        try:
            last_rate_limit_headers = dict(resp.headers)
        except Exception:
            last_rate_limit_headers = {}
        resp.raise_for_status()
        data = resp.json()
    except requests.exceptions.RequestException as e:
        print(f"eBay API request failed: {e}")
        return []

    soldlistings = []
    for item in data.get("itemSummaries", []):
        price_obj = item.get("price", {})
        if isinstance(price_obj, dict):
            price_val = price_obj.get("value")
        else:
            price_val = item.get("price")

        if price_val:
            try:
                soldlistings.append(
                    {
                        "price": float(price_val),
                        "date": item.get(
                            "itemCreationDate", item.get("itemOriginDate", "")
                        ),
                    }
                )
            except (ValueError, TypeError):
                continue

    soldlistings.sort(key=lambda x: x["price"], reverse=True)
    _cache[cache_key] = soldlistings
    return soldlistings[:limit]


def search_catalog_products(
    card_name, year=None, card_set=None, language=None, limit=10
):
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
        "Content-Type": "application/json",
    }
    params = {"q": q, "limit": str(limit)}
    resp = requests.get(url, headers=headers, params=params)
    try:
        resp.raise_for_status()
    except requests.exceptions.RequestException:
        return []
    data = resp.json()
    products = []
    for p in data.get("productSummaries", []):
        products.append(
            {
                "title": p.get("title"),
                "epid": p.get("epid"),
                "brand": p.get("brand"),
                "gtin": p.get("gtin"),
                "mpn": p.get("mpn"),
                "image": p.get("image", {}).get("imageUrl"),
                "productHref": p.get("productHref"),
                "productWebUrl": p.get("productWebUrl"),
            }
        )

    _cache[cache_key] = products
    return products
