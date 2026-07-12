"""
Market-wide movers + sector performance, read straight from the DB.

This used to live-fetch ~500 S&P 500 tickers via yf.download() on every
request. That doesn't scale to the full NYSE+NASDAQ universe (~6,000-9,000
tickers) -- a live per-request fetch at that size is exactly what caused the
"socket hang up" failures before. Per the user's explicit choice (scheduled
batch job over live-per-request), the actual fetching + computing now happens
in scripts/refresh_cache.py, which writes one row per ticker into
computed_metrics. This module is a pure, fast DB read + rank/aggregate layer
-- no network calls, no long-running requests.

If computed_metrics is empty (fresh install, refresh job never run), these
functions raise a RuntimeError with instructions rather than returning an
empty/misleading response.
"""

from app.computation.market_cap import VALID_BUCKETS
from app.computation.returns import PERIOD_TRADING_DAYS
from app.db.session import SessionLocal
from app.services import persistence
from app.services.sp500 import get_sp500_tickers

VALID_PERIODS = tuple(PERIOD_TRADING_DAYS.keys())  # ("1d", "1w", "1y", "3y")
# Kept as an explicit mapping (not derived from PERIOD_TRADING_DAYS) so a
# future PERIOD_TRADING_DAYS addition can't silently produce a KeyError here
# -- adding a period to VALID_PERIODS without a matching column here is now a
# visible dict-literal diff to review, not a runtime surprise.
PCT_FIELD_BY_PERIOD = {
    "1d": "pct_change_1d",
    "1w": "pct_change_1w",
    "1mo": "pct_change_1mo",
    "1y": "pct_change_1y",
    "3y": "pct_change_3y",
}

MAX_TOP_N = 100
DEFAULT_TOP_N = 10

# The 4 trailing-quarter momentum columns (see computation/returns.py
# momentum_trend() / db/models.py ComputedMetrics), oldest to newest.
MOMENTUM_FIELDS = ("momentum_m9_12", "momentum_m6_9", "momentum_m3_6", "momentum_m0_3")
DEFAULT_MIN_QUARTERLY_RETURN = 0.5

# Momentum v2: the 6 trailing-MONTH momentum columns (see computation/
# returns.py monthly_momentum_trend() / db/models.py ComputedMetrics), oldest
# to newest. Finer-grained than MOMENTUM_FIELDS above -- a screener here can
# require every SINGLE month to clear a threshold, not just every quarter.
MONTHLY_MOMENTUM_FIELDS = (
    "monthly_m5_6", "monthly_m4_5", "monthly_m3_4",
    "monthly_m2_3", "monthly_m1_2", "monthly_m0_1",
)
# Suggested initial UI threshold (10%) -- NOT the API/service default. The
# actual default is "All" (None, no per-month threshold at all): see
# get_monthly_momentum_screener().
DEFAULT_MIN_MONTHLY_RETURN = 0.1

# sort_by values accepted by get_monthly_momentum_screener(): "avg" (average
# of the 6 months) or one of the 6 month labels (e.g. "m0_1" = most recent
# month, "m5_6" = 5-6 months ago) -- lets a caller ask "who grew the most
# last month" instead of only "who grew the most on average".
MONTHLY_MOMENTUM_SORT_FIELDS: dict[str, str | None] = {"avg": None}
for _field in MONTHLY_MOMENTUM_FIELDS:
    MONTHLY_MOMENTUM_SORT_FIELDS[_field.removeprefix("monthly_")] = _field
del _field

# Full ticker list (get_ticker_list) -- separate from the movers/sectors
# knobs above since this is a plain browse/sort view, not a ranked top-N.
TICKER_SORT_FIELDS = {
    "ticker": "ticker",
    "company_name": "company_name",
    "price": "current_price",
    "volume": "volume",
    "market_cap": "market_cap",
    "pct_change_1d": "pct_change_1d",
    "pct_change_1mo": "pct_change_1mo",
    "pct_change_1y": "pct_change_1y",
}
DEFAULT_PAGE_SIZE = 50
MAX_PAGE_SIZE = 200


def _validate_period(period: str) -> str:
    if period not in VALID_PERIODS:
        raise ValueError(f"Invalid period '{period}' -- must be one of {VALID_PERIODS}")
    return period


