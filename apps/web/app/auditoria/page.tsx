"use client";

import { useEffect, useState } from "react";
import {
  Pencil,
  PlusCircle,
  RefreshCw,
  Repeat,
  Trash2,
  Users,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { AuditoriaLog } from "@/lib/types";

const ACCIONES: Record<
  string,
  { label: string; color: string; icon: typeof PlusCircle }
> = {
  creada: { label: "Creo", color: "text-emerald-700 bg-emerald-50", icon: PlusCircle },
  masiva_creada: { label: "Carga masiva", color: "text-emerald-700 bg-emerald-50", icon: Users },
  modificada: { label: "Modifico", color: "text-amber-700 bg-amber-50", icon: Pencil },
  eliminada: { label: "Elimino", color: "text-red-700 bg-red-50", icon: Trash2 },
  recurrente_creada: { label: "Recurrencia +", color: "text-brand bg-brand-50", icon: Repeat },
  recurrente_eliminada: { label: "Recurrencia -", color: "text-red-700 bg-red-50", icon: Trash2 },
  recurrente_aplicada: { label: "Recurrente auto", color: "text-slate-600 bg-slate-100", icon: RefreshCw },
};


export default function AuditoriaPage() {
  const [items, setItems] = useState<AuditoriaLog[]>([]);
  const [total, setTotal] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const cargar = async () => {
    setCargando(true);
    setError(null);
    try {
      const r = await api.auditoria(200, 0);
      setItems(r.items);
      setTotal(r.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    cargar();
  }, []);

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">
            Auditoria
          </h1>
          <p className="text-[13px] text-slate-500">
            {cargando
              ? "Cargando…"
              : `${formatoNumero(total)} evento${total === 1 ? "" : "s"}`}
          </p>
        </div>
        <button
          onClick={cargar}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[13px] hover:bg-slate-50"
        >
          <RefreshCw size={14} /> Actualizar
        </button>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {error}
        </p>
      )}

      <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full text-sm">
          <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
            <tr>
              <th className="px-4 py-2 w-36">Cuando</th>
              <th className="px-4 py-2">Accion</th>
              <th className="px-4 py-2">Usuario</th>
              <th className="px-4 py-2">Producto</th>
              <th className="px-4 py-2">Sucursal</th>
              <th className="px-4 py-2 text-right">Cantidad</th>
              <th className="px-4 py-2">Motivo / detalle</th>
            </tr>
          </thead>
          <tbody>
            {items.length === 0 && !cargando ? (
              <tr>
                <td colSpan={7} className="px-4 py-6 text-center text-slate-400">
                  Sin eventos registrados.
                </td>
              </tr>
            ) : (
              items.map((it) => {
                const meta = ACCIONES[it.accion] ?? {
                  label: it.accion,
                  color: "text-slate-600 bg-slate-100",
                  icon: PlusCircle,
                };
                const Icon = meta.icon;
                const cant =
                  it.dias_inventario != null
                    ? `+${it.dias_inventario} dias`
                    : it.unidades != null
                      ? `+${formatoNumero(it.unidades)} u`
                      : "—";
                return (
                  <tr key={it.id} className="border-t border-slate-100">
                    <td className="px-4 py-2 text-[12px] text-slate-500 whitespace-nowrap">
                      {formatoFechaHora(it.creado_en)}
                    </td>
                    <td className="px-4 py-2">
                      <span
                        className={`inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[11px] font-semibold ${meta.color}`}
                      >
                        <Icon size={12} /> {meta.label}
                      </span>
                    </td>
                    <td className="px-4 py-2 text-slate-700">
                      {it.usuario_email ?? "—"}
                    </td>
                    <td className="px-4 py-2 font-medium text-slate-900">
                      {it.producto ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-slate-600">
                      {it.sucursal_id ?? "—"}
                    </td>
                    <td className="px-4 py-2 text-right tabular-nums font-semibold">
                      {cant}
                    </td>
                    <td className="px-4 py-2 text-[12px] text-slate-500">
                      {it.motivo && <span>{it.motivo}</span>}
                      {it.motivo && it.detalle && " · "}
                      {it.detalle && <span>{it.detalle}</span>}
                      {!it.motivo && !it.detalle && "—"}
                    </td>
                  </tr>
                );
              })
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
