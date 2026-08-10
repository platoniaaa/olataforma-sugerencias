"use client";

/**
 * Lo que se abre bajo una línea de "Mi lista" mientras el vendedor arma el pedido.
 *
 * Antes solo veía código, descripción, precio y el stock de su sucursal. Con eso
 * no puede responder las dos preguntas que le va a hacer el comprador: ¿esto se
 * vende? y ¿de verdad hace falta comprarlo? La respuesta a la segunda muchas
 * veces es "hay unidades en otra sucursal": eso es un traslado y lo puede
 * gestionar la propia sucursal, sin orden de compra.
 *
 * No trae costo ni margen a propósito. El vendedor pide, no compra.
 */

import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Loader2 } from "lucide-react";
import { ConsumoChart } from "@/components/consumo-chart";
import { api } from "@/lib/api-client";
import { formatoFecha, formatoNumero } from "@/lib/formato";
import type { ContextoVendedor } from "@/lib/types";

export function DetalleLineaVendedor({
  producto,
  nombreSucursal,
}: {
  producto: string;
  nombreSucursal: string;
}) {
  const [abierto, setAbierto] = useState(false);
  const [d, setD] = useState<ContextoVendedor | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState(false);

  // Se pide al abrir, no al armar la lista: son 10 líneas y casi ninguna se mira.
  useEffect(() => {
    if (!abierto || d || cargando) return;
    setCargando(true);
    setError(false);
    api
      .contextoProducto(producto)
      .then(setD)
      .catch(() => setError(true))
      .finally(() => setCargando(false));
  }, [abierto, d, cargando, producto]);

  const otras = (d?.stock.por_sucursal ?? []).filter(
    (s) => s.stock > 0 && s.sucursal_id !== d?.sucursal_id
  );

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        className="flex items-center gap-1 text-[12.5px] text-ink-500 transition-colors hover:text-brand"
        aria-expanded={abierto}
      >
        {abierto ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
        {abierto ? "Ocultar el detalle" : "Ver la venta y el stock"}
      </button>

      {abierto && (
        <div className="mt-2 rounded-sm border-l-2 border-brand-200 bg-paper-50 px-3 py-3">
          {cargando && (
            <p className="flex items-center gap-2 text-[12.5px] text-ink-400">
              <Loader2 size={13} className="animate-spin" /> Buscando…
            </p>
          )}

          {error && (
            <p className="text-[12.5px] text-ink-500">
              No se pudo cargar el detalle. Puedes enviar la lista igual.
            </p>
          )}

          {d && !cargando && (
            <div className="space-y-3">
              {/* Que FORD lo haya dado de baja hay que saberlo ANTES de pedirlo. */}
              {d.reemplazo_ford?.reemplazado_por_ford && (
                <p className="rounded-sm border border-rose-200 bg-rose-50 px-2.5 py-1.5 text-[12.5px] text-rose-900">
                  <b>FORD dio de baja este código.</b> Lo reemplaza{" "}
                  <span className="font-mono">
                    {d.reemplazo_ford.reemplazado_por ??
                      d.reemplazo_ford.reemplazado_por_ford}
                  </span>
                  .
                </p>
              )}

              {d.consumo_12m_nacional === 0 ? (
                <p className="text-[12.5px] text-ink-600">
                  <b>Sin ventas en 12 meses</b>, ni acá ni en el resto de la empresa.
                  Si lo necesitas igual, cuéntale al comprador para qué es.
                </p>
              ) : (
                <ConsumoChart datos={d.consumo} nombreSucursal={nombreSucursal} />
              )}

              <div className="flex flex-wrap gap-x-6 gap-y-1.5 text-[12.5px]">
                <span>
                  <span className="text-ink-400">Vendido acá 12m:</span>{" "}
                  <b>{formatoNumero(d.consumo_12m_sucursal)}</b>
                  <span className="text-ink-400">
                    {" "}
                    · {d.meses_con_venta_12m} de 12 meses
                  </span>
                </span>
                <span>
                  <span className="text-ink-400">En toda la empresa:</span>{" "}
                  <b>{formatoNumero(d.consumo_12m_nacional)}</b>
                </span>
                <span>
                  <span className="text-ink-400">Stock acá:</span>{" "}
                  <b>{formatoNumero(d.stock.sucursal ?? 0)}</b>
                </span>
              </div>

              {/* Si ya viene en camino, quizá no hay nada que pedir. */}
              {!!d.transito.sucursal && d.transito.sucursal > 0 && (
                <p className="rounded-sm border border-brand-200 bg-brand-50 px-2.5 py-1.5 text-[12.5px] text-brand-900">
                  Ya vienen <b>{formatoNumero(d.transito.sucursal)}</b> unidades en
                  camino
                  {d.transito.pedido_desde && (
                    <> (pedidas el {formatoFecha(d.transito.pedido_desde)})</>
                  )}
                  .
                </p>
              )}

              {/* La respuesta muchas veces es un traslado, no una compra. */}
              {otras.length > 0 && (
                <div>
                  <p className="text-[11px] uppercase tracking-wide text-ink-400">
                    Hay stock en otras sucursales
                  </p>
                  <ul className="mt-1 space-y-0.5 text-[12.5px]">
                    {otras.slice(0, 6).map((s, i) => (
                      <li
                        key={`${s.sucursal_id}-${s.bodega}-${i}`}
                        className="flex justify-between gap-3"
                      >
                        <span className="truncate text-ink-600">
                          {s.sucursal_id ?? s.bodega ?? "—"}
                        </span>
                        <span className="tabular font-medium">
                          {formatoNumero(s.stock)}
                        </span>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-1 text-[11.5px] text-ink-500">
                    Quizá te sirve pedir un traslado en vez de esperar la compra.
                  </p>
                </div>
              )}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
