import { Device } from "../lib/types";
import { formatDateTime, formatStatus } from "../lib/format";

interface DeviceListProps {
  devices: Device[];
}

const statusClass = (status: string): string => {
  if (status === "online" || status === "active")
    return "bg-emerald-100 text-emerald-800";
  if (status === "offline") return "bg-slate-200 text-slate-700";
  return "bg-amber-100 text-amber-800";
};

export function DeviceList({ devices }: DeviceListProps) {
  if (devices.length === 0) {
    return (
      <p className="rounded border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
        Belum ada device terdaftar.
      </p>
    );
  }

  return (
    <ul className="space-y-2">
      {devices.map((d) => (
        <li
          key={d.id}
          className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
        >
          <div className="flex items-start justify-between gap-3">
            <div>
              <code className="text-sm font-semibold text-slate-900">
                {d.device_code}
              </code>
              <div className="text-xs text-slate-500">
                Last seen: {formatDateTime(d.last_seen_at)}
              </div>
            </div>
            <span
              className={[
                "rounded-full px-2 py-0.5 text-xs font-medium",
                statusClass(d.status),
              ].join(" ")}
            >
              {formatStatus(d.status)}
            </span>
          </div>
        </li>
      ))}
    </ul>
  );
}
