import Link from "next/link";
import { changeColorClass, formatCompactDollars, formatSignedPercent } from "@/lib/formatters";
import type { MomentumEntry } from "@/types/stock";

const COLUMNS = ["Ticker", "Company", "Sector", "Mkt cap", "Revenue (TTM)", "9-12mo", "6-9mo", "3-6mo", "Last 3mo", "Avg"];

export default function MomentumScreenerTable({ rows }: { rows: MomentumEntry[] }) {
  return (
    <div className="rounded-lg border border-neutral-800">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-neutral-500">
              {COLUMNS.map((label, i) => (
                <th
                  key={label}
                  className={`px-4 py-2 font-normal ${i >= 3 ? "text-right" : "text-left"}`}
                >
                  {label}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-4 py-3 text-center text-neutral-500">
                  No tickers matched -- try a lower threshold
                </td>
              </tr>
            )}
            {rows.map((r) => (
              <tr key={r.ticker} className="border-t border-neutral-800/60 hover:bg-neutral-900">
                <td className="px-4 py-2">
                  <Link href={`/stock/${r.ticker}`} className="font-mono font-semibold hover:underline">
                    {r.ticker}
                  </Link>
                </td>
                <td className="px-4 py-2 text-neutral-400 truncate max-w-[220px]">{r.company_name}</td>
                <td className="px-4 py-2 text-neutral-500 truncate max-w-[160px]">{r.sector ?? "—"}</td>
                <td className="table-cell-num text-neutral-400">{formatCompactDollars(r.market_cap)}</td>
                <td className="table-cell-num text-neutral-400">{formatCompactDollars(r.revenue_ttm)}</td>
                <td className={`table-cell-num font-mono ${changeColorClass(r.momentum_m9_12)}`}>
                  {formatSignedPercent(r.momentum_m9_12)}
                </td>
                <td className={`table-cell-num font-mono ${changeColorClass(r.momentum_m6_9)}`}>
                  {formatSignedPercent(r.momentum_m6_9)}
                </td>
                <td className={`table-cell-num font-mono ${changeColorClass(r.momentum_m3_6)}`}>
                  {formatSignedPercent(r.momentum_m3_6)}
                </td>
                <td className={`table-cell-num font-mono ${changeColorClass(r.momentum_m0_3)}`}>
                  {formatSignedPercent(r.momentum_m0_3)}
                </td>
                <td className={`table-cell-num font-mono font-semibold ${changeColorClass(r.avg_momentum)}`}>
                  {formatSignedPercent(r.avg_momentum)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
