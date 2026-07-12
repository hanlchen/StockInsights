import logging

import pandas as pd

from app.providers.base import ProviderError, StockDataProvider

logger = logging.getLogger(__name__)


class ProviderChain(StockDataProvider):
    """
    Tries each provider in order, falling back to the next on failure.
    This is the 'fallback chain' called out in the architecture doc's
    scaling table -- wraps N providers behind the same StockDataProvider
    interface so services/routes never know a fallback happened.
    """

    name = "provider_chain"

    def __init__(self, providers: list[StockDataProvider]):
        if not providers:
            raise ValueError("ProviderChain requires at least one provider")
        self._providers = providers

    def get_price_history(self, ticker: str, period: str = "5y") -> pd.DataFrame:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return provider.get_price_history(ticker, period=period)
            except ProviderError as exc:
                logger.warning("Provider %s failed for %s: %s", provider.name, ticker, exc)
                errors.append(f"{provider.name}: {exc}")
        raise ProviderError(
            f"All providers failed to fetch price history for {ticker} -- " + " | ".join(errors)
        )

    def get_quote(self, ticker: str) -> dict:
        errors: list[str] = []
        for provider in self._providers:
            try:
                return provider.get_quote(ticker)
            except ProviderError as exc:
                logger.warning("Provider %s failed for %s: %s", provider.name, ticker, exc)
                errors.append(f"{provider.name}: {exc}")
        raise ProviderError(
            f"All providers failed to fetch quote for {ticker} -- " + " | ".join(errors)
        )

    def get_quarterly_financials(self, ticker: str, max_quarters: int = 8) -> list[dict]:
        """Unlike get_price_history/get_quote, a NotImplementedError here means
        'this provider has no financials endpoint at all' (e.g. Stooq), not a
        failed fetch -- skip straight to the next provider without logging it
        as a warning, since it's expected/permanent, not a runtime failure."""
        errors: list[str] = []
        for provider in self._providers:
            try:
                return provider.get_quarterly_financials(ticker, max_quarters=max_quarters)
            except NotImplementedError:
                continue
            except ProviderError as exc:
                logger.warning("Provider %s failed for %s: %s", provider.name, ticker, exc)
                errors.append(f"{provider.name}: {exc}")
        detail = " | ".join(errors) if errors else "no provider in the chain supports quarterly financials"
        raise ProviderError(f"All providers failed to fetch quarterly financials for {ticker} -- {detail}")
