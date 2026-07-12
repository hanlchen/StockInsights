"use client";

import { Suspense, useEffect, useState } from "react";
import { ApiRequestError, getMomentumScreener, getMonthlyMomentumScreener } from "@/lib/api";
import { useQueryState } from "@/lib/useQueryState";
import MomentumScreenerTable from "@/components/MomentumScreenerTable";
import MonthlyMomentumTable from "@/components/MonthlyMomentumTable";
import type {
  MarketCapBucket,
  MomentumScreenerResponse,
  MonthlyMomentumScreenerResponse,
  MonthlySortBy,
} from "@/types/stock";

const CAP_OPTIONS: { value: MarketCapBucket | ""; label: string }[] = [
  { value: "", label: "All caps" },
  { value: "Large", label: "Large (>$10B)" },
  { value: "Mid", label: "Mid ($2B-$10B)" },
  { value: "Small", label: "Small (<$2B)" },
];

const TOP_N_OPTIONS = [10, 25, 50, 100];

type Tab = "quarterly" | "monthly";

export default function MomentumPage() {
  return (
    <Suspense fallback={<div className="text-neutral-500">Loading momentum screener…</div>}>
      <MomentumContent />
    </Suspense>
  );
}

function MomentumContent() {
  const { getParam, setParams } = useQueryState();
  // Active tab lives in the URL too (?tab=), same reasoning as every filter
  // below -- see lib/useQueryState.ts.
  const tab = (getParam("tab") as Tab) || "quarterly";

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-semibold mb-1">Momentum Screener</h1>
        <p className="text-sm text-neutral-500">
          Stocks with sustained strength over time -- ranked, not just a hot yearly average
          pulled up by one big period.
        </p>
      </div>

      <div className="flex gap-2 border-b border-neutral-800 text-sm">
        <TabButton active={tab === "quarterly"} onClick={() => setParams({ tab: "quarterly" })}>
          Quarterly
        </TabButton>
        <TabButton active={tab === "monthly"} onClick={() => setParams({ tab: "monthly" })}>
          Monthly (v2)
        </TabButton>
      </div>

      {tab === "quarterly" ? <QuarterlyTab /> : <MonthlyTab />}
    </div>
  );
}

function TabButton({
  active,
  onClick,
  children,
}: {
  active: boolean;
  onClick: () => void;
  children: React.ReactNode;
}) {
  return (
    <button
      onClick={onClick}
      className={`px-3 py-2 -mb-px border-b-2 ${
        active
          ? "border-neutral-100 text-neutral-100 font-semibold"
          : "border-transparent text-neutral-500 hover:text-neutral-300"
      }`}
    >
      {children}
    </button>
  );
}

const QUARTERLY_THRESHOLD_OPTIONS = [0.25, 0.5, 0.75, 1.0];

