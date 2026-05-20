import { useEffect, useState } from "react";
import { Task } from "../lib/types";
import * as api from "../lib/api";
import { isReady } from "../lib/env";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { TaskList } from "../components/TaskList";
import { EmptyState } from "../components/EmptyState";
import { BmoButton } from "../components/bmo/BmoButton";

const STATUS_OPTIONS: Array<{ value: string; label: string }> = [
  { value: "", label: "Semua" },
  { value: "pending", label: "Pending" },
  { value: "in_progress", label: "Dalam pengerjaan" },
  { value: "done", label: "Selesai" },
];

export function TasksPage() {
  const ready = isReady();
  const userId = ready.ok ? ready.userId : null;

  const [tasks, setTasks] = useState<Task[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);
  const [filter, setFilter] = useState<string>("");

  const load = async (uid: string, status: string) => {
    setLoading(true);
    setError(null);
    try {
      setTasks(await api.getTasks(uid, status || undefined));
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (userId) void load(userId, filter);
  }, [userId, filter]);

  const handleUpdate = (updated: Task) => {
    setTasks((prev) => prev.map((t) => (t.id === updated.id ? updated : t)));
  };

  const handleDelete = (taskId: string) => {
    setTasks((prev) => prev.filter((t) => t.id !== taskId));
  };

  return (
    <section className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-medium text-bmo-dark">Tugas</h1>
        <div className="flex flex-wrap gap-2">
          <div className="flex flex-wrap gap-1 rounded-md border border-bmo-border bg-surface-elev p-1">
            {STATUS_OPTIONS.map((opt) => {
              const active = filter === opt.value;
              return (
                <button
                  key={opt.value}
                  type="button"
                  onClick={() => setFilter(opt.value)}
                  disabled={!userId || loading}
                  className={`cursor-pointer rounded px-3 py-1 text-xs font-medium transition-colors ${
                    active
                      ? "bg-bmo-dark text-bmo-screen"
                      : "text-slate-600 hover:bg-bmo-screen/40"
                  }`}
                >
                  {opt.label}
                </button>
              );
            })}
          </div>
          <BmoButton
            variant="secondary"
            size="sm"
            onClick={() => userId && load(userId, filter)}
            disabled={!userId || loading}
          >
            Refresh
          </BmoButton>
        </div>
      </header>

      {loading ? <LoadingState /> : null}
      {error ? (
        <ErrorState
          error={error}
          onRetry={() => userId && load(userId, filter)}
        />
      ) : null}
      {!loading && !error ? (
        tasks.length === 0 ? (
          <EmptyState
            face="idle"
            title="Belum ada tugas"
            description="Coba katakan: catat tugas matematika besok jam 10 pagi"
          />
        ) : (
          <TaskList
            tasks={tasks}
            onUpdate={handleUpdate}
            onDelete={handleDelete}
          />
        )
      ) : null}
    </section>
  );
}
