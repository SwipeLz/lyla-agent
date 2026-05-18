import { useState } from "react";
import { Task } from "../lib/types";
import { formatDateTime, formatStatus } from "../lib/format";
import * as api from "../lib/api";

interface TaskListProps {
  tasks: Task[];
  onUpdate?: (task: Task) => void;
  onDelete?: (taskId: string) => void;
}

const statusClass = (status: string): string => {
  if (status === "done") return "bg-emerald-100 text-emerald-800";
  if (status === "pending") return "bg-amber-100 text-amber-800";
  if (status === "in_progress") return "bg-sky-100 text-sky-800";
  return "bg-slate-200 text-slate-700";
};

export function TaskList({ tasks, onUpdate, onDelete }: TaskListProps) {
  const [busyId, setBusyId] = useState<string | null>(null);

  if (tasks.length === 0) {
    return (
      <p className="rounded border border-dashed border-slate-300 bg-white p-4 text-sm text-slate-500">
        Belum ada tugas.
      </p>
    );
  }

  const handleDone = async (task: Task) => {
    if (busyId) return;
    setBusyId(task.id);
    try {
      const updated = await api.updateTask(task.id, { status: "done" });
      onUpdate?.(updated);
    } finally {
      setBusyId(null);
    }
  };

  const handleDelete = async (task: Task) => {
    if (busyId) return;
    setBusyId(task.id);
    try {
      await api.deleteTask(task.id);
      onDelete?.(task.id);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <ul className="space-y-2">
      {tasks.map((task) => {
        const isBusy = busyId === task.id;
        const isDone = task.status === "done";
        return (
          <li
            key={task.id}
            className="rounded-lg border border-slate-200 bg-white p-3 shadow-sm"
          >
            <div className="flex items-start justify-between gap-3">
              <div className="min-w-0 flex-1">
                <div className="flex items-center gap-2">
                  <h3 className="break-words text-sm font-semibold text-slate-900">
                    {task.title}
                  </h3>
                  <span
                    className={[
                      "rounded-full px-2 py-0.5 text-xs font-medium",
                      statusClass(task.status),
                    ].join(" ")}
                  >
                    {formatStatus(task.status)}
                  </span>
                  {task.priority ? (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-xs text-slate-600">
                      {task.priority}
                    </span>
                  ) : null}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {task.course ?? "—"} · Deadline:{" "}
                  {formatDateTime(task.deadline_at)} · Reminder:{" "}
                  {formatDateTime(task.reminder_at)}
                </div>
              </div>
              <div className="flex shrink-0 flex-col gap-1">
                {!isDone ? (
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => handleDone(task)}
                    className="rounded border border-emerald-300 bg-emerald-50 px-2 py-1 text-xs font-medium text-emerald-800 hover:bg-emerald-100 disabled:opacity-50"
                  >
                    {isBusy ? "Menyimpan…" : "Tandai selesai"}
                  </button>
                ) : null}
                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => handleDelete(task)}
                  className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
                >
                  {isBusy ? "Menghapus…" : "Hapus"}
                </button>
              </div>
            </div>
          </li>
        );
      })}
    </ul>
  );
}
