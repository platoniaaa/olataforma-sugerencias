"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import { formatoNumero } from "@/lib/formato";
import type { GrupoVentas } from "@/lib/types";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

/** "202504" -> "Abr 25" */
function etiquetaMes(yyyymm: string): string {
  if (!yyyymm || yyyymm.length < 6) return yyyymm;
  const mes = parseInt(yyyymm.slice(4, 6), 10);
  return `${MESES[mes - 1] ?? yyyymm.slice(4, 6)} ${yyyymm.slice(2, 4)}`;
}

// El vigente primero y en el color fuerte: es el que hay que mirar. Los demas en
// grises que se van apagando, que es justo lo que les paso a sus ventas.
const COLORES = ["#1e40af", "#94a3b8", "#cbd5e1", "#e2e8f0", "#f1f5f9"];

/**
 * El historial del repuesto: que codigo reemplazo a cual, y cuanto vendio cada uno.
 *
 * Sin esto el comprador ve un numero consolidado y no sabe de donde viene. Un
 * repuesto que siempre se vendio igual parece nuevo cada vez que FORD lo renumera.
 *
 * No se muestra nada cuando el codigo no tiene reemplazos: una tabla de una sola
 * fila no dice nada.
 */
export function GrupoReemplazos({ producto }: { producto: string }) {
  const [data, setData] = useState<GrupoVentas | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let activo = true;
    api
      .grupoVentas(producto)
      .then((r) => activo && setData(r))
      .catch(() => activo && setError(true));
    return () => {
      activo = false;
    };
  }, [producto]);

  const filas = useMemo(() => {
    if (!data) return [];
    return data.meses.map((m) => {
      const fila: Record<string, string | number> = { mes: etiquetaMes(String(m.mes)) };
      for (const miembro of data.miembros) {
        fila[miembro.producto] = Number(m[miembro.producto] ?? 0);
      }
      return fila;
    });
  }, [data]);

  if (error || !data || data.miembros.length < 2) return null;

  const fuera = data.miembros.filter((m) => !m.cuenta_en_el_total);

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle>Historial de reemplazos</CardTitle>
        <p className="text-[12px] text-slate-500">
          El sugerido trata estos {data.miembros.length} códigos como una sola pieza:
          suma su stock y su venta, y compra con el vigente.
        </p>
      </CardHeader>
      <CardContent className="space-y-4">
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-3 py-2">Código</th>
                <th className="px-3 py-2">Código FORD</th>
                <th className="px-3 py-2 text-right">Venta 12m</th>
                <th className="px-3 py-2 text-right">Venta total</th>
                <th className="px-3 py-2">Última venta</th>
                <th className="px-3 py-2 text-right">Stock</th>
              </tr>
            </thead>
            <tbody>
              {data.miembros.map((m) => (
                <tr
                  key={m.producto}
                  className={`border-t border-slate-100 ${
                    m.cuenta_en_el_total ? "" : "bg-amber-50/60"
                  }`}
                >
                  <td className="px-3 py-2">
                    <Link
                      href={`/catalogo/${encodeURIComponent(m.producto)}`}
                      className="font-mono text-[12px] text-slate-700 hover:text-brand"
                    >
                      {m.producto}
                    </Link>
                    {m.es_vigente ? (
                      <span className="ml-2 rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold text-emerald-800">
                        VIGENTE
                      </span>
                    ) : (
                      <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold text-slate-500">
                        DADO DE BAJA
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 font-mono text-[11px] text-slate-400">
                    {m.sku_ford ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatoNumero(m.venta_12m)}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums text-slate-500">
                    {formatoNumero(m.venta_total)}
                  </td>
                  <td className="px-3 py-2 text-slate-500">
                    {m.ultimo_mes_con_venta ? etiquetaMes(m.ultimo_mes_con_venta) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">
                    {formatoNumero(m.stock)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-slate-200 bg-slate-50 font-semibold">
                <td className="px-3 py-2" colSpan={2}>
                  Total del grupo
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatoNumero(data.total_venta_12m ?? 0)}
                </td>
                <td className="px-3 py-2" />
                <td className="px-3 py-2" />
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatoNumero(data.total_stock ?? 0)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>

        {/* Un codigo que FORD declara reemplazo pero el motor no agrupo NO puede
            sumar al total, o el numero del pie no cuadraria con el sugerido. */}
        {fuera.length > 0 && (
          <p className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
            {fuera.map((m) => m.producto).join(", ")}{" "}
            {fuera.length === 1 ? "no está sumado" : "no están sumados"} en el total.{" "}
            {fuera[0].motivo_fuera}
          </p>
        )}

        {filas.length > 0 && (
          <div>
            <p className="mb-1 text-[12px] text-slate-500">
              Venta de los últimos 12 meses, por código. La altura total es la venta
              del repuesto; los colores muestran el traspaso de un código al otro.
            </p>
            <ResponsiveContainer width="100%" height={240}>
              <BarChart data={filas} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" vertical={false} />
                <XAxis
                  dataKey="mes"
                  tick={{ fontSize: 11, fill: "#475569" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  tick={{ fontSize: 11, fill: "#94a3b8" }}
                  axisLine={false}
                  tickLine={false}
                  width={40}
                  tickFormatter={(v: number) => formatoNumero(v)}
                />
                <Tooltip
                  cursor={{ fill: "#f1f5f9" }}
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
                  formatter={(v: number, name: string) => [formatoNumero(v), name]}
                />
                <Legend iconType="square" wrapperStyle={{ fontSize: 11, paddingTop: 6 }} />
                {data.miembros.map((m, i) => (
                  // Apiladas (mismo stackId) y no lado a lado: lo que importa es
                  // cuanto se vende del repuesto, y adentro se ve el traspaso.
                  <Bar
                    key={m.producto}
                    dataKey={m.producto}
                    name={m.producto}
                    stackId="grupo"
                    fill={COLORES[i % COLORES.length]}
                    isAnimationActive={false}
                  />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
