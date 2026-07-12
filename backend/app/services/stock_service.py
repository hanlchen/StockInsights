import logging
import time
from datetime import datetime, timezone

from app.cache.memory_cache import cache
from app.computation.market_cap import market_cap_bucket
from app.computation.returns import (
    PERIOD_TRADING_DAYS,
    average_ytd_over_years,
    cagr,
    momentum_trend,
    monthly_momentum_trend,
    period_change,
    trailing_window,
    ytd_return,
)
from app.computation.risk import MAE_PROXY_NOTE, mae_proxy
from app.config import settings
from app.db.session import SessionLocal
from app.providers.base import ProviderError
from app.providers.provider_chain import ProviderChain
from app.providers.rate_limit import looks_rate_limited
from app.providers.stooq_provider import StooqProvider
from app.providers.yfinance_provider import YFinanceProvider
from app.services import persistence
from app.services.universe import get_universe_lookup

logger = logging.getLogger(__name__)

# Order matters: primary first, fallback(s) after. Adding a provider (e.g.
# AlphaVantage) later means appending here -- no other code changes.
provider = ProviderChain([YFinanceProvider(), StooqProvider()])

# This is a live request, not the batch job (scripts/refresh_cache.py, which
# can afford 45s+ backoff rounds since nothing is waiting on it) -- a user's
# browser is blocked on this call, so total added wait is capped at a few
# seconds. That's enough to ride out a brief 429 blip; a sustained throttle
# still surfaces as a normal UpstreamUnavailableError (503) once these run
# out, same as before this retry existed.
RATE_LIMIT_RETRY_BACKOFFS_SECONDS = (1.5, 3.0)


class TickerNotFoundError(Exception):
    pass


class UpstreamUnavailableError(Exception):
    pass



# A single-day move this large is unusual for a NYSE/NASDAQ common stock
# outside a halt/reverse-split edge case (e.g. ACB's 2020 1-for-12 reverse
# split), but it's not treated as a reason to withhold return figures --
# per the user, a >50% single-day move is fine, don't omit/null out data
# because of it. Still logged as a WARNING (not silently ignored) so a
# genuinely corrupted/misaligned history is at least visible in the logs if
# it ever turns out to matter.
MAX_PLAUSIBLE_DAILY_MOVE = 0.5


def _has_large_single_day_move(closes) -> bool:
    if len(closes) < 2:
        return False
    daily_returns = closes.pct_change().dropna()
    return bool((daily_returns.abs() > MAX_PLAUSIBLE_DAILY_MOVE).any())


def _call_with_rate_limit_retry(fn, ticker: str, label: str):
    """Calls `fn()` (a no-arg wrapper around a provider.get_quote/
    get_price_history call), retrying with a short backoff if the failure
    looks like a 429/throttle rather than a genuine bad-ticker error. Only
    rate-limited failures are retried -- a delisted ticker or malformed
    response will just fail identically again, so those raise immediately."""
    backoffs = (0.0,) + RATE_LIMIT_RETRY_BACKOFFS_SECONDS
    last_exc: ProviderError | None = None
    for attempt, backoff in enumerate(backoffs):
        if backoff:
            time.sleep(backoff)
        try:
            return fn()
        except ProviderError as exc:
            last_exc = exc
            if not looks_rate_limited(exc):
                raise
            remaining = len(backoffs) - attempt - 1
            if remaining:
                logger.warning(
                    "%s: %s looks rate-limited, retrying in %.1fs (%d attempt(s) left)",
                    ticker, label, backoffs[attempt + 1], remaining,
                )
    raise last_exc


# Periods offered on the stock-detail chart. Kept in sync with what both
# providers actually support: YFinanceProvider passes these straight through
# to yfinance's `period=` (which accepts them natively -- "1d" additionally
# switches to 5-minute intraday bars, see YFinanceProvider.get_price_history),
# and StooqProvider._period_to_days() has a matching entry for each one
# except "1d", which Stooq can't serve at all (daily-bar-only free feed) and
# deliberately raises on -- yfinance is the only provider for that period.
VALID_HISTORY_PERIODS = ("1d", "1mo", "3mo", "6mo", "1y", "5y")
DEFAULT_HISTORY_PERIOD = "6mo"

# Intraday data is only useful if it's close to real-time, unlike the daily
# bars for longer periods -- a much shorter TTL than the normal 15-min quote/
# price cache so a "1D" chart doesn't look stale for most of the trading day.
INTRADAY_CACHE_TTL_SECONDS = 2 * 60


