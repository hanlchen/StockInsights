"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ApiRequestError, getDailyRecommendation } from "@/lib/api";
import { changeColorClass, formatCompactDollars, formatSignedPercent } from "@/lib/formatters";
import type { DailyRecommendation } from "@/types/stock";

// Dashboard card for the AI-generated "pick of the day" (see
// backend/app/services/recommendation_service.py). Fetched from a pure DB
// read endpoint -- no live LLM call happens on page load. Renders nothing
// (not even an error banner) if the pick isn't available yet, since this is
// a supplementary feature -- a missing AI pick shouldn't look like the core
// dashboard is broken.
export default function DailyRecommendationCard() {
  const [rec, setRec] = useState<DailyRecommendation | null>(null);
  const [unavailable, setUnavailable] = useState(false);

  useEffect(() => {
    let cancelled = false;
    getDailyRecommendation()
      .then((data) => {
        if (!cancelled) setRec(data);
      })
      .catch((e) => {
        // 503 = generation job hasn't run yet -- expected on a fresh install,
        // not an error worth surfacing loudly on the dashboard.
        if (!cancelled) setUnavailable(!(e instanceof ApiRequestError) || e.status === 503);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  if (unavailable || !rec) return null;

  return (
    <div className="rounded-lg border border-amber-900/50 bg-amber-950/10 p-4">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div className="flex items-baseline gap-2">
          <span className="text-xs font-semibold uppercase tracking-wide text-amber-500">
            AI Pick of the Day
          </span>
          <span className="text-xs text-neutral-500">{rec.date}</span>
        </div>
        {rec.model_used && (
          <span className="text-xs text-neutral-600">via {rec.model_used}</span>
        )}
      </div>

      <div className="mt-3 flex flex-wrap items-baseline gap-3">
        <Link href={`/stock/${rec.ticker}`} className="font-mono text-lg font-semibold hover:underline">
          {rec.ticker}
        </Link>
        {rec.company_name && <span className="text-neutral-400">{rec.company_name}</span>}
        {rec.current_price !== null && (
          <span className="text-neutral-300">${rec.current_price.toFixed(2)}</span>
        )}
        {rec.pct_change_1d !== null && (
          <span className={`text-sm ${changeColorClass(rec.pct_change_1d)}`}>
            {formatSignedPercent(rec.pct_change_1d)} today
          </span>
        )}
        {rec.market_cap !== null && (
          <span className="text-xs text-neutral-500">{formatCompactDollars(rec.market_cap)} mkt cap</span>
        )}
      </div>

      <p className="mt-3 text-sm text-neutral-300">{rec.reasoning}</p>

      {rec.risk_note && (
        <p className="mt-2 text-sm text-neutral-500">
          <span className="font-semibold text-neutral-400">Risk: </span>
          {rec.risk_note}
        </p>
      )}

      <p className="mt-3 border-t border-amber-900/30 pt-2 text-xs text-neutral-600">
        {rec.disclaimer}
      </p>
    </div>
  );
}
