import { useEffect, useState } from "react";
import { VoiceCommandLog } from "../lib/types";
import * as api from "../lib/api";
import { isReady } from "../lib/env";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { VoiceLogList } from "../components/VoiceLogList";
import { EmptyState } from "../components/EmptyState";
import { BmoButton } from "../components/bmo/BmoButton";

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
        <h1 className="text-2xl font-medium text-bmo-dark">Riwayat Suara</h1>
        <BmoButton
          variant="secondary"
          size="sm"
          onClick={() => userId && load(userId)}
          disabled={!userId || loading}
        >
          Refresh
        </BmoButton>
      </header>

      {loading ? <LoadingState /> : null}
      {error ? <ErrorState error={error} onRetry={() => userId && load(userId)} /> : null}
      {!loading && !error ? (
        logs.length === 0 ? (
          <EmptyState
            face="idle"
            title="Belum ada riwayat"
            description="Riwayat perintah suara muncul di sini setelah Anda menggunakan Agent Command."
          />
        ) : (
          <VoiceLogList logs={logs} />
        )
      ) : null}
    </section>
  );
}
