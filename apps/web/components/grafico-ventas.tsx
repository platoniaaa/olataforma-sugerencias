"use client";

import { useEffect, useMemo, useState } from "react";
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
import type { VentasResponse } from "@/lib/types";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

/** "202504" -> "Abr 25" */
function etiquetaMes(yyyymm: string): string {
  if (!yyyymm || yyyymm.length < 6) return yyyymm;
  const anio = yyyymm.slice(2, 4);
  const mes = parseInt(yyyymm.slice(4, 6), 10);
  const nombre = MESES[mes - 1] ?? yyyymm.slice(4, 6);
  return `${nombre} ${anio}`;
}

export function GraficoVentas({
  producto,
  sucursalId,
  sucursalNombre,
}: {
  producto: string;
  sucursalId: string;
  sucursalNombre?: string | null;
}) {
  const [data, setData] = useState<VentasResponse | null>(null);
  const [error, setError] = useState(false);

  useEffect(() => {
    let activo = true;
    api
      .ventas(producto, sucursalId)
      .then((r) => activo && setData(r))
      .catch(() => activo && setError(true));
    return () => {
      activo = false;
    };
  }, [producto, sucursalId]);

  // Combina las dos series por mes para Recharts.
  const filas = useMemo(() => {
    if (!data) return [];
    const map = new Map<string, { mes: string; general: number; sucursal: number }>();
    for (const m of data.meses_general) {
      map.set(m.mes, { mes: m.mes, general: Math.round(m.cantidad), sucursal: 0 });
    }
    for (const m of data.meses_sucursal) {
      const row = map.get(m.mes) ?? { mes: m.mes, general: 0, sucursal: 0 };
      row.sucursal = Math.round(m.cantidad);
      map.set(m.mes, row);
    }
    return Array.from(map.values())
      .sort((a, b) => a.mes.localeCompare(b.mes))
      .map((r) => ({ ...r, mes: etiquetaMes(r.mes) }));
  }, [data]);

  if (error || (data && filas.length === 0)) return null;

  const promGeneral =
    filas.length > 0 ? (data?.total_general ?? 0) / filas.length : 0;
  const promSucursal =
    filas.length > 0 ? (data?.total_sucursal ?? 0) / filas.length : 0;

  const tituloSuc = sucursalNombre ?? sucursalId;

  return (
    <Card>
      <CardHeader className="space-y-1">
        <div className="flex flex-wrap items-baseline justify-between gap-2">
          <CardTitle>Venta últimos 12 meses</CardTitle>
          {data && (
            <span className="text-[12px] text-slate-500">
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-sm" style={{ background: "#94a3b8" }} />
                Total
              </span>{" "}
              <b className="tabular text-slate-800">{formatoNumero(data.total_general)}</b> u
              {" · "}
              <span className="inline-flex items-center gap-1">
                <span className="inline-block h-2 w-2 rounded-sm" style={{ background: "#1e40af" }} />
                {tituloSuc}
              </span>{" "}
              <b className="tabular text-slate-800">{formatoNumero(data.total_sucursal)}</b> u
            </span>
          )}
        </div>
        {data && (
          <p className="text-[11px] text-slate-400">
            Promedio mensual — total: {formatoNumero(promGeneral, 1)} u · esta sucursal:{" "}
            {formatoNumero(promSucursal, 1)} u
          </p>
        )}
      </CardHeader>
      <CardContent>
        {!data ? (
          <p className="py-8 text-center text-sm text-slate-400">Cargando ventas…</p>
        ) : (
          <ResponsiveContainer width="100%" height={260}>
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
                formatter={(v: number, name: string) => [formatoNumero(v), name]}
                cursor={{ fill: "#f1f5f9" }}
                contentStyle={{ fontSize: 12, borderRadius: 8, border: "1px solid #e2e8f0" }}
              />
              <Legend
                iconType="square"
                wrapperStyle={{ fontSize: 11, paddingTop: 6 }}
              />
              <Bar
                dataKey="general"
                name="Total producto"
                fill="#94a3b8"
                radius={[3, 3, 0, 0]}
                isAnimationActive={false}
              />
              <Bar
                dataKey="sucursal"
                name={tituloSuc}
                fill="#1e40af"
                radius={[3, 3, 0, 0]}
                isAnimationActive={false}
              />
            </BarChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
}