function QuarterlyTab() {
  const { getParam, setParams } = useQueryState();
  // Namespaced with a "q_" prefix so these don't collide with the Monthly
  // tab's own filters when both are reflected in the same URL.
  const minQuarterlyReturn = Number(getParam("q_min")) || 0.5;
  const marketCap = (getParam("q_cap") as MarketCapBucket) || "";
  const topN = Number(getParam("q_top")) || 25;

  const [data, setData] = useState<MomentumScreenerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await getMomentumScreener({
          minQuarterlyReturn,
          topN,
          marketCap: marketCap || null,
        });
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiRequestError
              ? `${e.status}: ${e.message}`
              : "Failed to load momentum screener. Is the backend running?"
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
  }, [minQuarterlyReturn, marketCap, topN]);

  return (
    <div className="space-y-6">
      <p className="text-sm text-neutral-500">
        Stocks whose return exceeded the threshold in EVERY one of the last 4 trailing quarters
        (9-12mo, 6-9mo, 3-6mo, last 3mo ago) -- sustained strength each quarter, not just a hot
        yearly average. Ranked by the average of the 4 quarters.
      </p>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-neutral-800 p-3 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-neutral-500">Min return per quarter</span>
          {QUARTERLY_THRESHOLD_OPTIONS.map((t) => (
            <button
              key={t}
              onClick={() => setParams({ q_min: t })}
              className={`rounded px-3 py-1 ${
                minQuarterlyReturn === t
                  ? "bg-neutral-100 text-neutral-900 font-semibold"
                  : "bg-neutral-800 text-neutral-300 hover:bg-neutral-700"
              }`}
            >
              {(t * 100).toFixed(0)}%
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <span className="text-neutral-500">Company size</span>
          <select
            value={marketCap}
            onChange={(e) => setParams({ q_cap: e.target.value || null })}
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
            onChange={(e) => setParams({ q_top: Number(e.target.value) })}
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

      {loading && <div className="text-neutral-500">Loading momentum screener…</div>}
      {error && (
        <div className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {data && (
        <>
          <p className="text-xs text-neutral-500">
            {data.universe_note} {data.matched_count.toLocaleString()} of{" "}
            {data.universe_size.toLocaleString()} tickers with a full 4-quarter trend matched.
            {data.as_of ? ` Last refreshed ${new Date(data.as_of).toLocaleString()}.` : ""}
          </p>
          <MomentumScreenerTable rows={data.results} />
        </>
      )}
    </div>
  );
}

// null = "All" (no per-month threshold at all, just rank everything with a full 6-month trend).
const MONTHLY_THRESHOLD_OPTIONS: { value: number | null; label: string }[] = [
  { value: 0.1, label: "10%" },
  { value: 0.2, label: "20%" },
  { value: 0.3, label: "30%" },
  { value: 0.5, label: "50%" },
  { value: null, label: "All" },
];

const SORT_OPTIONS: { value: MonthlySortBy; label: string }[] = [
  { value: "avg", label: "Avg (6mo)" },
  { value: "m0_1", label: "Last month" },
  { value: "m1_2", label: "1-2mo ago" },
  { value: "m2_3", label: "2-3mo ago" },
  { value: "m3_4", label: "3-4mo ago" },
  { value: "m4_5", label: "4-5mo ago" },
  { value: "m5_6", label: "5-6mo ago" },
];

function MonthlyTab() {
  const { getParam, setParams } = useQueryState();
  // Namespaced with an "m_" prefix -- see QuarterlyTab's "q_" comment above.
  // "All" is represented as the literal string "all" in the URL (a bare
  // missing param would be ambiguous with "haven't set a filter yet"),
  // and mapped back to null (the API/service's actual meaning of "All").
  const rawMin = getParam("m_min");
  const minMonthlyReturn = rawMin === null ? 0.1 : rawMin === "all" ? null : Number(rawMin);
  const marketCap = (getParam("m_cap") as MarketCapBucket) || "";
  const topN = Number(getParam("m_top")) || 25;
  const sortBy = (getParam("m_sort") as MonthlySortBy) || "avg";

  const [data, setData] = useState<MonthlyMomentumScreenerResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await getMonthlyMomentumScreener({
          minMonthlyReturn,
          topN,
          marketCap: marketCap || null,
          sortBy,
        });
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiRequestError
              ? `${e.status}: ${e.message}`
              : "Failed to load monthly momentum screener. Is the backend running?"
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
  }, [minMonthlyReturn, marketCap, topN, sortBy]);

  return (
    <div className="space-y-6">
      <p className="text-sm text-neutral-500">
        Stocks whose return exceeded the threshold in EVERY one of the last 6 trailing months --
        a finer-grained check than the quarterly tab, since one bad month can hide inside an
        otherwise strong quarter. "All" drops the per-month threshold entirely so you can just
        browse/sort every ticker with a full 6-month trend. Click a month column (or "Avg") to
        sort by it.
      </p>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-neutral-800 p-3 text-sm">
        <div className="flex items-center gap-2">
          <span className="text-neutral-500">Min return per month</span>
          {MONTHLY_THRESHOLD_OPTIONS.map((opt) => (
            <button
              key={opt.label}
              onClick={() => setParams({ m_min: opt.value === null ? "all" : opt.value })}
              className={`rounded px-3 py-1 ${
                minMonthlyReturn === opt.value
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
            onChange={(e) => setParams({ m_cap: e.target.value || null })}
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
          <span className="text-neutral-500">Sort by</span>
          <select
            value={sortBy}
            onChange={(e) => setParams({ m_sort: e.target.value })}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          >
            {SORT_OPTIONS.map((opt) => (
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
            onChange={(e) => setParams({ m_top: Number(e.target.value) })}
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

      {loading && <div className="text-neutral-500">Loading monthly momentum screener…</div>}
      {error && (
        <div className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {data && (
        <>
          <p className="text-xs text-neutral-500">
            {data.universe_note} {data.matched_count.toLocaleString()} of{" "}
            {data.universe_size.toLocaleString()} tickers with a full 6-month trend matched.
            {data.as_of ? ` Last refreshed ${new Date(data.as_of).toLocaleString()}.` : ""}
          </p>
          <MonthlyMomentumTable
            rows={data.results}
            sortBy={sortBy}
            onSortByChange={(next) => setParams({ m_sort: next })}
          />
        </>
      )}
    </div>
  );
}
