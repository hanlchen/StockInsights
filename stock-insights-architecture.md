# Stock Insights App — Architecture & Build Plan

**Scope:** US equities (NYSE/NASDAQ) · Personal MVP → SaaS-ready
**Data cost:** $0 (free tiers/unofficial APIs only)
**Target build time:** 2–3 weeks, solo dev

---

## 0. Assumptions (stated up front, per your instructions)

| Area | Assumption |
|---|---|
| MAE | No free source gives true trade-based MAE. Using proxy: **max drawdown from trailing local peak** over a rolling 1Y window, computed from daily closes. Labeled `mae_proxy` everywhere, never presented as literal MAE. |
| Primary data source | `yfinance` — free, no API key, wraps Yahoo Finance endpoints. Unofficial and can break/rate-limit; that's why the provider abstraction exists. |
| Backup source | `stooq` (via `pandas-datareader` or direct CSV pull) — free, no key, good for daily OHLCV history. |
| Alpha Vantage | Optional tertiary fallback (free tier = 25 req/day as of last check — verify current limit yourself before relying on it, it changes). |
| "Average YTD over 2Y/5Y" | Average of each calendar year's full-year return (Jan 1 → Dec 31 close), not a rolling window of the current YTD figure. |
| Sector/market overview universe | S&P 500 constituent list (scraped once from Wikipedia, free, cached) used as the "market" proxy for gainers/losers/sector performance, since there's no free full-exchange screener API. |
| "Last week" | Trading week = most recent Mon–Fri with market data; computed as close(last trading day) vs close(5 trading days prior). |
| Users | MVP = single user, no auth. Schema includes a nullable `user_id` from day one so multi-tenancy is additive, not a migration nightmare. |

---

## 1. System Architecture (text diagram)

```
┌──────────────────────────────────────────────────────────────┐
│                        FRONTEND (Next.js)                     │
│  /              → Dashboard (market overview, movers, sectors)│
│  /stock/[ticker] → Stock detail page                          │
│  /search         → Search w/ autocomplete                     │
└───────────────────────────┬────────────────────────────────────┘
                             │ REST (JSON) — fetch()
                             ▼
┌──────────────────────────────────────────────────────────────┐
│                     BACKEND (FastAPI)                         │
│  ┌────────────┐   ┌──────────────┐   ┌────────────────────┐  │
│  │  API layer  │→ │ Service layer │→ │ Computation engine  │  │
│  │ (routers)   │   │ (business    │   │ (pandas: returns,   │  │
│  │             │   │  logic)      │   │  CAGR, drawdown)    │  │
│  └────────────┘   └──────┬───────┘   └────────────────────┘  │
│                            │                                   │
│                    ┌───────▼────────┐                          │
│                    │  Cache layer    │  (in-memory dict/TTL    │
│                    │                 │   now → Redis later)    │
│                    └───────┬────────┘                          │
│                            │                                   │
│              ┌─────────────▼──────────────┐                    │
│              │ StockDataProvider interface │                   │
│              │  ├─ YFinanceProvider (impl) │                   │
│              │  ├─ StooqProvider (impl)    │                    │
│              │  └─ AlphaVantageProvider    │                    │
│              └─────────────┬──────────────┘                    │
└────────────────────────────┼──────────────────────────────────┘
                              ▼
                    External free data sources
                 (Yahoo Finance / Stooq / Alpha Vantage)

                    ┌────────────────────┐
                    │   SQLite (MVP)      │
                    │  → Postgres later    │
                    │  (Supabase free tier)│
                    └────────────────────┘
```

**Key design principle:** the API layer and frontend never talk to `yfinance` directly — everything goes through the service layer, which goes through the provider interface. This is what lets you swap data sources or add Redis later without touching routes or UI.

---

## 2. Backend Folder Structure

