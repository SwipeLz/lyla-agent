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
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from "recharts";

const DEFAULT_CATEGORIES = [
  { emoji: "🍜", label: "Makan" },
  { emoji: "🚗", label: "Transport" },
  { emoji: "📚", label: "Pendidikan" },
  { emoji: "👗", label: "Belanja" },
  { emoji: "💊", label: "Kesehatan" },
  { emoji: "🎮", label: "Hiburan" },
  { emoji: "🏠", label: "Kos/Rumah" },
  { emoji: "🎁", label: "Lainnya" },
];

const STORAGE_KEY = "taskbot_custom_categories";

const loadCustomCategories = (): { emoji: string; label: string }[] => {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
};

const saveCustomCategories = (cats: { emoji: string; label: string }[]) => {
  localStorage.setItem(STORAGE_KEY, JSON.stringify(cats));
};

const formatRp = (n: number) =>
  new Intl.NumberFormat("id-ID", {
    style: "currency",
    currency: "IDR",
    maximumFractionDigits: 0,
  }).format(n);

const BAR_COLOR_ODD = "#15803d";
const BAR_COLOR_EVEN = "#86efac";

const buildChartData = (expenses: Expense[], monthDate: Date) => {
  const daysInMonth = new Date(
    monthDate.getFullYear(),
    monthDate.getMonth() + 1,
    0,
  ).getDate();
  const map: Record<number, number> = {};
  for (let i = 1; i <= daysInMonth; i++) {
    map[i] = 0;
  }
  for (const e of expenses) {
    const d = new Date(e.spent_at);
    if (Number.isNaN(d.getTime())) continue;
    if (
      d.getMonth() !== monthDate.getMonth() ||
      d.getFullYear() !== monthDate.getFullYear()
    )
      continue;
    map[d.getDate()] = (map[d.getDate()] ?? 0) + e.amount;
  }
  return Object.entries(map).map(([day, total]) => ({
    label: String(parseInt(day, 10)),
    day: parseInt(day, 10),
    total,
  }));
};

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

  const [chartMonth, setChartMonth] = useState(new Date());
  const [showCategoryPicker, setShowCategoryPicker] = useState(false);
  const [customCategories, setCustomCategories] = useState(loadCustomCategories);
  const [newCatEmoji, setNewCatEmoji] = useState("✨");
  const [newCatLabel, setNewCatLabel] = useState("");
  const [showAddCat, setShowAddCat] = useState(false);

  const allCategories = [...DEFAULT_CATEGORIES, ...customCategories];

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
      setFormError(err instanceof ApiError ? err.message : String(err));
    } finally {
      setSubmitting(false);
    }
  };

  const handleAddCategory = () => {
    if (!newCatLabel.trim()) return;
    const newCat = { emoji: newCatEmoji, label: newCatLabel.trim() };
    const updated = [...customCategories, newCat];
    setCustomCategories(updated);
    saveCustomCategories(updated);
    setNewCatLabel("");
    setShowAddCat(false);
  };

  const chartData = buildChartData(expenses, chartMonth);
  const monthLabel = chartMonth.toLocaleDateString("id-ID", {
    month: "long",
    year: "numeric",
  });
  const prevMonth = () =>
    setChartMonth((d) => new Date(d.getFullYear(), d.getMonth() - 1, 1));
  const nextMonth = () =>
    setChartMonth((d) => new Date(d.getFullYear(), d.getMonth() + 1, 1));
  const totalBulan = chartData.reduce((acc, d) => acc + d.total, 0);

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

      {/* Chart */}
      <div className="rounded-lg border border-bmo-border bg-surface-elev p-4">
        <div className="mb-2 flex items-center justify-between">
          <div className="flex items-center gap-2">
            <h2 className="text-sm font-semibold text-bmo-dark">
              Grafik Pengeluaran
            </h2>
            <div className="flex items-center gap-1">
              <button
                type="button"
                onClick={prevMonth}
                className="rounded border border-bmo-border px-2 py-0.5 text-xs hover:bg-slate-50"
              >
                ‹
              </button>
              <span className="min-w-24 text-center text-xs text-bmo-dark">
                {monthLabel}
              </span>
              <button
                type="button"
                onClick={nextMonth}
                className="rounded border border-bmo-border px-2 py-0.5 text-xs hover:bg-slate-50"
              >
                ›
              </button>
            </div>
          </div>
        </div>
        <p className="mb-3 text-sm text-bmo-dark/60">
          Total:{" "}
          <span className="font-semibold text-bmo-dark">
            {formatRp(totalBulan)}
          </span>
        </p>
        <ResponsiveContainer width="100%" height={220}>
          <BarChart
            data={chartData}
            margin={{ top: 4, right: 4, left: 0, bottom: 30 }}
            barCategoryGap="20%"
          >
            <XAxis
              dataKey="label"
              tick={{ fontSize: 9 }}
              interval={0}
              angle={-45}
              textAnchor="end"
              height={50}
            />
            <YAxis
              tick={{ fontSize: 10 }}
              tickFormatter={(v: number) => `${(v / 1000).toFixed(0)}k`}
              width={35}
            />
            <Tooltip formatter={(value: number) => [formatRp(value), "Total"]} />
            <Bar dataKey="total" radius={[3, 3, 0, 0]} barSize={10}>
              {chartData.map((entry) => (
                <Cell
                  key={`cell-${entry.day}`}
                  fill={entry.day % 2 !== 0 ? BAR_COLOR_ODD : BAR_COLOR_EVEN}
                />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>

      {/* Form */}
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

        {/* Category Picker */}
        <div className="space-y-1 text-sm">
          <span className="block font-medium text-bmo-dark">Kategori</span>
          <button
            type="button"
            onClick={() => setShowCategoryPicker((v) => !v)}
            className="w-full rounded-md border-2 border-bmo-body bg-surface-elev px-3 py-2 text-left text-sm text-bmo-dark hover:bg-slate-50"
          >
            {category || (
              <span className="text-bmo-dark/40">Pilih kategori…</span>
            )}
          </button>
          {showCategoryPicker && (
            <div className="mt-1 rounded-lg border border-bmo-border bg-surface-elev p-3 shadow-md">
              <div className="grid grid-cols-4 gap-2">
                {allCategories.map((cat) => (
                  <button
                    key={cat.label}
                    type="button"
                    onClick={() => {
                      setCategory(`${cat.emoji} ${cat.label}`);
                      setShowCategoryPicker(false);
                    }}
                    className="flex flex-col items-center gap-1 rounded-lg border border-bmo-border p-2 text-xs hover:bg-slate-50"
                  >
                    <span className="text-xl">{cat.emoji}</span>
                    <span className="text-bmo-dark">{cat.label}</span>
                  </button>
                ))}
              </div>
              <div className="mt-2 border-t border-bmo-border pt-2">
                {!showAddCat ? (
                  <button
                    type="button"
                    onClick={() => setShowAddCat(true)}
                    className="w-full rounded border border-dashed border-bmo-border py-1 text-xs text-bmo-dark/50 hover:bg-slate-50"
                  >
                    + Tambah kategori
                  </button>
                ) : (
                  <div className="flex gap-2">
                    <input
                      type="text"
                      value={newCatEmoji}
                      onChange={(e) => setNewCatEmoji(e.target.value)}
                      maxLength={2}
                      className="w-12 rounded border border-bmo-border px-1 py-1 text-center text-sm"
                    />
                    <input
                      type="text"
                      value={newCatLabel}
                      onChange={(e) => setNewCatLabel(e.target.value)}
                      placeholder="Nama kategori"
                      className="flex-1 rounded border border-bmo-border px-2 py-1 text-sm"
                    />
                    <BmoButton type="button" size="sm" onClick={handleAddCategory}>
                      Simpan
                    </BmoButton>
                  </div>
                )}
              </div>
            </div>
          )}
        </div>

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
      {error ? (
        <ErrorState error={error} onRetry={() => userId && load(userId)} />
      ) : null}
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