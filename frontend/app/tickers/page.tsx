"use client";

import { Suspense, useEffect, useState } from "react";
import { ApiRequestError, getIndustryList, getTickerList } from "@/lib/api";
import { useQueryState } from "@/lib/useQueryState";
import TickerTable from "@/components/TickerTable";
import type { SortOrder, TickerListResponse, TickerSortField } from "@/types/stock";

const PAGE_SIZE = 50;

const EXCHANGE_OPTIONS: { value: "" | "NYSE" | "NASDAQ"; label: string }[] = [
  { value: "", label: "All exchanges" },
  { value: "NYSE", label: "NYSE" },
  { value: "NASDAQ", label: "NASDAQ" },
];

export default function TickersPage() {
  return (
    <Suspense fallback={<div className="text-neutral-500">Loading tickers…</div>}>
      <TickersContent />
    </Suspense>
  );
}

function TickersContent() {
  const { getParam, setParams } = useQueryState();

  // Filters live in the URL, not local state -- see lib/useQueryState.ts.
  // That's what makes the browser Back button land on the same sort/page/
  // filters you left, instead of resetting to page 1 with no filters.
  const sortBy = (getParam("sort_by") as TickerSortField) || "market_cap";
  const order = (getParam("order") as SortOrder) || "desc";
  const page = Number(getParam("page")) || 1;
  const exchange = (getParam("exchange") as "" | "NYSE" | "NASDAQ") || "";
  const sp500Only = getParam("sp500_only") === "true";
  const search = getParam("search") || "";
  const industry = getParam("industry") || "";

  const [data, setData] = useState<TickerListResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  // Industry options for the filter dropdown -- fetched once, independent of
  // the current filters (it should always list every industry, not just the
  // ones matching what's currently selected).
  const [industries, setIndustries] = useState<string[]>([]);

  useEffect(() => {
    let cancelled = false;
    getIndustryList()
      .then((res) => {
        if (!cancelled) setIndustries(res.industries);
      })
      .catch(() => {
        // Non-critical -- the dropdown just stays empty (only "All
        // industries") if this fails; the main ticker list load below
        // surfaces the real error if the backend itself is down.
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    let cancelled = false;
    async function load() {
      setLoading(true);
      setError(null);
      try {
        const res = await getTickerList({
          sortBy,
          order,
          page,
          pageSize: PAGE_SIZE,
          exchange: exchange || null,
          sp500Only,
          search: search.trim() || undefined,
          industry: industry || null,
        });
        if (!cancelled) setData(res);
      } catch (e) {
        if (!cancelled) {
          setError(
            e instanceof ApiRequestError
              ? `${e.status}: ${e.message}`
              : "Failed to load ticker list. Is the backend running?"
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
  }, [sortBy, order, page, exchange, sp500Only, search, industry]);

  function handleSort(field: TickerSortField) {
    if (field === sortBy) {
      setParams({ order: order === "desc" ? "asc" : "desc", page: 1 });
    } else {
      setParams({ sort_by: field, order: "desc", page: 1 });
    }
  }

  const totalPages = data ? Math.max(1, Math.ceil(data.total / data.page_size)) : 1;

  return (
    <div className="space-y-4">
      <h1 className="text-xl font-semibold">All Tickers</h1>

      <div className="flex flex-wrap items-center gap-4 rounded-lg border border-neutral-800 p-3 text-sm">
        <input
          defaultValue={search}
          onChange={(e) => setParams({ search: e.target.value.trim() || null, page: 1 })}
          placeholder="Filter by ticker or company"
          className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 outline-none focus:border-neutral-500"
        />

        <div className="flex items-center gap-2">
          <span className="text-neutral-500">Exchange</span>
          <select
            value={exchange}
            onChange={(e) => setParams({ exchange: e.target.value || null, page: 1 })}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1"
          >
            {EXCHANGE_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
        </div>

        <div className="flex items-center gap-2">
          <span className="text-neutral-500">Industry</span>
          <select
            value={industry}
            onChange={(e) => setParams({ industry: e.target.value || null, page: 1 })}
            className="rounded border border-neutral-700 bg-neutral-900 px-2 py-1 max-w-[220px]"
          >
            <option value="">All industries</option>
            {industries.map((ind) => (
              <option key={ind} value={ind}>
                {ind}
              </option>
            ))}
          </select>
        </div>

        <label className="flex items-center gap-2">
          <input
            type="checkbox"
            checked={sp500Only}
            onChange={(e) => setParams({ sp500_only: e.target.checked ? "true" : null, page: 1 })}
          />
          <span className="text-neutral-400">S&P 500 only</span>
        </label>
      </div>

      {loading && <div className="text-neutral-500">Loading tickers…</div>}
      {error && (
        <div className="rounded-md border border-red-900 bg-red-950/40 px-4 py-3 text-sm text-red-300">
          {error}
        </div>
      )}

      {data && (
        <>
          <p className="text-xs text-neutral-500">
            {data.universe_note} {data.total.toLocaleString()} tickers match current filters.
            {data.as_of ? ` Last refreshed ${new Date(data.as_of).toLocaleString()}.` : ""}
            {!data.sp500_data_available &&
              " S&P 500 membership data is currently unavailable -- treat every S&P 500 column value as unknown, not confirmed non-member."}
          </p>

          <TickerTable rows={data.items} sortBy={sortBy} order={order} onSort={handleSort} />

          <div className="flex items-center justify-between text-sm text-neutral-400">
            <span>
              Page {data.page} of {totalPages}
            </span>
            <div className="flex gap-2">
              <button
                onClick={() => setParams({ page: Math.max(1, page - 1) })}
                disabled={page <= 1}
                className="rounded bg-neutral-800 px-3 py-1 hover:bg-neutral-700 disabled:opacity-40 disabled:hover:bg-neutral-800"
              >
                Previous
              </button>
              <button
                onClick={() => setParams({ page: Math.min(totalPages, page + 1) })}
                disabled={page >= totalPages}
                className="rounded bg-neutral-800 px-3 py-1 hover:bg-neutral-700 disabled:opacity-40 disabled:hover:bg-neutral-800"
              >
                Next
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
