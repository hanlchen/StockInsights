"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { ApiRequestError, getStockMetrics } from "@/lib/api";
import PriceHeader from "@/components/PriceHeader";
import PriceChart from "@/components/PriceChart";
import FinancialsSection from "@/components/FinancialsSection";
import StockMetricsCard from "@/components/StockMetricsCard";
import type { StockMetrics } from "@/types/stock";

export default function StockDetailPage() {
  const params = useParams<{ ticker: string }>();
  const ticker = params.ticker;

  const [metrics, setMetrics] = useState<StockMetrics | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const data = await getStockMetrics(ticker);
        if (!cancelled) setMetrics(data);
      } catch (e) {
        if (!cancelled) {
          if (e instanceof ApiRequestError && e.status === 404) {
            setError(`Unknown ticker "${ticker.toUpperCase()}"`);
          } else if (e instanceof ApiRequestError && e.status === 503) {
            setError("Data provider unavailable right now. Try again shortly.");
          } else {
            setError("Failed to load stock data. Is the backend running?");
          }
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

  return (
    <div className="space-y-6">
      {loading && <div className="text-neutral-500">Loading {ticker.toUpperCase()}…</div>}
      {error && (
        <div className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}
      {metrics && (
        <>
          <PriceHeader metrics={metrics} />
          <PriceChart ticker={ticker} />
          <FinancialsSection ticker={ticker} />
          <StockMetricsCard metrics={metrics} />
          <div className="text-xs text-neutral-500">
            As of {new Date(metrics.as_of).toLocaleString()}
            {metrics.cache_hit ? " (cached)" : ""}
          </div>
        </>
      )}
    </div>
  );
}
