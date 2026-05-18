import { useEffect, useState } from "react";
import { Device } from "../lib/types";
import * as api from "../lib/api";
import { isReady } from "../lib/env";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { DeviceList } from "../components/DeviceList";

export function DevicesPage() {
  const ready = isReady();
  const userId = ready.ok ? ready.userId : null;

  const [devices, setDevices] = useState<Device[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

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
        <h1 className="text-xl font-semibold">Devices</h1>
        <button
          type="button"
          onClick={() => userId && load(userId)}
          disabled={!userId || loading}
          className="rounded border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          Refresh
        </button>
      </header>

      <p className="rounded border border-slate-200 bg-slate-50 p-3 text-xs text-slate-600">
        Integrasi firmware ESP32 untuk polling status real-time tertunda ke
        fase berikutnya. Halaman ini hanya menampilkan daftar device terdaftar.
      </p>

      {loading ? <LoadingState /> : null}
      {error ? <ErrorState error={error} onRetry={() => userId && load(userId)} /> : null}
      {!loading && !error ? <DeviceList devices={devices} /> : null}
    </section>
  );
}
