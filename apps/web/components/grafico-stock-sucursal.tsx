"use client";

import { useMemo } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  LabelList,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatoNumero } from "@/lib/formato";
import type { StockSucursalRow, TransitoSucursal } from "@/lib/types";

export interface StockDeSucursal {
  sucursal: string;
  stock: number;
}

export interface StockYTransito extends StockDeSucursal {
  transito: number;
}

/** "02 LINDEROS" y "Linderos" son la misma sucursal: sin el código del ERP y en mayúsculas. */
const sinCodigo = (n: string) => n.trim().replace(/^\d+\s+/, "");
const clave = (n: string) => sinCodigo(n).toUpperCase();

/**
 * Suma el stock de las bodegas de cada sucursal y deja de mayor a menor. Las que no tienen
 * stock no se dibujan: una barra en cero no dice nada y esconde a las que sí tienen.
 * Una fila sin sucursal cuenta con el nombre de su bodega y, si tampoco la tiene, como
 * "Sin sucursal": el stock no se pierde.
 */
export function stockPorSucursal(filas: StockSucursalRow[]): StockDeSucursal[] {
  return stockYTransitoPorSucursal(filas, [])
    .filter((d) => d.stock > 0)
    .map(({ sucursal, stock }) => ({ sucursal, stock }));
}

/**
 * Lo mismo, más lo que viene en camino a cada sucursal. Una sucursal con tránsito pero sin stock
 * SÍ se dibuja: es justo a la que no hay que pedirle más. El tránsito viene escrito con el código
 * del ERP ("02 LINDEROS") y el stock sin él: se juntan por el nombre normalizado. Orden: más stock
 * primero y, a igual stock, más tránsito.
 */
export function stockYTransitoPorSucursal(
  filas: StockSucursalRow[],
  transito: TransitoSucursal[] = []
): StockYTransito[] {
  const por = new Map<string, StockYTransito>();
  const fila = (nombre: string | null | undefined): StockYTransito => {
    const visible = sinCodigo(nombre ?? "") || "Sin sucursal";
    const k = clave(visible);
    let f = por.get(k);
    if (!f) {
      f = { sucursal: visible, stock: 0, transito: 0 };
      por.set(k, f);
    }
    return f;
  };
  for (const f of filas) {
    if (!(f.stock > 0)) continue;
    fila(f.sucursal_id ?? f.bodega).stock += f.stock;
  }
  for (const t of transito) {
    if (!(t.cantidad > 0)) continue;
    fila(t.sucursal_id).transito += t.cantidad;
  }
  return Array.from(por.values()).sort(
    (a, b) => b.stock - a.stock || b.transito - a.transito || a.sucursal.localeCompare(b.sucursal)
  );
}

const ALTO_UNA_BARRA = 34;
const ALTO_DOS_BARRAS = 58;

/**
 * Gráfico de barras horizontales: cuánto stock tiene el producto en cada sucursal y cuánto viene en
 * camino. Va junto a la tabla de bodegas y a la de tránsito, que quedan como el detalle y como
 * alternativa en texto del gráfico.
 */
export function GraficoStockSucursal({
  filas,
  transito = [],
}: {
  filas: StockSucursalRow[];
  transito?: TransitoSucursal[];
}) {
  const datos = useMemo(() => stockYTransitoPorSucursal(filas, transito), [filas, transito]);
  if (datos.length === 0) return null;

  const totalStock = datos.reduce((a, d) => a + d.stock, 0);
  const totalTransito = datos.reduce((a, d) => a + d.transito, 0);
  const sucursalesConStock = datos.filter((d) => d.stock > 0).length;
  const conTransito = totalTransito > 0;
  const n = formatoNumero;
  const resumen = datos
    .map((d) => {
      const base = d.stock > 0 ? `${d.sucursal} ${n(d.stock)}` : `${d.sucursal} sin stock`;
      return d.transito > 0 ? `${base} y ${n(d.transito)} en tránsito` : base;
    })
    .join(", ");

  return (
    <Card>
      <CardHeader className="space-y-1">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <CardTitle>{conTransito ? "Stock y tránsito por sucursal" : "Stock por sucursal"}</CardTitle>
          <span className="text-[12px] text-slate-600">
            {totalStock > 0 ? (
              <>
                <b className="tabular text-slate-800">{n(totalStock)}</b> u en {sucursalesConStock}{" "}
                {sucursalesConStock === 1 ? "sucursal" : "sucursales"}
              </>
            ) : (
              "Sin stock"
            )}
            {conTransito && (
              <>
                {" · "}
                <span>
                  <b className="tabular text-sky-800">{n(totalTransito)}</b> u en tránsito
                </span>
              </>
            )}
          </span>
        </div>
      </CardHeader>
      <CardContent>
        <div role="img" aria-label={`Stock por sucursal: ${resumen}`}>
          <ResponsiveContainer
            width="100%"
            height={datos.length * (conTransito ? ALTO_DOS_BARRAS : ALTO_UNA_BARRA) + (conTransito ? 56 : 28)}
          >
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
                formatter={(v: number, name: string) => [formatoNumero(v), name]}
              />
              {conTransito && <Legend iconType="square" wrapperStyle={{ fontSize: 11, paddingTop: 4 }} />}
              <Bar dataKey="stock" name="Stock" fill="#1e40af" radius={[0, 3, 3, 0]} isAnimationActive={false}>
                {/* El número al final de cada barra: se lee sin pasar el mouse. */}
                <LabelList
                  dataKey="stock"
                  position="right"
                  fontSize={12}
                  fill="#0f172a"
                  formatter={(v: number) => (v > 0 ? formatoNumero(v) : "")}
                />
              </Bar>
              {conTransito && (
                <Bar
                  dataKey="transito"
                  name="En tránsito"
                  fill="#38bdf8"
                  radius={[0, 3, 3, 0]}
                  isAnimationActive={false}
                >
                  <LabelList
                    dataKey="transito"
                    position="right"
                    fontSize={12}
                    fill="#075985"
                    formatter={(v: number) => (v > 0 ? formatoNumero(v) : "")}
                  />
                </Bar>
              )}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
