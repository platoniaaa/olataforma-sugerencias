"use client";

// El estado de la vigencia de un precio, en una etiqueta: «Fijo hasta 30-11», «Programado
// desde 05-11», «Vencido 12-10». La usan la tabla y la ficha, con el mismo texto.
//
// Cada estado tiene su propio ícono Y su propia palabra: el color ayuda, pero nunca es la
// única señal (el estado de la lista, OK / FIJO / MARGEN, ya usa color para otra cosa).
import { CalendarClock, CalendarRange, CalendarX, Hourglass, type LucideIcon } from "lucide-react";
import { claseVigencia } from "@/lib/columnas-precios";
import { etiquetaVigencia, type IconoVigencia } from "@/lib/vigencia";
import type { PrecioRow } from "@/lib/types";

const ICONOS: Record<IconoVigencia, LucideIcon> = {
  "calendario-reloj": CalendarClock,
  "reloj-arena": Hourglass,
  "calendario-rango": CalendarRange,
  "calendario-x": CalendarX,
};

type FilaVigencia = Partial<Pick<
  PrecioRow,
  "vigencia" | "vigente_desde" | "vigente_hasta" | "vigencia_dias" | "precio_fijo" | "margen_fijo" | "congelar"
>>;

/** No dibuja nada si no hay periodo, o si está vigente sin Hasta (queda fijo hasta que
 *  alguien lo cambie: no hay nada que avisar). */
export function ChipVigencia({ fila, hoy, className = "" }: {
  fila: FilaVigencia;
  /** Fecha de Chile del servidor; sin ella, la del reloj local. */
  hoy?: string;
  className?: string;
}) {
  const e = etiquetaVigencia(fila, hoy);
  if (!e) return null;
  const Icono = ICONOS[e.icono];
  return (
    <span
      title={e.titulo}
      data-tono={e.tono}
      data-testid="chip-vigencia"
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-sm border px-1.5 py-0.5 text-[11px] font-medium leading-none ${claseVigencia(e.tono)} ${className}`}
    >
      <Icono size={12} aria-hidden="true" data-icono={e.icono} />
      <span>{e.texto}</span>
    </span>
  );
}
