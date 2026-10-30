"use client";

import { useEffect, useState } from "react";
import { RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoFechaHora } from "@/lib/formato";

function tiempoRelativo(iso: string): string {
  const d = new Date(iso);
  const segs = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (segs < 60) return "hace segundos";
  const mins = Math.floor(segs / 60);
  if (mins < 60) return `hace ${mins} min`;
  const hs = Math.floor(mins / 60);
  if (hs < 24) return `hace ${hs} h`;
  return `hace ${Math.floor(hs / 24)} d`;
}

/**
 * Indicador de "última actualización de datos" para el header. Se muestra en todas
 * las vistas y a todos los usuarios (el endpoint /api/ultima-sincronizacion es publico).
 */
export function IndicadorSync() {
  const [ultima, setUltima] = useState<string | null>(null);

  useEffect(() => {
    api
      .ultimaSincronizacion()
      .then((r) => setUltima(r.creado_en))
      .catch(() => {
        /* el backend puede estar en cold start; sin dato no mostramos nada */
      });
  }, []);

  if (!ultima) return null;

  return (
    <span
      title={`Datos actualizados el ${formatoFechaHora(ultima)}`}
      className="hidden items-center gap-1.5 whitespace-nowrap text-[12px] text-ink-500 lg:inline-flex"
    >
      <RefreshCw size={13} className="text-ink-400" />
      Actualizado {tiempoRelativo(ultima)}
    </span>
  );
}
