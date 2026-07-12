"""
Return calculations. All functions take a date-indexed, ascending
pandas Series of close prices (see providers/base.py contract).

Assumptions (see architecture doc section 0):
- "Average YTD over 2Y/5Y" = average of each calendar year's FULL-YEAR
  return (Jan 1 close -> Dec 31 close), NOT a rolling window of the
  current in-progress YTD figure. Excludes the current year.
"""

from datetime import datetime

import pandas as pd


def ytd_return(price_series: pd.Series, as_of: datetime | None = None) -> float | None:
    """Year-to-date return as of `as_of` (defaults to latest available date)."""
    if price_series.empty:
        return None

    as_of = as_of or price_series.index.max()
    year_start = pd.Timestamp(year=as_of.year, month=1, day=1)

    ytd_slice = price_series.loc[price_series.index >= year_start]
    if ytd_slice.empty:
        return None

    start_price = ytd_slice.iloc[0]
    end_price = price_series.loc[price_series.index <= as_of].iloc[-1]

    if start_price == 0:
        return None
    return float((end_price - start_price) / start_price)


def cagr(price_series: pd.Series, years: float) -> float | None:
    """Cumulative Annualized Growth Rate over the full span of `price_series`."""
    if price_series.empty or years <= 0:
        return None

    start_price = price_series.iloc[0]
    end_price = price_series.iloc[-1]

    if start_price <= 0:
        return None
    return float((end_price / start_price) ** (1 / years) - 1)


def trailing_window(price_series: pd.Series, days: int) -> pd.Series:
    """Approximate a trailing N-calendar-day window using the last `days`
    worth of daily rows relative to the max date present. Falls back to the
    full series if fewer rows exist than requested (e.g. new listing)."""
    if price_series.empty:
        return price_series
    end = price_series.index.max()
    start = end - pd.Timedelta(days=days)
    window = price_series.loc[price_series.index >= start]
    return window if not window.empty else price_series


def average_ytd_over_years(price_series: pd.Series, n_years: int) -> float | None:
    """
    Average of each calendar year's full-year return (Jan 1 -> Dec 31 close)
    over the trailing n_years COMPLETE years. Excludes the current
    in-progress year. Returns None if no complete years are available
    (e.g. ticker IPO'd too recently).
    """
    if price_series.empty:
        return None

    current_year = price_series.index.max().year
    yearly_returns = []
    for y in range(current_year - n_years, current_year):
        yr_data = price_series[price_series.index.year == y]
        if yr_data.empty or yr_data.iloc[0] == 0:
            continue
        yearly_returns.append(float((yr_data.iloc[-1] - yr_data.iloc[0]) / yr_data.iloc[0]))

    if not yearly_returns:
        return None
    return sum(yearly_returns) / len(yearly_returns)


def last_week_change(price_series: pd.Series) -> float | None:
    """% change: close(last trading day) vs close(5 trading days prior)."""
    if len(price_series) < 6:
        return None
    end_price = price_series.iloc[-1]
    start_price = price_series.iloc[-6]
    if start_price == 0:
        return None
    return float((end_price - start_price) / start_price)


# Movers periods the user asked for (1 day / 1 month / 1 week / 1 year / 3
# year), expressed in trading days rather than calendar days so the window
# lines up with actual rows in the price series. ~252 trading days/year is
# the standard convention; "1mo" uses 21, same ~1-month convention as
# MONTH_TRADING_DAYS below. "1d" (trading_days=1) is just close(last row) vs
# close(the row before it) -- the same period_change() math as the others,
# no special-casing needed.
PERIOD_TRADING_DAYS: dict[str, int] = {"1d": 1, "1w": 5, "1mo": 21, "1y": 252, "3y": 756}


def period_change(price_series: pd.Series, trading_days: int) -> float | None:
    """Total % change over the trailing `trading_days` trading-day window:
    close(last row) vs close(trading_days rows before that). Returns None
    if there isn't enough history for the full window (e.g. a recent IPO
    doesn't have 3 years of data yet) rather than silently computing a
    shorter, misleading window."""
    if len(price_series) <= trading_days:
        return None
    end_price = price_series.iloc[-1]
    start_price = price_series.iloc[-(trading_days + 1)]
    if start_price == 0:
        return None
    return float((end_price - start_price) / start_price)


