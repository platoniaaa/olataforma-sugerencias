import * as React from "react";
import { cn } from "@/lib/utils";

/**
 * Badge "etiqueta industrial": esquinas cuadradas, tracking marcado.
 * Sensacion de label de archivador/almacen vs pildora de marketing.
 */
export function Badge({
  className,
  ...props
}: React.HTMLAttributes<HTMLSpanElement>) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider",
        className
      )}
      {...props}
    />
  );
}

/** Devuelve clases de color para una clasificacion ABC. */
export function colorABC(abc: string | null | undefined): string {
  switch ((abc ?? "").toUpperCase()) {
    case "A":
      return "bg-emerald-50 text-emerald-700 border border-emerald-200";
    case "B":
      return "bg-amber-50 text-amber-700 border border-amber-200";
    case "C":
      return "bg-ink-100 text-ink-600 border border-ink-200";
    default:
      return "bg-paper-100 text-ink-500 border border-ink-200";
  }
}
