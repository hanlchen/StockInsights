from abc import ABC, abstractmethod

import pandas as pd


class ProviderError(Exception):
    """Raised when a provider fails to fetch data. Caught by the service
    layer to trigger fallback to the next provider in the chain."""


class StockDataProvider(ABC):
    """
    Single interface every data source implements. The API layer and
    frontend never talk to yfinance/stooq/etc directly -- everything
    routes through this abstraction, which is what lets you swap or
    chain data sources without touching routes or UI. This is the other
    interface (besides Cache) worth over-investing in per the
    architecture doc.
    """

    name: str = "base"

    @abstractmethod
    def get_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        """Returns OHLCV DataFrame, date-indexed (tz-naive), ascending.
        Columns: Open, High, Low, Close, Volume. Raises ProviderError on failure."""
        ...

    @abstractmethod
    def get_quote(self, ticker: str) -> dict:
        """Returns current price, volume, company name, sector, industry,
        market_cap, and revenue_ttm (trailing-twelve-months revenue), plus
        best-effort profile/fundamentals fields (business_summary, website,
        employees, ipo_date, book_value, price_to_book, trailing_pe,
        forward_pe, trailing_eps, forward_eps, dividend_yield, beta,
        fifty_two_week_high, fifty_two_week_low). Any of these may be None
        if a provider can't source fundamentals (e.g. Stooq, the emergency
        fallback, only returns the required core fields). Raises
        ProviderError on failure."""
        ...

    def search(self, query: str) -> list[dict]:
        """Optional: providers may not support search (e.g. yfinance doesn't
        natively). Default: not supported. Use universe.py local search instead."""
        raise NotImplementedError(f"{self.name} does not support search")

    def get_quarterly_financials(self, ticker: str, max_quarters: int = 8) -> list[dict]:
        """Optional: quarterly income-statement line items -- revenue,
        gross_profit, operating_income, net_income, eps -- one dict per
        quarter, oldest -> newest, for the most recent `max_quarters`
        quarters. Any field may be None if a provider doesn't report it.
        Not every provider has a financials endpoint (Stooq is OHLCV-only).
        Default: not supported."""
        raise NotImplementedError(f"{self.name} does not support quarterly financials")
