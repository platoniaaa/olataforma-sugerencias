"use client";

// Evolucion del stock y el sugerido segun los snapshots diarios. Solo se muestra
// cuando hay al menos dos dias guardados: con un punto no hay nada que mirar.
import { useEffect, useState } from "react";
import {
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { api } from "@/lib/api-client";
import { formatoNumero } from "@/lib/formato";

interface Punto {
  fecha: string;
  sugerido: number;
  stock: number;
  punto_pedido: number;
}

export function GraficoHistoria({
  producto,
  sucursalId,
}: {
  producto: string;
  sucursalId: string;
}) {
  const [items, setItems] = useState<Punto[]>([]);

  useEffect(() => {
    let vigente = true;
    api
      .historiaProducto(producto, sucursalId)
      .then((r) => vigente && setItems(r.items))
      .catch(() => vigente && setItems([]));
    return () => {
      vigente = false;
    };
  }, [producto, sucursalId]);

  if (items.length < 2) return null;

  const data = items.map((p) => ({
    ...p,
    dia: p.fecha.slice(5), // MM-DD
  }));

  return (
    <Card>
      <CardHeader>
        <CardTitle>Evolución del stock y el sugerido</CardTitle>
      </CardHeader>
      <CardContent>
        <div style={{ height: 220 }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data} margin={{ top: 8, right: 16, bottom: 0, left: 0 }}>
          <CartesianGrid stroke="#ebe9dd" vertical={false} />
          <XAxis dataKey="dia" tick={{ fontSize: 11 }} stroke="#94a3b8" />
          <YAxis tick={{ fontSize: 11 }} stroke="#94a3b8" width={44} />
          <Tooltip
            formatter={(v: number) => formatoNumero(v)}
            contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #ebe9dd" }}
          />
          <Legend iconType="plainline" wrapperStyle={{ fontSize: 11, paddingTop: 6 }} />
          <Line
            type="monotone"
            dataKey="stock"
            name="Stock"
            stroke="#1e40af"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="sugerido"
            name="Sugerido"
            stroke="#b45309"
            strokeWidth={2}
            dot={false}
            isAnimationActive={false}
          />
          <Line
            type="monotone"
            dataKey="punto_pedido"
            name="Punto de pedido"
            stroke="#94a3b8"
            strokeWidth={1.5}
            strokeDasharray="4 3"
            dot={false}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
        </div>
      </CardContent>
    </Card>
  );
}
