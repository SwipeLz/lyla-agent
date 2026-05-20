import { DeviceStatusOut } from "../../lib/types";
import { DeviceCard } from "../devices/DeviceCard";
import { EmptyState } from "../EmptyState";

interface DeviceStatusGridProps {
  devices: DeviceStatusOut[];
}

export function DeviceStatusGrid({ devices }: DeviceStatusGridProps) {
  if (devices.length === 0) {
    return (
      <EmptyState
        face="idle"
        title="Belum ada device terdaftar"
        description="Pair device baru lewat halaman Devices untuk melihat status di sini."
      />
    );
  }

  return (
    <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
      {devices.map((d) => (
        <DeviceCard key={d.id} device={d} />
      ))}
    </div>
  );
}
