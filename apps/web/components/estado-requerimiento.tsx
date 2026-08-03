"use client";

/**
 * El estado de un requerimiento, con el mismo color en las cuatro pantallas.
 *
 * Que el vendedor y el comprador vean la misma etiqueta con el mismo color para
 * el mismo estado es la mitad de que dejen de llamarse por teléfono a preguntar
 * "¿lo viste?".
 */

import type { EstadoRequerimiento } from "@/lib/types";

const ESTILOS: Record<EstadoRequerimiento, { texto: string; clase: string }> = {
  enviado: { texto: "Enviado", clase: "bg-blue-50 text-blue-700 border-blue-200" },
  en_revision: { texto: "En revisión", clase: "bg-amber-50 text-amber-800 border-amber-200" },
  procesado: { texto: "Comprado", clase: "bg-emerald-50 text-emerald-700 border-emerald-200" },
  rechazado: { texto: "Rechazado", clase: "bg-red-50 text-red-700 border-red-200" },
};

export function EstadoRequerimientoBadge({ estado }: { estado: EstadoRequerimiento }) {
  const e = ESTILOS[estado] ?? ESTILOS.enviado;
  return (
    <span
      className={`inline-flex items-center rounded-sm border px-2 py-0.5 text-[11.5px] font-medium ${e.clase}`}
    >
      {e.texto}
    </span>
  );
}
