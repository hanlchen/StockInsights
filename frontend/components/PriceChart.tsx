"use client";

import { useEffect, useMemo, useState } from "react";
import { useCallback } from "react";
import { ApiRequestError, getPriceHistory } from "@/lib/api";
import { changeColorClass, formatCurrency } from "@/lib/formatters";
import type { ChartPeriod, PriceHistoryPoint } from "@/types/stock";

const PERIOD_OPTIONS: { value: ChartPeriod; label: string }[] = [
  { value: "1d", label: "1D" },
  { value: "1mo", label: "1M" },
  { value: "3mo", label: "3M" },
  { value: "6mo", label: "6M" },
  { value: "1y", label: "1Y" },
  { value: "5y", label: "5Y" },
];

// SVG viewBox dimensions -- fixed coordinate space that scales to whatever
// the container renders at (width: 100%), so no resize listener is needed.
const VB_WIDTH = 700;
const VB_HEIGHT = 240;
const PAD_LEFT = 56;
const PAD_RIGHT = 12;
const PAD_TOP = 16;
const PAD_BOTTOM = 24;

function formatDateLabel(iso: string, period: ChartPeriod): string {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return iso;
  if (period === "1d") {
    return d.toLocaleTimeString("en-US", { hour: "numeric", minute: "2-digit" });
  }
  if (period === "1mo" || period === "3mo") {
    return d.toLocaleDateString("en-US", { month: "short", day: "numeric" });
  }
  return d.toLocaleDateString("en-US", { month: "short", year: "2-digit" });
}

