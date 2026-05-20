import { ReactNode } from "react";

type Tone =
  | "online"
  | "idle"
  | "syncing"
  | "offline"
  | "success"
  | "error"
  | "info";

interface BmoBadgeProps {
  tone?: Tone;
  className?: string;
  children: ReactNode;
}

const TONE_CLASSES: Record<Tone, string> = {
  online: "bg-bmo-screen text-bmo-dark",
  success: "bg-bmo-screen text-bmo-dark",
  idle: "bg-yellow-100 text-yellow-900",
  syncing: "bg-bmo-blue-light text-bmo-blue",
  info: "bg-bmo-blue-light text-bmo-blue",
  offline: "bg-pink-100 text-bmo-red",
  error: "bg-pink-100 text-bmo-red",
};

export function BmoBadge({
  tone = "info",
  className = "",
  children,
}: BmoBadgeProps) {
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${TONE_CLASSES[tone]} ${className}`}
    >
      {children}
    </span>
  );
}
