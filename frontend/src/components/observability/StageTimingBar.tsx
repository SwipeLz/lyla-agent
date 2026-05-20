import { StageTimings } from "../../lib/types";

interface StageTimingBarProps {
  timings: StageTimings;
}

const STAGES: Array<{ key: keyof StageTimings; label: string; color: string }> = [
  { key: "validate", label: "validate", color: "#9FD5B1" },
  { key: "stt", label: "stt", color: "#77CFDB" },
  { key: "agent", label: "agent", color: "#313F98" },
  { key: "classify", label: "classify", color: "#F7E72F" },
  { key: "tts", label: "tts", color: "#1F8941" },
];

const fmtMs = (ms: number | null | undefined): string => {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

export function StageTimingBar({ timings }: StageTimingBarProps) {
  const total = STAGES.reduce(
    (sum, s) => sum + (timings[s.key] ?? 0),
    0,
  );
  if (total === 0) {
    return (
      <p className="text-sm text-slate-500">
        Stage timing belum tersedia untuk request ini.
      </p>
    );
  }

  return (
    <div className="space-y-2">
      <div className="flex h-6 w-full overflow-hidden rounded border border-bmo-border">
        {STAGES.map((s) => {
          const value = timings[s.key] ?? 0;
          if (value <= 0) return null;
          const pct = (value / total) * 100;
          return (
            <div
              key={s.key}
              title={`${s.label}: ${fmtMs(value)}`}
              style={{ width: `${pct}%`, background: s.color }}
              aria-label={`${s.label} ${fmtMs(value)}`}
            />
          );
        })}
      </div>
      <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs text-slate-600 md:grid-cols-5">
        {STAGES.map((s) => (
          <div key={s.key} className="flex items-center gap-1.5">
            <span
              className="inline-block h-2 w-2 rounded-sm"
              style={{ background: s.color }}
              aria-hidden="true"
            />
            <span className="font-medium text-bmo-dark">{s.label}</span>
            <span className="font-mono">{fmtMs(timings[s.key])}</span>
          </div>
        ))}
      </div>
      <p className="pt-1 text-xs text-slate-500">
        Total: <span className="font-mono">{fmtMs(total)}</span>
      </p>
    </div>
  );
}