export default function PriceChart({ ticker }: { ticker: string }) {
  const [period, setPeriod] = useState<ChartPeriod>("6mo");
  const [points, setPoints] = useState<PriceHistoryPoint[] | null>(null);
  const [asOf, setAsOf] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [hoverIndex, setHoverIndex] = useState<number | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      setHoverIndex(null);
      try {
        const res = await getPriceHistory(ticker, period);
        if (!cancelled) {
          setPoints(res.points);
          setAsOf(res.as_of);
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiRequestError
              ? `${e.status}: ${e.message}`
              : "Failed to load price history. Is the backend running?"
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
  }, [ticker, period]);

  const chart = useMemo(() => {
    if (!points || points.length < 2) return null;

    const closes = points.map((p) => p.close);
    const min = Math.min(...closes);
    const max = Math.max(...closes);
    const range = max - min || 1;

    const innerWidth = VB_WIDTH - PAD_LEFT - PAD_RIGHT;
    const innerHeight = VB_HEIGHT - PAD_TOP - PAD_BOTTOM;

    const xAt = (i: number) => PAD_LEFT + (i / (points.length - 1)) * innerWidth;
    const yAt = (close: number) => PAD_TOP + innerHeight - ((close - min) / range) * innerHeight;

    const linePath = points
      .map((p, i) => `${i === 0 ? "M" : "L"} ${xAt(i).toFixed(2)} ${yAt(p.close).toFixed(2)}`)
      .join(" ");

    const areaPath =
      `${linePath} L ${xAt(points.length - 1).toFixed(2)} ${(PAD_TOP + innerHeight).toFixed(2)} ` +
      `L ${xAt(0).toFixed(2)} ${(PAD_TOP + innerHeight).toFixed(2)} Z`;

    const first = closes[0];
    const last = closes[closes.length - 1];
    const pctChange = first !== 0 ? (last - first) / first : 0;
    const up = pctChange >= 0;

    return { min, max, xAt, yAt, linePath, areaPath, first, last, pctChange, up, innerWidth, innerHeight };
  }, [points]);

  const handleMove = useCallback(
    (e: React.MouseEvent<SVGRectElement>) => {
      if (!points || points.length === 0) return;
      const rect = e.currentTarget.getBoundingClientRect();
      const relX = ((e.clientX - rect.left) / rect.width) * VB_WIDTH;
      const innerWidth = VB_WIDTH - PAD_LEFT - PAD_RIGHT;
      const ratio = (relX - PAD_LEFT) / innerWidth;
      const idx = Math.round(ratio * (points.length - 1));
      setHoverIndex(Math.max(0, Math.min(points.length - 1, idx)));
    },
    [points]
  );

  // Matches the "up"/"down" colors defined in tailwind.config.js -- kept as
  // literal hex here (not a Tailwind class) since these are SVG stroke/fill
  // attributes, not className values.
  const lineColor = chart?.up ? "#16a34a" : "#dc2626";
  const hovered = hoverIndex !== null && points ? points[hoverIndex] : null;

  return (
    <div className="rounded-lg border border-neutral-800 p-4">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <div className="flex items-baseline gap-3">
          {chart && (
            <>
              <span className="text-lg font-mono font-semibold">
                {formatCurrency(hovered ? hovered.close : chart.last)}
              </span>
              <span className={`text-sm font-mono ${changeColorClass(chart.pctChange)}`}>
                {chart.up ? "+" : ""}
                {(chart.pctChange * 100).toFixed(2)}%{" "}
                <span className="text-neutral-500">
                  ({PERIOD_OPTIONS.find((o) => o.value === period)?.label})
                </span>
              </span>
            </>
          )}
        </div>
        <div className="flex gap-1">
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setPeriod(opt.value)}
              className={`rounded px-2.5 py-1 text-xs ${
                period === opt.value
                  ? "bg-neutral-100 text-neutral-900 font-semibold"
                  : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>
      </div>

      {loading && <div className="py-16 text-center text-sm text-neutral-500">Loading chart…</div>}
      {error && (
        <div className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {!loading && !error && chart && points && (
        <svg
          viewBox={`0 0 ${VB_WIDTH} ${VB_HEIGHT}`}
          className="w-full"
          style={{ height: 260 }}
          onMouseLeave={() => setHoverIndex(null)}
        >
          {/* y-axis gridlines + labels (min/mid/max) */}
          {[chart.max, (chart.max + chart.min) / 2, chart.min].map((val, i) => {
            const y = chart.yAt(val);
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
                  {formatCurrency(val)}
                </text>
              </g>
            );
          })}

          {/* x-axis date labels: first and last point */}
          <text x={PAD_LEFT} y={VB_HEIGHT - 6} textAnchor="start" className="fill-neutral-500" fontSize={10}>
            {formatDateLabel(points[0].date, period)}
          </text>
          <text
            x={VB_WIDTH - PAD_RIGHT}
            y={VB_HEIGHT - 6}
            textAnchor="end"
            className="fill-neutral-500"
            fontSize={10}
          >
            {formatDateLabel(points[points.length - 1].date, period)}
          </text>

          <path d={chart.areaPath} fill={lineColor} opacity={0.08} stroke="none" />
          <path d={chart.linePath} fill="none" stroke={lineColor} strokeWidth={1.75} />

          {hovered && hoverIndex !== null && (
            <g>
              <line
                x1={chart.xAt(hoverIndex)}
                x2={chart.xAt(hoverIndex)}
                y1={PAD_TOP}
                y2={PAD_TOP + chart.innerHeight}
                stroke="currentColor"
                className="text-neutral-600"
                strokeWidth={1}
                strokeDasharray="3 3"
              />
              <circle cx={chart.xAt(hoverIndex)} cy={chart.yAt(hovered.close)} r={3} fill={lineColor} />
            </g>
          )}

          {/* transparent overlay to capture hover across the whole plot area */}
          <rect
            x={PAD_LEFT}
            y={PAD_TOP}
            width={chart.innerWidth}
            height={chart.innerHeight}
            fill="transparent"
            onMouseMove={handleMove}
          />
        </svg>
      )}

      {!loading && !error && points && points.length < 2 && (
        <div className="py-16 text-center text-sm text-neutral-500">
          Not enough price history to chart this period.
        </div>
      )}

      {hovered && (
        <div className="mt-1 text-xs text-neutral-500">
          {period === "1d"
            ? new Date(hovered.date).toLocaleString("en-US", {
                month: "short",
                day: "numeric",
                hour: "numeric",
                minute: "2-digit",
              })
            : new Date(hovered.date).toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                year: "numeric",
              })}
        </div>
      )}
      {!hovered && asOf && (
        <div className="mt-1 text-xs text-neutral-500">Live from provider as of {new Date(asOf).toLocaleString()}</div>
      )}
    </div>
  );
}
