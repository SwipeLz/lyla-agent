import { VoiceCommandLog } from "../lib/types";
import { formatDateTime, formatStatus } from "../lib/format";

interface VoiceLogListProps {
  logs: VoiceCommandLog[];
}

const statusClass = (status: string): string => {
  if (status === "success") return "bg-emerald-100 text-emerald-800";
  if (status === "error") return "bg-red-100 text-red-800";
  return "bg-slate-200 text-slate-700";
};

export function VoiceLogList({ logs }: VoiceLogListProps) {
  if (logs.length === 0) {
    return (
      <p className="rounded border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
        Belum ada riwayat perintah.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {logs.map((log) => (
        <li
          key={log.id}
          className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1">
              <div className="text-xs text-slate-500">
                {formatDateTime(log.created_at)}
              </div>
              <p className="mt-1 break-words text-sm font-medium text-slate-900">
                {log.input_text}
              </p>
              {log.response_text ? (
                <p className="mt-1 line-clamp-2 break-words text-sm text-slate-700">
                  {log.response_text}
                </p>
              ) : null}
            </div>
            <span
              className={[
                "rounded-full px-2 py-0.5 text-xs font-medium",
                statusClass(log.status),
              ].join(" ")}
            >
              {formatStatus(log.status)}
            </span>
          </div>
          {log.parsed_actions && log.parsed_actions.length > 0 ? (
            <details className="mt-2">
              <summary className="text-xs text-slate-500 hover:text-slate-700">
                {log.parsed_actions.length} aksi
              </summary>
              <pre className="mt-1 overflow-x-auto rounded bg-slate-50 p-2 text-xs text-slate-700">
                {JSON.stringify(log.parsed_actions, null, 2)}
              </pre>
            </details>
          ) : null}
        </li>
      ))}
    </ul>
  );
}
