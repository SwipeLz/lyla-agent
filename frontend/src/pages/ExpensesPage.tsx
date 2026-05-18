import { FormEvent, useEffect, useState } from "react";
import { ApiError, Expense } from "../lib/types";
import * as api from "../lib/api";
import { isReady } from "../lib/env";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { ExpenseList } from "../components/ExpenseList";

export function ExpensesPage() {
  const ready = isReady();
  const userId = ready.ok ? ready.userId : null;

  const [expenses, setExpenses] = useState<Expense[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<Error | null>(null);

  const [amount, setAmount] = useState<string>("");
  const [category, setCategory] = useState<string>("");
  const [note, setNote] = useState<string>("");
  const [spentAt, setSpentAt] = useState<string>("");
  const [submitting, setSubmitting] = useState(false);
  const [formError, setFormError] = useState<string | null>(null);

  const load = async (uid: string) => {
    setLoading(true);
    setError(null);
    try {
      setExpenses(await api.getExpenses(uid));
    } catch (err) {
      setError(err instanceof Error ? err : new Error(String(err)));
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    if (userId) void load(userId);
  }, [userId]);

  const handleSubmit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (!userId) return;
    const amountNum = Number.parseInt(amount, 10);
    if (!Number.isFinite(amountNum) || amountNum <= 0) {
      setFormError("Amount harus bilangan bulat positif (rupiah).");
      return;
    }
    setSubmitting(true);
    setFormError(null);
    try {
      const created = await api.createExpense({
        user_id: userId,
        amount: amountNum,
        category: category.trim() || null,
        note: note.trim() || null,
        spent_at: spentAt ? new Date(spentAt).toISOString() : null,
      });
      setExpenses((prev) => [created, ...prev]);
      setAmount("");
      setCategory("");
      setNote("");
      setSpentAt("");
    } catch (err) {
      setFormError(
        err instanceof ApiError ? err.message : String(err),
      );
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <section className="space-y-4">
      <header className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Pengeluaran</h1>
        <button
          type="button"
          onClick={() => userId && load(userId)}
          disabled={!userId || loading}
          className="rounded border border-slate-300 bg-white px-3 py-1 text-sm hover:bg-slate-50 disabled:opacity-50"
        >
          Refresh
        </button>
      </header>

      <form
        onSubmit={handleSubmit}
        className="grid gap-3 rounded-lg border border-slate-200 bg-white p-4 shadow-sm md:grid-cols-2"
      >
        <label className="space-y-1 text-sm">
          <span className="text-slate-700">Amount (IDR)</span>
          <input
            type="number"
            min={1}
            step={1}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
            className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-slate-700">Kategori</span>
          <input
            type="text"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
            placeholder="makan, transport, …"
          />
        </label>
        <label className="space-y-1 text-sm md:col-span-2">
          <span className="text-slate-700">Catatan</span>
          <textarea
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="text-slate-700">Waktu</span>
          <input
            type="datetime-local"
            value={spentAt}
            onChange={(e) => setSpentAt(e.target.value)}
            className="w-full rounded border border-slate-300 px-2 py-1 text-sm"
          />
        </label>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={submitting || !userId}
            className="rounded bg-slate-900 px-3 py-1.5 text-sm font-medium text-white hover:bg-slate-800 disabled:opacity-50"
          >
            {submitting ? "Menyimpan…" : "Tambah"}
          </button>
        </div>
        {formError ? (
          <p className="md:col-span-2 rounded border border-red-200 bg-red-50 p-2 text-xs text-red-800">
            {formError}
          </p>
        ) : null}
      </form>

      {loading ? <LoadingState /> : null}
      {error ? <ErrorState error={error} onRetry={() => userId && load(userId)} /> : null}
      {!loading && !error ? <ExpenseList expenses={expenses} /> : null}
    </section>
  );
}
