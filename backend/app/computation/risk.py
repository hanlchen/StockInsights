"""
Risk / drawdown calculations.

IMPORTANT: There is no free data source that provides true trade-based MAE
(Maximum Adverse Excursion), which requires an actual entry point. Everything
here is a PROXY: max drawdown from a trailing local peak over a rolling
window of daily closes. It must always be surfaced to callers/UI labeled as
`mae_proxy`, never as literal MAE. See architecture doc section 0.
"""

import pandas as pd


def mae_proxy(price_series: pd.Series, window_days: int = 252) -> float | None:
    """
    Approximate Maximum Adverse Excursion.
    Defined as the max drawdown from a trailing local peak within the window:
        drawdown(t) = (price(t) - running_max(t)) / running_max(t)
    Returns the most negative drawdown value in the window (i.e. worst case),
    or None if there isn't enough data.
    """
    if price_series.empty:
        return None

    recent = price_series.tail(window_days)
    if recent.empty:
        return None

    running_max = recent.cummax()
    drawdown = (recent - running_max) / running_max
    value = drawdown.min()
    return float(value) if pd.notna(value) else None


MAE_PROXY_NOTE = (
    "Approximate max drawdown from trailing 1Y local peak, not true trade-based MAE"
)
