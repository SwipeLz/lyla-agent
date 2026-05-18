import { useEffect, useState } from "react";
import { Task } from "../lib/types";
import * as api from "../lib/api";
import { isReady } from "../lib/env";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { TaskList } from "../components/TaskList";

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
        <h1 className="text-xl font-semibold">Tugas</h1>
        <div className="flex gap-2">
          <select
            value={filter}
            onChange={(e) => setFilter(e.target.value)}
            disabled={!userId || loading}
            className="rounded border border-slate-300 bg-white px-2 py-1 text-sm"
          >
            {STATUS_OPTIONS.map((opt) => (
              <option key={opt.value} value={opt.value}>
                {opt.label}
              </option>
            ))}
          </select>
          <button
            type="button"
            onClick={() => userId && load(userId, filter)}
            disabled={!userId || loading}
            className="rounded border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
          >
            Refresh
          </button>
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
        <TaskList
          tasks={tasks}
          onUpdate={handleUpdate}
          onDelete={handleDelete}
        />
      ) : null}
    </section>
  );
}
