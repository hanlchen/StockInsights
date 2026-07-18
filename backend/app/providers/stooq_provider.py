import pandas as pd
import requests

from app.providers.base import ProviderError, StockDataProvider


class StooqProvider(StockDataProvider):
    """Backup data source for daily OHLCV history. Free, no API key.
    Stooq has no quote/fundamentals endpoint as clean as yfinance's, so
    get_quote() derives a minimal quote from the latest price row only --
    good enough as an emergency fallback, not a full replacement.

    Stooq's CSV endpoint will 404/empty-response requests that look like
    bots (no User-Agent, no Accept header) -- send browser-like headers.
    It's also served from two domains (.com and .pl); if one 404s/times out
    we retry the other before giving up.
    """

    name = "stooq"
    BASE_URLS = ("https://stooq.com/q/d/l/", "https://stooq.pl/q/d/l/")
    HEADERS = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept": "text/csv,text/plain,*/*",
    }

    def get_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        if period == "1d":
            # Stooq's free CSV endpoint is daily-bar-only -- no intraday
            # granularity at all, so a "1d" request here would return at
            # most a single row, not a chart. Fail fast so ProviderChain
            # treats this the same as any other failed fetch (yfinance is
            # the only provider that can actually serve this).
            raise ProviderError(f"stooq does not support intraday (1d) history for {ticker}")

        symbol = f"{ticker.lower()}.us"
        resp = None
        errors: list[str] = []

        for base_url in self.BASE_URLS:
            try:
                resp = requests.get(
                    base_url, params={"s": symbol, "i": "d"}, headers=self.HEADERS, timeout=10
                )
                resp.raise_for_status()
                if resp.text and "Date,Open,High,Low,Close,Volume" in resp.text:
                    break
                if resp.text.lstrip().lower().startswith("<!doctype html"):
                    # Stooq serves an HTML interstitial/robots-blocked page
                    # instead of CSV when it's throttling us -- this is
                    # Stooq's own rate-limit signal, distinct from a bad/
                    # delisted ticker (which returns a short non-HTML body).
                    # Phrased with "rate limited" so refresh_cache.py's
                    # RATE_LIMIT_MARKERS catches it and retries with backoff
                    # instead of treating it as a permanent failure.
                    errors.append(f"{base_url}: likely rate limited (got HTML page instead of CSV)")
                else:
                    errors.append(f"{base_url}: unexpected response body ({resp.text[:80]!r})")
                resp = None
            except Exception as exc:
                errors.append(f"{base_url}: {exc}")
                resp = None

        if resp is None:
            raise ProviderError(f"stooq history fetch failed for {ticker}: " + " | ".join(errors))

        from io import StringIO

        df = pd.read_csv(StringIO(resp.text), parse_dates=["Date"])
        if df.empty:
            raise ProviderError(f"stooq returned empty price history for {ticker}")

        df = df.set_index("Date").sort_index()
        df = df.rename(columns={
            "Open": "Open", "High": "High", "Low": "Low", "Close": "Close", "Volume": "Volume",
        })

        cutoff = _period_to_days(period)
        if cutoff:
            df = df.loc[df.index >= (df.index.max() - pd.Timedelta(days=cutoff))]

        return df[["Open", "High", "Low", "Close", "Volume"]]

    def get_quote(self, ticker: str, fetch_fundamentals: bool = True) -> dict:
        # `fetch_fundamentals` is accepted for interface compatibility with
        # YFinanceProvider but has no effect here -- Stooq never has these
        # fields regardless (see fundamentals_unavailable below).
        history = self.get_price_history(ticker, period="5d")
        last = history.iloc[-1]
        return {
            "ticker": ticker.upper(),
            "company_name": ticker.upper(),
            "sector": None,
            "industry": None,
            "exchange": None,
            "current_price": float(last["Close"]),
            "volume": int(last["Volume"]) if pd.notna(last["Volume"]) else None,
            # Stooq has no fundamentals endpoint -- these stay None here.
            # Emergency-fallback quotes just won't have cap/revenue until
            # yfinance is reachable again.
            "market_cap": None,
            "revenue_ttm": None,
            # Always true for Stooq -- it never has book_value/PE/EPS/
            # dividend_yield/beta/sector/industry/profile fields at all, not
            # just "unavailable this call." Lets the frontend show an actual
            # "unavailable" message instead of a bare "—", the same as it
            # does for a rate-limited yfinance .info call (see
            # yfinance_provider.py's matching field).
            "fundamentals_unavailable": True,
        }


def _period_to_days(period: str) -> int | None:
    mapping = {"1y": 365, "2y": 730, "5y": 1825, "6mo": 182, "3mo": 92, "1mo": 31, "5d": 5}
    return mapping.get(period)
