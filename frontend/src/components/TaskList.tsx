import { useState } from "react";
import { Task } from "../lib/types";
import { formatDateTime, formatStatus } from "../lib/format";
import * as api from "../lib/api";

interface TaskListProps {
  tasks: Task[];
  onUpdate?: (task: Task) => void;
  onDelete?: (taskId: string) => void;
}

interface EditForm {
  title: string;
  status: string;
  deadline_at: string;
  reminder_at: string;
}

const statusClass = (status: string): string => {
  if (status === "done") return "bg-emerald-100 text-emerald-800";
  if (status === "pending") return "bg-amber-100 text-amber-800";
  if (status === "in_progress") return "bg-sky-100 text-sky-800";
  return "bg-slate-200 text-slate-700";
};

/** Konversi ISO string ke format datetime-local (YYYY-MM-DDTHH:mm) */
const toDatetimeLocal = (value: string | null | undefined): string => {
  if (!value) return "";
  // Potong detik & timezone agar cocok dengan input datetime-local
  return value.slice(0, 16);
};

export function TaskList({ tasks, onUpdate, onDelete }: TaskListProps) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editForm, setEditForm] = useState<EditForm>({
    title: "",
    status: "pending",
    deadline_at: "",
    reminder_at: "",
  });

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

  const handleEditOpen = (task: Task) => {
    setEditingId(task.id);
    setEditForm({
      title: task.title,
      status: task.status,
      deadline_at: toDatetimeLocal(task.deadline_at),
      reminder_at: toDatetimeLocal(task.reminder_at),
    });
  };

  const handleEditCancel = () => {
    setEditingId(null);
    setEditForm({ title: "", status: "pending", deadline_at: "", reminder_at: "" });
  };

  const handleEditSave = async (task: Task) => {
    if (busyId) return;
    setBusyId(task.id);
    try {
      const updated = await api.updateTask(task.id, {
        title: editForm.title,
        status: editForm.status,
        deadline_at: editForm.deadline_at
          ? new Date(editForm.deadline_at).toISOString()
          : null,
        reminder_at: editForm.reminder_at
          ? new Date(editForm.reminder_at).toISOString()
          : null,
      });
      onUpdate?.(updated);
      setEditingId(null);
      setEditForm({ title: "", status: "pending", deadline_at: "", reminder_at: "" });
    } finally {
      setBusyId(null);
    }
  };

  return (
    <ul className="space-y-2">
      {tasks.map((task) => {
        const isBusy = busyId === task.id;
        const isDone = task.status === "done";
        const isEditing = editingId === task.id;

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
                    {isBusy && !isEditing ? "Menyimpan…" : "Tandai selesai"}
                  </button>
                ) : null}

                {/* Tombol Edit — hanya tampil jika belum selesai */}
                {!isEditing && !isDone ? (
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={() => handleEditOpen(task)}
                    className="rounded border border-sky-300 bg-sky-50 px-2 py-1 text-xs font-medium text-sky-700 hover:bg-sky-100 disabled:opacity-50"
                  >
                    Edit
                  </button>
                ) : null}

                <button
                  type="button"
                  disabled={isBusy}
                  onClick={() => handleDelete(task)}
                  className="rounded border border-red-300 bg-red-50 px-2 py-1 text-xs font-medium text-red-700 hover:bg-red-100 disabled:opacity-50"
                >
                  {isBusy && !isEditing ? "Menghapus…" : "Hapus"}
                </button>
              </div>
            </div>

            {/* Form Edit Inline */}
            {isEditing ? (
              <div className="mt-3 rounded-md border border-sky-200 bg-sky-50 p-3">
                <div className="space-y-2">
                  {/* Title */}
                  <div>
                    <label className="mb-0.5 block text-xs font-medium text-slate-600">
                      Judul
                    </label>
                    <input
                      type="text"
                      value={editForm.title}
                      onChange={(e) =>
                        setEditForm((f) => ({ ...f, title: e.target.value }))
                      }
                      className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
                    />
                  </div>

                  {/* Status */}
                  <div>
                    <label className="mb-0.5 block text-xs font-medium text-slate-600">
                      Status
                    </label>
                    <select
                      value={editForm.status}
                      onChange={(e) =>
                        setEditForm((f) => ({ ...f, status: e.target.value }))
                      }
                      className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
                    >
                      <option value="pending">Pending</option>
                      <option value="in_progress">Dalam Pengerjaan</option>
                      <option value="done">Selesai</option>
                    </select>
                  </div>

                  {/* Deadline */}
                  <div>
                    <label className="mb-0.5 block text-xs font-medium text-slate-600">
                      Deadline
                    </label>
                    <input
                      type="datetime-local"
                      value={editForm.deadline_at}
                      onChange={(e) =>
                        setEditForm((f) => ({
                          ...f,
                          deadline_at: e.target.value,
                        }))
                      }
                      className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
                    />
                  </div>

                  {/* Reminder */}
                  <div>
                    <label className="mb-0.5 block text-xs font-medium text-slate-600">
                      Reminder
                    </label>
                    <input
                      type="datetime-local"
                      value={editForm.reminder_at}
                      onChange={(e) =>
                        setEditForm((f) => ({
                          ...f,
                          reminder_at: e.target.value,
                        }))
                      }
                      className="w-full rounded border border-slate-300 bg-white px-2 py-1 text-sm text-slate-900 focus:border-sky-400 focus:outline-none focus:ring-1 focus:ring-sky-400"
                    />
                  </div>
                </div>

                {/* Aksi form */}
                <div className="mt-3 flex gap-2">
                  <button
                    type="button"
                    disabled={isBusy || editForm.title.trim() === ""}
                    onClick={() => handleEditSave(task)}
                    className="rounded border border-sky-400 bg-sky-500 px-3 py-1 text-xs font-medium text-white hover:bg-sky-600 disabled:opacity-50"
                  >
                    {isBusy ? "Menyimpan…" : "Simpan"}
                  </button>
                  <button
                    type="button"
                    disabled={isBusy}
                    onClick={handleEditCancel}
                    className="rounded border border-slate-300 bg-white px-3 py-1 text-xs font-medium text-slate-600 hover:bg-slate-100 disabled:opacity-50"
                  >
                    Batal
                  </button>
                </div>
              </div>
            ) : null}
          </li>
        );
      })}
    </ul>
  );
}