import {
  formatCompactCount,
  formatCompactDollars,
  formatCurrency,
  formatVolume,
  formatYear,
} from "@/lib/formatters";
import type { StockMetrics } from "@/types/stock";

export default function PriceHeader({ metrics }: { metrics: StockMetrics }) {
  return (
    <div className="rounded-lg border border-neutral-800 p-5">
      <div className="flex flex-wrap items-end justify-between gap-4">
        <div>
          <div className="flex items-baseline gap-2">
            <h1 className="text-2xl font-bold font-mono">{metrics.ticker}</h1>
            {metrics.exchange && (
              <span className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-400">
                {metrics.exchange}
              </span>
            )}
            {metrics.market_cap_bucket && (
              <span className="rounded bg-neutral-800 px-2 py-0.5 text-xs text-neutral-400">
                {metrics.market_cap_bucket} cap
              </span>
            )}
          </div>
          <div className="text-neutral-400">{metrics.company_name}</div>
          {metrics.sector && <div className="text-xs text-neutral-500 mt-1">{metrics.sector}</div>}
          <div className="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-xs text-neutral-500">
            <span>Market cap {formatCompactDollars(metrics.market_cap)}</span>
            <span>Revenue (TTM) {formatCompactDollars(metrics.revenue_ttm)}</span>
            {metrics.employees !== null && <span>{formatCompactCount(metrics.employees)} employees</span>}
            {metrics.ipo_date && <span>Listed since {formatYear(metrics.ipo_date)}</span>}
            {metrics.website && (
              <a
                href={metrics.website}
                target="_blank"
                rel="noopener noreferrer"
                className="underline hover:text-neutral-300"
              >
                Website
              </a>
            )}
          </div>
        </div>
        <div className="text-right">
          <div className="text-3xl font-mono font-semibold">{formatCurrency(metrics.current_price)}</div>
          <div className="text-xs text-neutral-500">Vol {formatVolume(metrics.volume)}</div>
          {(metrics.fifty_two_week_low !== null || metrics.fifty_two_week_high !== null) && (
            <div className="text-xs text-neutral-500">
              52W {formatCurrency(metrics.fifty_two_week_low)} – {formatCurrency(metrics.fifty_two_week_high)}
            </div>
          )}
        </div>
      </div>
      {metrics.business_summary && (
        <p className="mt-4 text-sm leading-relaxed text-neutral-400">{metrics.business_summary}</p>
      )}
    </div>
  );
}