# Momentum trend: 4 sequential trailing-quarter returns (oldest to most
# recent), each a ~63-trading-day (1 quarter) window covering the last year:
# 9-12 months ago, 6-9 months ago, 3-6 months ago, and 0-3 months ago
# (today). Reading these 4 numbers in sequence shows whether a stock's
# growth is accelerating or decelerating quarter over quarter -- a single
# "1Y return" figure can't distinguish a stock that climbed steadily all
# year from one that ran up 11 months ago and has been flat/falling since.
QUARTER_TRADING_DAYS = 63
MOMENTUM_LABELS = ("m9_12", "m6_9", "m3_6", "m0_3")  # oldest -> most recent quarter


def _idx_quarters_ago(quarters_ago: int) -> int:
    """Row position `quarters_ago` quarters back from the most recent row
    (0 = today)."""
    return -1 if quarters_ago == 0 else -(quarters_ago * QUARTER_TRADING_DAYS) - 1


def momentum_trend(price_series: pd.Series) -> dict[str, float | None]:
    """4 sequential trailing-quarter % changes, oldest to newest, tracking
    momentum over the past year. Needs a full 4 quarters (~252 trading days)
    of history to fill in all 4 windows -- returns all-None instead of a
    partial trend, since a partial result would misleadingly look like "flat"
    quarters rather than "not enough history yet" (e.g. a recent IPO)."""
    if len(price_series) <= QUARTER_TRADING_DAYS * 4:
        return {label: None for label in MOMENTUM_LABELS}

    boundary_prices = [price_series.iloc[_idx_quarters_ago(q)] for q in (4, 3, 2, 1, 0)]

    result: dict[str, float | None] = {}
    for label, start_price, end_price in zip(MOMENTUM_LABELS, boundary_prices, boundary_prices[1:]):
        result[label] = float((end_price - start_price) / start_price) if start_price != 0 else None
    return result


# Monthly momentum ("momentum v2"): 6 sequential trailing-MONTH returns
# (oldest to most recent), each a ~21-trading-day window covering the last 6
# months. Finer-grained than momentum_trend()'s 4 quarters -- lets a
# screener require every SINGLE month (not just every quarter) to clear a
# threshold, e.g. "every one of the last 6 months returned 10%+", which a
# quarterly check could miss (a strong quarter can hide one bad month).
MONTH_TRADING_DAYS = 21
MONTHLY_MOMENTUM_LABELS = ("m5_6", "m4_5", "m3_4", "m2_3", "m1_2", "m0_1")  # oldest -> most recent month


def _idx_months_ago(months_ago: int) -> int:
    """Row position `months_ago` months back from the most recent row
    (0 = today). Same convention as _idx_quarters_ago, just a shorter period."""
    return -1 if months_ago == 0 else -(months_ago * MONTH_TRADING_DAYS) - 1


def monthly_momentum_trend(price_series: pd.Series) -> dict[str, float | None]:
    """6 sequential trailing-month % changes, oldest to newest, over the past
    6 months -- the monthly analogue of momentum_trend(). Needs a full 6
    months (~126 trading days) of history to fill in all 6 windows -- returns
    all-None instead of a partial trend for the same reason momentum_trend()
    does (a partial result would misleadingly look like "flat" months rather
    than "not enough history yet", e.g. a recent IPO)."""
    if len(price_series) <= MONTH_TRADING_DAYS * 6:
        return {label: None for label in MONTHLY_MOMENTUM_LABELS}

    boundary_prices = [price_series.iloc[_idx_months_ago(m)] for m in (6, 5, 4, 3, 2, 1, 0)]

    result: dict[str, float | None] = {}
    for label, start_price, end_price in zip(MONTHLY_MOMENTUM_LABELS, boundary_prices, boundary_prices[1:]):
        result[label] = float((end_price - start_price) / start_price) if start_price != 0 else None
    return result