def _validate_market_cap(bucket: str | None) -> str | None:
    if bucket is not None and bucket not in VALID_BUCKETS:
        raise ValueError(f"Invalid market_cap '{bucket}' -- must be one of {VALID_BUCKETS} or omitted")
    return bucket


def _load_rows(market_cap_filter: str | None) -> list[dict]:
    with SessionLocal() as db:
        rows = persistence.get_all_market_rows(db, market_cap_filter=market_cap_filter)
    if not rows:
        raise RuntimeError(
            "No computed metrics in the database yet -- run "
            "`python -m scripts.refresh_cache` to populate the full NYSE/NASDAQ "
            "universe before movers/sector data is available."
        )
    return rows


def _as_of(rows: list[dict]):
    timestamps = [r["computed_at"] for r in rows if r.get("computed_at")]
    return max(timestamps) if timestamps else None


def _to_mover(row: dict, pct_field: str) -> dict:
    return {
        "ticker": row["ticker"],
        "company_name": row["company_name"],
        "sector": row["sector"],
        "market_cap": row["market_cap"],
        "market_cap_bucket": row["market_cap_bucket"],
        "revenue_ttm": row["revenue_ttm"],
        "pct_change": row[pct_field],
    }


def get_market_overview(period: str = "1w", top_n: int = DEFAULT_TOP_N, market_cap: str | None = None) -> dict:
    period = _validate_period(period)
    market_cap = _validate_market_cap(market_cap)
    top_n = max(1, min(top_n, MAX_TOP_N))
    pct_field = PCT_FIELD_BY_PERIOD[period]

    rows = _load_rows(market_cap)
    entries = [r for r in rows if r.get(pct_field) is not None]
    ranked = sorted(entries, key=lambda r: r[pct_field], reverse=True)

    top_gainers = [_to_mover(r, pct_field) for r in ranked[:top_n]]
    losers_slice = list(reversed(ranked[-top_n:])) if len(ranked) >= top_n else list(reversed(ranked))
    top_losers = [_to_mover(r, pct_field) for r in losers_slice]

    return {
        "period": period,
        "market_cap_filter": market_cap,
        "as_of": _as_of(rows),
        "universe_size": len(rows),
        "top_gainers": top_gainers,
        "top_losers": top_losers,
    }


def get_sector_performance(period: str = "1w", market_cap: str | None = None) -> dict:
    period = _validate_period(period)
    market_cap = _validate_market_cap(market_cap)
    pct_field = PCT_FIELD_BY_PERIOD[period]

    rows = _load_rows(market_cap)

    by_sector: dict[str, list[float]] = {}
    for r in rows:
        if r.get(pct_field) is None:
            continue
        sector = r["sector"] or "Unknown"
        by_sector.setdefault(sector, []).append(r[pct_field])

    sectors = []
    for sector, changes in by_sector.items():
        avg = sum(changes) / len(changes)
        direction = "up" if avg > 0.001 else "down" if avg < -0.001 else "flat"
        sectors.append({
            "sector": sector,
            "avg_pct_change": avg,
            "direction": direction,
            "count": len(changes),
        })

    sectors.sort(key=lambda s: s["avg_pct_change"], reverse=True)

    return {
        "period": period,
        "market_cap_filter": market_cap,
        "as_of": _as_of(rows),
        "sectors": sectors,
    }


def _to_momentum_entry(row: dict, avg_momentum: float) -> dict:
    return {
        "ticker": row["ticker"],
        "company_name": row["company_name"],
        "sector": row["sector"],
        "market_cap": row["market_cap"],
        "market_cap_bucket": row["market_cap_bucket"],
        "revenue_ttm": row["revenue_ttm"],
        "momentum_m9_12": row["momentum_m9_12"],
        "momentum_m6_9": row["momentum_m6_9"],
        "momentum_m3_6": row["momentum_m3_6"],
        "momentum_m0_3": row["momentum_m0_3"],
        "avg_momentum": avg_momentum,
    }