def get_price_history(ticker: str, period: str = DEFAULT_HISTORY_PERIOD, use_cache: bool = True) -> dict:
    """Live OHLCV series for the stock-detail chart -- fetched directly from
    the provider chain on every call (subject to the same short TTL cache as
    get_stock_metrics), NOT read from computed_metrics. That table only ever
    stores a single latest snapshot per ticker, not a history, so a chart has
    to go straight to the source."""
    ticker = ticker.upper().strip()
    if period not in VALID_HISTORY_PERIODS:
        raise ValueError(f"Invalid period '{period}' -- must be one of {VALID_HISTORY_PERIODS}")

    cache_key = f"history:{ticker}:{period}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return {**cached, "cache_hit": True}

    try:
        history = _call_with_rate_limit_retry(
            lambda: provider.get_price_history(ticker, period=period), ticker, "price history"
        )
    except ProviderError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    closes = history["Close"].dropna()
    if closes.empty:
        raise TickerNotFoundError(f"No price data available for {ticker}")

    points = [
        {
            "date": ts.to_pydatetime(),
            "close": float(row["Close"]),
            "open": float(row["Open"]) if row.notna()["Open"] else None,
            "high": float(row["High"]) if row.notna()["High"] else None,
            "low": float(row["Low"]) if row.notna()["Low"] else None,
            "volume": int(row["Volume"]) if row.notna()["Volume"] else None,
        }
        for ts, row in history.iterrows()
        if row.notna()["Close"]
    ]

    result = {
        "ticker": ticker,
        "period": period,
        "points": points,
        "as_of": datetime.now(timezone.utc),
        "cache_hit": False,
    }
    ttl = INTRADAY_CACHE_TTL_SECONDS if period == "1d" else settings.cache_ttl_seconds
    cache.set(cache_key, result, ttl=ttl)
    return result


# Quarterly financials only change ~4x/year (one new earnings report), so a
# much longer TTL than the 15-min quote/price cache is safe and avoids
# hitting yfinance's heavier statements call on every page load.
FINANCIALS_CACHE_TTL_SECONDS = 6 * 60 * 60  # 6 hours
MAX_FINANCIAL_QUARTERS = 8


def get_quarterly_financials(ticker: str, use_cache: bool = True) -> dict:
    """Quarterly income-statement line items (revenue, gross profit,
    operating income, net income, EPS) for the last MAX_FINANCIAL_QUARTERS
    quarters, oldest -> newest -- live from the provider chain (yfinance
    only today; Stooq has no financials endpoint), never from
    computed_metrics (which only ever holds a single latest snapshot)."""
    ticker = ticker.upper().strip()
    cache_key = f"financials:{ticker}"
    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return {**cached, "cache_hit": True}

    try:
        points = _call_with_rate_limit_retry(
            lambda: provider.get_quarterly_financials(ticker, max_quarters=MAX_FINANCIAL_QUARTERS),
            ticker, "quarterly financials",
        )
    except ProviderError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    if not points:
        raise TickerNotFoundError(f"No quarterly financials available for {ticker}")

    result = {
        "ticker": ticker,
        "points": points,
        "as_of": datetime.now(timezone.utc),
        "cache_hit": False,
    }
    cache.set(cache_key, result, ttl=FINANCIALS_CACHE_TTL_SECONDS)
    return result


def get_stock_metrics(ticker: str, use_cache: bool = True) -> dict:
    ticker = ticker.upper().strip()
    cache_key = f"stock:{ticker}"

    if use_cache:
        cached = cache.get(cache_key)
        if cached:
            return {**cached, "cache_hit": True}

    try:
        quote = _call_with_rate_limit_retry(lambda: provider.get_quote(ticker), ticker, "quote")
        history = _call_with_rate_limit_retry(
            lambda: provider.get_price_history(ticker, period="5y"), ticker, "price history"
        )
    except ProviderError as exc:
        raise UpstreamUnavailableError(str(exc)) from exc

    closes = history["Close"].dropna()
    if closes.empty:
        raise TickerNotFoundError(f"No price data available for {ticker}")

    if _has_large_single_day_move(closes):
        logger.warning(
            "%s: price history contains a single-day move > %.0f%% -- "
            "computing return figures normally (large moves are no longer "
            "treated as corrupted data), flagged here in case it turns out "
            "to be a real data issue rather than a legitimate move/split",
            ticker, MAX_PLAUSIBLE_DAILY_MOVE * 100,
        )

    two_year_window = trailing_window(closes, days=730)

    result = {
        **quote,
        "mae_proxy": mae_proxy(closes, window_days=252),
        "mae_proxy_note": MAE_PROXY_NOTE,
        "ytd_return": ytd_return(closes),
        "return_2y_cagr": cagr(two_year_window, years=2) if len(two_year_window) > 1 else None,
        "return_5y_cagr": cagr(closes, years=5),
        "avg_ytd_2y": average_ytd_over_years(closes, 2),
        "avg_ytd_5y": average_ytd_over_years(closes, 5),
        "market_cap_bucket": market_cap_bucket(quote.get("market_cap")),
        "pct_change_1d": period_change(closes, PERIOD_TRADING_DAYS["1d"]),
        "pct_change_1w": period_change(closes, PERIOD_TRADING_DAYS["1w"]),
        "pct_change_1mo": period_change(closes, PERIOD_TRADING_DAYS["1mo"]),
        "pct_change_1y": period_change(closes, PERIOD_TRADING_DAYS["1y"]),
        "pct_change_3y": period_change(closes, PERIOD_TRADING_DAYS["3y"]),
        "momentum_trend": momentum_trend(closes),
        "monthly_momentum_trend": monthly_momentum_trend(closes),
        "as_of": datetime.now(timezone.utc),
        "cache_hit": False,
    }
    cache.set(cache_key, result, ttl=settings.cache_ttl_seconds)
    _persist_best_effort(ticker, quote, result)
    return result


