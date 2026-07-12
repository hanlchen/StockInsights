import Link from "next/link";
import { changeColorClass, formatCompactDollars, formatSignedPercent } from "@/lib/formatters";
import type { MoverEntry } from "@/types/stock";

export default function MoversTable({ title, rows }: { title: string; rows: MoverEntry[] }) {
  return (
    <div className="rounded-lg border border-neutral-800">
      <div className="flex items-baseline justify-between border-b border-neutral-800 px-4 py-2">
        <span className="text-sm font-semibold">{title}</span>
        <span className="text-xs text-neutral-500">{rows.length} shown</span>
      </div>
      <div className="max-h-[600px] overflow-y-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-neutral-500">
              <th className="px-4 py-2 text-left font-normal">Ticker</th>
              <th className="px-4 py-2 text-left font-normal">Company</th>
              <th className="px-4 py-2 text-right font-normal">Mkt cap</th>
              <th className="px-4 py-2 text-right font-normal">Revenue (TTM)</th>
              <th className="px-4 py-2 text-right font-normal">Change</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={5} className="px-4 py-3 text-center text-neutral-500">
                  No data
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
                <td className="px-4 py-2 text-neutral-400 truncate max-w-[220px]">
                  {r.company_name}
                </td>
                <td className="table-cell-num text-neutral-400">{formatCompactDollars(r.market_cap)}</td>
                <td className="table-cell-num text-neutral-400">{formatCompactDollars(r.revenue_ttm)}</td>
                <td className={`table-cell-num ${changeColorClass(r.pct_change)}`}>
                  {formatSignedPercent(r.pct_change)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
