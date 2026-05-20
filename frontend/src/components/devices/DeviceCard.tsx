import { BmoMascot } from "../bmo/BmoMascot";
import { BmoBadge } from "../bmo/BmoBadge";
import { Device, DeviceStatusOut } from "../../lib/types";

type CardDevice = Device | DeviceStatusOut;

interface DeviceCardProps {
  device: CardDevice;
}

const isStatusOut = (d: CardDevice): d is DeviceStatusOut =>
  "is_online" in d;

const formatTimeAgo = (iso: string | null): string => {
  if (!iso) return "belum pernah";
  const then = new Date(iso).getTime();
  if (Number.isNaN(then)) return iso;
  const diff = Date.now() - then;
  if (diff < 60_000) return "baru saja";
  if (diff < 3600_000) return `${Math.floor(diff / 60_000)} menit lalu`;
  if (diff < 86400_000) return `${Math.floor(diff / 3600_000)} jam lalu`;
  return `${Math.floor(diff / 86400_000)} hari lalu`;
};

export function DeviceCard({ device }: DeviceCardProps) {
  const isOnline = isStatusOut(device)
    ? device.is_online
    : device.status === "online";
  const name = isStatusOut(device) ? device.name : device.device_code;
  const tone = isOnline ? "online" : "offline";
  const fw = isStatusOut(device) ? device.firmware_version : device.firmware_version;
  const rssi = isStatusOut(device) ? device.wifi_rssi_dbm : device.wifi_rssi_dbm;
  const battery = isStatusOut(device) ? device.battery_pct : device.battery_pct;

  return (
    <div className="flex items-center gap-4 rounded-lg border border-bmo-border bg-surface-elev p-4">
      <BmoMascot size={48} />
      <div className="min-w-0 flex-1">
        <div className="flex items-center gap-2">
          <p className="truncate text-sm font-medium text-bmo-dark">{name}</p>
          <BmoBadge tone={tone}>{isOnline ? "online" : "offline"}</BmoBadge>
        </div>
        <p className="mt-0.5 truncate font-mono text-xs text-slate-500">
          {device.device_code}
        </p>
        <div className="mt-1 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-slate-500">
          {fw ? <span>fw {fw}</span> : null}
          {rssi != null ? <span>RSSI {rssi} dBm</span> : null}
          {battery != null && battery >= 0 ? (
            <span>battery {battery}%</span>
          ) : null}
          <span>last seen {formatTimeAgo(device.last_seen_at)}</span>
        </div>
      </div>
    </div>
  );
}
