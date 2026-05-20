import { useCallback, useEffect, useRef, useState } from "react";
import * as api from "../lib/api";
import {
  ApiError,
  AuthRequiredError,
  DeviceStatusOut,
  RecentLogSummary,
  StatsResponse,
} from "../lib/types";
import { ObsStatsBar } from "../components/observability/ObsStatsBar";
import { LiveTailTable } from "../components/observability/LiveTailTable";
import { TraceDrawer } from "../components/observability/TraceDrawer";
import { DeviceStatusGrid } from "../components/observability/DeviceStatusGrid";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";

const POLL_INTERVAL_MS = 3000;

export function ObservabilityPage() {
  const [recent, setRecent] = useState<RecentLogSummary[]>([]);
  const [stats, setStats] = useState<StatsResponse | null>(null);
  const [devices, setDevices] = useState<DeviceStatusOut[]>([]);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [polling, setPolling] = useState(true);
  const [initialLoading, setInitialLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const initialLoadedRef = useRef(false);

  const fetchAll = useCallback(async () => {
    try {
      const [r, s, d] = await Promise.all([
        api.getRecent({ limit: 50 }),
        api.getStats("1h"),
        api.getObsDevices(),
      ]);
      setRecent(r);
      setStats(s);
      setDevices(d);
      setError(null);
    } catch (err) {
      if (err instanceof AuthRequiredError) {
        setError(err);
      } else if (err instanceof ApiError) {
        setError(err);
      } else {
        setError(err instanceof Error ? err : new Error(String(err)));
      }
    }
  }, []);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      await fetchAll();
      if (!cancelled) {
        initialLoadedRef.current = true;
        setInitialLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [fetchAll]);

  useEffect(() => {
    if (!polling || selectedId) return;
    const id = window.setInterval(() => {
      if (document.hidden) return;
      void fetchAll();
    }, POLL_INTERVAL_MS);
    return () => window.clearInterval(id);
  }, [polling, selectedId, fetchAll]);

  return (
    <section className="space-y-5">
      <header className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-medium text-bmo-dark">Observability</h1>
          <p className="text-sm text-slate-500">
            Live tail request /agent/audio dengan drill-down per stage.
          </p>
        </div>
      </header>

      {initialLoading ? <LoadingState label="Memuat data observability…" /> : null}
      {error && initialLoadedRef.current === false ? (
        <ErrorState error={error} onRetry={fetchAll} />
      ) : null}

      {initialLoadedRef.current ? (
        <>
          <ObsStatsBar stats={stats} loading={false} />

          <LiveTailTable
            rows={recent}
            selectedId={selectedId}
            onRowClick={setSelectedId}
            polling={polling && !selectedId}
            onTogglePolling={() => setPolling((v) => !v)}
          />

          <section className="space-y-2">
            <h2 className="text-sm font-medium uppercase tracking-wide text-slate-600">
              Devices
            </h2>
            <DeviceStatusGrid devices={devices} />
          </section>

          <TraceDrawer
            logId={selectedId}
            onClose={() => setSelectedId(null)}
          />
        </>
      ) : null}
    </section>
  );
}
