# Stock Insights

US equities (NYSE/NASDAQ) insights app. Personal MVP today, architected for multi-user SaaS later. See `stock-insights-architecture.md` for the full design doc this was built from.

Want to host this for free (Supabase + Render + Vercel + a daily GitHub Actions refresh)? See **`DEPLOYMENT.md`**.

## Stack

- **Backend:** FastAPI + pandas + yfinance (primary data source) with a Stooq fallback, SQLite (Postgres-compatible schema), in-memory TTL cache.
- **Frontend:** Next.js 14 (App Router) + Tailwind. Five pages: dashboard (movers/sectors), stock detail (price chart + quarterly financials), search, all-tickers (full sortable/paginated browse), momentum screeners.
- **Universe:** full NYSE + NASDAQ common-stock listings (~6,000-9,000 tickers, ETFs/test issues excluded), sourced from Nasdaq Trader's free symbol directory files — not a S&P 500 proxy.
- **Market-wide data (movers, sectors, momentum screeners, ticker list) is DB-backed**, populated by a scheduled batch job (`scripts/refresh_cache.py`), not fetched live per request — see "Populating the database" below. This is required at full-exchange scale; a live per-request fetch across thousands of tickers is what caused the "socket hang up" failures during the S&P-500-only version. Single-ticker lookups (stock detail: quote, price chart, financials) are the exception -- those are always live, direct provider calls.

## Prerequisites

- Python 3.10+
- Node.js 18+
- Internet access (both installs pull packages, and the backend calls Yahoo Finance / Stooq / Nasdaq Trader at runtime)

## First-time setup

```bash
# Backend
cd backend
python3 -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env

# Frontend
cd ../frontend
npm install
cp .env.local.example .env.local
```

## Running locally

Two terminals:

```bash
# Terminal 1 — backend (port 8000)
cd backend
source .venv/bin/activate
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend (port 4000)
cd frontend
npm run dev
```

Open **http://localhost:4000**. The frontend proxies `/api/*` to `http://localhost:8000` via `next.config.js` rewrites, so there's no CORS setup needed locally.

API docs (Swagger UI): **http://localhost:8000/docs**

## If you already ran this app before this update

