"use client";

// Detalle de una sucursal para jefatura: la "lista" tipo SharePoint con cantidades,
// diferencias, estado, evidencia y observacion. El admin puede marcar evidencia aqui.
import { useMemo, useState } from "react";
import { Badge, colorABC } from "@/components/ui/badge";
import { formatoCLP, formatoFechaHora, formatoNumero } from "@/lib/formato";
import { ESTADOS, inventarioApi, type EstadoItem, type ItemInventario } from "@/lib/inventario-ciclico";
import { Evidencias } from "./evidencias";

interface Props {
  items: ItemInventario[];
  onCambio: (item: ItemInventario) => void;
}

const CLASES = ["A", "B", "C", "D"];

export function Detalle({ items, onCambio }: Props) {
  const [q, setQ] = useState("");
  const [clase, setClase] = useState("");
  const [estado, setEstado] = useState<EstadoItem | "">("");
  const [soloDif, setSoloDif] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const visibles = useMemo(() => {
    const t = q.trim().toLowerCase();
    return items.filter(
      (i) =>
        (!clase || i.clase === clase) &&
        (!estado || i.estado === estado) &&
        (!soloDif || (i.diferencia ?? 0) !== 0) &&
        (!t || i.producto.toLowerCase().includes(t) || (i.descripcion ?? "").toLowerCase().includes(t))
    );
  }, [items, q, clase, estado, soloDif]);

  const marcarEvidencia = async (item: ItemInventario, valor: boolean) => {
    setError(null);
    try {
      onCambio(await inventarioApi.actualizar(item.id, { requiere_evidencia: valor }));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    }
  };

  const select = "h-9 rounded-sm border border-ink-200 bg-white px-2 text-[13px]";

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-2">
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Buscar código o descripción"
          className="h-9 min-w-[200px] flex-1 rounded-sm border border-ink-200 bg-white px-3 text-[13px] focus:border-accent-700 focus:outline-none"
        />
        <select value={clase} onChange={(e) => setClase(e.target.value)} className={select} aria-label="Clase">
          <option value="">Todas las clases</option>
          {CLASES.map((c) => (
            <option key={c} value={c}>
              Clase {c}
            </option>
          ))}
        </select>
        <select
          value={estado}
          onChange={(e) => setEstado(e.target.value as EstadoItem | "")}
          className={select}
          aria-label="Estado"
        >
          <option value="">Todos los estados</option>
          {Object.entries(ESTADOS).map(([k, v]) => (
            <option key={k} value={k}>
              {v.label}
            </option>
          ))}
        </select>
        <label className="flex items-center gap-1.5 text-[13px] text-ink-700">
          <input type="checkbox" checked={soloDif} onChange={(e) => setSoloDif(e.target.checked)} />
          Solo con diferencia
        </label>
      </div>
      {error && <p className="rounded-sm bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>}

      <div className="overflow-x-auto rounded-sm border border-ink-200 bg-white shadow-card">
        <table className="w-full min-w-[1000px] text-[12.5px]">
          <thead className="bg-paper-100 text-left text-[11px] uppercase tracking-wider text-ink-500">
            <tr>
              <th className="px-2 py-2">Producto</th>
              <th className="px-2 py-2">Clase</th>
              <th className="px-2 py-2 text-right">Sistema</th>
              <th className="px-2 py-2 text-right">Contado</th>
              <th className="px-2 py-2 text-right">Dif.</th>
              <th className="px-2 py-2 text-right">Dif. $</th>
              <th className="px-2 py-2">Estado</th>
              <th className="px-2 py-2">Evidencia</th>
              <th className="px-2 py-2">Observación</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-ink-100">
            {visibles.map((i) => {
              const meta = ESTADOS[i.estado];
              const dif = i.diferencia ?? 0;
              return (
                <tr key={i.id} className="align-top">
                  <td className="px-2 py-2">
                    <p className="font-medium text-ink-900">{i.producto}</p>
                    <p className="text-ink-500">{i.descripcion ?? "—"}</p>
                  </td>
                  <td className="px-2 py-2">
                    <Badge className={colorABC(i.clase)}>{i.clase}</Badge>
                  </td>
                  <td className="px-2 py-2 text-right">{formatoNumero(i.cantidad_sistema)}</td>
                  <td className="px-2 py-2 text-right">
                    {formatoNumero(i.cantidad_contada)}
                    {i.contado_por && (
                      <p className="text-[10.5px] text-ink-400" title={i.contado_por}>
                        {formatoFechaHora(i.contado_en)}
                      </p>
                    )}
                  </td>
                  <td className={`px-2 py-2 text-right font-medium ${dif > 0 ? "text-blue-700" : dif < 0 ? "text-red-700" : ""}`}>
                    {i.diferencia === null ? "—" : `${dif > 0 ? "+" : ""}${formatoNumero(dif)}`}
                  </td>
                  <td className={`px-2 py-2 text-right ${dif > 0 ? "text-blue-700" : dif < 0 ? "text-red-700" : ""}`}>
                    {i.diferencia_valor === null ? "—" : formatoCLP(i.diferencia_valor)}
                  </td>
                  <td className="px-2 py-2">
                    <span className={`whitespace-nowrap rounded px-2 py-0.5 text-[11px] font-semibold ${meta.clase}`}>
                      {meta.label}
                    </span>
                  </td>
                  <td className="px-2 py-2">
                    <label className="mb-1 flex items-center gap-1 whitespace-nowrap text-[11.5px] text-ink-600">
                      <input
                        type="checkbox"
                        checked={i.requiere_evidencia}
                        onChange={(e) => marcarEvidencia(i, e.target.checked)}
                      />
                      Requiere
                    </label>
                    <Evidencias item={i} puedeSubir={false} esAdmin onCambio={onCambio} />
                  </td>
                  <td className="max-w-[260px] whitespace-pre-wrap px-2 py-2 text-ink-700">{i.observacion ?? ""}</td>
                </tr>
              );
            })}
            {visibles.length === 0 && (
              <tr>
                <td colSpan={9} className="px-2 py-6 text-center text-ink-500">
                  Nada coincide con el filtro.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  );
}