```
backend/
├── app/
│   ├── main.py                     # FastAPI app entrypoint
│   ├── config.py                   # env vars, settings (pydantic BaseSettings)
│   │
│   ├── api/
│   │   ├── __init__.py
│   │   ├── routes/
│   │   │   ├── stock.py            # /stock/{ticker}, /stock/search
│   │   │   └── market.py           # /market/overview, /market/sectors
│   │   └── deps.py                 # shared FastAPI dependencies
│   │
│   ├── services/
│   │   ├── stock_service.py        # orchestrates fetch + compute + cache for a ticker
│   │   ├── market_service.py       # orchestrates movers + sector aggregation
│   │   └── universe.py             # S&P 500 ticker list loader/cache
│   │
│   ├── providers/
│   │   ├── base.py                 # StockDataProvider abstract interface
│   │   ├── yfinance_provider.py
│   │   ├── stooq_provider.py
│   │   └── alpha_vantage_provider.py
│   │
│   ├── computation/
│   │   ├── returns.py              # YTD, 2Y, 5Y, CAGR, avg-YTD
│   │   └── risk.py                 # mae_proxy / drawdown
│   │
│   ├── cache/
│   │   ├── base.py                 # Cache interface (get/set/ttl)
│   │   └── memory_cache.py         # MVP in-memory impl (swap for RedisCache later)
│   │
│   ├── db/
│   │   ├── models.py                # SQLAlchemy models
│   │   ├── session.py                # engine/session setup
│   │   └── init_db.py               # create tables, seed universe
│   │
│   └── schemas/
│       ├── stock.py                  # Pydantic response models
│       └── market.py
│
├── scripts/
│   └── refresh_cache.py             # cron/manual job to pre-warm cache
├── requirements.txt
└── .env.example
```

---

## 3. Frontend Folder Structure (Next.js, App Router)

```
frontend/
├── app/
│   ├── layout.tsx
│   ├── page.tsx                     # Dashboard (market overview)
│   ├── stock/
│   │   └── [ticker]/
│   │       └── page.tsx             # Stock detail page
│   ├── search/
│   │   └── page.tsx                 # Search w/ autocomplete
│   └── api/                         # (optional) Next.js proxy routes to backend
│
├── components/
│   ├── SearchBar.tsx
│   ├── StockMetricsCard.tsx
│   ├── MoversTable.tsx              # top gainers/losers
│   ├── SectorPerformanceTable.tsx
│   └── PriceHeader.tsx
│
├── lib/
│   ├── api.ts                       # typed fetch wrappers to FastAPI backend
│   └── formatters.ts                # % / currency formatting helpers
│
├── types/
│   └── stock.ts                     # shared TS types matching backend Pydantic schemas
│
├── next.config.js
└── package.json
```

---

## 4. Database Schema

MVP on SQLite, same schema forward-compatible with Postgres (Supabase).

