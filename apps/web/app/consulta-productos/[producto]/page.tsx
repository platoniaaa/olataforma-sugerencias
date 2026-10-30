"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import { GraficoStockSucursal } from "@/components/grafico-stock-sucursal";
import { GraficoVentas } from "@/components/grafico-ventas";
import { TablaTransito } from "@/components/tabla-transito";
import { GrupoReemplazos } from "@/components/grupo-reemplazos";
import type { ConsultaDetalle } from "@/lib/types";

/**
 * Detalle de un producto para el vendedor: precio, stock en TODAS las sucursales,
 * reemplazos (los equivalentes del mix y lo que dice FORD) y la venta de los
 * últimos 12 meses. Es la ficha del catálogo sin el costo.
 */
const LS_SUCURSAL = "consulta_productos_sucursal";

export default function DetalleConsultaPage({ params }: { params: { producto: string } }) {
  const producto = decodeURIComponent(params.producto);
  const [d, setD] = useState<ConsultaDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  // Filtro de ventas: "" = todas las sucursales. Se recuerda al pasar de un producto a otro.
  const [sucursales, setSucursales] = useState<string[]>([]);
  const [sucursal, setSucursal] = useState("");

  useEffect(() => {
    let activo = true;
    setCargando(true);
    setError(null);
    api
      .consultaDetalle(producto)
      .then((r) => activo && setD(r))
      .catch((e) => activo && setError(e instanceof Error ? e.message : "No se pudo cargar el producto"))
      .finally(() => activo && setCargando(false));
    return () => {
      activo = false;
    };
  }, [producto]);

  // Las sucursales que vendieron este producto (o su grupo) son las opciones del filtro.
  useEffect(() => {
    let activo = true;
    api
      .consultaSucursales(producto)
      .then((r) => {
        if (!activo) return;
        setSucursales(r.sucursales);
        let guardada = "";
        try {
          guardada = sessionStorage.getItem(LS_SUCURSAL) ?? "";
        } catch {
          /* sin sessionStorage: se parte en "todas" */
        }
        setSucursal(r.sucursales.includes(guardada) ? guardada : "");
      })
      .catch(() => activo && setSucursales([]));
    return () => {
      activo = false;
    };
  }, [producto]);

  const elegirSucursal = (valor: string) => {
    setSucursal(valor);
    try {
      sessionStorage.setItem(LS_SUCURSAL, valor);
    } catch {
      /* noop */
    }
  };

  const volver = (
    <Link
      href="/consulta-productos"
      className="inline-flex min-h-[44px] items-center gap-1 text-sm text-slate-600 hover:text-slate-900"
    >
      <ArrowLeft size={14} aria-hidden="true" /> Volver a productos
    </Link>
  );

  if (cargando) return <p className="text-slate-600">Cargando…</p>;
  if (error || !d) {
    return (
      <div className="space-y-2">
        {volver}
        <p role="alert" className="text-sm text-slate-700">
          {error ?? "Este producto no está en el catálogo."}
        </p>
      </div>
    );
  }

  const stockTotal = d.stock_total ?? 0;
  const conStock = d.stock_por_sucursal
    .filter((s) => s.stock > 0)
    .sort((a, b) => b.stock - a.stock);
  const reemplazos = (d.reemplazo ?? "").split(",").map((s) => s.trim()).filter(Boolean);
  const ford = d.reemplazo_ford;
  const atributos: [string, string | null][] = [
    ["Familia", d.familia],
    ["Subfamilia", d.subfamilia],
    ["Categoría", d.categoria],
    ["Procedencia", d.procedencia],
    ["Modelo", d.sub_modelo],
    ["Cilindrada", d.cilindrada],
    ["Combustible", d.combustible],
    ["Año", d.anio],
  ];

  return (
    <div className="space-y-4">
      <div>
        {volver}
        <h1 className="mt-1 font-mono text-xl font-semibold tracking-tight text-slate-900">
          {d.producto}
        </h1>
        <p className="text-sm text-slate-700">{d.glosa ?? "Sin descripción"}</p>
      </div>

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Dato titulo="Precio de venta" valor={d.precio != null ? formatoCLP(d.precio) : "—"} />
        <Dato
          titulo="Stock total"
          valor={stockTotal > 0 ? formatoNumero(stockTotal) : "Sin stock"}
          acento={stockTotal > 0}
        />
        <Dato
          titulo="En tránsito"
          valor={(d.en_transito ?? 0) > 0 ? formatoNumero(d.en_transito ?? 0) : "Nada"}
          acento={(d.en_transito ?? 0) > 0}
          color="sky"
        />
        <Dato titulo="Unidad" valor={d.unidad ?? "—"} />
      </div>

      {/* FORD dio de baja el código: no se fabrica más y hay otro que lo reemplaza. */}
      {ford?.reemplazado_por_ford && (
        <div className="rounded-xl border border-rose-200 bg-rose-50 p-4">
          <h2 className="text-sm font-semibold text-rose-900">FORD dio de baja este código</h2>
          <p className="mt-1 text-[13px] text-rose-900">
            Lo reemplaza{" "}
            {ford.reemplazado_por ? (
              <Link
                href={`/consulta-productos/${encodeURIComponent(ford.reemplazado_por)}`}
                className="rounded bg-rose-100 px-1.5 py-0.5 font-mono text-[12px] font-semibold text-rose-900 hover:bg-rose-200"
              >
                {ford.reemplazado_por}
              </Link>
            ) : (
              <>
                <span className="rounded bg-rose-100 px-1.5 py-0.5 font-mono text-[12px] font-semibold text-rose-900">
                  {ford.reemplazado_por_ford}
                </span>{" "}
                <span className="text-rose-800">
                  (código de FORD: todavía no está creado en Curifor)
                </span>
              </>
            )}
          </p>
          {ford.cadena && (
            <p className="mt-1 font-mono text-[11.5px] text-rose-800">{ford.cadena}</p>
          )}
        </div>
      )}

      {/* Equivalentes: piezas distintas que sirven para lo mismo. */}
      {reemplazos.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">
            Productos equivalentes (reemplazos)
          </h2>
          <p className="mt-0.5 text-xs text-slate-600">
            Sirven para lo mismo que este código. Toca uno para ver su detalle.
          </p>
          <div className="mt-2.5 flex flex-wrap gap-2">
            {reemplazos.map((r) => (
              <Link
                key={r}
                href={`/consulta-productos/${encodeURIComponent(r)}`}
                className="inline-flex min-h-[44px] items-center rounded bg-slate-100 px-3 font-mono text-[12px] text-slate-800 transition-colors hover:bg-brand-50 hover:text-brand"
              >
                {r}
              </Link>
            ))}
          </div>
        </section>
      )}

      <GraficoStockSucursal filas={d.stock_por_sucursal} transito={d.transito_por_sucursal ?? []} />

      <TablaTransito filas={d.transito_por_sucursal ?? []} />

      {/* Filtro de ventas por sucursal: afecta al historial de reemplazos y a la venta de
          los últimos 12 meses. Sin elegir, se ven todas las sucursales juntas. */}
      {sucursales.length > 0 && (
        <section className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
          <label htmlFor="filtro-sucursal" className="text-[13px] font-medium text-slate-700">
            Ver ventas de
          </label>
          <select
            id="filtro-sucursal"
            className="h-11 min-w-[200px] rounded-md border border-slate-300 bg-white px-3 text-[13px] text-slate-900 focus-visible:outline focus-visible:outline-2 focus-visible:outline-brand"
            value={sucursal}
            onChange={(e) => elegirSucursal(e.target.value)}
          >
            <option value="">Todas las sucursales</option>
            {sucursales.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
          {sucursal && (
            <span className="text-[12px] text-slate-600">
              Mostrando solo la venta y el stock de <b>{sucursal}</b>.
            </span>
          )}
        </section>
      )}

      {/* UN solo gráfico de ventas: el historial de reemplazos (este código y los que lo
          reemplazan, apilados) cuando hay grupo; si no, la venta del código solo. */}
      <GrupoReemplazos
        producto={d.producto}
        consulta
        sucursalId={sucursal || undefined}
        alternativa={
          <GraficoVentas
            producto={d.producto}
            consulta
            sucursalId={sucursal || undefined}
            sucursalNombre={sucursal || undefined}
          />
        }
      />

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Detalle por bodega</h2>
          <p className="text-xs text-slate-600">
            El mismo stock del gráfico, bodega por bodega.
          </p>
        </div>
        {conStock.length === 0 ? (
          <p className="px-4 py-6 text-sm text-slate-600">Este producto no tiene stock registrado.</p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-slate-50 text-left text-xs uppercase text-slate-600">
                <tr>
                  <th scope="col" className="px-4 py-2">Sucursal</th>
                  <th scope="col" className="px-4 py-2">Bodega</th>
                  <th scope="col" className="px-4 py-2 text-right">Stock</th>
                </tr>
              </thead>
              <tbody>
                {conStock.map((s, i) => (
                  <tr key={i} className="border-t border-slate-100">
                    <td className="px-4 py-2 font-medium">{s.sucursal_id ?? "—"}</td>
                    <td className="px-4 py-2 text-slate-700">{s.bodega ?? "—"}</td>
                    <td className="px-4 py-2 text-right font-semibold tabular-nums">
                      {formatoNumero(s.stock)}
                    </td>
                  </tr>
                ))}
              </tbody>
              <tfoot>
                <tr className="border-t border-slate-200 bg-slate-50">
                  <td className="px-4 py-2 font-semibold" colSpan={2}>
                    Total
                  </td>
                  <td className="px-4 py-2 text-right font-semibold tabular-nums">
                    {formatoNumero(stockTotal)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        )}
      </section>

      {atributos.some(([, v]) => v) && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="text-sm font-semibold text-slate-900">Datos del producto</h2>
          <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-2 text-[13px] sm:grid-cols-4">
            {atributos
              .filter(([, v]) => v)
              .map(([k, v]) => (
                <div key={k}>
                  <dt className="text-[11px] uppercase tracking-wide text-slate-600">{k}</dt>
                  <dd className="text-slate-900">{v}</dd>
                </div>
              ))}
          </dl>
        </section>
      )}
    </div>
  );
}

function Dato({
  titulo,
  valor,
  acento,
  color = "emerald",
}: {
  titulo: string;
  valor: string;
  acento?: boolean;
  color?: "emerald" | "sky";
}) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-[11px] uppercase tracking-wide text-slate-600">{titulo}</p>
      <p
        className={`mt-1 text-lg font-semibold ${
          acento ? (color === "sky" ? "text-sky-800" : "text-emerald-700") : "text-slate-900"
        }`}
      >
        {valor}
      </p>
    </div>
  );
}
