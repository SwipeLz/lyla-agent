import { BmoFace, BmoExpression } from "../bmo/BmoFace";

interface HowItWorksStepProps {
  step: number;
  expression: BmoExpression;
  title: string;
  description: string;
}

export function HowItWorksStep({
  step,
  expression,
  title,
  description,
}: HowItWorksStepProps) {
  return (
    <div className="flex flex-col items-center gap-3 rounded-lg border border-bmo-border bg-surface-elev p-5 text-center">
      <div className="flex h-7 w-7 items-center justify-center rounded-full bg-bmo-dark text-xs font-medium text-bmo-screen">
        {step}
      </div>
      <BmoFace expression={expression} size={120} />
      <h4 className="text-sm font-medium text-bmo-dark">{title}</h4>
      <p className="text-xs leading-relaxed text-slate-600">{description}</p>
    </div>
  );
}