`computed_metrics` gained new columns (`market_cap`, `revenue_ttm`, `pct_change_1w/1y/3y`, `market_cap_bucket`, `momentum_m9_12/m6_9/m3_6/m0_3`, `monthly_m5_6/m4_5/m3_4/m2_3/m1_2/m0_1` for the monthly momentum screener, and now `pct_change_1mo` for the All Tickers page's 1-month column). Table creation (`Base.metadata.create_all`) only creates missing tables — it does not add columns to a table that already exists, and this project doesn't have a migration tool (Alembic) set up yet. If you have an existing `backend/stock_insights.db` from before, delete it before running the app again so it gets recreated with the new schema:

```bash
rm backend/stock_insights.db
```

This is a personal MVP with no auth/user data yet, so there's nothing meaningful to lose by recreating it — everything in `computed_metrics` is a recomputable cache, not a source of truth.

The new `daily_recommendations` table (AI Pick of the Day) is a brand-new table, not a new column on an existing one — `Base.metadata.create_all()` creates missing tables automatically (it just can't add columns to a table that already exists), so this one needs no manual step, on SQLite or Supabase, new install or existing.

## Populating the database (required for movers/sectors/momentum/tickers)

`/market/overview`, `/market/sectors`, `/market/momentum-screener`, `/market/monthly-momentum-screener`, and `/market/tickers` all read from `computed_metrics` in the database — they do **not** fetch live data per request. Until you run the refresh job at least once, those endpoints return a 503 telling you to run it. `/stock/{ticker}`, `/stock/{ticker}/history`, and `/stock/{ticker}/financials` (single-ticker lookups) work immediately without this, since they're live fetches -- `/stock/{ticker}` also opportunistically writes its result into the DB, incrementally warming the same table.

```bash
cd backend
source .venv/bin/activate
python -m scripts.refresh_cache            # whole NYSE+NASDAQ universe (~6,000-9,000 tickers, batches of 100 tickers/3 workers with a pause between batches -- expect this to take a while the first time)
python -m scripts.refresh_cache AAPL MSFT  # just these tickers, for a quick smoke test
```

Run this daily (cron / Task Scheduler / launchd) to keep movers/sectors/momentum/tickers fresh. It's idempotent — safe to re-run any time.

## Project layout

```
backend/app/
  providers/    StockDataProvider interface + yfinance/stooq impls + fallback chain
  computation/  returns.py (YTD/CAGR/avg-YTD/period_change for 1D/1W/1Y/3Y, quarterly + monthly momentum_trend), risk.py (mae_proxy), market_cap.py (Large/Mid/Small bucketing)
  cache/        Cache interface + in-memory TTL impl (swap for Redis later)
  services/     stock_service (single-ticker, live: quote/history/financials), market_service (movers/sectors/momentum screeners/ticker list, DB read), universe (full NYSE/NASDAQ list), sp500 (S&P 500 membership flag, Wikipedia-sourced), persistence (DB upsert/read helpers)
  db/           SQLAlchemy models (stocks, price_history, computed_metrics, users, watchlists)
  api/routes/   stock.py: /stock/{ticker}, /stock/{ticker}/history, /stock/{ticker}/financials, /stock/search
                market.py: /market/overview, /market/sectors, /market/momentum-screener, /market/monthly-momentum-screener, /market/tickers
scripts/
  refresh_cache.py   scheduled batch job -- fetches + computes metrics for the whole universe, writes to computed_metrics
frontend/
  app/          dashboard (/), stock detail (/stock/[ticker]), search (/search), all tickers (/tickers), momentum screeners (/momentum)
  components/   SearchBar, MoversTable, SectorPerformanceTable, TickerTable, MomentumScreenerTable, MonthlyMomentumTable, PriceHeader, PriceChart, FinancialsSection, StockMetricsCard
  lib/          typed api.ts fetch wrappers, formatters.ts, useQueryState.ts (URL-backed filter state)
```

**Filter state lives in the URL, not component state.** Dashboard, All Tickers, and Momentum all keep their filters (period, market cap, top N, sort, page, active tab, etc.) in the page's query string via `lib/useQueryState.ts`, using `router.replace` so tweaking a filter never adds its own history entry. That's what makes the browser Back button (e.g. after clicking into a stock from a filtered list) land back on the same filtered/sorted view instead of resetting to defaults -- the history entry it's returning to already has the filters baked into the URL. Each of those three pages is wrapped in a `<Suspense>` boundary, which `useSearchParams()` requires in the App Router.

## Stock detail: current price, chart, financials

`GET /stock/{ticker}`, `GET /stock/{ticker}/history`, and `GET /stock/{ticker}/financials` are all **live, on-demand fetches** from the provider chain -- unlike `/market/overview`/`/market/sectors`, they don't read from `computed_metrics`, so there's no batch job to run first.

- **`GET /stock/{ticker}/history?period=`** -- OHLCV points for the stock-detail chart. `period` is one of `1d`, `1mo`, `3mo`, `6mo` (default), `1y`, `5y`. All but `1d` are daily bars; `1d` switches to 5-minute intraday bars (yfinance-only -- Stooq's free feed is daily-bar-only, so it can't serve `1d` at all, same "one provider only" situation as financials below). Cached in-memory for `cache_ttl_seconds` (default 15 min), except `1d` which uses a much shorter 2-minute TTL so an intraday chart doesn't look stale mid-session.
- **`GET /stock/{ticker}/financials`** -- quarterly income-statement line items (revenue, gross profit, operating income, net income, diluted EPS), oldest -> newest, up to the last 8 quarters. **yfinance only** -- Stooq has no financials endpoint, so this 503s if yfinance is down even though price/quote would still work via the Stooq fallback. Cached in-memory for 6 hours (much longer than the 15-min quote/price cache, since a company only reports once a quarter).
- The frontend's `PriceChart` component renders history as a dependency-free inline SVG line chart (period switcher + hover tooltip); `FinancialsSection` renders financials as a dependency-free inline SVG QoQ revenue bar chart plus a metrics grid (revenue, QoQ growth, gross/operating/net margins, EPS). No charting library was added, to keep the frontend's dependency footprint minimal.
- `computed_metrics.current_price` (used by movers/sectors) is a snapshot from whenever the batch job last ran; everything on the stock-detail page is always live, from the same calls as above.

## Market overview: periods, filters, fields

- **Periods:** `1w` (1 week), `1y` (1 year), `3y` (3 year) total return — pass `?period=` to `/market/overview` and `/market/sectors`. Default `1w`.
- **Top N:** `/market/overview?top_n=` accepts 1-100 (default 10) for gainers/losers each.
- **Market cap filter:** `?market_cap=Large|Mid|Small` on both endpoints. Simple 3-tier bucketing: Large ≥ $10B, Mid $2B-$10B, Small < $2B.
- **Revenue:** every stock/mover entry that has fundamentals available includes `revenue_ttm` — trailing-twelve-months revenue (Yahoo's "Revenue (ttm)" figure), not most-recent-quarter revenue.
- **`as_of`** on movers/sectors responses is when the batch job last ran, not "now" — these are DB reads, not live data.

## Momentum screeners: quarterly vs. monthly (v2)

Both are DB-backed (same `computed_metrics` table, populated by `scripts.refresh_cache`) and both require EVERY window in the trailing period to clear a threshold — not just the average.

- **`GET /market/momentum-screener`** — quarterly (4 trailing ~3-month windows over the last year). `?min_quarterly_return=` (decimal, default 0.5), `?top_n=`, `?market_cap=`.
- **`GET /market/monthly-momentum-screener`** ("momentum v2") — monthly (6 trailing ~1-month windows over the last 6 months), a finer-grained check that a quarterly screen can miss (a strong quarter can hide one bad month). `?min_monthly_return=` (decimal; omit for "All" — no per-month threshold, just rank every ticker with a full 6-month trend), `?top_n=`, `?market_cap=`, `?sort_by=` (`avg`, or a specific month: `m5_6`, `m4_5`, `m3_4`, `m2_3`, `m1_2`, `m0_1` — `m0_1` is the most recent month).

Frontend: both live under the **Momentum** nav link, as the "Quarterly" and "Monthly (v2)" tabs on `/momentum`.

## Full ticker list + S&P 500 flag

**`GET /market/tickers`** -- plain browse/sort/paginate view over the entire NYSE+NASDAQ universe (DB-backed, same `computed_metrics` source as movers/sectors/momentum), for "let me look at all ~6,000-9,000 rows" rather than a ranked top-N. Params: `?sort_by=` (`ticker`, `company_name`, `price`, `volume`, `market_cap`, `pct_change_1d`, `pct_change_1mo`, `pct_change_1y`, default `market_cap`), `?order=` (`asc`/`desc`, default `desc`), `?page=`/`?page_size=` (default 50, max 200), `?exchange=` (`NYSE`/`NASDAQ`), `?sp500_only=true`, `?search=` (ticker/company name substring), `?industry=` (exact match -- see `/market/industries` below).

- **`GET /market/industries`** -- sorted list of distinct industry names across the universe, for populating the industry filter dropdown. Returns an empty list (not an error) if the refresh job hasn't populated `computed_metrics` yet.
- Each ticker row includes `industry` (from `stocks.industry`, same source as `sector`) and 1-day/1-month/1-year % change (`pct_change_1d/1mo/1y`).
- **`is_sp500`** on each ticker is fetched live from Wikipedia's "List of S&P 500 companies" page (there's no free official index-membership API), refreshed once a day and cached to disk as a fallback if that fetch fails. If the response's `sp500_data_available` is `false`, treat every `is_sp500` value as unknown, not as "confirmed not a member" -- see `known limitations` below.
- Frontend: the **All Tickers** nav link (`/tickers`), with exchange/industry filters, an S&P-500-only checkbox, a ticker/company search box, and sortable columns including industry and the three % change columns.

## AI Pick of the Day

An optional, best-effort feature: once a day, after `scripts.refresh_cache` runs, `scripts.generate_recommendation` takes the current quarterly momentum screener's top ~15 candidates (see above) and asks Claude (Anthropic API) to pick exactly one and explain why in plain language, citing the specific numbers it was given. The pick is stored (one row per day, in `daily_recommendations`) and served by `GET /market/recommendation/today` — a pure DB read, same pattern as movers/sectors/momentum, so **no live LLM call ever happens on a page load**, only once a day in the batch job.

- **Requires `ANTHROPIC_API_KEY`** (get one at console.anthropic.com), set only wherever the daily batch job runs (a GitHub Actions secret in the free-hosting setup — see `DEPLOYMENT.md`). Not needed on Render; the API endpoint itself never calls Anthropic. `ANTHROPIC_MODEL` (default `claude-sonnet-5`) is also configurable.
- **Best-effort, non-fatal:** if the key isn't set or the API call fails, `scripts.generate_recommendation` logs a warning and exits 0 rather than failing the whole daily-refresh workflow — this feature is supplementary, not core data.
- **"Pure LLM judgment," not a fixed formula:** the model chooses which of the ~15 pre-filtered candidates to highlight and writes its own reasoning + a risk note, rather than a deterministic score picking the winner and the model only narrating it. More flexible, less reproducible run-to-run — a documented tradeoff, not an oversight.
- **Guardrail:** if the model's response names a ticker outside the candidate list it was given, that response is rejected rather than persisted (see `recommendation_service.py`'s `_call_claude`) — the pick can only ever be one of the tickers actually shown to it.
- **Not financial advice.** The prompt asks the model to describe what the data shows rather than what to do with your money, and both the API response (`disclaimer` field) and the frontend card carry an explicit disclaimer independent of the model's own wording.
- Frontend: an "AI Pick of the Day" card at the top of the dashboard (`DailyRecommendationCard.tsx`), which renders nothing (not an error) if no pick has been generated yet — a fresh install without the API key configured looks like the feature simply isn't there, not broken.

## Known limitations (carried over from the architecture doc)

- **`mae_proxy` is not true MAE.** No free source gives trade-based Maximum Adverse Excursion (which needs an entry point). It's the max drawdown from a trailing 1Y local peak — labeled as a proxy everywhere in the API and UI.
- **Movers/sectors are a snapshot, not real-time.** They reflect whenever `scripts.refresh_cache` last ran, per the scheduled-batch-job design (chosen over live-per-request, which doesn't hold up at full-exchange scale).
- **yfinance is unofficial** and can rate-limit or break without notice. The `ProviderChain` falls back to Stooq automatically (no fundamentals from Stooq, so `market_cap`/`revenue_ttm` may be null if a ticker only got data from the fallback); extend it with Alpha Vantage if you hit persistent throttling.
- **Universe list** is fetched from Nasdaq Trader's free symbol directory files and cached to disk for a day; if that fetch fails (e.g. offline, or Nasdaq Trader moves the files), it falls back to a bundled ~70-ticker static list so the app still runs. This URL could not be verified live while building (see note below) — confirm your first refresh run picks up thousands of tickers, not ~70.
- **S&P 500 membership (`is_sp500`)** is scraped from a Wikipedia table, the standard free no-key source for this -- there's no official free index-membership API. No static fallback list is bundled on purpose (unlike the ticker universe): membership changes periodically, so a stale bundled list could silently mislabel tickers with no way to notice. If Wikipedia's page structure changes and there's no usable disk cache yet, `is_sp500` is unavailable for every ticker (`sp500_data_available: false`) rather than wrong.
- **Quarterly financials are yfinance-only.** Stooq (the fallback provider) has no income-statement endpoint, so `/stock/{ticker}/financials` 503s whenever yfinance is down, even though price/quote for the same ticker would still work via Stooq.

## Scaling to SaaS

The provider and cache interfaces are the two things intentionally over-built now — everything in the table below is meant to be a drop-in swap later, not a rewrite:

| Now | Later |
|---|---|
| No auth | Supabase Auth / Clerk — `users` table already exists |
| In-memory cache | Redis, same `Cache` interface |
| SQLite | Postgres (Supabase) — done, see `DEPLOYMENT.md` (just set `DATABASE_URL`, `psycopg2-binary` is already in requirements.txt) |
| Manual cache refresh | Done for free hosting via GitHub Actions (`.github/workflows/daily-refresh.yml`); Celery/Redis or a scheduled Edge Function are the paid/higher-volume upgrade path |
| yfinance + Stooq fallback | Add Alpha Vantage or others to `ProviderChain` |
| No rate limiting | `slowapi` per-user limits once multi-tenant |
| No watchlists/alerts | `watchlists` table exists — add `alerts` + scheduled comparison job |

## A note on this build

This code was written and saved to your project folder in an environment without outbound internet access, so package installs (`pip install`, `npm install`) and live data calls (Yahoo Finance, Stooq, Nasdaq Trader) couldn't be executed or smoke-tested here. Every Python file was verified to compile (`py_compile`) and the frontend was verified with `tsc --noEmit` (a full `next build` didn't complete in this sandbox), but you'll want to run through the "Running locally" steps above yourself as the real first test.

Specifically unverified against the live internet: the Nasdaq Trader symbol directory URLs in `app/services/universe.py` (`nasdaqlisted.txt` / `otherlisted.txt`). If `python -m scripts.refresh_cache` logs a warning about using the bundled ~70-ticker fallback instead of pulling thousands of tickers, that URL/parsing needs a look.