```sql
-- Stock metadata
CREATE TABLE stocks (
    ticker          TEXT PRIMARY KEY,
    company_name    TEXT NOT NULL,
    sector          TEXT,
    industry        TEXT,
    exchange        TEXT CHECK (exchange IN ('NYSE', 'NASDAQ')),
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Cached daily price history (optional but recommended for perf)
CREATE TABLE price_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ticker          TEXT NOT NULL REFERENCES stocks(ticker),
    date            DATE NOT NULL,
    open            REAL,
    high            REAL,
    low             REAL,
    close           REAL NOT NULL,
    volume          INTEGER,
    UNIQUE(ticker, date)
);
CREATE INDEX idx_price_history_ticker_date ON price_history(ticker, date);

-- Precomputed metrics (cache layer, DB-backed fallback)
CREATE TABLE computed_metrics (
    ticker              TEXT PRIMARY KEY REFERENCES stocks(ticker),
    current_price       REAL,
    volume              INTEGER,
    mae_proxy           REAL,        -- max drawdown proxy, see risk.py
    ytd_return          REAL,
    return_2y           REAL,        -- CAGR
    return_5y           REAL,        -- CAGR
    avg_ytd_2y          REAL,
    avg_ytd_5y          REAL,
    computed_at         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Multi-tenancy-ready from day one (nullable = single user MVP)
CREATE TABLE users (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    email           TEXT UNIQUE,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE watchlists (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id         INTEGER REFERENCES users(id),   -- NULL in MVP
    ticker          TEXT NOT NULL REFERENCES stocks(ticker),
    added_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

---

## 5. API Specification

Base URL: `/api/v1`

### `GET /stock/{ticker}`
Returns full metrics for one stock.

**Response 200**
```json
{
  "ticker": "AAPL",
  "company_name": "Apple Inc.",
  "sector": "Technology",
  "current_price": 213.55,
  "volume": 48213000,
  "mae_proxy": -0.184,
  "mae_proxy_note": "Approximate max drawdown from trailing 1Y local peak, not true MAE",
  "ytd_return": 0.062,
  "return_2y_cagr": 0.171,
  "return_5y_cagr": 0.223,
  "avg_ytd_2y": 0.089,
  "avg_ytd_5y": 0.134,
  "as_of": "2026-07-02T20:00:00Z",
  "cache_hit": true
}
```
**Errors:** `404` unknown ticker, `503` upstream data provider unavailable (with fallback attempted first).

### `GET /stock/search?q=`
Autocomplete search.

**Response 200**
```json
{
  "results": [
    { "ticker": "AAPL", "company_name": "Apple Inc.", "exchange": "NASDAQ" },
    { "ticker": "AAP",  "company_name": "Advance Auto Parts", "exchange": "NYSE" }
  ]
}
```

### `GET /market/overview`
Last-week gainers/losers.

**Response 200**
```json
{
  "week_ending": "2026-06-27",
  "top_gainers": [
    { "ticker": "NVDA", "pct_change": 0.081 }
  ],
  "top_losers": [
    { "ticker": "XYZ", "pct_change": -0.063 }
  ]
}
```

### `GET /market/sectors`
Sector performance summary, last week.

**Response 200**
```json
{
  "week_ending": "2026-06-27",
  "sectors": [
    { "sector": "Technology", "avg_pct_change": 0.021, "direction": "up" },
    { "sector": "Energy", "avg_pct_change": -0.014, "direction": "down" }
  ]
}
```

---

## 6. Core Computation Logic

### `computation/returns.py`
```python
import pandas as pd
from datetime import datetime

def ytd_return(price_series: pd.Series, as_of: datetime | None = None) -> float:
    """price_series: date-indexed close prices, ascending."""
    as_of = as_of or price_series.index.max()
    year_start = pd.Timestamp(year=as_of.year, month=1, day=1)
    start_price = price_series.loc[price_series.index >= year_start].iloc[0]
    end_price = price_series.loc[price_series.index <= as_of].iloc[-1]
    return (end_price - start_price) / start_price


def cagr(price_series: pd.Series, years: float) -> float:
    """Cumulative annualized growth rate over `years`."""
    start_price = price_series.iloc[0]
    end_price = price_series.iloc[-1]
    return (end_price / start_price) ** (1 / years) - 1


def average_ytd_over_years(price_series: pd.Series, n_years: int) -> float:
    """
    Average of each calendar year's FULL-YEAR return (Jan 1 -> Dec 31 close)
    over the trailing n_years complete years. Excludes the current
    in-progress year.
    """
    current_year = price_series.index.max().year
    yearly_returns = []
    for y in range(current_year - n_years, current_year):
        yr_data = price_series[price_series.index.year == y]
        if yr_data.empty:
            continue
        yearly_returns.append((yr_data.iloc[-1] - yr_data.iloc[0]) / yr_data.iloc[0])
    if not yearly_returns:
        return None
    return sum(yearly_returns) / len(yearly_returns)
```

### `computation/risk.py`
```python
import pandas as pd

def mae_proxy(price_series: pd.Series, window_days: int = 252) -> float:
    """
    Approximate Maximum Adverse Excursion.
    Defined as the max drawdown from a trailing local peak within the window:
        drawdown(t) = (price(t) - running_max(t)) / running_max(t)
    Returns the most negative drawdown value in the window (i.e. worst case).
    NOTE: This is a proxy, not true trade-based MAE (which requires entry points).
    """
    recent = price_series.tail(window_days)
    running_max = recent.cummax()
    drawdown = (recent - running_max) / running_max
    return float(drawdown.min())
