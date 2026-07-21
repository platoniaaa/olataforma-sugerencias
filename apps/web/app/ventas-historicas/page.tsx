"use client";

// Consulta del historico de ventas (desde 2018) sin bajar ningun Excel.
import { useCallback, useEffect, useState } from "react";
import { Download, History, Search } from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type { VentasHistoricasMeta, VentasHistoricasResp } from "@/lib/types";

/** "202601" -> "01-2026" (lo que la gente lee). */
function periodoLegible(p: string): string {
  return p.length === 6 ? `${p.slice(4)}-${p.slice(0, 4)}` : p;
}

export default function VentasHistoricasPage() {
  const [meta, setMeta] = useState<VentasHistoricasMeta | null>(null);
  const [producto, setProducto] = useState("");
  const [sucursal, setSucursal] = useState("");
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [data, setData] = useState<VentasHistoricasResp | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .ventasHistoricasMeta()
      .then(setMeta)
      .catch(() => setMeta(null));
  }, []);

  const buscar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      setData(
        await api.ventasHistoricas({
          producto: producto.trim() || undefined,
          sucursal: sucursal || undefined,
          periodo_desde: desde || undefined,
          periodo_hasta: hasta || undefined,
        })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al consultar");
    } finally {
      setCargando(false);
    }
  }, [producto, sucursal, desde, hasta]);

  const sinDatos = meta !== null && meta.filas === 0;
  const serie = (data?.por_periodo ?? []).map((p) => ({
    ...p,
    label: periodoLegible(p.periodo),
  }));

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
          <History size={20} /> Ventas históricas
        </h1>
        <p className="text-[13px] text-slate-500">
          {meta && meta.filas > 0
            ? `${formatoNumero(meta.filas)} registros · ${periodoLegible(meta.periodo_min ?? "")} a ${periodoLegible(meta.periodo_max ?? "")}`
            : "Consulta la venta por producto, sucursal y período sin descargar planillas."}
        </p>
      </div>

      {sinDatos && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
          Todavía no hay histórico cargado. Se carga desde la carpeta oficial de datos con
          el job <code className="font-mono">cargar_ventas_historicas</code>.
        </p>
      )}

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="block md:col-span-2">
            <span className="mb-1 block text-[12px] font-medium text-slate-600">Producto</span>
            <input
              value={producto}
              onChange={(e) => setProducto(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && buscar()}
              placeholder="Código o parte del código"
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px]"
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[12px] font-medium text-slate-600">Sucursal</span>
            <select
              value={sucursal}
              onChange={(e) => setSucursal(e.target.value)}
              className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-[13px]"
            >
              <option value="">Todas</option>
              {(meta?.sucursales ?? []).map((s) => (
                <option key={s} value={s}>
                  {s}
                </option>
              ))}
            </select>
          </label>
          <div className="grid grid-cols-2 gap-2">
            <label className="block">
              <span className="mb-1 block text-[12px] font-medium text-slate-600">Desde</span>
              <input
                value={desde}
                onChange={(e) => setDesde(e.target.value)}
                placeholder="202401"
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-[13px]"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[12px] font-medium text-slate-600">Hasta</span>
              <input
                value={hasta}
                onChange={(e) => setHasta(e.target.value)}
                placeholder="202612"
                className="w-full rounded-md border border-slate-300 px-2 py-1.5 text-[13px]"
              />
            </label>
          </div>
        </div>
        <div className="mt-3 flex flex-wrap gap-2">
          <button
            onClick={buscar}
            disabled={cargando}
            className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            <Search size={14} /> {cargando ? "Buscando…" : "Consultar"}
          </button>
          {data && data.detalle.total > 0 && (
            <button
              onClick={() =>
                api.exportarVentasHistoricas({
                  producto: producto.trim() || undefined,
                  sucursal: sucursal || undefined,
                  periodo_desde: desde || undefined,
                  periodo_hasta: hasta || undefined,
                })
              }
              className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-3 py-1.5 text-[13px] hover:bg-slate-50"
            >
              <Download size={14} /> Descargar CSV
            </button>
          )}
        </div>
        {error && (
          <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
        )}
      </section>

      {data && (
        <>
          <p className="text-[13px] text-slate-600">
            {formatoNumero(data.detalle.total)} registros encontrados
            {data.detalle.truncado && (
              <span className="text-amber-700">
                {" "}
                · se muestran los {formatoNumero(data.detalle.items.length)} más recientes
                (descarga el CSV para verlos todos)
              </span>
            )}
          </p>

          {serie.length > 0 && (
            <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
              <h2 className="mb-3 text-[14px] font-semibold text-slate-900">Venta por mes</h2>
              <div style={{ height: 240 }}>
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={serie}>
                    <CartesianGrid stroke="#ebe9dd" vertical={false} />
                    <XAxis dataKey="label" tick={{ fontSize: 11 }} stroke="#94a3b8" />
                    <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" width={50} />
                    <Tooltip
                      formatter={(v: number, n: string) =>
                        n === "neto" ? [formatoCLP(v), "Neto"] : [formatoNumero(v), "Unidades"]
                      }
                      contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #ebe9dd" }}
                    />
                    <Bar
                      dataKey="cantidad"
                      name="Unidades"
                      fill="#1e40af"
                      radius={[2, 2, 0, 0]}
                      isAnimationActive={false}
                    />
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </section>
          )}

          {data.por_sucursal.length > 1 && (
            <section>
              <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
                Por sucursal
              </h2>
              <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-4 py-2">Sucursal</th>
                      <th className="px-4 py-2 text-right">Unidades</th>
                      <th className="px-4 py-2 text-right">Neto</th>
                    </tr>
                  </thead>
                  <tbody>
                    {data.por_sucursal.map((s) => (
                      <tr key={s.sucursal} className="border-t border-slate-100">
                        <td className="px-4 py-2">{s.sucursal}</td>
                        <td className="px-4 py-2 text-right tabular">
                          {formatoNumero(s.cantidad)}
                        </td>
                        <td className="px-4 py-2 text-right tabular text-slate-600">
                          {formatoCLPCorto(s.neto)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <section>
            <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
              Detalle
            </h2>
            <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2">Período</th>
                    <th className="px-4 py-2">Producto</th>
                    <th className="px-4 py-2">Sucursal</th>
                    <th className="px-4 py-2 text-right">Unidades</th>
                    <th className="px-4 py-2 text-right">Neto</th>
                  </tr>
                </thead>
                <tbody>
                  {data.detalle.items.map((it, i) => (
                    <tr key={`${it.periodo}-${it.producto}-${it.sucursal}-${i}`} className="border-t border-slate-100">
                      <td className="px-4 py-2 tabular text-slate-600">
                        {periodoLegible(it.periodo)}
                      </td>
                      <td className="px-4 py-2 font-medium text-slate-900">{it.producto}</td>
                      <td className="px-4 py-2 text-slate-600">{it.sucursal ?? "—"}</td>
                      <td className="px-4 py-2 text-right tabular">
                        {formatoNumero(it.cantidad)}
                      </td>
                      <td className="px-4 py-2 text-right tabular text-slate-600">
                        {it.neto ? formatoCLP(it.neto) : "—"}
                      </td>
                    </tr>
                  ))}
                  {data.detalle.items.length === 0 && (
                    <tr>
                      <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                        Sin resultados para esos filtros.
                      </td>
                    </tr>
                  )}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
