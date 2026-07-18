import logging
from datetime import datetime, timezone

import pandas as pd
import yfinance as yf

from app.providers.base import ProviderError, StockDataProvider

logger = logging.getLogger(__name__)

# yfinance's quarterly_financials index uses these exact line-item labels
# (case/wording has shifted across yfinance versions -- e.g. some releases
# use "Net Income Common Stockholders" instead of a plain "Net Income" row
# -- so each field tries a few known label variants in order, first match
# wins). Row not present at all -> that field stays None for every quarter,
# same "best-effort, never fail the whole call over one missing line item"
# approach as get_quote()'s fundamentals fields.
_REVENUE_LABELS = ("Total Revenue", "TotalRevenue")
_GROSS_PROFIT_LABELS = ("Gross Profit", "GrossProfit")
_OPERATING_INCOME_LABELS = ("Operating Income", "OperatingIncome")
_NET_INCOME_LABELS = ("Net Income", "NetIncome", "Net Income Common Stockholders")
_EPS_LABELS = ("Diluted EPS", "Basic EPS")


class YFinanceProvider(StockDataProvider):
    """Primary data source. Free, no API key, wraps Yahoo Finance endpoints.
    Unofficial and can break/rate-limit without notice -- that's why the
    provider abstraction + fallback chain exist. Do not depend on this
    having 100% uptime."""

    name = "yfinance"

    def get_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        # "1d" is the odd one out: every other period is a *range* charted
        # with daily bars, but a single daily bar for "today" isn't a chart.
        # 5-minute bars are what actually makes a 1-day intraday view useful.
        # yfinance only keeps intraday granularity for a handful of recent
        # days, which is exactly the "1d" use case -- no need for it anywhere
        # else here.
        interval = "5m" if period == "1d" else "1d"
        try:
            df = yf.Ticker(ticker).history(period=period, interval=interval)
        except Exception as exc:  # yfinance raises a variety of exception types
            raise ProviderError(f"yfinance history fetch failed for {ticker}: {exc}") from exc

        if df is None or df.empty:
            raise ProviderError(f"yfinance returned no price history for {ticker}")

        df.index = pd.to_datetime(df.index).tz_localize(None)
        # Defensive, not just tidying: computation/returns.py's period_change()
        # and trailing_window() index into this series by *position*
        # (iloc[-1], iloc[-(n+1)]) assuming ascending chronological order with
        # no duplicate dates. yfinance normally returns data that way, but
        # under concurrent/threaded fetches (scripts/refresh_cache.py runs
        # 4-8 workers) and rate-limit-triggered partial/retried responses, a
        # returned frame can occasionally be unsorted or contain a duplicate
        # timestamp -- and iloc-based slicing on top of that silently
        # produces a *wrong* window (comparing today's price against some
        # date other than N trading days ago) instead of raising an error.
        # That's the likely cause of implausible movers like "+3781% in a
        # week" for a mega-cap: not a real price move, a misaligned
        # comparison. Sorting + deduping (keep the last/most authoritative
        # row per date) guarantees downstream iloc-based math is correct.
        df = df[~df.index.duplicated(keep="last")].sort_index()
        return df[["Open", "High", "Low", "Close", "Volume"]]

    def get_quarterly_financials(self, ticker: str, max_quarters: int = 8) -> list[dict]:
        try:
            df = yf.Ticker(ticker).quarterly_financials
        except Exception as exc:  # yfinance raises a variety of exception types
            raise ProviderError(f"yfinance quarterly financials fetch failed for {ticker}: {exc}") from exc

        if df is None or df.empty:
            raise ProviderError(f"yfinance returned no quarterly financials for {ticker}")

        revenue_row = _find_row(df, _REVENUE_LABELS)
        gross_profit_row = _find_row(df, _GROSS_PROFIT_LABELS)
        operating_income_row = _find_row(df, _OPERATING_INCOME_LABELS)
        net_income_row = _find_row(df, _NET_INCOME_LABELS)
        eps_row = _find_row(df, _EPS_LABELS)

        # yfinance returns columns most-recent-quarter-first -- sort ascending
        # (oldest -> newest) so the chart reads left-to-right chronologically,
        # same convention as momentum_trend()/monthly_momentum_trend().
        columns = sorted(df.columns)[-max_quarters:]

        return [
            {
                "period_end": col.to_pydatetime(),
                "revenue": _cell(revenue_row, col),
                "gross_profit": _cell(gross_profit_row, col),
                "operating_income": _cell(operating_income_row, col),
                "net_income": _cell(net_income_row, col),
                "eps": _cell(eps_row, col),
            }
            for col in columns
        ]

    def get_quote(self, ticker: str, fetch_fundamentals: bool = True) -> dict:
        """
        Two Yahoo endpoints back this, with very different reliability:
        - `fast_info` (price/volume/exchange) -- lightweight, rarely needs the
          "crumb" auth token Yahoo has increasingly required, so it's the
          resilient path. Always fetched.
        - `.info` (company name/sector/industry/valuation fundamentals) --
          heavier, and the one that most commonly breaks/rate-limits/needs a
          crumb. Treated as best-effort enrichment: if it fails we still
          return a usable quote with just those fields left blank, instead
          of failing the whole request over data we don't strictly need
          live. Skipped entirely when `fetch_fundamentals=False` (see
          stock_service.py -- this is the slow-changing data the daily batch
          job already refreshes, so re-fetching it live on every page view
          isn't just unnecessary, it's extra load on an endpoint that's
          already prone to rate-limiting).
        """
        t = yf.Ticker(ticker)

        price = volume = exchange = market_cap = None
        try:
            fast = t.fast_info
            price = fast.get("last_price") or fast.get("lastPrice")
            volume = fast.get("last_volume") or fast.get("lastVolume")
            exchange = _normalize_exchange(fast.get("exchange"))
            # fast_info's market cap key -- cheap, no crumb/cookie needed,
            # so prefer it over .info's marketCap the same way we prefer
            # fast_info for price.
            market_cap = fast.get("market_cap") or fast.get("marketCap")
        except Exception:
            pass  # fall through to .info below; only fail if that fails too

        company_name = ticker.upper()
        sector = industry = revenue_ttm = None
        # Fundamentals/profile fields below all come from the same `.info`
        # call above -- no extra network round-trip, just reading more keys
        # out of a dict we already fetched. All best-effort like sector/
        # industry: left None if `.info` fails, never fails the whole quote.
        business_summary = website = employees = ipo_date = None
        book_value = price_to_book = None
        trailing_pe = forward_pe = trailing_eps = forward_eps = None
        dividend_yield = beta = None
        fifty_two_week_high = fifty_two_week_low = None
        info_error: Exception | None = None
        info_empty = False
        if fetch_fundamentals:
            try:
                info = t.info
                if info:
                    company_name = info.get("longName") or info.get("shortName") or company_name
                    sector = info.get("sector")
                    industry = info.get("industry")
                    price = price if price is not None else (info.get("currentPrice") or info.get("regularMarketPrice"))
                    volume = volume if volume is not None else (info.get("volume") or info.get("regularMarketVolume"))
                    exchange = exchange or _normalize_exchange(info.get("exchange"))
                    market_cap = market_cap or info.get("marketCap")
                    # yfinance's `totalRevenue` is trailing-twelve-months revenue
                    # (Yahoo's "Revenue (ttm)" figure), which is what the user
                    # asked for -- not most-recent-quarter revenue.
                    revenue_ttm = info.get("totalRevenue")

                    business_summary = info.get("longBusinessSummary")
                    website = info.get("website")
                    employees = info.get("fullTimeEmployees")
                    # Yahoo/yfinance has no true "founding year" field -- the
                    # closest available proxy is the stock's first trade date
                    # (IPO/listing date on this exchange), not when the company
                    # itself was founded. Exposed as `ipo_date`, not
                    # `founded_year`, so the distinction is visible downstream.
                    ipo_epoch = info.get("firstTradeDateEpochUtc") or info.get("firstTradeDateMilliseconds")
                    if ipo_epoch:
                        # Some yfinance versions report seconds, others ms --
                        # anything larger than a plausible seconds value
                        # (year ~5138) is almost certainly milliseconds.
                        if ipo_epoch > 10_000_000_000:
                            ipo_epoch = ipo_epoch / 1000
                        try:
                            ipo_date = datetime.fromtimestamp(ipo_epoch, tz=timezone.utc)
                        except (OverflowError, OSError, ValueError):
                            ipo_date = None

                    book_value = info.get("bookValue")
                    price_to_book = info.get("priceToBook")
                    trailing_pe = info.get("trailingPE")
                    forward_pe = info.get("forwardPE")
                    trailing_eps = info.get("trailingEps")
                    forward_eps = info.get("forwardEps")
                    dividend_yield = info.get("dividendYield")
                    beta = info.get("beta")
                    fifty_two_week_high = info.get("fiftyTwoWeekHigh")
                    fifty_two_week_low = info.get("fiftyTwoWeekLow")
                else:
                    info_empty = True
            except Exception as exc:
                info_error = exc

        if fetch_fundamentals and (info_error is not None or info_empty):
            # Previously silent whenever `price` still came through via
            # fast_info -- that left zero visibility into why book_value/
            # trailing_pe/EPS/dividend_yield/beta/etc. are empty in
            # production (they ALL come from `.info` only, never fast_info).
            # `.info` is the heavier, crumb/cookie-gated call and is known to
            # be more likely to get rate-limited/blocked than fast_info.
            #
            # Two distinct failure shapes here, both worth logging: (a) an
            # actual exception (info_error) and (b) yfinance swallowing a
            # blocked/rate-limited response itself and just handing back an
            # empty/falsy dict with NO exception raised (info_empty) -- the
            # second one is the one that was still silent after the first
            # fix, since that fix only checked for a raised exception.
            reason = str(info_error) if info_error is not None else (
                "t.info returned empty/falsy data with no exception raised "
                "-- likely Yahoo silently rate-limiting or blocking this "
                "request rather than erroring"
            )
            logger.warning(
                "yfinance .info fetch failed for %s -- fundamentals "
                "(book_value/PE/EPS/dividend_yield/beta/sector/industry/"
                "profile fields) will be null this call: %s",
                ticker, reason,
            )

        if price is None:
            detail = f" (.info also failed: {info_error})" if info_error else ""
            raise ProviderError(
                f"yfinance returned no price for {ticker} via fast_info or .info{detail}"
            )

        return {
            "ticker": ticker.upper(),
            "company_name": company_name,
            "sector": sector,
            "industry": industry,
            "exchange": exchange,
            "current_price": price,
            "volume": volume,
            "market_cap": market_cap,
            "revenue_ttm": revenue_ttm,
            "business_summary": business_summary,
            "website": website,
            "employees": employees,
            "ipo_date": ipo_date,
            "book_value": book_value,
            "price_to_book": price_to_book,
            "trailing_pe": trailing_pe,
            "forward_pe": forward_pe,
            "trailing_eps": trailing_eps,
            "forward_eps": forward_eps,
            "dividend_yield": dividend_yield,
            "beta": beta,
            # True whenever `.info` (the ONLY source of every field above
            # except current_price/volume/exchange/market_cap, which prefer
            # fast_info) was skipped (fetch_fundamentals=False), failed, or
            # came back empty this call -- lets callers distinguish "we
            # asked and there's genuinely no value" (e.g. no dividend) from
            # "we don't have a live value right now" (skipped in favor of
            # the DB, or rate-limited/blocked), so the frontend can show a
            # real message instead of a blank "—" for the latter, and so
            # stock_service.py knows it should fill gaps from the DB
            # snapshot regardless of which of these three reasons applies.
            "fundamentals_unavailable": not fetch_fundamentals or info_error is not None or info_empty,
            "fifty_two_week_high": fifty_two_week_high,
            "fifty_two_week_low": fifty_two_week_low,
        }


