import { FormEvent, useEffect, useState } from "react";
import { ApiError, Expense } from "../lib/types";
import * as api from "../lib/api";
import { isReady } from "../lib/env";
import { LoadingState } from "../components/LoadingState";
import { ErrorState } from "../components/ErrorState";
import { ExpenseList } from "../components/ExpenseList";
import { EmptyState } from "../components/EmptyState";
import { BmoButton } from "../components/bmo/BmoButton";
import { BmoInput } from "../components/bmo/BmoInput";

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
        <h1 className="text-2xl font-medium text-bmo-dark">Pengeluaran</h1>
        <BmoButton
          variant="secondary"
          size="sm"
          onClick={() => userId && load(userId)}
          disabled={!userId || loading}
        >
          Refresh
        </BmoButton>
      </header>

      <form
        onSubmit={handleSubmit}
        className="grid gap-3 rounded-lg border border-bmo-border bg-surface-elev p-4 md:grid-cols-2"
      >
        <label className="space-y-1 text-sm">
          <span className="font-medium text-bmo-dark">Amount (IDR)</span>
          <BmoInput
            type="number"
            min={1}
            step={1}
            value={amount}
            onChange={(e) => setAmount(e.target.value)}
            required
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium text-bmo-dark">Kategori</span>
          <BmoInput
            type="text"
            value={category}
            onChange={(e) => setCategory(e.target.value)}
            placeholder="makan, transport, …"
          />
        </label>
        <label className="space-y-1 text-sm md:col-span-2">
          <span className="font-medium text-bmo-dark">Catatan</span>
          <textarea
            rows={2}
            value={note}
            onChange={(e) => setNote(e.target.value)}
            className="w-full rounded-md border-2 border-bmo-body bg-surface-elev px-3 py-2 text-sm text-bmo-dark focus:border-bmo-mouth focus:outline-none focus:ring-2 focus:ring-bmo-mouth/20"
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="font-medium text-bmo-dark">Waktu</span>
          <BmoInput
            type="datetime-local"
            value={spentAt}
            onChange={(e) => setSpentAt(e.target.value)}
          />
        </label>
        <div className="flex items-end">
          <BmoButton type="submit" disabled={submitting || !userId}>
            {submitting ? "Menyimpan…" : "Tambah"}
          </BmoButton>
        </div>
        {formError ? (
          <p className="md:col-span-2 rounded border border-bmo-red/40 bg-pink-50 p-2 text-xs text-bmo-red">
            {formError}
          </p>
        ) : null}
      </form>

      {loading ? <LoadingState /> : null}
      {error ? <ErrorState error={error} onRetry={() => userId && load(userId)} /> : null}
      {!loading && !error ? (
        expenses.length === 0 ? (
          <EmptyState
            face="idle"
            title="Belum ada pengeluaran"
            description="Coba: catat makan siang 25000"
          />
        ) : (
          <ExpenseList expenses={expenses} />
        )
      ) : null}
    </section>
  );
}
