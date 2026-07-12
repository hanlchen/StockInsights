import {
  changeColorClass,
  formatCurrency,
  formatDecimal,
  formatPercent,
  formatSignedPercent,
} from "@/lib/formatters";
import type { StockMetrics } from "@/types/stock";

function Metric({
  label,
  value,
  colorClass,
  tooltip,
}: {
  label: string;
  value: string;
  colorClass?: string;
  tooltip?: string;
}) {
  return (
    <div className="rounded-lg border border-neutral-800 p-4" title={tooltip}>
      <div className="text-xs text-neutral-500">{label}</div>
      <div className={`mt-1 font-mono text-lg font-semibold ${colorClass || ""}`}>{value}</div>
    </div>
  );
}

const MOMENTUM_STEPS: { key: keyof NonNullable<StockMetrics["momentum_trend"]>; label: string }[] = [
  { key: "m9_12", label: "9-12mo ago" },
  { key: "m6_9", label: "6-9mo ago" },
  { key: "m3_6", label: "3-6mo ago" },
  { key: "m0_3", label: "Last 3mo" },
];

function MomentumTrendRow({ trend }: { trend: StockMetrics["momentum_trend"] }) {
  const hasData = trend && MOMENTUM_STEPS.some((s) => trend[s.key] !== null);
  return (
    <div className="mt-4 rounded-lg border border-neutral-800 p-4">
      <div className="text-xs text-neutral-500">Momentum trend (quarterly, oldest → newest)</div>
      {hasData ? (
        <div className="mt-2 grid grid-cols-4 gap-2">
          {MOMENTUM_STEPS.map((step) => (
            <div key={step.key} className="text-center">
              <div className="text-[11px] text-neutral-500">{step.label}</div>
              <div className={`font-mono text-sm font-semibold ${changeColorClass(trend![step.key])}`}>
                {formatSignedPercent(trend![step.key])}
              </div>
            </div>
          ))}
        </div>
      ) : (
        <div className="mt-2 text-sm text-neutral-500">Not enough history yet (needs ~1Y of data)</div>
      )}
    </div>
  );
}

export default function StockMetricsCard({ metrics }: { metrics: StockMetrics }) {
  return (
    <div>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Metric
          label="1D Change"
          value={formatSignedPercent(metrics.pct_change_1d)}
          colorClass={changeColorClass(metrics.pct_change_1d)}
        />
        <Metric
          label="1W Change"
          value={formatSignedPercent(metrics.pct_change_1w)}
          colorClass={changeColorClass(metrics.pct_change_1w)}
        />
        <Metric
          label="1Y Change"
          value={formatSignedPercent(metrics.pct_change_1y)}
          colorClass={changeColorClass(metrics.pct_change_1y)}
        />
        <Metric
          label="3Y Change"
          value={formatSignedPercent(metrics.pct_change_3y)}
          colorClass={changeColorClass(metrics.pct_change_3y)}
        />
        <Metric
          label="YTD Return"
          value={formatSignedPercent(metrics.ytd_return)}
          colorClass={changeColorClass(metrics.ytd_return)}
        />
        <Metric
          label="2Y CAGR"
          value={formatSignedPercent(metrics.return_2y_cagr)}
          colorClass={changeColorClass(metrics.return_2y_cagr)}
        />
        <Metric
          label="5Y CAGR"
          value={formatSignedPercent(metrics.return_5y_cagr)}
          colorClass={changeColorClass(metrics.return_5y_cagr)}
        />
        <Metric label="Avg YTD (2Y)" value={formatSignedPercent(metrics.avg_ytd_2y)} />
        <Metric label="Avg YTD (5Y)" value={formatSignedPercent(metrics.avg_ytd_5y)} />
        <Metric
          label="MAE proxy"
          value={formatPercent(metrics.mae_proxy)}
          colorClass="text-down"
          tooltip={metrics.mae_proxy_note}
        />
      </div>
      <MomentumTrendRow trend={metrics.momentum_trend} />

      <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Metric label="Book Value/Share" value={formatCurrency(metrics.book_value)} />
        <Metric label="Price/Book" value={formatDecimal(metrics.price_to_book)} />
        <Metric label="P/E (trailing)" value={formatDecimal(metrics.trailing_pe)} />
        <Metric label="P/E (forward)" value={formatDecimal(metrics.forward_pe)} />
        <Metric label="EPS (trailing)" value={formatCurrency(metrics.trailing_eps)} />
        <Metric label="EPS (forward)" value={formatCurrency(metrics.forward_eps)} />
        <Metric label="Dividend Yield" value={formatPercent(metrics.dividend_yield)} />
        <Metric label="Beta" value={formatDecimal(metrics.beta)} />
      </div>

      <p className="mt-3 text-xs text-neutral-500">{metrics.mae_proxy_note}</p>
    </div>
  );
}
