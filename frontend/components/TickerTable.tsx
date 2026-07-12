import Link from "next/link";
import { changeColorClass, formatCompactDollars, formatSignedPercent, formatVolume } from "@/lib/formatters";
import type { SortOrder, TickerEntry, TickerSortField } from "@/types/stock";

const COLUMNS: { field: TickerSortField | null; label: string; align: "left" | "right" | "center" }[] = [
  { field: "ticker", label: "Ticker", align: "left" },
  { field: "company_name", label: "Company", align: "left" },
  { field: null, label: "Exchange", align: "left" },
  { field: null, label: "Industry", align: "left" },
  { field: "price", label: "Price", align: "right" },
  { field: "pct_change_1d", label: "1D %", align: "right" },
  { field: "pct_change_1mo", label: "1M %", align: "right" },
  { field: "pct_change_1y", label: "1Y %", align: "right" },
  { field: "volume", label: "Volume", align: "right" },
  { field: "market_cap", label: "Mkt cap", align: "right" },
  { field: null, label: "S&P 500", align: "center" },
];

export default function TickerTable({
  rows,
  sortBy,
  order,
  onSort,
}: {
  rows: TickerEntry[];
  sortBy: TickerSortField;
  order: SortOrder;
  onSort: (field: TickerSortField) => void;
}) {
  return (
    <div className="rounded-lg border border-neutral-800">
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className="text-neutral-500">
              {COLUMNS.map((col) => {
                const alignClass =
                  col.align === "right" ? "text-right" : col.align === "center" ? "text-center" : "text-left";
                if (!col.field) {
                  return (
                    <th key={col.label} className={`px-4 py-2 font-normal ${alignClass}`}>
                      {col.label}
                    </th>
                  );
                }
                const active = sortBy === col.field;
                return (
                  <th key={col.label} className={`px-4 py-2 font-normal ${alignClass}`}>
                    <button
                      onClick={() => onSort(col.field as TickerSortField)}
                      className={`hover:text-neutral-100 ${active ? "text-neutral-100 font-semibold" : ""}`}
                    >
                      {col.label}
                      {active ? (order === "desc" ? " ▼" : " ▲") : ""}
                    </button>
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length} className="px-4 py-3 text-center text-neutral-500">
                  No tickers match the current filters
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
                <td className="px-4 py-2 text-neutral-400 truncate max-w-[240px]">{r.company_name}</td>
                <td className="px-4 py-2 text-neutral-500">{r.exchange ?? "—"}</td>
                <td className="px-4 py-2 text-neutral-500 truncate max-w-[180px]">{r.industry ?? "—"}</td>
                <td className="table-cell-num">
                  {r.current_price != null ? `$${r.current_price.toFixed(2)}` : "—"}
                </td>
                <td className={`table-cell-num font-mono ${changeColorClass(r.pct_change_1d)}`}>
                  {formatSignedPercent(r.pct_change_1d)}
                </td>
                <td className={`table-cell-num font-mono ${changeColorClass(r.pct_change_1mo)}`}>
                  {formatSignedPercent(r.pct_change_1mo)}
                </td>
                <td className={`table-cell-num font-mono ${changeColorClass(r.pct_change_1y)}`}>
                  {formatSignedPercent(r.pct_change_1y)}
                </td>
                <td className="table-cell-num text-neutral-400">{formatVolume(r.volume)}</td>
                <td className="table-cell-num text-neutral-400">{formatCompactDollars(r.market_cap)}</td>
                <td className="px-4 py-2 text-center">
                  {r.is_sp500 ? (
                    <span className="rounded bg-neutral-100 px-1.5 py-0.5 text-xs font-semibold text-neutral-900">
                      S&P 500
                    </span>
                  ) : (
                    <span className="text-neutral-600">—</span>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
