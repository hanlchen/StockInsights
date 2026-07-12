"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { searchStocks } from "@/lib/api";
import type { SearchResult } from "@/types/stock";

export default function SearchBar({ autoFocus = false }: { autoFocus?: boolean }) {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const debounceRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const router = useRouter();

  useEffect(() => {
    if (debounceRef.current) clearTimeout(debounceRef.current);

    if (!query.trim()) {
      setResults([]);
      setOpen(false);
      return;
    }

    debounceRef.current = setTimeout(async () => {
      setLoading(true);
      try {
        const res = await searchStocks(query.trim());
        setResults(res.results);
        setOpen(true);
      } catch {
        setResults([]);
      } finally {
        setLoading(false);
      }
    }, 250);

    return () => {
      if (debounceRef.current) clearTimeout(debounceRef.current);
    };
  }, [query]);

  function goToTicker(ticker: string) {
    setOpen(false);
    setQuery("");
    router.push(`/stock/${ticker}`);
  }

  return (
    <div className="relative w-full max-w-md">
      <input
        autoFocus={autoFocus}
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        onFocus={() => results.length > 0 && setOpen(true)}
        onBlur={() => setTimeout(() => setOpen(false), 150)}
        placeholder="Search ticker or company (e.g. AAPL, Apple)"
        className="w-full rounded-md border border-neutral-700 bg-neutral-900 px-3 py-2 text-sm outline-none focus:border-neutral-500"
      />
      {open && (
        <div className="absolute z-10 mt-1 w-full rounded-md border border-neutral-700 bg-neutral-900 shadow-lg max-h-72 overflow-y-auto">
          {loading && <div className="px-3 py-2 text-sm text-neutral-500">Searching…</div>}
          {!loading && results.length === 0 && (
            <div className="px-3 py-2 text-sm text-neutral-500">No matches</div>
          )}
          {!loading &&
            results.map((r) => (
              <button
                key={r.ticker}
                onMouseDown={() => goToTicker(r.ticker)}
                className="flex w-full items-center justify-between px-3 py-2 text-left text-sm hover:bg-neutral-800"
              >
                <span>
                  <span className="font-mono font-semibold">{r.ticker}</span>{" "}
                  <span className="text-neutral-400">{r.company_name}</span>
                </span>
                {r.exchange && <span className="text-xs text-neutral-500">{r.exchange}</span>}
              </button>
            ))}
        </div>
      )}
    </div>
  );
}
