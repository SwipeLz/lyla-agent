import { useEffect, useState } from "react";
import { Device } from "../lib/types";
import * as api from "../lib/api";
import { isReady } from "../lib/env";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { DeviceCard } from "../components/devices/DeviceCard";
import { PairDeviceModal } from "../components/devices/PairDeviceModal";
import { EmptyState } from "../components/EmptyState";
import { BmoButton } from "../components/bmo/BmoButton";

export function DevicesPage() {
  const ready = isReady();
  const userId = ready.ok ? ready.userId : null;

  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [modalOpen, setModalOpen] = useState(false);

  const load = async (uid: string) => {
    setLoading(true);
    setError(null);
    try {
      setDevices(await api.getDevices(uid));
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (userId) void load(userId);
  }, [userId]);

  return (
    <section className="space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-2xl font-medium text-bmo-dark">Devices</h1>
        <div className="flex gap-2">
          <BmoButton
            variant="secondary"
            size="sm"
            onClick={() => userId && load(userId)}
            disabled={!userId || loading}
          >
            Refresh
          </BmoButton>
          <BmoButton size="sm" onClick={() => setModalOpen(true)}>
            Pair Device Baru
          </BmoButton>
        </div>
      </header>

      {loading ? <LoadingState /> : null}
      {error ? (
        <ErrorState error={error} onRetry={() => userId && load(userId)} />
      ) : null}
      {!loading && !error ? (
        devices.length === 0 ? (
          <EmptyState
            face="idle"
            title="Belum ada device terdaftar"
            description="Pair device baru lewat tombol di atas untuk menghubungkan ESP."
            cta={
              <BmoButton onClick={() => setModalOpen(true)}>
                Pair sekarang
              </BmoButton>
            }
          />
        ) : (
          <div className="grid grid-cols-1 gap-3 md:grid-cols-2 lg:grid-cols-3">
            {devices.map((d) => (
              <DeviceCard key={d.id} device={d} />
            ))}
          </div>
        )
      ) : null}

      <PairDeviceModal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        onSuccess={() => userId && void load(userId)}
      />
    </section>
  );
}
