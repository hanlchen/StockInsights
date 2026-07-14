from fastapi import APIRouter, HTTPException, Query

from app.computation.market_cap import VALID_BUCKETS
from app.computation.returns import PERIOD_TRADING_DAYS
from app.db.session import SessionLocal
from app.schemas.market import (
    DailyRecommendationResponse,
    IndustryListResponse,
    MarketOverview,
    MomentumScreenerResponse,
    MonthlyMomentumScreenerResponse,
    SectorPerformance,
    TickerListResponse,
)
from app.services import market_service, persistence

router = APIRouter(prefix="/market", tags=["market"])

VALID_PERIODS = tuple(PERIOD_TRADING_DAYS.keys())


@router.get("/overview", response_model=MarketOverview)
def overview(
    period: str = Query("1w", description=f"One of {VALID_PERIODS}"),
    top_n: int = Query(10, ge=1, le=100, description="Number of gainers/losers to return, max 100"),
    market_cap: str | None = Query(None, description=f"Filter by bucket: one of {VALID_BUCKETS}"),
) -> MarketOverview:
    try:
        data = market_service.get_market_overview(period=period, top_n=top_n, market_cap=market_cap)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {exc}") from exc
    return MarketOverview(**data)


@router.get("/sectors", response_model=SectorPerformance)
def sectors(
    period: str = Query("1w", description=f"One of {VALID_PERIODS}"),
    market_cap: str | None = Query(None, description=f"Filter by bucket: one of {VALID_BUCKETS}"),
) -> SectorPerformance:
    try:
        data = market_service.get_sector_performance(period=period, market_cap=market_cap)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Market data unavailable: {exc}") from exc
    return SectorPerformance(**data)


@router.get("/momentum-screener", response_model=MomentumScreenerResponse)
def momentum_screener(
    min_quarterly_return: float = Query(
        market_service.DEFAULT_MIN_QUARTERLY_RETURN,
        description="Minimum required return in EACH of the 4 trailing quarters, as a decimal (0.5 = 50%)",
    ),
    top_n: int = Query(
        market_service.DEFAULT_TOP_N, ge=1, le=market_service.MAX_TOP_N,
        description="Max number of matches to return, ranked by avg momentum",
    ),
    market_cap: str | None = Query(None, description=f"Filter by bucket: one of {VALID_BUCKETS}"),
) -> MomentumScreenerResponse:
    try:
        data = market_service.get_momentum_screener(
            min_quarterly_return=min_quarterly_return, top_n=top_n, market_cap=market_cap
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Momentum screener unavailable: {exc}") from exc
    return MomentumScreenerResponse(**data)


@router.get("/monthly-momentum-screener", response_model=MonthlyMomentumScreenerResponse)
def monthly_momentum_screener(
    min_monthly_return: float | None = Query(
        None,
        description=(
            "Minimum required return in EVERY one of the trailing 6 months, as a "
            "decimal (0.1 = 10%). Omit for 'All' -- no per-month threshold, just "
            "rank every ticker with a full 6-month trend."
        ),
    ),
    top_n: int = Query(
        market_service.DEFAULT_TOP_N, ge=1, le=market_service.MAX_TOP_N,
        description="Max number of matches to return, ranked by sort_by",
    ),
    market_cap: str | None = Query(None, description=f"Filter by bucket: one of {VALID_BUCKETS}"),
    sort_by: str = Query(
        "avg", description=f"One of {tuple(market_service.MONTHLY_MOMENTUM_SORT_FIELDS)}"
    ),
) -> MonthlyMomentumScreenerResponse:
    try:
        data = market_service.get_monthly_momentum_screener(
            min_monthly_return=min_monthly_return, top_n=top_n, market_cap=market_cap, sort_by=sort_by
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Monthly momentum screener unavailable: {exc}") from exc
    return MonthlyMomentumScreenerResponse(**data)


@router.get("/tickers", response_model=TickerListResponse)
def tickers(
    sort_by: str = Query("market_cap", description=f"One of {tuple(market_service.TICKER_SORT_FIELDS)}"),
    order: str = Query("desc", description="'asc' or 'desc'"),
    page: int = Query(1, ge=1),
    page_size: int = Query(
        market_service.DEFAULT_PAGE_SIZE, ge=1, le=market_service.MAX_PAGE_SIZE
    ),
    exchange: str | None = Query(None, description="Filter: 'NYSE' or 'NASDAQ'"),
    sp500_only: bool = Query(False, description="Only return current S&P 500 constituents"),
    search: str | None = Query(None, description="Filter by ticker/company name substring"),
    industry: str | None = Query(None, description="Filter by exact industry name (see /market/industries)"),
) -> TickerListResponse:
    try:
        data = market_service.get_ticker_list(
            sort_by=sort_by,
            order=order,
            page=page,
            page_size=page_size,
            exchange=exchange,
            sp500_only=sp500_only,
            search=search,
            industry=industry,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f"Ticker list unavailable: {exc}") from exc
    return TickerListResponse(**data)


@router.get("/industries", response_model=IndustryListResponse)
def industries() -> IndustryListResponse:
    return IndustryListResponse(industries=market_service.get_industry_list())


@router.get("/recommendation/today", response_model=DailyRecommendationResponse)
def recommendation_today() -> DailyRecommendationResponse:
    """Pure DB read of the latest AI-generated pick -- no live LLM call ever
    happens on this request path. See scripts/generate_recommendation.py
    (the daily batch job that actually writes this) and
    services/recommendation_service.py for how the pick is produced."""
    with SessionLocal() as db:
        data = persistence.get_latest_recommendation(db)
    if data is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "No AI pick of the day has been generated yet -- run "
                "`python -m scripts.generate_recommendation` (requires "
                "ANTHROPIC_API_KEY) after the daily refresh job."
            ),
        )
    return DailyRecommendationResponse(**data)
