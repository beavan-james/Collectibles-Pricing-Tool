from fastapi import FastAPI, HTTPException
from fastapi.responses import Response
from typing import List, Optional
from pydantic import BaseModel
from app.services.ebay import fetch_sold_listings
from app.services.pricing import calculate_market_price
from app.models.price import compute_response
from app.services.cardinfo import card_statistics, generate_price_date_plot

app = FastAPI(title="Pokemon Card Price Comparator")

#For API test use /#Docs endpoint

class CardInfoResponse(BaseModel):
    message: str
    min: float
    max: float
    mean: float
    trend: str

class SoldListing(BaseModel):
    price: float
    date: Optional[str]

class PastSoldListingsResponse(BaseModel):
    listings: List[SoldListing]

class PricingResponse(BaseModel):
    card_name: str
    price: str

@app.get("/CardInformationService", response_model=CardInfoResponse)
def card_info(card_name: str, year: Optional[int] = None, card_set: Optional[str] = None, language: Optional[str] = None, limit: int = 25):
    card_name = card_name.lower()
    listings = fetch_sold_listings(card_name, year=year, card_set=card_set, language=language, limit=limit)
    if not listings:
         raise HTTPException(status_code=404, detail="No sold listings found for the specified card.")
    response = card_statistics(listings)
    return response

@app.get("/PricingService", response_model=PricingResponse)
def get_price(card_name: str, fee: float = 1, year: Optional[int] = None, card_set: Optional[str] = None, language: Optional[str] = None, limit: int = 25):
    card_name = card_name.lower()
    listings = fetch_sold_listings(card_name, year=year, card_set=card_set, language=language, limit=limit)
    if not listings:
         raise HTTPException(status_code=404, detail="No sold listings found for the specified card.")
    price = calculate_market_price(listings, fee)
    response = compute_response(card_name, price)
    return response

@app.get("/pastsoldlisting", response_model=PastSoldListingsResponse)
def past_sold_listings(card_name: str, year: Optional[int] = None, card_set: Optional[str] = None, language: Optional[str] = None, limit: int = 25):
    card_name = card_name.lower()
    listings = fetch_sold_listings(card_name, year=year, card_set=card_set, language=language, limit=limit)
    if not listings:
         raise HTTPException(status_code=404, detail="No sold listings found for the specified card.")
    return {"listings": listings}

@app.get("/pricechart")
def price_chart(card_name: str, year: Optional[int] = None, card_set: Optional[str] = None, language: Optional[str] = None, limit: int = 25):
    """Returns a PNG scatter plot of sold date vs sold price."""
    card_name_lower = card_name.lower()
    listings = fetch_sold_listings(card_name_lower, year=year, card_set=card_set, language=language, limit=limit)
    if not listings:
         raise HTTPException(status_code=404, detail="No sold listings found for the specified card.")
    image_bytes = generate_price_date_plot(listings, card_name)
    if image_bytes is None:
         raise HTTPException(status_code=404, detail="No date data available to generate chart.")
    return Response(content=image_bytes, media_type="image/png")

@app.get("/metrics")
def metrics():
    """Basic runtime metrics for debugging eBay usage."""
    from app.services import ebay
    return {
        "ebay_api_calls": ebay.api_call_count,
        "cache_hits": ebay.cache_hits,
        "cache_misses": ebay.cache_misses,
        "last_rate_limit_headers": ebay.last_rate_limit_headers,
    }