def get_momentum_screener(
    min_quarterly_return: float = DEFAULT_MIN_QUARTERLY_RETURN,
    top_n: int = DEFAULT_TOP_N,
    market_cap: str | None = None,
) -> dict:
    """Stocks where EVERY one of the 4 trailing-quarter momentum windows
    (9-12mo/6-9mo/3-6mo/0-3mo ago) exceeded `min_quarterly_return` --
    e.g. 0.5 means every single quarter over the past year returned more
    than 50%, not just the year as a whole. This is a strict "sustained
    strength each quarter" filter, deliberately stricter than sorting by
    pct_change_1y, which a single huge quarter could dominate. Ranked by
    the average of the 4 qualifying quarters, ties broken by ticker order
    from the DB read."""
    market_cap = _validate_market_cap(market_cap)
    top_n = max(1, min(top_n, MAX_TOP_N))

    rows = _load_rows(market_cap)
    has_full_trend = [r for r in rows if all(r.get(f) is not None for f in MOMENTUM_FIELDS)]
    qualifying = [r for r in has_full_trend if all(r[f] > min_quarterly_return for f in MOMENTUM_FIELDS)]

    scored = [(r, sum(r[f] for f in MOMENTUM_FIELDS) / len(MOMENTUM_FIELDS)) for r in qualifying]
    scored.sort(key=lambda pair: pair[1], reverse=True)

    return {
        "min_quarterly_return": min_quarterly_return,
        "market_cap_filter": market_cap,
        "as_of": _as_of(rows),
        "universe_size": len(has_full_trend),
        "matched_count": len(scored),
        "results": [_to_momentum_entry(r, avg) for r, avg in scored[:top_n]],
    }


def _to_monthly_momentum_entry(row: dict, avg_momentum: float) -> dict:
    return {
        "ticker": row["ticker"],
        "company_name": row["company_name"],
        "sector": row["sector"],
        "market_cap": row["market_cap"],
        "market_cap_bucket": row["market_cap_bucket"],
        "revenue_ttm": row["revenue_ttm"],
        "monthly_m5_6": row["monthly_m5_6"],
        "monthly_m4_5": row["monthly_m4_5"],
        "monthly_m3_4": row["monthly_m3_4"],
        "monthly_m2_3": row["monthly_m2_3"],
        "monthly_m1_2": row["monthly_m1_2"],
        "monthly_m0_1": row["monthly_m0_1"],
        "avg_monthly_momentum": avg_momentum,
    }


def _validate_monthly_sort_by(sort_by: str) -> str:
    if sort_by not in MONTHLY_MOMENTUM_SORT_FIELDS:
        raise ValueError(
            f"Invalid sort_by '{sort_by}' -- must be one of {tuple(MONTHLY_MOMENTUM_SORT_FIELDS)}"
        )
    return sort_by


def get_monthly_momentum_screener(
    min_monthly_return: float | None = None,
    top_n: int = DEFAULT_TOP_N,
    market_cap: str | None = None,
    sort_by: str = "avg",
) -> dict:
    """Momentum v2: stocks where EVERY one of the trailing 6 monthly windows
    exceeded `min_monthly_return` -- e.g. 0.1 means every single month over
    the past 6 months returned more than 10%, a stricter/finer-grained
    version of get_momentum_screener()'s quarterly check (a strong quarter
    can hide one bad month; this can't). `min_monthly_return=None` ("All",
    the default) skips the per-month threshold entirely and just ranks every
    ticker that has a full 6-month trend -- use this to browse/sort without
    filtering. Ranked by `sort_by`: "avg" (average of the 6 months, default)
    or a specific month label (e.g. "m0_1" = most recent month), ties broken
    by ticker order from the DB read."""
    market_cap = _validate_market_cap(market_cap)
    sort_by = _validate_monthly_sort_by(sort_by)
    top_n = max(1, min(top_n, MAX_TOP_N))

    rows = _load_rows(market_cap)
    has_full_trend = [r for r in rows if all(r.get(f) is not None for f in MONTHLY_MOMENTUM_FIELDS)]

    if min_monthly_return is None:
        qualifying = has_full_trend
    else:
        qualifying = [
            r for r in has_full_trend
            if all(r[f] > min_monthly_return for f in MONTHLY_MOMENTUM_FIELDS)
        ]

    scored = [
        (r, sum(r[f] for f in MONTHLY_MOMENTUM_FIELDS) / len(MONTHLY_MOMENTUM_FIELDS))
        for r in qualifying
    ]

    sort_field = MONTHLY_MOMENTUM_SORT_FIELDS[sort_by]
    if sort_field is None:  # "avg"
        scored.sort(key=lambda pair: pair[1], reverse=True)
    else:
        scored.sort(key=lambda pair: pair[0][sort_field], reverse=True)

    return {
        "min_monthly_return": min_monthly_return,
        "sort_by": sort_by,
        "market_cap_filter": market_cap,
        "as_of": _as_of(rows),
        "universe_size": len(has_full_trend),
        "matched_count": len(scored),
        "results": [_to_monthly_momentum_entry(r, avg) for r, avg in scored[:top_n]],
    }


