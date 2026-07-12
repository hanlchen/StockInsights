from datetime import datetime

from pydantic import BaseModel, Field


class StockMetrics(BaseModel):
    ticker: str
    company_name: str
    sector: str | None = None
    exchange: str | None = None
    current_price: float | None = None
    volume: int | None = None
    market_cap: float | None = None
    market_cap_bucket: str | None = Field(
        default=None, description="'Large' (>= $10B), 'Mid' ($2B-$10B), or 'Small' (< $2B)"
    )
    revenue_ttm: float | None = Field(
        default=None, description="Trailing-twelve-months revenue, in dollars."
    )

    business_summary: str | None = Field(
        default=None, description="What the company does, from Yahoo Finance's company profile."
    )
    website: str | None = None
    employees: int | None = Field(default=None, description="Full-time employee count.")
    ipo_date: datetime | None = Field(
        default=None,
        description=(
            "First trade/listing date on this exchange, the closest proxy Yahoo "
            "Finance offers to a 'founding year' -- not the company's actual "
            "founding date, which Yahoo does not track."
        ),
    )

    book_value: float | None = Field(default=None, description="Book value per share.")
    price_to_book: float | None = None
    trailing_pe: float | None = Field(default=None, description="P/E using trailing 12 months EPS.")
    forward_pe: float | None = Field(default=None, description="P/E using analysts' forward EPS estimate.")
    trailing_eps: float | None = None
    forward_eps: float | None = None
    dividend_yield: float | None = Field(
        default=None, description="Trailing dividend yield as a decimal (e.g. 0.02 = 2%)."
    )
    beta: float | None = Field(default=None, description="Volatility relative to the overall market.")
    fifty_two_week_high: float | None = None
    fifty_two_week_low: float | None = None

    pct_change_1d: float | None = None
    pct_change_1w: float | None = None
    pct_change_1mo: float | None = None
    pct_change_1y: float | None = None
    pct_change_3y: float | None = None

    momentum_trend: dict[str, float | None] | None = Field(
        default=None,
        description=(
            "4 sequential trailing-quarter % changes tracking momentum over the "
            "past year, oldest to newest: m9_12 (9-12mo ago), m6_9 (6-9mo ago), "
            "m3_6 (3-6mo ago), m0_3 (last 3mo). None (all keys) if there isn't a "
            "full year of history yet."
        ),
    )
    monthly_momentum_trend: dict[str, float | None] | None = Field(
        default=None,
        description=(
            "Momentum v2: 6 sequential trailing-MONTH % changes over the past 6 "
            "months, oldest to newest: m5_6, m4_5, m3_4, m2_3, m1_2, m0_1 (last "
            "month). Finer-grained than momentum_trend. None (all keys) if there "
            "isn't a full 6 months of history yet."
        ),
    )

    mae_proxy: float | None = Field(
        default=None,
        description="Approximate max drawdown proxy, NOT literal MAE. See mae_proxy_note.",
    )
    mae_proxy_note: str = (
        "Approximate max drawdown from trailing 1Y local peak, not true trade-based MAE"
    )

    ytd_return: float | None = None
    return_2y_cagr: float | None = None
    return_5y_cagr: float | None = None
    avg_ytd_2y: float | None = None
    avg_ytd_5y: float | None = None

    as_of: datetime
    cache_hit: bool = False


class PriceHistoryPoint(BaseModel):
    date: datetime
    close: float
    open: float | None = None
    high: float | None = None
    low: float | None = None
    volume: int | None = None


class PriceHistoryResponse(BaseModel):
    ticker: str
    period: str
    points: list[PriceHistoryPoint]
    as_of: datetime
    cache_hit: bool = False


class QuarterlyFinancialPoint(BaseModel):
    period_end: datetime
    revenue: float | None = None
    gross_profit: float | None = None
    operating_income: float | None = None
    net_income: float | None = None
    eps: float | None = Field(default=None, description="Diluted EPS, falling back to basic EPS.")


class QuarterlyFinancialsResponse(BaseModel):
    ticker: str
    points: list[QuarterlyFinancialPoint] = Field(
        default_factory=list,
        description="Oldest -> newest, most recent quarters available (up to 8).",
    )
    as_of: datetime
    cache_hit: bool = False


class SearchResult(BaseModel):
    ticker: str
    company_name: str
    exchange: str | None = None


class SearchResponse(BaseModel):
    results: list[SearchResult]