def _normalize_exchange(raw: str | None) -> str | None:
    """Maps Yahoo's exchange codes to our two supported values. Anything we
    don't recognize (BATS/Cboe BZX ("BTS"), AMEX, OTC, foreign exchanges,
    etc.) returns None rather than the raw code -- `stocks.exchange` has a
    CHECK constraint limiting it to 'NYSE'/'NASDAQ'/NULL (per project scope:
    NYSE+NASDAQ only), and passing through an unrecognized code violates
    that constraint and fails the DB write entirely. Better to have a
    missing exchange than a crashed persist. Note: for tickers in our own
    universe (services/universe.py), stock_service prefers that list's
    exchange classification over this one anyway, since it's the
    authoritative source (Nasdaq Trader) -- this normalization mainly
    matters for the fast_info/.info exchange field before that override.
    """
    if not raw:
        return None
    raw = raw.upper()
    if raw in ("NMS", "NASDAQ", "NGM", "NCM"):
        return "NASDAQ"
    if raw in ("NYQ", "NYSE"):
        return "NYSE"
    return None


def _find_row(df: pd.DataFrame, labels: tuple[str, ...]) -> pd.Series | None:
    """First matching row (by index label) out of `labels`, or None if the
    statement doesn't have any of them -- see the module-level comment on
    the _*_LABELS tuples for why there's more than one candidate per field."""
    for label in labels:
        if label in df.index:
            return df.loc[label]
    return None


def _cell(row: pd.Series | None, col) -> float | None:
    if row is None or col not in row.index:
        return None
    value = row[col]
    return None if pd.isna(value) else float(value)
