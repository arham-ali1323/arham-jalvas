import { forwardRef, type InputHTMLAttributes } from "react";

import { cn } from "@/lib/utils";

export const Input = forwardRef<HTMLInputElement, InputHTMLAttributes<HTMLInputElement>>(
  ({ className, type, ...props }, ref) => (
    <input
      ref={ref}
      type={type}
      className={cn(
        "h-10 w-full rounded-lg border border-border bg-surface/70 px-3 text-sm text-slate-100 placeholder:text-muted focus:border-primary/70 focus:outline-none focus:ring-1 focus:ring-primary/40 disabled:opacity-50",
        className,
      )}
      {...props}
    />
  ),
);
Input.displayName = "Input";
