import type {
  ChartPeriod,
  IndustryListResponse,
  MarketCapBucket,
  MarketOverview,
  MomentumScreenerResponse,
  MonthlyMomentumScreenerResponse,
  MonthlySortBy,
  MoversPeriod,
  PriceHistoryResponse,
  QuarterlyFinancialsResponse,
  SearchResponse,
  SectorPerformance,
  SortOrder,
  StockMetrics,
  TickerListResponse,
  TickerSortField,
} from "@/types/stock";

// Requests go through Next.js rewrites (see next.config.js) to same-origin
// /api/*, which proxy to the FastAPI backend server-side. This means the
// browser never needs CORS and the backend URL stays a server-only detail.
const API_BASE = "/api/v1";

export class ApiRequestError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
    this.name = "ApiRequestError";
  }
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers || {}) },
    cache: "no-store",
  });

  if (!res.ok) {
    let detail = res.statusText;
    try {
      const body = await res.json();
      detail = body.detail || detail;
    } catch {
      // ignore parse failure, use statusText
    }
    throw new ApiRequestError(res.status, detail);
  }

  return res.json() as Promise<T>;
}

export function getStockMetrics(ticker: string): Promise<StockMetrics> {
  return request<StockMetrics>(`/stock/${encodeURIComponent(ticker)}`);
}

export function searchStocks(query: string): Promise<SearchResponse> {
  return request<SearchResponse>(`/stock/search?q=${encodeURIComponent(query)}`);
}

export function getPriceHistory(
  ticker: string,
  period: ChartPeriod = "6mo"
): Promise<PriceHistoryResponse> {
  return request<PriceHistoryResponse>(
    `/stock/${encodeURIComponent(ticker)}/history?period=${period}`
  );
}

export function getQuarterlyFinancials(ticker: string): Promise<QuarterlyFinancialsResponse> {
  return request<QuarterlyFinancialsResponse>(`/stock/${encodeURIComponent(ticker)}/financials`);
}

export interface MoversParams {
  period?: MoversPeriod;
  topN?: number;
  marketCap?: MarketCapBucket | null;
}

function buildQuery(params: Record<string, string | number | null | undefined>): string {
  const usp = new URLSearchParams();
  for (const [key, value] of Object.entries(params)) {
    if (value !== null && value !== undefined && value !== "") usp.set(key, String(value));
  }
  const qs = usp.toString();
  return qs ? `?${qs}` : "";
}

export function getMarketOverview(params: MoversParams = {}): Promise<MarketOverview> {
  const qs = buildQuery({
    period: params.period ?? "1w",
    top_n: params.topN ?? 10,
    market_cap: params.marketCap ?? undefined,
  });
  return request<MarketOverview>(`/market/overview${qs}`);
}

export function getSectorPerformance(
  params: Omit<MoversParams, "topN"> = {}
): Promise<SectorPerformance> {
  const qs = buildQuery({
    period: params.period ?? "1w",
    market_cap: params.marketCap ?? undefined,
  });
  return request<SectorPerformance>(`/market/sectors${qs}`);
}

export interface TickerListParams {
  sortBy?: TickerSortField;
  order?: SortOrder;
  page?: number;
  pageSize?: number;
  exchange?: "NYSE" | "NASDAQ" | null;
  sp500Only?: boolean;
  search?: string;
  industry?: string | null;
}

export function getIndustryList(): Promise<IndustryListResponse> {
  return request<IndustryListResponse>("/market/industries");
}

export interface MomentumScreenerParams {
  minQuarterlyReturn?: number;
  topN?: number;
  marketCap?: MarketCapBucket | null;
}

export function getMomentumScreener(
  params: MomentumScreenerParams = {}
): Promise<MomentumScreenerResponse> {
  const qs = buildQuery({
    min_quarterly_return: params.minQuarterlyReturn ?? 0.5,
    top_n: params.topN ?? 25,
    market_cap: params.marketCap ?? undefined,
  });
  return request<MomentumScreenerResponse>(`/market/momentum-screener${qs}`);
}

export interface MonthlyMomentumScreenerParams {
  minMonthlyReturn?: number | null; // null/undefined = "All" (no per-month threshold)
  topN?: number;
  marketCap?: MarketCapBucket | null;
  sortBy?: MonthlySortBy;
}

export function getMonthlyMomentumScreener(
  params: MonthlyMomentumScreenerParams = {}
): Promise<MonthlyMomentumScreenerResponse> {
  const qs = buildQuery({
    min_monthly_return: params.minMonthlyReturn ?? undefined,
    top_n: params.topN ?? 25,
    market_cap: params.marketCap ?? undefined,
    sort_by: params.sortBy ?? "avg",
  });
  return request<MonthlyMomentumScreenerResponse>(`/market/monthly-momentum-screener${qs}`);
}

export function getTickerList(params: TickerListParams = {}): Promise<TickerListResponse> {
  const qs = buildQuery({
    sort_by: params.sortBy ?? "market_cap",
    order: params.order ?? "desc",
    page: params.page ?? 1,
    page_size: params.pageSize ?? 50,
    exchange: params.exchange ?? undefined,
    sp500_only: params.sp500Only ? "true" : undefined,
    search: params.search ?? undefined,
    industry: params.industry ?? undefined,
  });
  return request<TickerListResponse>(`/market/tickers${qs}`);
}
