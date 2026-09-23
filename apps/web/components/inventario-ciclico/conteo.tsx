"use client";

// "Mi conteo": lo que bodega usa en el celular. Una tarjeta por producto con
// cantidad, observacion y evidencia. Guarda al apretar "Guardar" (cantidad) o al
// salir del campo (observacion).
import { useMemo, useState } from "react";
import { Check, Loader2, Search } from "lucide-react";
import { Badge, colorABC } from "@/components/ui/badge";
import { formatoNumero } from "@/lib/formato";
import { ESTADOS, inventarioApi, type ItemInventario } from "@/lib/inventario-ciclico";
import { Evidencias } from "./evidencias";

interface Props {
  items: ItemInventario[];
  esAdmin: boolean;
  onCambio: (item: ItemInventario) => void;
}

export function Conteo({ items, esAdmin, onCambio }: Props) {
  const [q, setQ] = useState("");
  const [soloPendientes, setSoloPendientes] = useState(false);

  const contados = items.filter((i) => i.cantidad_contada !== null).length;
  const pct = items.length ? Math.round((contados / items.length) * 100) : 0;
  const sucursales = new Set(items.map((i) => i.sucursal_id));

  const visibles = useMemo(() => {
    const t = q.trim().toLowerCase();
    return items.filter(
      (i) =>
        (!soloPendientes || i.estado === "pendiente" || i.estado === "falta_evidencia") &&
        (!t || i.producto.toLowerCase().includes(t) || (i.descripcion ?? "").toLowerCase().includes(t))
    );
  }, [items, q, soloPendientes]);

  return (
    <div className="space-y-3">
      <div className="rounded-sm border border-ink-200 bg-white p-3 shadow-card">
        <div className="flex items-baseline justify-between text-[13px]">
          <span className="font-medium text-ink-900">
            {contados} de {items.length} contados
          </span>
          <span className="text-ink-500">{pct}%</span>
        </div>
        <div className="mt-2 h-2 overflow-hidden rounded-full bg-ink-100">
          <div className="h-full bg-emerald-500 transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>

      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[200px] flex-1">
          <Search size={15} className="absolute left-2.5 top-1/2 -translate-y-1/2 text-ink-400" />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar código o descripción"
            className="h-10 w-full rounded-sm border border-ink-200 bg-white pl-8 pr-3 text-[14px] focus:border-accent-700 focus:outline-none"
          />
        </div>
        <label className="flex items-center gap-1.5 text-[13px] text-ink-700">
          <input
            type="checkbox"
            checked={soloPendientes}
            onChange={(e) => setSoloPendientes(e.target.checked)}
            className="h-4 w-4"
          />
          Solo pendientes
        </label>
      </div>

      {visibles.length === 0 ? (
        <p className="rounded-sm border border-dashed border-ink-200 bg-white px-4 py-8 text-center text-[13px] text-ink-500">
          {items.length === 0 ? "No hay productos asignados esta semana." : "Nada coincide con el filtro."}
        </p>
      ) : (
        <ul className="space-y-2">
          {visibles.map((i) => (
            <li key={i.id}>
              <TarjetaItem item={i} esAdmin={esAdmin} mostrarSucursal={sucursales.size > 1} onCambio={onCambio} />
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function TarjetaItem({
  item,
  esAdmin,
  mostrarSucursal,
  onCambio,
}: {
  item: ItemInventario;
  esAdmin: boolean;
  mostrarSucursal: boolean;
  onCambio: (item: ItemInventario) => void;
}) {
  const [cantidad, setCantidad] = useState(item.cantidad_contada === null ? "" : String(item.cantidad_contada));
  const [obs, setObs] = useState(item.observacion ?? "");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const meta = ESTADOS[item.estado];

  const numero = cantidad.trim() === "" ? null : Number(cantidad.replace(",", "."));
  const cantidadInvalida = numero !== null && (Number.isNaN(numero) || numero < 0);
  const cantidadCambio = numero !== item.cantidad_contada;

  const guardar = async (cambios: Parameters<typeof inventarioApi.actualizar>[1]) => {
    setGuardando(true);
    setError(null);
    try {
      onCambio(await inventarioApi.actualizar(item.id, cambios));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  };

  return (
    <div className="rounded-sm border border-ink-200 bg-white p-3 shadow-card">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="flex flex-wrap items-center gap-1.5 text-[14px] font-semibold text-ink-900">
            {item.producto}
            <Badge className={colorABC(item.clase)}>{item.clase}</Badge>
            {mostrarSucursal && <span className="text-[11px] font-normal text-ink-500">{item.sucursal_id}</span>}
          </p>
          <p className="text-[13px] text-ink-600">{item.descripcion ?? "—"}</p>
        </div>
        <span className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-semibold ${meta.clase}`}>{meta.label}</span>
      </div>

      <div className="mt-3 flex flex-wrap items-end gap-3">
        <div className="text-[12px] text-ink-500">
          Sistema
          <p className="text-[16px] font-semibold text-ink-900">{formatoNumero(item.cantidad_sistema, 0)}</p>
        </div>
        <div className="flex items-end gap-2">
          <label className="text-[12px] text-ink-500">
            Contado
            <input
              inputMode="decimal"
              value={cantidad}
              onChange={(e) => setCantidad(e.target.value)}
              className={`mt-0.5 block h-10 w-24 rounded-sm border px-2 text-[16px] font-semibold text-ink-900 focus:outline-none ${
                cantidadInvalida ? "border-red-400" : "border-ink-200 focus:border-accent-700"
              }`}
            />
          </label>
          <button
            type="button"
            onClick={() => guardar({ cantidad_contada: numero })}
            disabled={guardando || cantidadInvalida || !cantidadCambio}
            className="inline-flex h-10 items-center gap-1 rounded-sm bg-ink-900 px-3 text-[13px] font-medium text-paper hover:bg-accent-700 disabled:opacity-40"
          >
            {guardando ? <Loader2 size={14} className="animate-spin" /> : <Check size={14} />}
            Guardar
          </button>
        </div>
        {item.diferencia !== null && item.diferencia !== 0 && (
          <p className={`text-[13px] font-medium ${item.diferencia > 0 ? "text-blue-700" : "text-red-700"}`}>
            Diferencia {item.diferencia > 0 ? "+" : ""}
            {formatoNumero(item.diferencia, 0)}
          </p>
        )}
      </div>

      <textarea
        value={obs}
        onChange={(e) => setObs(e.target.value)}
        onBlur={() => obs.trim() !== (item.observacion ?? "") && guardar({ observacion: obs })}
        rows={2}
        maxLength={2000}
        placeholder="Observación (opcional)"
        className="mt-3 w-full rounded-sm border border-ink-200 px-2.5 py-1.5 text-[13.5px] focus:border-accent-700 focus:outline-none"
      />

      <div className="mt-2">
        {item.requiere_evidencia && (
          <p className="mb-1 text-[12px] font-medium text-amber-800">Este producto requiere evidencia.</p>
        )}
        <Evidencias item={item} puedeSubir esAdmin={esAdmin} onCambio={onCambio} />
      </div>
      {error && <p className="mt-1 text-[12px] text-red-700">{error}</p>}
    </div>
  );
}
