"""
DB read/write helpers for stocks + computed_metrics. Both the single-ticker
on-demand path (stock_service.get_stock_metrics) and the full-universe batch
job (scripts/refresh_cache.py) write through here, so there's exactly one
place that knows the upsert logic and the computed_metrics -> API-dict shape.

Deliberately uses portable "SELECT then update-or-insert" upserts rather than
a dialect-specific ON CONFLICT clause -- this app runs on SQLite today and
Postgres later (per architecture doc), and this way the same code works on
both without an if/else per dialect.
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.computation.market_cap import market_cap_bucket
from app.db.models import ComputedMetrics, Stock


def upsert_stock(
    db: Session,
    *,
    ticker: str,
    company_name: str,
    sector: str | None,
    industry: str | None,
    exchange: str | None,
    business_summary: str | None = None,
    website: str | None = None,
    employees: int | None = None,
    ipo_date=None,
) -> Stock:
    obj = db.get(Stock, ticker)
    if obj is None:
        obj = Stock(ticker=ticker)
        db.add(obj)
    obj.company_name = company_name
    obj.sector = sector
    obj.industry = industry
    obj.exchange = exchange
    # Profile fields are best-effort (see yfinance_provider.py) -- only
    # overwrite when a fresh value came back, so a transient `.info` miss on
    # a later refresh doesn't blank out a profile field a prior refresh
    # successfully captured.
    if business_summary is not None:
        obj.business_summary = business_summary
    if website is not None:
        obj.website = website
    if employees is not None:
        obj.employees = employees
    if ipo_date is not None:
        obj.ipo_date = ipo_date
    return obj


def upsert_computed_metrics(db: Session, ticker: str, metrics: dict) -> ComputedMetrics:
    """`metrics` may be a partial dict (e.g. single-ticker lookups don't
    compute pct_change_1w/1y/3y the batch job does) -- only keys present are
    written, everything else on the row is left as-is."""
    obj = db.get(ComputedMetrics, ticker)
    if obj is None:
        obj = ComputedMetrics(ticker=ticker)
        db.add(obj)

    fields = (
        "current_price", "volume", "mae_proxy", "ytd_return", "return_2y",
        "return_5y", "avg_ytd_2y", "avg_ytd_5y", "market_cap", "revenue_ttm",
        "pct_change_1d", "pct_change_1w", "pct_change_1mo", "pct_change_1y", "pct_change_3y",
        "momentum_m9_12", "momentum_m6_9", "momentum_m3_6", "momentum_m0_3",
        "monthly_m5_6", "monthly_m4_5", "monthly_m3_4", "monthly_m2_3",
        "monthly_m1_2", "monthly_m0_1",
        "book_value", "price_to_book", "trailing_pe", "forward_pe",
        "trailing_eps", "forward_eps", "dividend_yield", "beta",
        "fifty_two_week_high", "fifty_two_week_low",
    )
    for field in fields:
        if field in metrics:
            setattr(obj, field, metrics[field])

    if "market_cap" in metrics:
        obj.market_cap_bucket = market_cap_bucket(metrics["market_cap"])

    return obj


def get_distinct_industries(db: Session) -> list[str]:
    """Sorted distinct industry names, for the All Tickers page's industry
    filter dropdown. Scoped to stocks that have a computed_metrics row (i.e.
    have actually been through a refresh) so the dropdown never offers an
    industry with zero visible tickers behind it."""
    query = (
        select(Stock.industry)
        .join(ComputedMetrics, Stock.ticker == ComputedMetrics.ticker)
        .where(Stock.industry.is_not(None))
        .distinct()
    )
    return sorted({row[0] for row in db.execute(query).all() if row[0]})


def get_recently_computed_tickers(db: Session, since) -> set[str]:
    """Tickers whose computed_metrics row was written/updated at or after
    `since` (a naive UTC datetime, matching how SQLite's CURRENT_TIMESTAMP
    is stored/read back). Used by scripts/refresh_cache.py's --resume flag
    to skip re-fetching tickers an interrupted prior run already completed,
    instead of hammering yfinance/Stooq for the whole universe again."""
    query = select(ComputedMetrics.ticker).where(ComputedMetrics.computed_at >= since)
    return {row[0] for row in db.execute(query).all()}


def get_all_market_rows(db: Session, market_cap_filter: str | None = None) -> list[dict]:
    """Joins stocks + computed_metrics for every ticker that has a computed
    row (i.e. has been through the refresh job or an on-demand lookup at
    least once). Returns plain dicts, not ORM objects, so callers don't
    hold a session open."""
    query = select(Stock, ComputedMetrics).join(ComputedMetrics, Stock.ticker == ComputedMetrics.ticker)
    if market_cap_filter:
        query = query.where(ComputedMetrics.market_cap_bucket == market_cap_filter)

    rows = db.execute(query).all()
    return [
        {
            "ticker": stock.ticker,
            "company_name": stock.company_name,
            "sector": stock.sector,
            "industry": stock.industry,
            "exchange": stock.exchange,
            "current_price": metrics.current_price,
            "volume": metrics.volume,
            "market_cap": metrics.market_cap,
            "market_cap_bucket": metrics.market_cap_bucket,
            "revenue_ttm": metrics.revenue_ttm,
            "pct_change_1d": metrics.pct_change_1d,
            "pct_change_1w": metrics.pct_change_1w,
            "pct_change_1mo": metrics.pct_change_1mo,
            "pct_change_1y": metrics.pct_change_1y,
            "pct_change_3y": metrics.pct_change_3y,
            "momentum_m9_12": metrics.momentum_m9_12,
            "momentum_m6_9": metrics.momentum_m6_9,
            "momentum_m3_6": metrics.momentum_m3_6,
            "momentum_m0_3": metrics.momentum_m0_3,
            "monthly_m5_6": metrics.monthly_m5_6,
            "monthly_m4_5": metrics.monthly_m4_5,
            "monthly_m3_4": metrics.monthly_m3_4,
            "monthly_m2_3": metrics.monthly_m2_3,
            "monthly_m1_2": metrics.monthly_m1_2,
            "monthly_m0_1": metrics.monthly_m0_1,
            "computed_at": metrics.computed_at,
        }
        for stock, metrics in rows
    ]
