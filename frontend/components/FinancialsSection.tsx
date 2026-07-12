"use client";

import { useEffect, useState } from "react";
import { ApiRequestError, getQuarterlyFinancials } from "@/lib/api";
import {
  changeColorClass,
  formatCompactDollars,
  formatCurrency,
  formatPercent,
  formatSignedPercent,
} from "@/lib/formatters";
import type { QuarterlyFinancialPoint } from "@/types/stock";

const VB_WIDTH = 700;
const VB_HEIGHT = 220;
const PAD_LEFT = 56;
const PAD_RIGHT = 12;
const PAD_TOP = 28;
const PAD_BOTTOM = 28;

function quarterLabel(iso: string): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  const q = Math.floor(d.getUTCMonth() / 3) + 1;
  return `Q${q} '${String(d.getUTCFullYear()).slice(2)}`;
}

function Metric({ label, value, colorClass }: { label: string; value: string; colorClass?: string }) {
  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="text-xs text-neutral-500">{label}</div>
      <div className={`mt-1 font-mono text-lg font-semibold ${colorClass || ""}`}>{value}</div>
    </div>
  );
}

function RevenueBarChart({ points }: { points: QuarterlyFinancialPoint[] }) {
  const withRevenue = points.filter((p) => p.revenue !== null) as (QuarterlyFinancialPoint & {
    revenue: number;
  })[];

  if (withRevenue.length === 0) {
    return <div className="py-16 text-center text-sm text-neutral-500">No revenue data available.</div>;
  }

  const max = Math.max(...withRevenue.map((p) => p.revenue), 0);
  const innerWidth = VB_WIDTH - PAD_LEFT - PAD_RIGHT;
  const innerHeight = VB_HEIGHT - PAD_TOP - PAD_BOTTOM;
  const n = withRevenue.length;
  const slot = innerWidth / n;
  const barWidth = Math.min(48, slot * 0.55);

  return (
    <svg viewBox={`0 0 ${VB_WIDTH} ${VB_HEIGHT}`} className="w-full" style={{ height: 220 }}>
      {/* gridlines at 0 / mid / max */}
      {[max, max / 2, 0].map((val, i) => {
        const y = PAD_TOP + innerHeight - (val / (max || 1)) * innerHeight;
        return (
          <g key={i}>
            <line
              x1={PAD_LEFT}
              x2={VB_WIDTH - PAD_RIGHT}
              y1={y}
              y2={y}
              stroke="currentColor"
              className="text-neutral-800"
              strokeWidth={1}
            />
            <text x={PAD_LEFT - 8} y={y + 3} textAnchor="end" className="fill-neutral-500" fontSize={10}>
              {formatCompactDollars(val)}
            </text>
          </g>
        );
      })}

      {withRevenue.map((p, i) => {
        const barHeight = (p.revenue / (max || 1)) * innerHeight;
        const x = PAD_LEFT + i * slot + (slot - barWidth) / 2;
        const y = PAD_TOP + innerHeight - barHeight;

        const prev = i > 0 ? withRevenue[i - 1] : null;
        const qoq = prev && prev.revenue !== 0 ? (p.revenue - prev.revenue) / prev.revenue : null;
        const barColor = qoq === null ? "#737373" : qoq >= 0 ? "#16a34a" : "#dc2626";

        return (
          <g key={p.period_end}>
            <rect x={x} y={y} width={barWidth} height={Math.max(barHeight, 1)} fill={barColor} rx={2} />
            {qoq !== null && (
              <text
                x={x + barWidth / 2}
                y={y - 6}
                textAnchor="middle"
                fontSize={10}
                className={qoq >= 0 ? "fill-up" : "fill-down"}
              >
                {qoq >= 0 ? "+" : ""}
                {(qoq * 100).toFixed(0)}%
              </text>
            )}
            <text
              x={x + barWidth / 2}
              y={VB_HEIGHT - PAD_BOTTOM + 16}
              textAnchor="middle"
              className="fill-neutral-500"
              fontSize={10}
            >
              {quarterLabel(p.period_end)}
            </text>
          </g>
        );
      })}
    </svg>
  );
}

export default function FinancialsSection({ ticker }: { ticker: string }) {
  const [points, setPoints] = useState<QuarterlyFinancialPoint[] | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await getQuarterlyFinancials(ticker);
        if (!cancelled) {
          setPoints(res.points);
          setAsOf(res.as_of);
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiRequestError
              ? e.status === 404
                ? "No quarterly financials available for this ticker."
                : `${e.status}: ${e.message}`
              : "Failed to load financials. Is the backend running?"
          );
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    }
    load();
    return () => {
      cancelled = true;
    };
  }, [ticker]);

  const latest = points && points.length > 0 ? points[points.length - 1] : null;
  const prior = points && points.length > 1 ? points[points.length - 2] : null;
  const revenueQoQ =
    latest && prior && latest.revenue !== null && prior.revenue !== null && prior.revenue !== 0
      ? (latest.revenue - prior.revenue) / prior.revenue
      : null;
  const grossMargin =
    latest && latest.revenue ? (latest.gross_profit ?? null) !== null ? latest.gross_profit! / latest.revenue : null : null;
  const operatingMargin =
    latest && latest.revenue
      ? (latest.operating_income ?? null) !== null
        ? latest.operating_income! / latest.revenue
        : null
      : null;
  const netMargin =
    latest && latest.revenue ? (latest.net_income ?? null) !== null ? latest.net_income! / latest.revenue : null : null;

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="mb-3 flex items-baseline justify-between">
        <h2 className="text-sm font-semibold text-neutral-300">Financials (quarterly)</h2>
        {latest && (
          <span className="text-xs text-neutral-500">Latest: {quarterLabel(latest.period_end)}</span>
        )}
      </div>

      {loading && <div className="py-16 text-center text-sm text-neutral-500">Loading financials…</div>}
      {error && (
        <div className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {!loading && !error && points && (
        <>
          <RevenueBarChart points={points} />

          <div className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4">
            <Metric label="Revenue (latest Q)" value={formatCompactDollars(latest?.revenue)} />
            <Metric
              label="Revenue QoQ"
              value={formatSignedPercent(revenueQoQ)}
              colorClass={changeColorClass(revenueQoQ)}
            />
            <Metric label="Gross Profit" value={formatCompactDollars(latest?.gross_profit)} />
            <Metric label="Gross Margin" value={formatPercent(grossMargin)} />
            <Metric label="Operating Income" value={formatCompactDollars(latest?.operating_income)} />
            <Metric label="Operating Margin" value={formatPercent(operatingMargin)} />
            <Metric label="Net Income" value={formatCompactDollars(latest?.net_income)} />
            <Metric label="Net Margin" value={formatPercent(netMargin)} />
            <Metric label="EPS (diluted)" value={formatCurrency(latest?.eps)} />
          </div>

          {asOf && (
            <div className="mt-3 text-xs text-neutral-500">
              Live from provider as of {new Date(asOf).toLocaleString()}
            </div>
          )}
        </>
      )}
    </div>
  );
}
