import os
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, Request, Query
from fastapi.responses import Response, HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware
from pydantic_settings import BaseSettings, SettingsConfigDict
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from typing import List, Optional
from pydantic import BaseModel


class Settings(BaseSettings):
    app_name: str = "Pokemon Card Price Comparator"
    debug: bool = False
    allowed_origins: List[str] = ["*"]
    redis_url: str = "redis://localhost:6379"
    rate_limit: str = "100/minute"

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


settings = Settings()

limiter = Limiter(key_func=get_remote_address, default_limits=[settings.rate_limit])


@asynccontextmanager
async def lifespan(app: FastAPI):
    print(f"Starting {settings.app_name}")
    redis_client = None
    if os.getenv("REDIS_URL"):
        try:
            import redis

            redis_client = redis.from_url(os.getenv("REDIS_URL"))
            redis_client.ping()
            app.state.redis = redis_client
            print("Redis connected")
        except Exception as e:
            print(f"Redis connection failed: {e}")
    yield
    if redis_client:
        redis_client.close()
    print("Shutting down...")


app = FastAPI(title=settings.app_name, debug=settings.debug, lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

templates = Jinja2Templates(directory="templates")

if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

from app.services.ebay import fetch_sold_listings
from app.services.pricing import calculate_market_price
from app.models.price import compute_response
from app.services.cardinfo import card_statistics, generate_price_date_plot


class CardInfoResponse(BaseModel):
    message: str
    min: float
    max: float
    mean: float
    trend: str


class SoldListing(BaseModel):
    price: float
    date: Optional[str]


class PaginationMeta(BaseModel):
    total: int
    limit: int
    offset: int
    has_more: bool


class PaginatedListingsResponse(BaseModel):
    listings: List[SoldListing]
    pagination: PaginationMeta


class PricingResponse(BaseModel):
    card_name: str
    price: str


class HistoricalPricingResponse(BaseModel):
    card_name: str
    listings: List[SoldListing]
    days_range: int
    avg_price: Optional[float]


@app.get("/", response_class=HTMLResponse)
def root():
    with open("templates/index.html", "r") as f:
        return f.read()


@app.get("/health")
def health():
    return {
        "status": "ok",
        "app": settings.app_name,
        "redis": hasattr(app.state, "redis") and app.state.redis is not None,
    }


@app.get("/CardInformationService", response_model=CardInfoResponse)
@limiter.limit(settings.rate_limit)
def card_info(
    request: Request,
    card_name: str,
    year: Optional[int] = None,
    card_set: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 25,
):
    card_name = card_name.lower()
    listings = fetch_sold_listings(
        card_name, year=year, card_set=card_set, language=language, limit=limit
    )
    if not listings:
        raise HTTPException(
            status_code=404, detail="No sold listings found for the specified card."
        )
    response = card_statistics(listings)
    return response


@app.get("/PricingService", response_model=PricingResponse)
@limiter.limit(settings.rate_limit)
def get_price(
    request: Request,
    card_name: str,
    fee: float = 1,
    year: Optional[int] = None,
    card_set: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 25,
):
    card_name = card_name.lower()
    listings = fetch_sold_listings(
        card_name, year=year, card_set=card_set, language=language, limit=limit
    )
    if not listings:
        raise HTTPException(
            status_code=404, detail="No sold listings found for the specified card."
        )
    price = calculate_market_price(listings, fee)
    response = compute_response(card_name, price)
    return response


@app.get("/pastsoldlisting", response_model=PaginatedListingsResponse)
@limiter.limit(settings.rate_limit)
def past_sold_listings(
    request: Request,
    card_name: str,
    year: Optional[int] = None,
    card_set: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 25,
    offset: int = 0,
):
    card_name = card_name.lower()
    listings = fetch_sold_listings(
        card_name, year=year, card_set=card_set, language=language, limit=limit + offset
    )
    if not listings:
        raise HTTPException(
            status_code=404, detail="No sold listings found for the specified card."
        )

    paginated = listings[offset : offset + limit]
    return {
        "listings": paginated,
        "pagination": {
            "total": len(listings),
            "limit": limit,
            "offset": offset,
            "has_more": offset + limit < len(listings),
        },
    }


@app.get("/historical", response_model=HistoricalPricingResponse)
@limiter.limit("30/minute")
def historical_pricing(
    request: Request,
    card_name: str,
    days: int = Query(
        default=90, ge=1, le=365, description="Number of days of historical data"
    ),
    year: Optional[int] = None,
    card_set: Optional[str] = None,
    language: Optional[str] = None,
):
    """Get historical pricing data for a card over a specified number of days."""
    card_name = card_name.lower()

    cutoff_date = datetime.now() - timedelta(days=days)

    listings = fetch_sold_listings(
        card_name, year=year, card_set=card_set, language=language, limit=200
    )
    if not listings:
        raise HTTPException(
            status_code=404, detail="No sold listings found for the specified card."
        )

    filtered_listings = []
    for listing in listings:
        if listing.get("date"):
            try:
                listing_date = datetime.fromisoformat(
                    listing["date"].replace("Z", "+00:00")
                )
                if listing_date >= cutoff_date:
                    filtered_listings.append(listing)
            except (ValueError, TypeError):
                filtered_listings.append(listing)

    avg_price = (
        sum(l["price"] for l in filtered_listings) / len(filtered_listings)
        if filtered_listings
        else None
    )

    return {
        "card_name": card_name,
        "listings": filtered_listings,
        "days_range": days,
        "avg_price": round(avg_price, 2) if avg_price else None,
    }


@app.get("/pricechart")
@limiter.limit(settings.rate_limit)
def price_chart(
    request: Request,
    card_name: str,
    year: Optional[int] = None,
    card_set: Optional[str] = None,
    language: Optional[str] = None,
    limit: int = 25,
):
    """Returns a PNG scatter plot of sold date vs sold price."""
    card_name_lower = card_name.lower()
    listings = fetch_sold_listings(
        card_name_lower, year=year, card_set=card_set, language=language, limit=limit
    )
    if not listings:
        raise HTTPException(
            status_code=404, detail="No sold listings found for the specified card."
        )
    image_bytes = generate_price_date_plot(listings, card_name)
    if image_bytes is None:
        raise HTTPException(
            status_code=404, detail="No date data available to generate chart."
        )
    return Response(content=image_bytes, media_type="image/png")


@app.get("/metrics")
def metrics():
    """Basic runtime metrics for debugging eBay usage."""
    from app.services import ebay

    redis_status = (
        "connected"
        if hasattr(app.state, "redis") and app.state.redis
        else "not configured"
    )
    return {
        "ebay_api_calls": ebay.api_call_count,
        "cache_hits": ebay.cache_hits,
        "cache_misses": ebay.cache_misses,
        "last_rate_limit_headers": ebay.last_rate_limit_headers,
        "redis_status": redis_status,
    }
