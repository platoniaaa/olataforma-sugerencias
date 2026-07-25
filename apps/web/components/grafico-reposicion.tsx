"use client";

// "Diente de sierra": el ciclo de reposicion del producto. El stock baja al ritmo
// de la demanda diaria, cruza el punto de pedido (ahi se emite la OC), sigue
// bajando durante el lead time y al llegar la reposicion vuelve a subir.
//
// Sirve para ver de un vistazo por que el modelo pide cuando pide: si el punto de
// pedido esta bien puesto, la curva toca el stock de seguridad justo cuando llega
// la reposicion. Es una PROYECCION teorica con la demanda promedio, no un
// historico: la venta real no es una linea recta.
import { useMemo } from "react";
import {
  Area,
  ComposedChart,
  Line,
  ReferenceLine,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { formatoNumero } from "@/lib/formato";

interface Props {
  demandaDiaria: number;
  leadTime: number;
  cicloOrden: number;
  stockSeguridad: number;
  puntoPedido: number;
  stockOptimo: number;
  /** Lo que hay hoy (activo + transito): marca donde esta parado el producto. */
  disponibleHoy: number;
}

export function GraficoReposicion({
  demandaDiaria,
  leadTime,
  cicloOrden,
  stockSeguridad,
  puntoPedido,
  stockOptimo,
  disponibleHoy,
}: Props) {
  const filas = useMemo(() => {
    const dd = demandaDiaria;
    // Sin consumo no hay ciclo que dibujar (la curva seria una recta).
    if (!dd || dd <= 0 || stockOptimo <= 0) return [];

    const cantidad = Math.max(Math.round(stockOptimo - stockSeguridad), 1);
    const pts: { dia: number; stock: number }[] = [];
    let dia = 0;
    let nivel = stockOptimo;
    const maxDias = 400; // corte de seguridad por si los parametros son raros

    for (let ciclo = 0; ciclo < 2 && dia < maxDias; ciclo++) {
      // Baja hasta tocar el punto de pedido (ahi se emite la orden).
      while (nivel > puntoPedido && dia < maxDias) {
        pts.push({ dia, stock: +nivel.toFixed(1) });
        dia++;
        nivel -= dd;
      }
      // Sigue consumiendo mientras el pedido viaja.
      for (let d = 0; d < Math.max(leadTime, 0) && dia < maxDias; d++) {
        pts.push({ dia, stock: +Math.max(nivel, 0).toFixed(1) });
        dia++;
        nivel -= dd;
      }
      // Llega la reposicion.
      nivel = Math.max(nivel, 0) + cantidad;
      pts.push({ dia, stock: +nivel.toFixed(1) });
    }
    return pts;
  }, [demandaDiaria, leadTime, stockSeguridad, puntoPedido, stockOptimo]);

  if (filas.length === 0) return null;

  // Dia en que la curva cruza el punto de pedido por primera vez: ahi se pide.
  const diaPedido = filas.find((f) => f.stock <= puntoPedido)?.dia ?? null;
  const cobertura = demandaDiaria > 0 ? disponibleHoy / demandaDiaria : 0;

  return (
    <Card>
      <CardHeader className="space-y-1">
        <CardTitle>Ciclo de reposición</CardTitle>
        <p className="text-[11px] text-slate-400">
          Proyección con la demanda promedio de {formatoNumero(demandaDiaria, 2)} u/día. Se pide al
          tocar el punto de pedido ({formatoNumero(puntoPedido)}) y la reposición llega{" "}
          {formatoNumero(leadTime)} días después, cuando quedan las{" "}
          {formatoNumero(stockSeguridad)} u del stock de seguridad.
        </p>
      </CardHeader>
      <CardContent>
        <ResponsiveContainer width="100%" height={240}>
          <ComposedChart data={filas} margin={{ top: 8, right: 8, left: 0, bottom: 4 }}>
            <defs>
              <linearGradient id="areaStock" x1="0" y1="0" x2="0" y2="1">
                <stop offset="0%" stopColor="#1e40af" stopOpacity={0.16} />
                <stop offset="100%" stopColor="#1e40af" stopOpacity={0.02} />
              </linearGradient>
            </defs>
            <XAxis
              dataKey="dia"
              type="number"
              domain={[0, "dataMax"]}
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
              label={{ value: "días", position: "insideBottomRight", offset: -2, fontSize: 10, fill: "#cbd5e1" }}
            />
            <YAxis
              tick={{ fontSize: 11, fill: "#94a3b8" }}
              axisLine={false}
              tickLine={false}
              width={40}
              tickFormatter={(v: number) => formatoNumero(v)}
            />
            <Tooltip
              formatter={(v: number) => [`${formatoNumero(v, 1)} u`, "Stock proyectado"]}
              labelFormatter={(d: number) => `Día ${d}`}
              contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
            />
            <ReferenceLine
              y={puntoPedido}
              stroke="#ea580c"
              strokeDasharray="5 4"
              label={{ value: "Punto de pedido", position: "insideTopRight", fontSize: 10, fill: "#ea580c" }}
            />
            <ReferenceLine
              y={stockSeguridad}
              stroke="#94a3b8"
              strokeDasharray="2 3"
              label={{ value: "Stock de seguridad", position: "insideBottomRight", fontSize: 10, fill: "#94a3b8" }}
            />
            {diaPedido !== null && (
              <ReferenceLine
                x={diaPedido}
                stroke="#cbd5e1"
                label={{ value: "se pide", position: "top", fontSize: 10, fill: "#94a3b8" }}
              />
            )}
            <Area
              type="linear"
              dataKey="stock"
              stroke="#1e40af"
              strokeWidth={2}
              fill="url(#areaStock)"
              isAnimationActive={false}
              dot={false}
            />
          </ComposedChart>
        </ResponsiveContainer>
        <p className="mt-1 text-[11px] text-slate-500">
          Hoy hay <b className="tabular text-slate-700">{formatoNumero(disponibleHoy)}</b> u
          disponibles ={" "}
          <b className="tabular text-slate-700">{formatoNumero(cobertura, 0)}</b> días de cobertura
          {disponibleHoy < stockSeguridad && (
            <span className="text-red-700"> · bajo el stock de seguridad</span>
          )}
          {disponibleHoy >= stockSeguridad && disponibleHoy <= puntoPedido && (
            <span className="text-amber-700"> · bajo el punto de pedido, toca reponer</span>
          )}
          . El ciclo completo dura ~{formatoNumero(cicloOrden + leadTime)} días entre que se pide y
          llega.
        </p>
      </CardContent>
    </Card>
  );
}
