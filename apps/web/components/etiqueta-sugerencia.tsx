"use client";

// Explica de dónde salió una sugerencia manual: con qué criterio se pidió, si se
// repite sola, si vino de una carga masiva y hasta cuándo vive. El número de
// unidades por sí solo no dice nada de eso.
import { CalendarClock, Layers, Repeat, Target, TrendingUp } from "lucide-react";
import { formatoFecha, formatoNumero } from "@/lib/formato";
import type { SugerenciaManual } from "@/lib/types";

/** Cómo se pidió: define el texto y el ícono de la etiqueta principal. */
export function tipoDeSugerencia(m: SugerenciaManual) {
  if (m.stock_objetivo)
    return {
      icon: Target,
      etiqueta: `Mantener ${formatoNumero(m.stock_objetivo)} u en stock`,
      clase: "bg-emerald-50 text-emerald-700",
      detalle:
        "Se pidió la diferencia que faltaba para llegar a ese nivel, " +
        "descontando stock, tránsito y lo que ya sugería el sistema.",
    };
  if (m.dias_inventario)
    return {
      icon: TrendingUp,
      etiqueta: `${m.dias_inventario} días de inventario`,
      clase: "bg-blue-50 text-blue-700",
      detalle: "Las unidades salen de la demanda diaria del producto en esa sucursal.",
    };
  return {
    icon: null,
    etiqueta: "Unidades directas",
    clase: "bg-slate-100 text-slate-600",
    detalle: "Cantidad fija cargada a mano.",
  };
}

export function EtiquetaSugerencia({ m }: { m: SugerenciaManual }) {
  const tipo = tipoDeSugerencia(m);
  const Icon = tipo.icon;
  const vencida = m.expira_en ? new Date(m.expira_en) < new Date() : false;

  return (
    <span className="inline-flex flex-wrap items-center gap-1.5">
      <span
        title={tipo.detalle}
        className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold ${tipo.clase}`}
      >
        {Icon && <Icon size={11} />}
        {tipo.etiqueta}
      </span>

      {m.recurrente_id && (
        <span
          title="Se vuelve a aplicar sola cada cierto tiempo; cada repetición reemplaza a la anterior."
          className="inline-flex items-center gap-1 rounded bg-brand-50 px-1.5 py-0.5 text-[11px] font-semibold text-brand"
        >
          <Repeat size={11} /> Se repite
        </span>
      )}

      {m.lote_id && !m.recurrente_id && (
        <span
          title="Se creó junto a otras en una carga masiva."
          className="inline-flex items-center gap-1 rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-600"
        >
          <Layers size={11} /> Carga masiva
        </span>
      )}

      {m.expira_en && (
        <span
          className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold ${
            vencida ? "bg-red-50 text-red-700" : "bg-amber-50 text-amber-800"
          }`}
        >
          <CalendarClock size={11} />
          {vencida ? "Vencida" : `Hasta ${formatoFecha(m.expira_en)}`}
        </span>
      )}

      {m.archivada && (
        <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[11px] font-semibold text-slate-500">
          Archivada
        </span>
      )}
    </span>
  );
}