def _validate_sort_by(sort_by: str) -> str:
    if sort_by not in TICKER_SORT_FIELDS:
        raise ValueError(f"Invalid sort_by '{sort_by}' -- must be one of {tuple(TICKER_SORT_FIELDS)}")
    return sort_by


def _to_ticker_entry(row: dict) -> dict:
    return {
        "ticker": row["ticker"],
        "company_name": row["company_name"],
        "exchange": row["exchange"],
        "sector": row["sector"],
        "industry": row.get("industry"),
        "current_price": row["current_price"],
        "volume": row.get("volume"),
        "market_cap": row["market_cap"],
        "pct_change_1d": row.get("pct_change_1d"),
        "pct_change_1mo": row.get("pct_change_1mo"),
        "pct_change_1y": row.get("pct_change_1y"),
        "is_sp500": row.get("is_sp500", False),
    }


def get_industry_list() -> list[str]:
    """Distinct industry names for the All Tickers page's filter dropdown.
    Returns an empty list (not an error) if the refresh job hasn't run yet --
    an empty dropdown is a benign degraded state here, unlike movers/sectors
    where no data at all means the whole response would be misleading."""
    with SessionLocal() as db:
        return persistence.get_distinct_industries(db)


def get_ticker_list(
    *,
    sort_by: str = "market_cap",
    order: str = "desc",
    page: int = 1,
    page_size: int = DEFAULT_PAGE_SIZE,
    exchange: str | None = None,
    sp500_only: bool = False,
    search: str | None = None,
    industry: str | None = None,
) -> dict:
    """Plain browse/sort/paginate view over the full universe -- unlike
    get_market_overview/get_sector_performance (ranked top-N by % change),
    this returns every ticker matching the filters, one page at a time,
    since the point is 'let me look at all ~6,700 rows', not 'show me the
    extremes'."""
    sort_by = _validate_sort_by(sort_by)
    if order not in ("asc", "desc"):
        raise ValueError("order must be 'asc' or 'desc'")
    if exchange is not None and exchange not in ("NYSE", "NASDAQ"):
        raise ValueError("exchange must be 'NYSE' or 'NASDAQ'")
    page = max(1, page)
    page_size = max(1, min(page_size, MAX_PAGE_SIZE))

    rows = _load_rows(None)
    sp500_tickers = get_sp500_tickers()
    for r in rows:
        r["is_sp500"] = r["ticker"] in sp500_tickers

    if exchange:
        rows = [r for r in rows if r.get("exchange") == exchange]
    if search:
        q = search.strip().upper()
        rows = [
            r for r in rows
            if q in r["ticker"].upper() or q in (r.get("company_name") or "").upper()
        ]
    if sp500_only:
        rows = [r for r in rows if r["is_sp500"]]
    if industry:
        rows = [r for r in rows if r.get("industry") == industry]

    field = TICKER_SORT_FIELDS[sort_by]
    # Null values always sort last regardless of asc/desc -- a plain
    # `reverse=True` sort would otherwise put None values first on a
    # descending sort (None compares as "less than" nothing consistently in
    # Python, so mixed None/number sorts raise TypeError without this split).
    with_value = [r for r in rows if r.get(field) is not None]
    without_value = [r for r in rows if r.get(field) is None]
    with_value.sort(key=lambda r: r[field], reverse=(order == "desc"))
    sorted_rows = with_value + without_value

    total = len(sorted_rows)
    start = (page - 1) * page_size
    page_rows = sorted_rows[start:start + page_size]

    return {
        "items": [_to_ticker_entry(r) for r in page_rows],
        "total": total,
        "page": page,
        "page_size": page_size,
        "as_of": _as_of(rows),
        "sp500_data_available": bool(sp500_tickers),
    }