```

### `providers/base.py`
```python
from abc import ABC, abstractmethod
import pandas as pd

class StockDataProvider(ABC):
    @abstractmethod
    def get_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        """Returns OHLCV DataFrame, date-indexed, ascending."""
        ...

    @abstractmethod
    def get_quote(self, ticker: str) -> dict:
        """Returns current price, volume, company name, sector, industry."""
        ...

    @abstractmethod
    def search(self, query: str) -> list[dict]:
        ...
```

### `providers/yfinance_provider.py`
```python
import yfinance as yf
import pandas as pd
from .base import StockDataProvider

class YFinanceProvider(StockDataProvider):
    def get_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        df = yf.Ticker(ticker).history(period=period, interval="1d")
        df.index = pd.to_datetime(df.index).tz_localize(None)
        return df[["Open", "High", "Low", "Close", "Volume"]]

    def get_quote(self, ticker: str) -> dict:
        info = yf.Ticker(ticker).info
        return {
            "ticker": ticker,
            "company_name": info.get("longName", ticker),
            "sector": info.get("sector"),
            "industry": info.get("industry"),
            "current_price": info.get("currentPrice") or info.get("regularMarketPrice"),
            "volume": info.get("volume"),
        }

    def search(self, query: str) -> list[dict]:
        # yfinance has no native search; simplest free approach is matching
        # against a locally cached ticker/company list (see universe.py)
        raise NotImplementedError("Use universe.py local search instead")
```

### `services/stock_service.py` (orchestration + caching)
```python
from app.providers.yfinance_provider import YFinanceProvider
from app.computation.returns import ytd_return, cagr, average_ytd_over_years
from app.computation.risk import mae_proxy
from app.cache.memory_cache import cache

provider = YFinanceProvider()
CACHE_TTL_SECONDS = 15 * 60  # 15 min, tune as needed

def get_stock_metrics(ticker: str) -> dict:
    cache_key = f"stock:{ticker}"
    cached = cache.get(cache_key)
    if cached:
        return {**cached, "cache_hit": True}

    quote = provider.get_quote(ticker)
    history = provider.get_price_history(ticker, period="5y")
    closes = history["Close"]

    result = {
        **quote,
        "mae_proxy": mae_proxy(closes),
        "mae_proxy_note": "Approximate max drawdown from trailing 1Y local peak, not true MAE",
        "ytd_return": ytd_return(closes),
        "return_2y_cagr": cagr(closes.last("730D"), years=2),
        "return_5y_cagr": cagr(closes, years=5),
        "avg_ytd_2y": average_ytd_over_years(closes, 2),
        "avg_ytd_5y": average_ytd_over_years(closes, 5),
        "cache_hit": False,
    }
    cache.set(cache_key, result, ttl=CACHE_TTL_SECONDS)
    return result
```

### `cache/memory_cache.py`
```python
import time

class MemoryCache:
    """Simple TTL dict cache. Swap for RedisCache(same interface) at scale."""
    def __init__(self):
        self._store: dict[str, tuple[float, dict]] = {}

    def get(self, key: str):
        entry = self._store.get(key)
        if not entry:
            return None
        expires_at, value = entry
        if time.time() > expires_at:
            del self._store[key]
            return None
        return value

    def set(self, key: str, value: dict, ttl: int):
        self._store[key] = (time.time() + ttl, value)

