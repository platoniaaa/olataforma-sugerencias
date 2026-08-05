"use client";

/**
 * Lo que se abre bajo una linea del requerimiento: el contexto para decidir.
 *
 * La tabla de arriba tiene que seguir leyendose de una pasada, asi que todo lo
 * que sirve para profundizar en UNA linea vive aca y se abre a peticion. La
 * pregunta que responde es siempre la misma: compro o no compro.
 *
 * Regla de honestidad: cuando un bloque no tiene dato, dice POR QUE no lo tiene.
 * Un "—" se lee como "fallo el sistema" cuando muchas veces significa "este
 * repuesto no se vende en ninguna parte", que es justo lo que hay que saber.
 */

import { useEffect, useState } from "react";
import { Loader2, TrendingDown, Truck } from "lucide-react";
import { ConsumoChart } from "@/components/consumo-chart";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoFecha, formatoNumero } from "@/lib/formato";
import type { DetalleProducto } from "@/lib/types";

function Dato({
  etiqueta,
  valor,
  nota,
  acento,
}: {
  etiqueta: string;
  valor: React.ReactNode;
  nota?: React.ReactNode;
  acento?: "bueno" | "ojo";
}) {
  const color =
    acento === "bueno" ? "text-emerald-700" : acento === "ojo" ? "text-amber-800" : "text-ink-900";
  return (
    <div>
      <p className="text-[11px] uppercase tracking-wide text-ink-400">{etiqueta}</p>
      <p className={`mt-0.5 text-[15px] font-medium ${color}`}>{valor}</p>
      {nota && <p className="text-[11.5px] text-ink-500">{nota}</p>}
    </div>
  );
}

/** Cuántos meses dura el stock (+ tránsito) al ritmo de venta observado. */
function cobertura(d: DetalleProducto): { meses: number; texto: string } | null {
  const porMes = d.consumo_12m_sucursal / 12;
  if (porMes <= 0) return null;
  const unidades = (d.stock.sucursal ?? 0) + (d.transito.sucursal ?? 0);
  const meses = unidades / porMes;
  return {
    meses,
    texto: meses >= 24 ? "más de 2 años" : `${meses.toLocaleString("es-CL", { maximumFractionDigits: 1 })} meses`,
  };
}

