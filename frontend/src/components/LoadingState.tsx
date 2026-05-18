interface LoadingStateProps {
  label?: string;
}

export function LoadingState({ label = "Memuat data…" }: LoadingStateProps) {
  return (
    <div
      className="flex items-center gap-3 rounded-lg border border-slate-200 bg-white p-4 text-sm text-slate-500 shadow-sm"
      role="status"
      aria-live="polite"
    >
      <span className="inline-block h-3 w-3 animate-pulse rounded-full bg-slate-400" />
      <span className="animate-pulse">{label}</span>
    </div>
  );
}
