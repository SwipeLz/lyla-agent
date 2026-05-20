import { ReactNode } from "react";

type Variant = "default" | "success" | "info" | "warning" | "error";

interface BmoCardProps {
  variant?: Variant;
  className?: string;
  children: ReactNode;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  default: "bg-surface-elev border-bmo-border",
  success: "bg-bmo-screen border-bmo-mouth/40",
  info: "bg-bmo-blue-light/40 border-bmo-blue/30",
  warning: "bg-yellow-50 border-yellow-300",
  error: "bg-red-50 border-bmo-red/40",
};

export function BmoCard({
  variant = "default",
  className = "",
  children,
}: BmoCardProps) {
  return (
    <div
      className={`rounded-lg border p-4 ${VARIANT_CLASSES[variant]} ${className}`}
    >
      {children}
    </div>
  );
}
