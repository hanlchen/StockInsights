from sqlalchemy import (
    CheckConstraint,
    Column,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import relationship

from app.db.session import Base


class Stock(Base):
    __tablename__ = "stocks"

    ticker = Column(String, primary_key=True)
    company_name = Column(String, nullable=False)
    sector = Column(String, nullable=True)
    industry = Column(String, nullable=True)
    exchange = Column(String, nullable=True)

    # Company profile fields (project decision 2026-07-06): slow-changing
    # descriptive data, sourced from yfinance's `.info` dict same as
    # sector/industry -- lives on Stock (not computed_metrics) since it's a
    # profile attribute, not a per-refresh computed number.
    business_summary = Column(Text, nullable=True)
    website = Column(String, nullable=True)
    employees = Column(Integer, nullable=True)
    # Yahoo/yfinance has no true "founding year" field -- this is the
    # stock's first trade/listing date (IPO on this exchange), the closest
    # available proxy. See yfinance_provider.py's get_quote() for detail.
    ipo_date = Column(DateTime, nullable=True)

    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        CheckConstraint("exchange IN ('NYSE', 'NASDAQ') OR exchange IS NULL", name="ck_exchange"),
    )


class PriceHistory(Base):
    __tablename__ = "price_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    ticker = Column(String, ForeignKey("stocks.ticker"), nullable=False)
    date = Column(DateTime, nullable=False)
    open = Column(Float)
    high = Column(Float)
    low = Column(Float)
    close = Column(Float, nullable=False)
    volume = Column(Integer)

    __table_args__ = (UniqueConstraint("ticker", "date", name="uq_ticker_date"),)


class ComputedMetrics(Base):
    """One row per ticker, overwritten in place on each refresh (see
    services/persistence.py) -- this is a "latest snapshot" table, not a
    time series. Populated by scripts/refresh_cache.py for the whole
    universe, and opportunistically by stock_service.get_stock_metrics()
    for a single ticker on-demand lookups.
    """

    __tablename__ = "computed_metrics"

    ticker = Column(String, ForeignKey("stocks.ticker"), primary_key=True)
    current_price = Column(Float)
    volume = Column(Integer)
    mae_proxy = Column(Float)
    ytd_return = Column(Float)
    return_2y = Column(Float)
    return_5y = Column(Float)
    avg_ytd_2y = Column(Float)
    avg_ytd_5y = Column(Float)

    # Added for full-exchange movers/filtering (see project decisions
    # 2026-07-05): market cap + a precomputed 3-tier bucket so the
    # market-cap filter is a plain indexed string match, not a per-request
    # recompute; trailing-twelve-months revenue; and total-return over the
    # three explicit movers windows the user asked for (1 week/1 year/3
    # year), computed from price history rather than re-derived at request
    # time so movers endpoints can be a pure DB read.
    market_cap = Column(Float, nullable=True)
    market_cap_bucket = Column(String, nullable=True)  # "Large" | "Mid" | "Small"
    revenue_ttm = Column(Float, nullable=True)
    pct_change_1d = Column(Float, nullable=True)
    pct_change_1w = Column(Float, nullable=True)
    pct_change_1mo = Column(Float, nullable=True)
    pct_change_1y = Column(Float, nullable=True)
    pct_change_3y = Column(Float, nullable=True)

    # Momentum trend (project decision 2026-07-06): 4 trailing-quarter
    # returns over the last year, oldest to newest, flattened into columns
    # since computed_metrics is a flat "latest snapshot" table -- see
    # computation/returns.py's momentum_trend() for the calculation and
    # stock_service.py's _persist_best_effort() for where the nested API
    # dict gets flattened into these 4 fields.
    momentum_m9_12 = Column(Float, nullable=True)
    momentum_m6_9 = Column(Float, nullable=True)
    momentum_m3_6 = Column(Float, nullable=True)
    momentum_m0_3 = Column(Float, nullable=True)

    # Monthly momentum / "momentum v2" (project decision 2026-07-10): 6
    # trailing-MONTH returns over the last 6 months, oldest to newest --
    # finer-grained than momentum_m9_12 etc (quarterly) so a screener can
    # require e.g. "every single month >= 10%" instead of every quarter. See
    # computation/returns.py's monthly_momentum_trend().
    monthly_m5_6 = Column(Float, nullable=True)
    monthly_m4_5 = Column(Float, nullable=True)
    monthly_m3_4 = Column(Float, nullable=True)
    monthly_m2_3 = Column(Float, nullable=True)
    monthly_m1_2 = Column(Float, nullable=True)
    monthly_m0_1 = Column(Float, nullable=True)

    # Valuation/fundamentals (project decision 2026-07-06), sourced from
    # yfinance's `.info` dict -- live here (not on Stock) since, unlike
    # business_summary/website, these change with the market and get
    # refreshed on the same cadence as price/market_cap.
    book_value = Column(Float, nullable=True)
    price_to_book = Column(Float, nullable=True)
    trailing_pe = Column(Float, nullable=True)
    forward_pe = Column(Float, nullable=True)
    trailing_eps = Column(Float, nullable=True)
    forward_eps = Column(Float, nullable=True)
    dividend_yield = Column(Float, nullable=True)
    beta = Column(Float, nullable=True)
    fifty_two_week_high = Column(Float, nullable=True)
    fifty_two_week_low = Column(Float, nullable=True)

    computed_at = Column(DateTime, server_default=func.now(), onupdate=func.now())


class User(Base):
    """Multi-tenancy-ready from day one. MVP has no auth, so rows here are
    unused, but watchlists.user_id can reference this table once auth ships
    -- additive, not a migration nightmare."""

    __tablename__ = "users"

    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, unique=True, nullable=True)
    created_at = Column(DateTime, server_default=func.now())

    watchlists = relationship("Watchlist", back_populates="user")


class Watchlist(Base):
    __tablename__ = "watchlists"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)  # NULL in single-user MVP
    ticker = Column(String, ForeignKey("stocks.ticker"), nullable=False)
    added_at = Column(DateTime, server_default=func.now())

    user = relationship("User", back_populates="watchlists")
