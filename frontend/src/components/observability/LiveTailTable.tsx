import { RecentLogSummary } from "../../lib/types";
import { parseIsoUtc } from "../../lib/format";
import { BmoBadge } from "../bmo/BmoBadge";

interface LiveTailTableProps {
  rows: RecentLogSummary[];
  selectedId?: string | null;
  onRowClick: (id: string) => void;
  polling: boolean;
  onTogglePolling?: () => void;
}

const fmtTime = (iso: string): string => {
  const d = parseIsoUtc(iso);
  if (!d) return iso;
  return d.toLocaleTimeString("id-ID", {
    hour12: false,
    timeZone: "Asia/Jakarta",
  });
};

const fmtMs = (ms: number | null): string => {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

const tone = (status: string): "success" | "error" | "info" => {
  if (status === "success") return "success";
  if (status === "error") return "error";
  return "info";
};

export function LiveTailTable({
  rows,
  selectedId,
  onRowClick,
  polling,
  onTogglePolling,
}: LiveTailTableProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-bmo-border bg-surface-elev">
      <div className="flex items-center justify-between border-b border-bmo-border bg-bmo-screen/30 px-4 py-2">
        <h3 className="text-sm font-medium text-bmo-dark">Live Tail</h3>
        <div className="flex items-center gap-2">
          <span
            className={`inline-flex items-center gap-1.5 text-xs ${
              polling ? "text-bmo-mouth" : "text-slate-500"
            }`}
          >
            <span
              className={`inline-block h-2 w-2 rounded-full ${
                polling ? "animate-pulse bg-bmo-mouth" : "bg-slate-400"
              }`}
              aria-hidden="true"
            />
            {polling ? "live" : "paused"}
          </span>
          {onTogglePolling ? (
            <button
              type="button"
              onClick={onTogglePolling}
              className="cursor-pointer rounded border border-bmo-border bg-surface-elev px-2 py-0.5 text-xs hover:bg-bmo-screen/50"
            >
              {polling ? "Pause" : "Resume"}
            </button>
          ) : null}
        </div>
      </div>
      <div className="max-h-[480px] overflow-auto">
        <table className="w-full text-sm">
          <thead className="sticky top-0 bg-surface-elev text-xs uppercase tracking-wide text-slate-500">
            <tr className="border-b border-bmo-border">
              <th className="px-3 py-2 text-left font-medium">Waktu</th>
              <th className="px-3 py-2 text-left font-medium">Device</th>
              <th className="px-3 py-2 text-left font-medium">Audio code</th>
              <th className="px-3 py-2 text-left font-medium">Status</th>
              <th className="px-3 py-2 text-right font-medium">Total</th>
            </tr>
          </thead>
          <tbody>
            {rows.length === 0 ? (
              <tr>
                <td
                  colSpan={5}
                  className="px-3 py-8 text-center text-sm text-slate-500"
                >
                  Belum ada request. Trigger /agent/audio dari ESP atau
                  curl untuk melihat data.
                </td>
              </tr>
            ) : (
              rows.map((row) => (
                <tr
                  key={row.id}
                  onClick={() => onRowClick(row.id)}
                  className={`cursor-pointer border-b border-bmo-border/60 transition-colors hover:bg-bmo-screen/30 ${
                    selectedId === row.id ? "bg-bmo-screen/50" : ""
                  }`}
                >
                  <td className="px-3 py-2 font-mono text-xs text-slate-600">
                    {fmtTime(row.created_at)}
                  </td>
                  <td className="px-3 py-2 font-mono text-xs text-slate-600">
                    {row.device_id ? row.device_id.slice(0, 8) : "—"}
                  </td>
                  <td className="px-3 py-2 text-bmo-dark">
                    {row.audio_code ?? "—"}
                  </td>
                  <td className="px-3 py-2">
                    <BmoBadge tone={tone(row.status)}>{row.status}</BmoBadge>
                  </td>
                  <td className="px-3 py-2 text-right font-mono text-xs text-slate-600">
                    {fmtMs(row.total_ms)}
                  </td>
                </tr>
              ))
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
