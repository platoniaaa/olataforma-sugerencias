"use client";

// Una tarjeta por sucursal: avance de la semana, diferencias en $ y cobertura del ano.
import { AlertTriangle } from "lucide-react";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import type { ResumenSucursal } from "@/lib/inventario-ciclico";

interface Props {
  filas: ResumenSucursal[];
  seleccionada: string | null;
  onSeleccionar: (sucursal: string) => void;
}

export function Resumen({ filas, seleccionada, onSeleccionar }: Props) {
  if (filas.length === 0) {
    return (
      <p className="rounded-sm border border-dashed border-ink-200 bg-white px-4 py-8 text-center text-[13px] text-ink-500">
        No hay productos cargados para esta semana. Súbelos en la pestaña “Carga semanal”.
      </p>
    );
  }
  const total = filas.reduce(
    (a, f) => ({
      asignados: a.asignados + f.asignados,
      contados: a.contados + f.contados,
      sobrante: a.sobrante + f.diferencia_sobrante,
      faltante: a.faltante + f.diferencia_faltante,
    }),
    { asignados: 0, contados: 0, sobrante: 0, faltante: 0 }
  );

  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
        <Kpi label="Avance total" valor={`${pct(total.contados, total.asignados)}%`} detalle={`${total.contados} de ${total.asignados}`} />
        <Kpi label="Sucursales" valor={String(filas.length)} />
        <Kpi label="Sobrante" valor={formatoCLP(total.sobrante)} clase="text-blue-700" />
        <Kpi label="Faltante" valor={formatoCLP(total.faltante)} clase="text-red-700" />
      </div>

      <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
        {filas.map((f) => {
          const avance = pct(f.contados, f.asignados);
          const cobertura = pct(f.contados_en_el_ano, f.productos_con_stock);
          return (
            <button
              key={f.sucursal_id}
              type="button"
              onClick={() => onSeleccionar(f.sucursal_id)}
              className={`rounded-sm border bg-white p-3 text-left shadow-card transition-colors hover:border-accent-500 ${
                seleccionada === f.sucursal_id ? "border-accent-500 ring-1 ring-accent-500" : "border-ink-200"
              }`}
            >
              <div className="flex items-baseline justify-between">
                <p className="font-display text-[15px] font-medium text-ink-900">{f.sucursal_id}</p>
                <p className="text-[13px] font-semibold text-ink-700">{avance}%</p>
              </div>
              <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-ink-100">
                <div className="h-full bg-emerald-500" style={{ width: `${avance}%` }} />
              </div>
              <dl className="mt-2 grid grid-cols-2 gap-x-3 gap-y-0.5 text-[12px]">
                <Dato k="Contados" v={`${f.contados} de ${f.asignados}`} />
                <Dato k="Pendientes" v={String(f.pendientes)} />
                <Dato k="Con diferencia" v={String(f.con_diferencia)} />
                <Dato k="Falta evidencia" v={String(f.falta_evidencia)} alerta={f.falta_evidencia > 0} />
                <Dato k="Sobrante" v={formatoCLP(f.diferencia_sobrante)} />
                <Dato k="Faltante" v={formatoCLP(f.diferencia_faltante)} />
              </dl>
              <p className="mt-2 border-t border-ink-100 pt-1.5 text-[11.5px] text-ink-500">
                Año: {formatoNumero(f.contados_en_el_ano)} de {formatoNumero(f.productos_con_stock)} productos con stock ({cobertura}%)
                {f.cuota_sugerida > 0 && ` · sugerido ${f.cuota_sugerida}/semana`}
              </p>
              {(f.clases_faltantes.length > 0 || f.asignados < f.cuota_sugerida) && (
                <div className="mt-1.5 space-y-0.5 text-[11.5px] text-amber-800">
                  {f.clases_faltantes.length > 0 && (
                    <p className="flex items-center gap-1">
                      <AlertTriangle size={12} /> Falta clase {f.clases_faltantes.join(", ")}
                    </p>
                  )}
                  {f.asignados < f.cuota_sugerida && (
                    <p className="flex items-center gap-1">
                      <AlertTriangle size={12} /> Bajo lo sugerido para cubrir el año
                    </p>
                  )}
                </div>
              )}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function pct(a: number, b: number): number {
  return b ? Math.min(100, Math.round((a / b) * 100)) : 0;
}

function Kpi({ label, valor, detalle, clase }: { label: string; valor: string; detalle?: string; clase?: string }) {
  return (
    <div className="rounded-sm border border-ink-200 bg-white px-3 py-2 shadow-card">
      <p className="text-[11px] uppercase tracking-wider text-ink-500">{label}</p>
      <p className={`text-[17px] font-semibold ${clase ?? "text-ink-900"}`}>{valor}</p>
      {detalle && <p className="text-[11px] text-ink-500">{detalle}</p>}
    </div>
  );
}

function Dato({ k, v, alerta }: { k: string; v: string; alerta?: boolean }) {
  return (
    <>
      <dt className="text-ink-500">{k}</dt>
      <dd className={`text-right font-medium ${alerta ? "text-amber-800" : "text-ink-800"}`}>{v}</dd>
    </>
  );
}
