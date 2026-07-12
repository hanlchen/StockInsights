import Link from "next/link";
import { changeColorClass, formatCompactDollars, formatSignedPercent } from "@/lib/formatters";
import type { MonthlyMomentumEntry, MonthlySortBy } from "@/types/stock";

// Oldest -> newest, mirrors MONTHLY_MOMENTUM_FIELDS in backend/app/services/market_service.py.
const MONTH_COLUMNS: { field: keyof MonthlyMomentumEntry; sortBy: MonthlySortBy; label: string }[] = [
  { field: "monthly_m5_6", sortBy: "m5_6", label: "5-6mo" },
  { field: "monthly_m4_5", sortBy: "m4_5", label: "4-5mo" },
  { field: "monthly_m3_4", sortBy: "m3_4", label: "3-4mo" },
  { field: "monthly_m2_3", sortBy: "m2_3", label: "2-3mo" },
  { field: "monthly_m1_2", sortBy: "m1_2", label: "1-2mo" },
  { field: "monthly_m0_1", sortBy: "m0_1", label: "Last mo" },
];

export default function MonthlyMomentumTable({
  rows,
  sortBy,
  onSortByChange,
}: {
  rows: MonthlyMomentumEntry[];
  sortBy: MonthlySortBy;
  onSortByChange: (sortBy: MonthlySortBy) => void;
}) {
  return (
    <div className="rounded-lg border border-neutral-800">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-neutral-500">
              <th className="px-4 py-2 text-left font-normal">Ticker</th>
              <th className="px-4 py-2 text-left font-normal">Company</th>
              <th className="px-4 py-2 text-left font-normal">Sector</th>
              <th className="px-4 py-2 text-right font-normal">Mkt cap</th>
              <th className="px-4 py-2 text-right font-normal">Revenue (TTM)</th>
              {MONTH_COLUMNS.map((col) => (
                <SortableHeader
                  key={col.field}
                  label={col.label}
                  active={sortBy === col.sortBy}
                  onClick={() => onSortByChange(col.sortBy)}
                />
              ))}
              <SortableHeader label="Avg" active={sortBy === "avg"} onClick={() => onSortByChange("avg")} />
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={5 + MONTH_COLUMNS.length + 1} className="px-4 py-3 text-center text-neutral-500">
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
                {MONTH_COLUMNS.map((col) => {
                  const value = r[col.field] as number;
                  return (
                    <td key={col.field} className={`table-cell-num font-mono ${changeColorClass(value)}`}>
                      {formatSignedPercent(value)}
                    </td>
                  );
                })}
                <td className={`table-cell-num font-mono font-semibold ${changeColorClass(r.avg_monthly_momentum)}`}>
                  {formatSignedPercent(r.avg_monthly_momentum)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

function SortableHeader({ label, active, onClick }: { label: string; active: boolean; onClick: () => void }) {
  return (
    <th className="px-4 py-2 text-right font-normal">
      <button
        onClick={onClick}
        className={`hover:text-neutral-100 ${active ? "text-neutral-100 font-semibold underline" : ""}`}
        title={`Sort by ${label}`}
      >
        {label}
      </button>
    </th>
  );
}
