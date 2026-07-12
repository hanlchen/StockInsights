from datetime import datetime

from pydantic import BaseModel, Field


class MoverEntry(BaseModel):
    ticker: str
    company_name: str | None = None
    sector: str | None = None
    market_cap: float | None = None
    market_cap_bucket: str | None = None
    revenue_ttm: float | None = None
    pct_change: float


class MarketOverview(BaseModel):
    period: str
    market_cap_filter: str | None = None
    as_of: datetime | None = None
    universe_size: int = 0
    universe_note: str = (
        "Movers are computed across the full NYSE + NASDAQ common-stock "
        "universe (test issues and ETFs excluded), not a S&P 500 proxy -- "
        "see architecture doc assumptions. Data is refreshed by a scheduled "
        "batch job, not live per request; `as_of` is when that job last ran."
    )
    top_gainers: list[MoverEntry]
    top_losers: list[MoverEntry]


class SectorEntry(BaseModel):
    sector: str
    avg_pct_change: float
    direction: str  # "up" | "down" | "flat"
    count: int = 0


class SectorPerformance(BaseModel):
    period: str
    market_cap_filter: str | None = None
    as_of: datetime | None = None
    sectors: list[SectorEntry]


class TickerEntry(BaseModel):
    ticker: str
    company_name: str | None = None
    exchange: str | None = None
    sector: str | None = None
    industry: str | None = None
    current_price: float | None = None
    volume: int | None = None
    market_cap: float | None = None
    pct_change_1d: float | None = None
    pct_change_1mo: float | None = None
    pct_change_1y: float | None = None
    is_sp500: bool = False


class MomentumEntry(BaseModel):
    ticker: str
    company_name: str | None = None
    sector: str | None = None
    market_cap: float | None = None
    market_cap_bucket: str | None = None
    revenue_ttm: float | None = None
    momentum_m9_12: float
    momentum_m6_9: float
    momentum_m3_6: float
    momentum_m0_3: float
    avg_momentum: float


class MomentumScreenerResponse(BaseModel):
    min_quarterly_return: float
    market_cap_filter: str | None = None
    as_of: datetime | None = None
    universe_size: int = 0
    matched_count: int = 0
    universe_note: str = (
        "Screens the full NYSE + NASDAQ common-stock universe for stocks "
        "whose trailing-quarter momentum (see /stock/{ticker}'s "
        "momentum_trend) exceeded the threshold in EVERY one of the last 4 "
        "quarters -- sustained strength each quarter, not just a hot "
        "average pulled up by one big quarter. Ranked by the average of "
        "the 4 quarterly returns. Data is refreshed by a scheduled batch "
        "job; as_of is when that job last ran."
    )
    results: list[MomentumEntry]


class MonthlyMomentumEntry(BaseModel):
    ticker: str
    company_name: str | None = None
    sector: str | None = None
    market_cap: float | None = None
    market_cap_bucket: str | None = None
    revenue_ttm: float | None = None
    monthly_m5_6: float
    monthly_m4_5: float
    monthly_m3_4: float
    monthly_m2_3: float
    monthly_m1_2: float
    monthly_m0_1: float
    avg_monthly_momentum: float


class MonthlyMomentumScreenerResponse(BaseModel):
    min_monthly_return: float | None = None
    sort_by: str = "avg"
    market_cap_filter: str | None = None
    as_of: datetime | None = None
    universe_size: int = 0
    matched_count: int = 0
    universe_note: str = (
        "Momentum v2: screens the full NYSE + NASDAQ common-stock universe "
        "using 6 trailing MONTHLY returns (not quarterly) -- see "
        "/stock/{ticker}'s monthly_momentum_trend. min_monthly_return=null "
        "means 'All': every ticker with a full 6-month trend, no per-month "
        "threshold. Ranked by sort_by (average of the 6 months, or a "
        "specific month). Data is refreshed by a scheduled batch job; "
        "as_of is when that job last ran."
    )
    results: list[MonthlyMomentumEntry]


class TickerListResponse(BaseModel):
    items: list[TickerEntry]
    total: int
    page: int
    page_size: int
    as_of: datetime | None = None
    sp500_data_available: bool = True
    universe_note: str = (
        "Full NYSE + NASDAQ common-stock universe (test issues and ETFs "
        "excluded). is_sp500 reflects current S&P 500 membership fetched "
        "from Wikipedia -- if sp500_data_available is false, that fetch "
        "failed and every is_sp500 value here should be treated as unknown, "
        "not as 'not a member'."
    )


class IndustryListResponse(BaseModel):
    industries: list[str] = Field(
        default_factory=list,
        description=(
            "Sorted distinct industry names across the full universe, for the "
            "All Tickers page's industry filter. Empty if the refresh job "
            "hasn't populated computed_metrics yet."
        ),
    )
