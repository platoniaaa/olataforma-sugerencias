"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { ArrowLeft } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import { GraficoStockSucursal } from "@/components/grafico-stock-sucursal";
import { GraficoVentas } from "@/components/grafico-ventas";
import { GrupoReemplazos } from "@/components/grupo-reemplazos";
import type { ConsultaDetalle } from "@/lib/types";

/**
 * Detalle de un producto para el vendedor: precio, stock en TODAS las sucursales,
 * reemplazos (los equivalentes del mix y lo que dice FORD) y la venta de los
 * últimos 12 meses. Es la ficha del catálogo sin el costo.
 */
export default function DetalleConsultaPage({ params }: { params: { producto: string } }) {
  const producto = decodeURIComponent(params.producto);
  const [d, setD] = useState<ConsultaDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

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

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
        <Dato titulo="Precio de venta" valor={d.precio != null ? formatoCLP(d.precio) : "—"} />
        <Dato
          titulo="Stock total"
          valor={stockTotal > 0 ? formatoNumero(stockTotal) : "Sin stock"}
          acento={stockTotal > 0}
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

      <GrupoReemplazos producto={d.producto} consulta />

      <GraficoStockSucursal filas={d.stock_por_sucursal} />

      <GraficoVentas producto={d.producto} consulta />

      <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
        <div className="border-b border-slate-100 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-900">Detalle por bodega</h2>
          <p className="text-xs text-slate-600">
            El mismo stock del gráfico, bodega por bodega. Se actualiza en cada corrida del sugerido.
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

function Dato({ titulo, valor, acento }: { titulo: string; valor: string; acento?: boolean }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <p className="text-[11px] uppercase tracking-wide text-slate-600">{titulo}</p>
      <p className={`mt-1 text-lg font-semibold ${acento ? "text-emerald-700" : "text-slate-900"}`}>
        {valor}
      </p>
    </div>
  );
}
