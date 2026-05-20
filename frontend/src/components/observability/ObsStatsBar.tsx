import { StatsResponse } from "../../lib/types";

interface ObsStatsBarProps {
  stats: StatsResponse | null;
  loading?: boolean;
}

const fmtMs = (ms: number | null): string => {
  if (ms == null) return "—";
  if (ms < 1000) return `${ms}ms`;
  return `${(ms / 1000).toFixed(2)}s`;
};

const fmtPct = (success: number, total: number): string => {
  if (total === 0) return "—";
  return `${Math.round((success / total) * 100)}%`;
};

interface StatItemProps {
  label: string;
  value: string;
  hint?: string;
}

function StatItem({ label, value, hint }: StatItemProps) {
  return (
    <div className="flex-1 rounded-lg border border-bmo-border bg-surface-elev p-4">
      <div className="text-xs font-medium uppercase tracking-wide text-slate-500">
        {label}
      </div>
      <div className="mt-1 text-2xl font-medium text-bmo-dark">{value}</div>
      {hint ? (
        <div className="mt-1 text-xs text-slate-500">{hint}</div>
      ) : null}
    </div>
  );
}

export function ObsStatsBar({ stats, loading }: ObsStatsBarProps) {
  const top = stats?.top_audio_codes?.[0];
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <StatItem
        label="Total request"
        value={loading ? "…" : (stats?.count ?? 0).toString()}
        hint="dalam window aktif"
      />
      <StatItem
        label="Success rate"
        value={
          loading || !stats
            ? "…"
            : fmtPct(stats.success_count, stats.count)
        }
        hint={
          stats
            ? `${stats.success_count} ok · ${stats.error_count} err`
            : undefined
        }
      />
      <StatItem
        label="p95 latency"
        value={loading ? "…" : fmtMs(stats?.p95_ms ?? null)}
        hint={stats ? `p50 ${fmtMs(stats.p50_ms)}` : undefined}
      />
      <StatItem
        label="Top audio_code"
        value={loading ? "…" : top?.code ?? "—"}
        hint={top ? `${top.count}×` : undefined}
      />
    </div>
  );
}