cache = MemoryCache()
```

---

## 7. Minimal MVP Implementation Plan (step by step)

**Week 1 — Backend core**
1. Scaffold FastAPI project, `requirements.txt` (`fastapi`, `uvicorn`, `yfinance`, `pandas`, `sqlalchemy`, `pydantic-settings`).
2. Implement `StockDataProvider` interface + `YFinanceProvider`.
3. Implement `computation/returns.py` and `risk.py`, write quick sanity tests against 2–3 known tickers (AAPL, MSFT, TSLA) by hand-checking numbers.
4. Implement `MemoryCache` + `stock_service.get_stock_metrics`.
5. Wire up `/stock/{ticker}` route. Test in Swagger UI (`/docs`, free with FastAPI).

**Week 1–2 — Market overview + search**
6. Build `universe.py`: scrape/cache S&P 500 ticker+company+sector list (Wikipedia table, refresh weekly).
7. Implement local ticker/company-name search over the cached universe (no API call needed — fast, free).
8. Implement `market_service`: pull last-week price for each universe ticker (batch via `yf.download(tickers, period="5d")` — much faster than per-ticker calls), compute % change, sort for gainers/losers.
9. Aggregate sector performance: group tickers by sector, average % change.
10. Wire up `/market/overview`, `/market/sectors`, `/stock/search`.

**Week 2 — SQLite persistence**
11. Add SQLAlchemy models, `init_db.py` to create tables and seed `stocks` table from universe.
12. Optionally persist `price_history` and `computed_metrics` so cold-start after cache expiry hits DB before hitting yfinance again (reduces rate-limit risk).
13. Add `scripts/refresh_cache.py` — a script you run manually (or cron) each morning to pre-warm metrics for your watchlist + universe.

**Week 2–3 — Frontend**
14. Scaffold Next.js app, set up `lib/api.ts` typed fetch wrappers.
15. Build Dashboard page: fetch `/market/overview` + `/market/sectors`, render tables.
16. Build Stock detail page `/stock/[ticker]`: fetch `/stock/{ticker}`, render metric cards.
17. Build Search page/component with debounced autocomplete against `/stock/search`.
18. Polish: loading states, error states (esp. for the `503`/unknown ticker cases), minimal styling (Tailwind, Bloomberg-lite: dense tables, monospace numbers, no chart clutter unless it clarifies).

**Buffer**
19. Manual QA against 10–15 tickers across sectors, sanity-check numbers vs. a source like Google Finance.
20. Rate-limit handling: yfinance has no official SLA — add retry/backoff and a Stooq fallback in the provider layer if you hit throttling.

---

## 8. Suggested Improvements — Scaling to SaaS

| Now (MVP) | Later (SaaS) |
|---|---|
| No auth | Add auth (Supabase Auth or Clerk free tier) — `users` table already exists |
| In-memory cache | Redis (same `Cache` interface, swap implementation only) |
| SQLite | Postgres via Supabase (schema is already Postgres-compatible) |
| Manual/cron cache refresh | Celery + Redis broker for scheduled jobs, or Supabase Edge Functions on a cron |
| Single yfinance provider | Add fallback chain + circuit breaker across providers for reliability |
| No rate limiting on your API | Add per-user rate limiting (e.g. `slowapi`) once multi-tenant |
| No watchlists/alerts | `watchlists` table exists — add `alerts` table + a scheduled job comparing thresholds |
| Free tier only | Stripe (test mode is free) for a paid tier gated by `users.plan` |
| Single-region | Not urgent pre-revenue; revisit if latency complaints arise |
| No real-time | Polling every 15 min is fine at MVP scale; real-time (WebSocket) is a post-revenue feature — free real-time equity data essentially doesn't exist, so this is likely your first paid infra cost |

**The one thing worth over-investing in now:** the `StockDataProvider` interface and the `Cache` interface. Everything else is cheap to change later; a data-source or caching rewrite touching every route is not.

---

## Known limitations to keep in mind

- `yfinance` is unofficial (scrapes Yahoo endpoints) — it can break without notice. Don't build anything that depends on 100% uptime without a fallback provider wired in.
- The "market overview" is really "S&P 500 overview," not literally all of NYSE/NASDAQ — a true full-exchange scan needs a paid screener API. Worth labeling this honestly in the UI ("S&P 500 movers") rather than implying full-market coverage.
- `mae_proxy` is clearly not real MAE — keep the label and tooltip in the UI so it's never mistaken for the real thing.