def _persist_best_effort(ticker: str, quote: dict, result: dict) -> None:
    """Writes this lookup's quote + computed metrics to the DB so a single
    on-demand search also warms the movers/sector tables incrementally --
    but a DB hiccup should never break the live single-stock response, so
    failures here are logged and swallowed, not raised."""
    try:
        # Prefer our own universe list's exchange classification (sourced
        # from Nasdaq Trader, authoritative per project scope: NYSE/NASDAQ
        # only) over the live quote's exchange field -- providers sometimes
        # report a different/unmapped venue (e.g. BATS/Cboe "BTS") for a
        # ticker we already know is NYSE or NASDAQ listed, and the
        # `stocks.exchange` CHECK constraint rejects anything else, which
        # would otherwise fail the whole persist for that ticker.
        universe_record = get_universe_lookup().get(ticker)
        exchange = universe_record["exchange"] if universe_record else quote.get("exchange")

        with SessionLocal() as db:
            persistence.upsert_stock(
                db,
                ticker=ticker,
                company_name=quote.get("company_name", ticker),
                sector=quote.get("sector"),
                industry=quote.get("industry"),
                exchange=exchange,
                business_summary=quote.get("business_summary"),
                website=quote.get("website"),
                employees=quote.get("employees"),
                ipo_date=quote.get("ipo_date"),
            )
            # momentum_trend is a nested dict on the API response but the DB
            # stores it as 4 flat columns (see db/models.py) -- flatten here,
            # the one place that knows both shapes, rather than leaking the
            # nested shape into persistence.py's upsert.
            momentum = result.get("momentum_trend") or {}
            # Same flattening as momentum_trend above, one quarter's worth of
            # months at a time -- see monthly_momentum_trend() in
            # computation/returns.py for the nested shape.
            monthly = result.get("monthly_momentum_trend") or {}
            persistence.upsert_computed_metrics(db, ticker, {
                "current_price": result.get("current_price"),
                "volume": result.get("volume"),
                "mae_proxy": result.get("mae_proxy"),
                "ytd_return": result.get("ytd_return"),
                "return_2y": result.get("return_2y_cagr"),
                "return_5y": result.get("return_5y_cagr"),
                "avg_ytd_2y": result.get("avg_ytd_2y"),
                "avg_ytd_5y": result.get("avg_ytd_5y"),
                "market_cap": quote.get("market_cap"),
                "revenue_ttm": quote.get("revenue_ttm"),
                "pct_change_1d": result.get("pct_change_1d"),
                "pct_change_1w": result.get("pct_change_1w"),
                "pct_change_1mo": result.get("pct_change_1mo"),
                "pct_change_1y": result.get("pct_change_1y"),
                "pct_change_3y": result.get("pct_change_3y"),
                "momentum_m9_12": momentum.get("m9_12"),
                "momentum_m6_9": momentum.get("m6_9"),
                "momentum_m3_6": momentum.get("m3_6"),
                "momentum_m0_3": momentum.get("m0_3"),
                "monthly_m5_6": monthly.get("m5_6"),
                "monthly_m4_5": monthly.get("m4_5"),
                "monthly_m3_4": monthly.get("m3_4"),
                "monthly_m2_3": monthly.get("m2_3"),
                "monthly_m1_2": monthly.get("m1_2"),
                "monthly_m0_1": monthly.get("m0_1"),
                "book_value": quote.get("book_value"),
                "price_to_book": quote.get("price_to_book"),
                "trailing_pe": quote.get("trailing_pe"),
                "forward_pe": quote.get("forward_pe"),
                "trailing_eps": quote.get("trailing_eps"),
                "forward_eps": quote.get("forward_eps"),
                "dividend_yield": quote.get("dividend_yield"),
                "beta": quote.get("beta"),
                "fifty_two_week_high": quote.get("fifty_two_week_high"),
                "fifty_two_week_low": quote.get("fifty_two_week_low"),
            })
            db.commit()
    except Exception as exc:
        logger.warning("Failed to persist computed metrics for %s: %s", ticker, exc)
