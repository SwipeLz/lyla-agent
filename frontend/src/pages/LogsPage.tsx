import { useEffect, useState } from "react";
import { VoiceCommandLog } from "../lib/types";
import * as api from "../lib/api";
import { isReady } from "../lib/env";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { VoiceLogList } from "../components/VoiceLogList";

export function LogsPage() {
  const ready = isReady();
  const userId = ready.ok ? ready.userId : null;

  const [logs, setLogs] = useState<VoiceCommandLog[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const load = async (uid: string) => {
    setLoading(true);
    setError(null);
    try {
      setLogs(await api.getLogs(uid));
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
        <h1 className="text-xl font-semibold">Riwayat perintah</h1>
        <button
          type="button"
          onClick={() => userId && load(userId)}
          disabled={!userId || loading}
          className="rounded border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          Refresh
        </button>
      </header>

      {loading ? <LoadingState /> : null}
      {error ? <ErrorState error={error} onRetry={() => userId && load(userId)} /> : null}
      {!loading && !error ? <VoiceLogList logs={logs} /> : null}
    </section>
  );
}
