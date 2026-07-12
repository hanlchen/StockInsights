import { changeColorClass, formatSignedPercent } from "@/lib/formatters";
import type { MoversPeriod, SectorEntry } from "@/types/stock";

const PERIOD_LABEL: Record<MoversPeriod, string> = {
  "1d": "today",
  "1w": "last week",
  "1y": "last year",
  "3y": "last 3 years",
};

export default function SectorPerformanceTable({
  sectors,
  period,
}: {
  sectors: SectorEntry[];
  period: MoversPeriod;
}) {
  return (
    <div className="rounded-lg border border-neutral-800">
      <div className="border-b border-neutral-800 px-4 py-2 text-sm font-semibold">
        Sector performance ({PERIOD_LABEL[period]})
      </div>
      <table className="w-full text-sm">
        <thead>
          <tr className="text-neutral-500">
            <th className="px-4 py-2 text-left font-normal">Sector</th>
            <th className="px-4 py-2 text-right font-normal">Stocks</th>
            <th className="px-4 py-2 text-right font-normal">Avg change</th>
          </tr>
        </thead>
        <tbody>
          {sectors.map((s) => (
            <tr key={s.sector} className="border-t border-neutral-800/60 hover:bg-neutral-900">
              <td className="px-4 py-2">{s.sector}</td>
              <td className="table-cell-num text-neutral-500">{s.count}</td>
              <td className={`table-cell-num ${changeColorClass(s.avg_pct_change)}`}>
                {formatSignedPercent(s.avg_pct_change)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