export function DetalleProductoRequerimiento({
  requerimientoId,
  producto,
  nombreSucursal,
}: {
  requerimientoId: number;
  producto: string;
  nombreSucursal: string;
}) {
  const [d, setD] = useState<DetalleProducto | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    api
      .detalleProductoRequerimiento(requerimientoId, producto)
      .then((r) => vivo && setD(r))
      .catch((e) => vivo && setError(e instanceof Error ? e.message : "No se pudo cargar"));
    return () => {
      vivo = false;
    };
  }, [requerimientoId, producto]);

  if (error) {
    return (
      <div className="px-4 py-3 text-[12.5px] text-red-800">
        No se pudo cargar el detalle: {error}
      </div>
    );
  }
  if (!d) {
    return (
      <div className="flex items-center gap-2 px-4 py-4 text-[12.5px] text-ink-400">
        <Loader2 size={14} className="animate-spin" /> Cargando el detalle…
      </div>
    );
  }

  const cob = cobertura(d);
  const conStock = d.stock.por_sucursal.filter((s) => s.stock > 0);
  const enTransito = d.transito.por_sucursal.filter((t) => t.cantidad > 0);
  const nuncaSeVende = d.consumo_12m_nacional === 0;

  return (
    <div className="space-y-4 border-l-2 border-brand-200 bg-paper-50 px-4 py-4">
      {/* La conclusión primero, cuando el dato la permite. */}
      {nuncaSeVende && (
        <div className="flex items-start gap-2 rounded-sm border border-amber-200 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
          <TrendingDown size={14} className="mt-0.5 shrink-0" />
          <span>
            <strong>Sin una sola venta en 12 meses en toda la empresa.</strong> Si se
            compra, es contra un pedido puntual del cliente, no contra rotación.
          </span>
        </div>
      )}
      {d.transito.sucursal != null && d.transito.sucursal > 0 && (
        <div className="flex items-start gap-2 rounded-sm border border-brand-200 bg-brand-50 px-3 py-2 text-[12.5px] text-brand-900">
          <Truck size={14} className="mt-0.5 shrink-0" />
          <span>
            Ya vienen <strong>{formatoNumero(d.transito.sucursal)}</strong> unidades a{" "}
            {nombreSucursal}
            {d.transito.pedido_desde && <> (OC del {formatoFecha(d.transito.pedido_desde)})</>}.
            Revisa si hace falta comprar de nuevo.
          </span>
        </div>
      )}

      <ConsumoChart datos={d.consumo} nombreSucursal={nombreSucursal} />

      <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-3 lg:grid-cols-5">
        <Dato
          etiqueta={`Consumo 12m · ${nombreSucursal}`}
          valor={formatoNumero(d.consumo_12m_sucursal)}
          nota={`${d.meses_con_venta_12m} de 12 meses con venta`}
        />
        <Dato
          etiqueta="Consumo 12m · empresa"
          valor={formatoNumero(d.consumo_12m_nacional)}
        />
        <Dato
          etiqueta="En tránsito acá"
          valor={
            d.transito.sucursal == null ? (
              <span className="text-ink-300">sin dato</span>
            ) : (
              formatoNumero(d.transito.sucursal)
            )
          }
          nota={
            d.transito.pedido_desde
              ? `pedido el ${formatoFecha(d.transito.pedido_desde)}`
              : undefined
          }
        />
        <Dato
          etiqueta="Stock acá / CD"
          valor={`${formatoNumero(d.stock.sucursal ?? 0)} / ${formatoNumero(d.stock.cd ?? 0)}`}
        />
        <Dato
          etiqueta="Cobertura"
          valor={cob ? cob.texto : <span className="text-ink-300">—</span>}
          nota={cob ? "con el stock y lo que viene" : "sin venta acá, no se puede estimar"}
          acento={cob && cob.meses >= 12 ? "ojo" : undefined}
        />
      </div>

      <div className="grid gap-4 md:grid-cols-3">
        {/* Dónde están las unidades: a veces la respuesta es un traslado. */}
        <div>
          <p className="text-[11px] uppercase tracking-wide text-ink-400">
            Stock por sucursal
          </p>
          {conStock.length === 0 ? (
            <p className="mt-1 text-[12.5px] text-ink-500">
              No hay stock de este repuesto en ninguna sucursal.
            </p>
          ) : (
            <ul className="mt-1 space-y-0.5 text-[12.5px]">
              {conStock.slice(0, 8).map((s, i) => (
                <li key={`${s.sucursal_id}-${s.bodega}-${i}`} className="flex justify-between gap-3">
                  <span className="truncate text-ink-600">
                    {s.sucursal_id ?? s.bodega ?? "—"}
                  </span>
                  <span className="tabular font-medium">{formatoNumero(s.stock)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div>
          <p className="text-[11px] uppercase tracking-wide text-ink-400">
            En tránsito por sucursal
          </p>
          {enTransito.length === 0 ? (
            <p className="mt-1 text-[12.5px] text-ink-500">
              No hay órdenes de compra pendientes de este repuesto.
            </p>
          ) : (
            <ul className="mt-1 space-y-0.5 text-[12.5px]">
              {enTransito.slice(0, 8).map((t, i) => (
                <li key={`${t.sucursal_id}-${i}`} className="flex justify-between gap-3">
                  <span className="truncate text-ink-600">
                    {t.sucursal_id ?? "—"}
                    {t.pedido_desde && (
                      <span className="text-ink-400"> · {formatoFecha(t.pedido_desde)}</span>
                    )}
                  </span>
                  <span className="tabular font-medium">{formatoNumero(t.cantidad)}</span>
                </li>
              ))}
            </ul>
          )}
        </div>

        <div className="space-y-3">
          <div>
            <p className="text-[11px] uppercase tracking-wide text-ink-400">Precio</p>
            <p className="mt-1 text-[12.5px]">
              Venta <strong>{formatoCLP(d.precio.precio)}</strong>
              {d.precio.costo != null && <> · costo {formatoCLP(d.precio.costo)}</>}
            </p>
            {d.precio.margen_pct != null && (
              <p
                className={`text-[12.5px] ${
                  d.precio.margen_pct < 0 ? "text-red-700" : "text-ink-500"
                }`}
              >
                Margen {d.precio.margen_pct.toLocaleString("es-CL", { maximumFractionDigits: 1 })}%
                {d.precio.margen_pct < 0 && " — se vendería con pérdida"}
              </p>
            )}
            {d.precio.proveedor && (
              <p className="text-[12.5px] text-ink-500">Proveedor {d.precio.proveedor}</p>
            )}
          </div>

          <div>
            <p className="text-[11px] uppercase tracking-wide text-ink-400">El modelo</p>
            {d.modelo ? (
              <p className="mt-1 text-[12.5px] text-ink-600">
                Clase <strong>{d.modelo.clasificacion_abc ?? "—"}</strong>
                {d.modelo.punto_de_pedido != null && (
                  <> · punto de pedido {formatoNumero(d.modelo.punto_de_pedido)}</>
                )}
                {d.modelo.stock_seguridad != null && (
                  <> · stock de seguridad {formatoNumero(d.modelo.stock_seguridad)}</>
                )}
                {d.modelo.nivel_maximo != null && (
                  <> · máximo {formatoNumero(d.modelo.nivel_maximo)}</>
                )}
                {d.modelo.sugerido != null && d.modelo.sugerido > 0 && (
                  <>
                    {" "}
                    · <strong>ya sugiere {formatoNumero(d.modelo.sugerido)}</strong>
                  </>
                )}
                {d.modelo.lead_time_dias != null && (
                  <> · lead time {d.modelo.lead_time_dias} días</>
                )}
              </p>
            ) : (
              <p className="mt-1 text-[12.5px] text-ink-500">
                El modelo no evalúa este repuesto en {nombreSucursal}: no tiene demanda
                histórica acá, así que no hay punto de pedido ni stock de seguridad que
                comparar.
              </p>
            )}
          </div>
        </div>
      </div>

      {d.reemplazos && (
        <p className="text-[12.5px] text-amber-800">
          Reemplazo: <span className="font-mono">{d.reemplazos}</span>
        </p>
      )}
    </div>
  );
}
