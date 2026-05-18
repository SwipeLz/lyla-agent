import { useCallback, useEffect, useMemo, useState } from "react";
import {
  DashboardSummary,
  Device,
  Expense,
  Task,
  VoiceCommandLog,
} from "../lib/types";
import * as api from "../lib/api";
import { isReady } from "../lib/env";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { StatCard } from "../components/StatCard";
import { AgentCommandBox } from "../components/AgentCommandBox";
import { VoiceLogList } from "../components/VoiceLogList";
import { formatCurrencyIDR } from "../lib/format";

interface Snapshot {
  summary: DashboardSummary;
  pendingTasks: Task[];
  expenses: Expense[];
  logs: VoiceCommandLog[];
  devices: Device[];
}

const sumMonthExpenses = (expenses: Expense[]): number => {
  const now = new Date();
  const y = now.getFullYear();
  const m = now.getMonth();
  return expenses.reduce((acc, e) => {
    const d = new Date(e.spent_at);
    if (Number.isNaN(d.getTime())) return acc;
    return d.getFullYear() === y && d.getMonth() === m ? acc + e.amount : acc;
  }, 0);
};

export function DashboardPage() {
  const ready = isReady();
  const userId = ready.ok ? ready.userId : null;

  const [data, setData] = useState<Snapshot | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);

  const load = useCallback(async (uid: string) => {
    setLoading(true);
    setError(null);
    try {
      const [summary, pendingTasks, expenses, logs, devices] =
        await Promise.all([
          api.getSummary(uid),
          api.getTasks(uid, "pending"),
          api.getExpenses(uid),
          api.getLogs(uid),
          api.getDevices(uid),
        ]);
      setData({ summary, pendingTasks, expenses, logs, devices });
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (userId) void load(userId);
  }, [userId, refreshKey, load]);

  const monthExpenses = useMemo(
    () => (data ? sumMonthExpenses(data.expenses) : 0),
    [data],
  );

  const recentLogs = useMemo(
    () => (data ? data.logs.slice(0, 5) : []),
    [data],
  );

  return (
    <section className="space-y-6">
      <header>
        <h1 className="text-xl font-semibold">Ringkasan</h1>
        <p className="text-sm text-slate-500">
          Snapshot aktivitas hari ini.
        </p>
      </header>

      {loading && !data ? <LoadingState /> : null}
      {error ? (
        <ErrorState
          error={error}
          onRetry={() => userId && void load(userId)}
        />
      ) : null}

      {data ? (
        <>
          <div className="grid grid-cols-2 gap-3 md:grid-cols-3 xl:grid-cols-5">
            <StatCard
              label="Tugas pending"
              value={data.pendingTasks.length}
              tone={data.pendingTasks.length > 0 ? "warn" : "good"}
            />
            <StatCard
              label="Jatuh tempo hari ini"
              value={data.summary.tasks_due_today}
              tone={data.summary.tasks_due_today > 0 ? "warn" : "neutral"}
            />
            <StatCard
              label="Pengeluaran hari ini"
              value={formatCurrencyIDR(data.summary.total_expenses_today)}
            />
            <StatCard
              label="Pengeluaran bulan ini"
              value={formatCurrencyIDR(monthExpenses)}
            />
            <StatCard
              label="Devices terdaftar"
              value={data.devices.length}
            />
          </div>

          <AgentCommandBox onSuccess={() => setRefreshKey((k) => k + 1)} />

          <section className="space-y-2">
            <h2 className="text-sm font-semibold uppercase tracking-wide text-slate-600">
              Aktivitas terkini
            </h2>
            <VoiceLogList logs={recentLogs} />
          </section>
        </>
      ) : null}
    </section>
  );
}
