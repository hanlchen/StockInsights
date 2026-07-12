"use client";

import { Suspense, useEffect, useState } from "react";
import { ApiRequestError, getMarketOverview, getSectorPerformance } from "@/lib/api";
import { useQueryState } from "@/lib/useQueryState";
import MoversTable from "@/components/MoversTable";
import SectorPerformanceTable from "@/components/SectorPerformanceTable";
import SearchBar from "@/components/SearchBar";
import type { MarketCapBucket, MarketOverview, MoversPeriod, SectorPerformance } from "@/types/stock";

const PERIOD_OPTIONS: { value: MoversPeriod; label: string }[] = [
  { value: "1d", label: "1 Day" },
  { value: "1w", label: "1 Week" },
  { value: "1y", label: "1 Year" },
  { value: "3y", label: "3 Year" },
];

const CAP_OPTIONS: { value: MarketCapBucket | ""; label: string }[] = [
  { value: "", label: "All caps" },
  { value: "Large", label: "Large (>$10B)" },
  { value: "Mid", label: "Mid ($2B-$10B)" },
  { value: "Small", label: "Small (<$2B)" },
];

const TOP_N_OPTIONS = [10, 25, 50, 100];

export default function DashboardPage() {
  return (
    <Suspense fallback={<div className="text-neutral-500">Loading market data…</div>}>
      <DashboardContent />
    </Suspense>
  );
}

function DashboardContent() {
  const { getParam, setParams } = useQueryState();

  // Filters live in the URL (?period=&market_cap=&top_n=), not local state --
  // that's what makes the browser Back button restore them instead of
  // resetting to defaults. See lib/useQueryState.ts.
  const period = (getParam("period") as MoversPeriod) || "1w";
  const marketCap = (getParam("market_cap") as MarketCapBucket) || "";
  const topN = Number(getParam("top_n")) || 10;

  const [overview, setOverview] = useState<MarketOverview | null>(null);
  const [sectors, setSectors] = useState<SectorPerformance | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const capFilter = marketCap || null;
        const [ov, sec] = await Promise.all([
          getMarketOverview({ period, topN, marketCap: capFilter }),
          getSectorPerformance({ period, marketCap: capFilter }),
        ]);
        if (!cancelled) {
          setOverview(ov);
          setSectors(sec);
        }
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiRequestError
              ? `${e.status}: ${e.message}`
              : "Failed to load market data. Is the backend running?"
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
  }, [period, marketCap, topN]);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold mb-3">NYSE + NASDAQ Market Overview</h1>
        <SearchBar />
      </div>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-neutral-800 p-3 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-neutral-500">Period</span>
          {PERIOD_OPTIONS.map((opt) => (
            <button
              key={opt.value}
              onClick={() => setParams({ period: opt.value })}
              className={`rounded px-3 py-1 ${
                period === opt.value
                  ? "bg-neutral-100 text-neutral-900 font-semibold"
                  : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
              }`}
            >
              {opt.label}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-neutral-500">Company size</span>
          <select
            value={marketCap}
            onChange={(e) => setParams({ market_cap: e.target.value || null })}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          >
            {CAP_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-neutral-500">Show top</span>
          <select
            value={topN}
            onChange={(e) => setParams({ top_n: Number(e.target.value) })}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          >
            {TOP_N_OPTIONS.map((n) => (
              <option key={n} value={n}>
                {n}
              </option>
            ))}
          </select>
        </div>
      </div>

      {loading && <div className="text-neutral-500">Loading market data…</div>}
      {error && (
        <div className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {overview && (
        <>
          <p className="text-xs text-neutral-500">
            {overview.universe_note} {overview.universe_size.toLocaleString()} tickers covered.
            {overview.as_of ? ` Last refreshed ${new Date(overview.as_of).toLocaleString()}.` : ""}
          </p>
          <div className="grid gap-4 md:grid-cols-2">
            <MoversTable title="Top Gainers" rows={overview.top_gainers} />
            <MoversTable title="Top Losers" rows={overview.top_losers} />
          </div>
        </>
      )}

      {sectors && <SectorPerformanceTable sectors={sectors.sectors} period={period} />}
    </div>
  );
}
