"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatoNumero } from "@/lib/formato";
import type { StockSucursalRow } from "@/lib/types";

export interface StockDeSucursal {
  sucursal: string;
  stock: number;
}

/**
 * Suma el stock de las bodegas de cada sucursal y deja de mayor a menor. Las que no tienen
 * stock no se dibujan: una barra en cero no dice nada y esconde a las que sí tienen.
 * Una fila sin sucursal cuenta con el nombre de su bodega y, si tampoco la tiene, como
 * "Sin sucursal": el stock no se pierde.
 */
export function stockPorSucursal(filas: StockSucursalRow[]): StockDeSucursal[] {
  const por = new Map<string, number>();
  for (const f of filas) {
    if (!(f.stock > 0)) continue;
    const nombre = (f.sucursal_id ?? f.bodega ?? "").trim() || "Sin sucursal";
    por.set(nombre, (por.get(nombre) ?? 0) + f.stock);
  }
  return Array.from(por, ([sucursal, stock]) => ({ sucursal, stock })).sort(
    (a, b) => b.stock - a.stock || a.sucursal.localeCompare(b.sucursal)
  );
}

const ALTO_BARRA = 34;

/**
 * Gráfico de barras horizontales: cuánto stock tiene el producto en cada sucursal. Va junto a
 * la tabla de bodegas, que queda como el detalle y como alternativa en texto del gráfico.
 */
export function GraficoStockSucursal({ filas }: { filas: StockSucursalRow[] }) {
  const datos = useMemo(() => stockPorSucursal(filas), [filas]);
  const total = datos.reduce((a, d) => a + d.stock, 0);
  if (datos.length === 0) return null;

  const resumen = datos.map((d) => `${d.sucursal} ${formatoNumero(d.stock)}`).join(", ");

  return (
    <Card>
      <CardHeader className="space-y-1">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <CardTitle>Stock por sucursal</CardTitle>
          <span className="text-[12px] text-slate-600">
            <b className="tabular text-slate-800">{formatoNumero(total)}</b> u en{" "}
            {datos.length} {datos.length === 1 ? "sucursal" : "sucursales"}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <div role="img" aria-label={`Stock por sucursal: ${resumen}`}>
          <ResponsiveContainer width="100%" height={datos.length * ALTO_BARRA + 28}>
            <BarChart
              data={datos}
              layout="vertical"
              margin={{ top: 4, right: 36, left: 0, bottom: 4 }}
              barCategoryGap={6}
            >
              <CartesianGrid strokeDasharray="3 3" stroke="#f1f5f9" horizontal={false} />
              <XAxis
                type="number"
                tick={{ fontSize: 11, fill: "#64748b" }}
                axisLine={false}
                tickLine={false}
                allowDecimals={false}
                tickFormatter={(v: number) => formatoNumero(v)}
              />
              <YAxis
                type="category"
                dataKey="sucursal"
                width={96}
                tick={{ fontSize: 12, fill: "#334155" }}
                axisLine={false}
                tickLine={false}
              />
              <Tooltip
                cursor={{ fill: "#f1f5f9" }}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
                formatter={(v: number) => [formatoNumero(v), "Stock"]}
              />
              <Bar dataKey="stock" name="Stock" fill="#1e40af" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                {/* El número al final de cada barra: se lee sin pasar el mouse. */}
                <LabelList
                  dataKey="stock"
                  position="right"
                  fontSize={12}
                  fill="#0f172a"
                  formatter={(v: number) => formatoNumero(v)}
                />
              </Bar>
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
