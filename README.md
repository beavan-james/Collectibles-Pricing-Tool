# 🃏 Pokemon Card Price Comparator

A lightweight FastAPI service that pulls real-time sold listing data from eBay to help you make smarter buying and selling decisions on Pokémon cards.

> **Why?** Manually looking up comps on eBay is tedious. This tool automates it — giving you stats, suggested prices, and visual trends in seconds.

## Features

- **Market pricing** — calculates a suggested buy/sell price based on recent sold comps
- **Card statistics** — min, max, mean prices and market trend (Stable / Falling)
- **Raw sold listings** — returns individual sold prices with dates
- **Price chart** — generates a scatter plot (PNG) of sold price vs. date with a trend line
- **Flexible search** — filter by card name, year, set, and language
- **Best Offer filtering** — automatically skips listings where the actual sold price is unknown
- **Pagination** — paginated results for large datasets
- **Historical data** — query pricing trends over configurable time ranges (1-365 days)
- **Rate limiting** — protects API from abuse (100 req/min default)
- **Redis caching** — optional distributed cache for multi-instance deployments
- **Web UI** — user-friendly interface at `/`
- **Docker support** — one-command deployment with Redis

## Quick Start

### 1. Clone & install

```bash
git clone <your-repo-url>
cd PokemonCompCalculator
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```bash
# eBay OAuth credentials
EBAY_CLIENT_ID=your_client_id
EBAY_CLIENT_SECRET=your_client_secret
EBAY_MARKETPLACE=EBAY_US

# Optional: Redis for distributed caching
REDIS_URL=redis://localhost:6379

# Optional: Rate limit (default: 100/minute)
APP_RATE_LIMIT=100/minute
```

> Get eBay OAuth credentials by registering at the [eBay Developer Program](https://developer.ebay.com/).

### 3. Run the server

```bash
uvicorn app.main:app --reload
```

The API will be available at `http://127.0.0.1:8000`. Interactive docs are at [`/docs`](http://127.0.0.1:8000/docs). Web UI is at [`http://127.0.0.1:8000/`](http://127.0.0.1:8000/).

### Docker Deployment

```bash
docker-compose up -d
```

This starts both the API and Redis containers.

## API Endpoints

### `GET /PricingService`

Returns a suggested market price for a card.

| Parameter   | Type    | Default     | Description                                                         |
|-------------|---------|-------------|---------------------------------------------------------------------|
| `card_name` | string  | *required*  | Card name to search for                                             |
| `fee`       | float   | `1`         | Price multiplier (e.g. `0.7` = 70% of suggested price)             |
| `year`      | int     | —           | Filter by year                                                      |
| `card_set`  | string  | —           | Filter by set (e.g. `Obsidian Flames`)                              |
| `language`  | string  | `English`   | Filter by language (e.g. `Japanese`)                                |
| `limit`     | int     | `25`        | Number of sold listings to base the calculation on                  |

```bash
curl "http://127.0.0.1:8000/PricingService?card_name=Charizard&fee=0.7&limit=25"
```

```json
{ "card_name": "charizard", "price": "$12.35" }
```

### `GET /CardInformationService`

Returns price statistics and market trend.

```bash
curl "http://127.0.0.1:8000/CardInformationService?card_name=Pikachu&card_set=Base+Set&limit=10"
```

```json
{ "message": "Statistics calculated", "min": 2.5, "max": 45.0, "mean": 18.75, "trend": "Stable" }
```

### `GET /pastsoldlisting`

Returns paginated raw sold listing data (price + date).

| Parameter   | Type    | Default | Description                              |
|------------|---------|---------|------------------------------------------|
| `card_name`| string  | *required* | Card name to search for              |
| `limit`    | int     | `25`    | Results per page                         |
| `offset`   | int     | `0`     | Pagination offset                        |

```bash
curl "http://127.0.0.1:8000/pastsoldlisting?card_name=Mewtwo&language=Japanese&limit=5"
```

```json
{
  "listings": [
    { "price": 12.5, "date": "2026-02-15T08:30:00.000Z" },
    { "price": 9.99, "date": "2026-02-10T14:22:00.000Z" }
  ],
  "pagination": {
    "total": 50,
    "limit": 5,
    "offset": 0,
    "has_more": true
  }
}
```

### `GET /historical`

Returns historical pricing data over a configurable time range.

| Parameter   | Type    | Default | Description                              |
|------------|---------|---------|------------------------------------------|
| `card_name`| string  | *required* | Card name to search for              |
| `days`     | int     | `90`    | Days of historical data (1-365)         |

```bash
curl "http://127.0.0.1:8000/historical?card_name=Charizard&days=30"
```

```json
{
  "card_name": "charizard",
  "listings": [...],
  "days_range": 30,
  "avg_price": 45.67
}
```

### `GET /pricechart`

Returns a **PNG scatter plot** of sold price vs. date with a trend line. Open directly in a browser.

```
http://127.0.0.1:8000/pricechart?card_name=Charizard&limit=50
```

### `GET /health`

Health check endpoint for monitoring and load balancers.

```json
{ "status": "ok", "app": "Pokemon Card Price Comparator", "redis": true }
```

### `GET /metrics`

Returns internal metrics about eBay API usage and caching.

```json
{
  "ebay_api_calls": 150,
  "cache_hits": 450,
  "cache_misses": 100,
  "redis_status": "connected"
}
```

## Project Structure

```
PokemonCompCalculator/
├── .env                        # Environment variables (git-ignored)
├── requirements.txt            # Python dependencies
├── Dockerfile                   # Single-container deployment
├── docker-compose.yml          # Multi-container deployment (API + Redis)
├── README.md
└── app/
    ├── main.py                 # FastAPI app & endpoint definitions
    ├── models/
    │   └── price.py            # Response formatting
    └── services/
        ├── ebay.py             # eBay Browse API integration
        ├── pricing.py          # Market price calculation
        ├── cardinfo.py         # Statistics & chart generation
        └── redis_cache.py      # Redis caching utilities
```

## How Pricing Works

1. Fetches recent sold listings from eBay (excluding Best Offer sales)
2. Calculates the **average** and **median** sold price
3. Determines market trend:
   - **Stable** — median ≥ average (prices are consistent)
   - **Falling** — median < average (outliers are pulling the average up, most cards sell for less)
4. If the trend is **Falling**, the suggested price is discounted by 5%
5. The `fee` multiplier is applied (e.g. `fee=0.7` means you want to pay 70% of the suggested price)

## Tech Stack

- **[FastAPI](https://fastapi.tiangolo.com/)** — API framework
- **[eBay Browse API](https://developer.ebay.com/api-docs/buy/browse/overview.html)** — sold listing data
- **[Matplotlib](https://matplotlib.org/)** — chart generation
- **[NumPy](https://numpy.org/)** — trend line calculation
- **[Redis](https://redis.io/)** — distributed caching (optional)
- **[slowapi](https://github.com/laurentS/slowapi)** — rate limiting
- **[Docker](https://www.docker.com/)** — containerization
- **[pydantic-settings](https://github.com/pydantic/pydantic-settings)** — environment config
