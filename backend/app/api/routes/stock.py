from fastapi import APIRouter, HTTPException, Query

from app.schemas.stock import (
    PriceHistoryResponse,
    QuarterlyFinancialsResponse,
    SearchResponse,
    SearchResult,
    StockMetrics,
)
from app.services import stock_service
from app.services.universe import search_universe

router = APIRouter(prefix="/stock", tags=["stock"])


@router.get("/search", response_model=SearchResponse)
def search(q: str = Query("", min_length=0, max_length=50)) -> SearchResponse:
    results = search_universe(q)
    return SearchResponse(
        results=[
            SearchResult(ticker=r["ticker"], company_name=r["company_name"], exchange=r.get("exchange"))
            for r in results
        ]
    )


@router.get("/{ticker}", response_model=StockMetrics)
def get_stock(ticker: str) -> StockMetrics:
    try:
        metrics = stock_service.get_stock_metrics(ticker)
    except stock_service.TickerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except stock_service.UpstreamUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return StockMetrics(**metrics)


@router.get("/{ticker}/history", response_model=PriceHistoryResponse)
def get_stock_history(
    ticker: str,
    period: str = Query(
        stock_service.DEFAULT_HISTORY_PERIOD,
        description=f"One of {stock_service.VALID_HISTORY_PERIODS}",
    ),
) -> PriceHistoryResponse:
    try:
        history = stock_service.get_price_history(ticker, period=period)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except stock_service.TickerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except stock_service.UpstreamUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return PriceHistoryResponse(**history)


@router.get("/{ticker}/financials", response_model=QuarterlyFinancialsResponse)
def get_stock_financials(ticker: str) -> QuarterlyFinancialsResponse:
    try:
        financials = stock_service.get_quarterly_financials(ticker)
    except stock_service.TickerNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except stock_service.UpstreamUnavailableError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return QuarterlyFinancialsResponse(**financials)
