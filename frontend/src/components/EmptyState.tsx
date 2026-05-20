import { ReactNode } from "react";
import { BmoFace, BmoExpression } from "./bmo/BmoFace";

interface EmptyStateProps {
  face?: BmoExpression;
  title: string;
  description?: string;
  cta?: ReactNode;
  className?: string;
}

export function EmptyState({
  face = "idle",
  title,
  description,
  cta,
  className = "",
}: EmptyStateProps) {
  return (
    <div
      className={`flex flex-col items-center justify-center gap-4 rounded-lg border border-bmo-border bg-surface-elev p-8 text-center ${className}`}
    >
      <BmoFace expression={face} size={140} />
      <div className="space-y-1">
        <h3 className="text-base font-medium text-bmo-dark">{title}</h3>
        {description ? (
          <p className="text-sm text-slate-600">{description}</p>
        ) : null}
      </div>
      {cta ? <div className="mt-2">{cta}</div> : null}
    </div>
  );
}
