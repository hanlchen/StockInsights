// Mirrors backend/app/schemas/stock.py and market.py -- keep in sync manually
// for now; consider generating from the OpenAPI schema once this grows.

export interface StockMetrics {
  ticker: string;
  company_name: string;
  sector: string | null;
  exchange: string | null;
  current_price: number | null;
  volume: number | null;

  market_cap: number | null;
  market_cap_bucket: "Large" | "Mid" | "Small" | null;
  revenue_ttm: number | null;

  business_summary: string | null;
  website: string | null;
  employees: number | null;
  ipo_date: string | null;

  book_value: number | null;
  price_to_book: number | null;
  trailing_pe: number | null;
  forward_pe: number | null;
  trailing_eps: number | null;
  forward_eps: number | null;
  dividend_yield: number | null;
  beta: number | null;
  fifty_two_week_high: number | null;
  fifty_two_week_low: number | null;

  pct_change_1d: number | null;
  pct_change_1w: number | null;
  pct_change_1y: number | null;
  pct_change_3y: number | null;

  momentum_trend: MomentumTrend | null;
  monthly_momentum_trend: MonthlyMomentumTrend | null;

  mae_proxy: number | null;
  mae_proxy_note: string;

  ytd_return: number | null;
  return_2y_cagr: number | null;
  return_5y_cagr: number | null;
  avg_ytd_2y: number | null;
  avg_ytd_5y: number | null;

  as_of: string;
  cache_hit: boolean;
}

// Oldest -> newest trailing-quarter % change over the past year (see
// backend/app/computation/returns.py momentum_trend()). All 4 are null
// together if there isn't a full year of history yet.
export interface MomentumTrend {
  m9_12: number | null;
  m6_9: number | null;
  m3_6: number | null;
  m0_3: number | null;
}

// Momentum v2: oldest -> newest trailing-MONTH % change over the past 6
// months (see backend/app/computation/returns.py monthly_momentum_trend()).
// All 6 are null together if there isn't a full 6 months of history yet.
export interface MonthlyMomentumTrend {
  m5_6: number | null;
  m4_5: number | null;
  m3_4: number | null;
  m2_3: number | null;
  m1_2: number | null;
  m0_1: number | null;
}

export type ChartPeriod = "1d" | "1mo" | "3mo" | "6mo" | "1y" | "5y";

export interface PriceHistoryPoint {
  date: string;
  close: number;
  open: number | null;
  high: number | null;
  low: number | null;
  volume: number | null;
}

export interface PriceHistoryResponse {
  ticker: string;
  period: ChartPeriod;
  points: PriceHistoryPoint[];
  as_of: string;
  cache_hit: boolean;
}

export interface QuarterlyFinancialPoint {
  period_end: string;
  revenue: number | null;
  gross_profit: number | null;
  operating_income: number | null;
  net_income: number | null;
  eps: number | null;
}

export interface QuarterlyFinancialsResponse {
  ticker: string;
  points: QuarterlyFinancialPoint[];
  as_of: string;
  cache_hit: boolean;
}

export interface SearchResult {
  ticker: string;
  company_name: string;
  exchange: string | null;
}

export interface SearchResponse {
  results: SearchResult[];
}

export type MoversPeriod = "1d" | "1w" | "1y" | "3y";
export type MarketCapBucket = "Large" | "Mid" | "Small";

export interface MoverEntry {
  ticker: string;
  company_name: string | null;
  sector: string | null;
  market_cap: number | null;
  market_cap_bucket: MarketCapBucket | null;
  revenue_ttm: number | null;
  pct_change: number;
}

export interface MarketOverview {
  period: MoversPeriod;
  market_cap_filter: MarketCapBucket | null;
  as_of: string | null;
  universe_size: number;
  universe_note: string;
  top_gainers: MoverEntry[];
  top_losers: MoverEntry[];
}

export interface SectorEntry {
  sector: string;
  avg_pct_change: number;
  direction: "up" | "down" | "flat";
  count: number;
}

export interface SectorPerformance {
  period: MoversPeriod;
  market_cap_filter: MarketCapBucket | null;
  as_of: string | null;
  sectors: SectorEntry[];
}

export interface ApiError {
  status: number;
  message: string;
}

export type TickerSortField =
  | "ticker"
  | "company_name"
  | "price"
  | "volume"
  | "market_cap"
  | "pct_change_1d"
  | "pct_change_1mo"
  | "pct_change_1y";
export type SortOrder = "asc" | "desc";

export interface TickerEntry {
  ticker: string;
  company_name: string | null;
  exchange: "NYSE" | "NASDAQ" | null;
  sector: string | null;
  industry: string | null;
  current_price: number | null;
  volume: number | null;
  market_cap: number | null;
  pct_change_1d: number | null;
  pct_change_1mo: number | null;
  pct_change_1y: number | null;
  is_sp500: boolean;
}

export interface TickerListResponse {
  items: TickerEntry[];
  total: number;
  page: number;
  page_size: number;
  as_of: string | null;
  sp500_data_available: boolean;
  universe_note: string;
}

export interface IndustryListResponse {
  industries: string[];
}

export interface MomentumEntry {
  ticker: string;
  company_name: string | null;
  sector: string | null;
  market_cap: number | null;
  market_cap_bucket: MarketCapBucket | null;
  revenue_ttm: number | null;
  momentum_m9_12: number;
  momentum_m6_9: number;
  momentum_m3_6: number;
  momentum_m0_3: number;
  avg_momentum: number;
}

export interface MomentumScreenerResponse {
  min_quarterly_return: number;
  market_cap_filter: MarketCapBucket | null;
  as_of: string | null;
  universe_size: number;
  matched_count: number;
  universe_note: string;
  results: MomentumEntry[];
}

// Momentum v2 (monthly). "avg" sorts by avg_monthly_momentum; any other
// value is one of the 6 month labels below (m0_1 = most recent month).
export type MonthlySortBy = "avg" | "m5_6" | "m4_5" | "m3_4" | "m2_3" | "m1_2" | "m0_1";

export interface MonthlyMomentumEntry {
  ticker: string;
  company_name: string | null;
  sector: string | null;
  market_cap: number | null;
  market_cap_bucket: MarketCapBucket | null;
  revenue_ttm: number | null;
  monthly_m5_6: number;
  monthly_m4_5: number;
  monthly_m3_4: number;
  monthly_m2_3: number;
  monthly_m1_2: number;
  monthly_m0_1: number;
  avg_monthly_momentum: number;
}

export interface MonthlyMomentumScreenerResponse {
  min_monthly_return: number | null;
  sort_by: MonthlySortBy;
  market_cap_filter: MarketCapBucket | null;
  as_of: string | null;
  universe_size: number;
  matched_count: number;
  universe_note: string;
  results: MonthlyMomentumEntry[];
}
