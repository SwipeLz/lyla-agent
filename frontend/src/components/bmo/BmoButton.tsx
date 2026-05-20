import { ButtonHTMLAttributes, forwardRef } from "react";

type Variant = "primary" | "secondary" | "accent" | "destructive";
type Size = "sm" | "md";

interface BmoButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const VARIANT_CLASSES: Record<Variant, string> = {
  primary:
    "bg-bmo-dark text-bmo-screen hover:bg-bmo-mouth disabled:bg-bmo-dark/60",
  secondary:
    "bg-transparent text-bmo-dark border border-bmo-dark hover:bg-bmo-screen disabled:opacity-50",
  accent:
    "bg-bmo-blue text-bmo-blue-light hover:bg-bmo-blue/90 disabled:opacity-50",
  destructive:
    "bg-bmo-red text-white hover:bg-bmo-red/90 disabled:opacity-50",
};

const SIZE_CLASSES: Record<Size, string> = {
  sm: "px-3 py-1 text-xs rounded-md",
  md: "px-5 py-2 text-sm rounded-md",
};

export const BmoButton = forwardRef<HTMLButtonElement, BmoButtonProps>(
  function BmoButton(
    {
      variant = "primary",
      size = "md",
      className = "",
      type = "button",
      ...props
    },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type={type}
        className={`cursor-pointer font-medium transition-colors duration-200 focus:outline-none focus:ring-2 focus:ring-bmo-blue focus:ring-offset-2 disabled:cursor-not-allowed ${VARIANT_CLASSES[variant]} ${SIZE_CLASSES[size]} ${className}`}
        {...props}
      />
    );
  },
);
