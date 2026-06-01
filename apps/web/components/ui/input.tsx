import * as React from "react";
import { cn } from "@/lib/utils";

export const Input = React.forwardRef<
  HTMLInputElement,
  React.InputHTMLAttributes<HTMLInputElement>
>(({ className, ...props }, ref) => (
  <input
    ref={ref}
    className={cn(
      "h-9 w-full rounded-sm border border-ink-200 bg-white px-3 text-[13.5px] text-ink-900 placeholder:text-ink-400 transition-colors focus-visible:border-accent-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-700/30",
      className
    )}
    {...props}
  />
));
Input.displayName = "Input";

export const Textarea = React.forwardRef<
  HTMLTextAreaElement,
  React.TextareaHTMLAttributes<HTMLTextAreaElement>
>(({ className, ...props }, ref) => (
  <textarea
    ref={ref}
    className={cn(
      "w-full rounded-sm border border-ink-200 bg-white px-3 py-2 text-[13.5px] text-ink-900 placeholder:text-ink-400 transition-colors focus-visible:border-accent-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-700/30",
      className
    )}
    {...props}
  />
));
Textarea.displayName = "Textarea";

export function Label({
  className,
  ...props
}: React.LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label
      className={cn("mb-1 block text-[12.5px] font-medium text-ink-700", className)}
      {...props}
    />
  );
}
