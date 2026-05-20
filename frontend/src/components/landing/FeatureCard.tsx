import { ReactNode } from "react";

interface FeatureCardProps {
  icon: ReactNode;
  title: string;
  description: string;
}

export function FeatureCard({ icon, title, description }: FeatureCardProps) {
  return (
    <div className="flex flex-col gap-3 rounded-lg border border-bmo-border bg-surface-elev p-6 transition-shadow duration-200 hover:shadow-md">
      <div className="flex h-10 w-10 items-center justify-center rounded-md bg-bmo-screen text-bmo-dark">
        {icon}
      </div>
      <h3 className="text-lg font-medium text-bmo-dark">{title}</h3>
      <p className="text-sm leading-relaxed text-slate-600">{description}</p>
    </div>
  );
}
