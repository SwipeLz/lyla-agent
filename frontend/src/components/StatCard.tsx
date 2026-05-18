type Tone = "neutral" | "warn" | "good";

interface StatCardProps {
  label: string;
  value: string | number;
  hint?: string;
  tone?: Tone;
}

const TONE_CLASSES: Record<Tone, { border: string; value: string }> = {
  neutral: { border: "border-slate-200", value: "text-slate-900" },
  warn: { border: "border-amber-200", value: "text-amber-700" },
  good: { border: "border-emerald-200", value: "text-emerald-700" },
};

export function StatCard({
  label,
  value,
  hint,
  tone = "neutral",
}: StatCardProps) {
  const t = TONE_CLASSES[tone];
  return (
    <div
      className={`rounded-lg border ${t.border} bg-white p-4 shadow-sm`}
    >
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className={`mt-1 text-2xl font-semibold ${t.value}`}>{value}</div>
      {hint ? (
        <div className="mt-1 text-xs text-slate-400">{hint}</div>
      ) : null}
    </div>
  );
}
