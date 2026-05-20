import { InputHTMLAttributes, forwardRef } from "react";

type BmoInputProps = InputHTMLAttributes<HTMLInputElement>;

export const BmoInput = forwardRef<HTMLInputElement, BmoInputProps>(
  function BmoInput({ className = "", ...props }, ref) {
    return (
      <input
        ref={ref}
        className={`w-full rounded-md border-2 border-bmo-body bg-surface-elev px-3 py-2 text-sm text-bmo-dark placeholder:text-slate-400 focus:border-bmo-mouth focus:outline-none focus:ring-2 focus:ring-bmo-mouth/20 disabled:cursor-not-allowed disabled:opacity-60 ${className}`}
        {...props}
      />
    );
  },
);
