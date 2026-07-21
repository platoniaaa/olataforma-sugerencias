"use client";

// Modo sombra: muestra que tan cerca esta el motor propio del Power BI. Mientras
// la paridad no se sostenga, el motor NO carga datos: solo se compara.
import { useEffect, useState } from "react";
import { GitCompare, TrendingUp } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import { formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { ComparacionMotor } from "@/lib/types";

export function PanelMotorSombra() {
  const [items, setItems] = useState<ComparacionMotor[]>([]);
  const [cargando, setCargando] = useState(true);

  useEffect(() => {
    api
      .comparacionesMotor()
      .then((r) => setItems(r.items))
      .catch(() => setItems([]))
      .finally(() => setCargando(false));
  }, []);

  if (cargando || items.length === 0) return null;

  const ultima = items[0];
  const color =
    ultima.paridad_pct >= 99
      ? "text-emerald-700"
      : ultima.paridad_pct >= 90
        ? "text-amber-700"
        : "text-red-700";
  const peores = (ultima.detalle?.ejemplos ?? []).slice(0, 8);

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <GitCompare size={17} /> Motor propio (modo sombra)
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3 text-[13px] text-slate-700">
        <p className="text-[12px] text-slate-500">
          El motor calcula el sugerido sin Power BI y se compara contra el vigente.
          No carga nada: la tabla que ven los compradores no se toca.
        </p>

        <div className="flex flex-wrap items-baseline gap-x-8 gap-y-2">
          <div>
            <p className="text-[12px] text-slate-500">Paridad</p>
            <p className={`text-3xl font-semibold tabular ${color}`}>
              {formatoNumero(ultima.paridad_pct, 2)}%
            </p>
          </div>
          <div>
            <p className="text-[12px] text-slate-500">Filas comparadas</p>
            <p className="text-lg font-medium tabular">
              {formatoNumero(ultima.filas_comunes)}
            </p>
          </div>
          {(ultima.filas_solo_motor > 0 || ultima.filas_solo_bi > 0) && (
            <div>
              <p className="text-[12px] text-slate-500">Solo en un lado</p>
              <p className="text-lg font-medium tabular">
                {formatoNumero(ultima.filas_solo_motor)} motor ·{" "}
                {formatoNumero(ultima.filas_solo_bi)} BI
              </p>
            </div>
          )}
        </div>
        <p className="text-[11px] text-slate-400">
          Última comparación: {formatoFechaHora(ultima.creado_en)}
          {ultima.ejecutado_por ? ` · ${ultima.ejecutado_por}` : ""}
        </p>

        {peores.length > 0 && (
          <details className="rounded-md bg-slate-50 px-3 py-2">
            <summary className="cursor-pointer text-[12px] font-medium text-slate-600">
              Mayores divergencias ({peores.length})
            </summary>
            <ul className="mt-2 space-y-1 text-[12px]">
              {peores.map((e) => (
                <li key={`${e.producto}-${e.sucursal_id}`} className="tabular">
                  <span className="font-medium">{e.producto}</span> · {e.sucursal_id}
                  <span className="text-slate-500">
                    {" — "}
                    {Object.entries(e.diferencias)
                      .map(([c, v]) => `${c}: motor ${v.motor ?? "—"} vs BI ${v.bi ?? "—"}`)
                      .join(" · ")}
                  </span>
                </li>
              ))}
            </ul>
          </details>
        )}

        {items.length > 1 && (
          <details className="text-[12px] text-slate-500">
            <summary className="cursor-pointer">
              <TrendingUp size={12} className="mr-1 inline" />
              Historial ({items.length})
            </summary>
            <ul className="mt-1 space-y-0.5">
              {items.map((c) => (
                <li key={c.id} className="tabular">
                  {formatoFechaHora(c.creado_en)} — {formatoNumero(c.paridad_pct, 2)}% sobre{" "}
                  {formatoNumero(c.filas_comunes)} filas
                </li>
              ))}
            </ul>
          </details>
        )}
      </CardContent>
    </Card>
  );
}
