"use client";

// Salud del inventario: el complemento del sugerido. El sugerido dice que comprar;
// esto dice donde esta la plata detenida (inmovilizado, sobre-stock) y donde falta
// (quiebres, bajo punto de pedido).
import { useEffect, useState } from "react";
import Link from "next/link";
import {
  AlertTriangle,
  Boxes,
  Clock,
  PackageX,
  RefreshCw,
  Snowflake,
  TrendingUp,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type { InventarioSalud } from "@/lib/types";

const OPCIONES_SOBRE_STOCK = [90, 180, 365];

export default function InventarioPage() {
  const [data, setData] = useState<InventarioSalud | null>(null);
  const [dias, setDias] = useState(180);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vigente = true;
    setCargando(true);
    setError(null);
    api
      .inventarioSalud({ diasSobreStock: dias })
      .then((r) => vigente && setData(r))
      .catch((e) => vigente && setError(e instanceof Error ? e.message : "Error al cargar"))
      .finally(() => vigente && setCargando(false));
    return () => {
      vigente = false;
    };
  }, [dias]);

  const r = data?.resumen;
  const v = (s: string) => (cargando || !r ? "—" : s);

  // Top sucursales por plata inmovilizada (una sola serie: sin leyenda, color de identidad).
  const grafico = (data?.por_sucursal ?? [])
    .filter((s) => s.inmovilizado_clp > 0)
    .slice(0, 10)
    .map((s) => ({ nombre: s.nombre_sucursal, valor: s.inmovilizado_clp }));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">
            Salud del inventario
          </h1>
          <p className="text-[13px] text-slate-500">
            {cargando
              ? "Calculando…"
              : `${formatoNumero(r?.n_filas)} combinaciones producto × sucursal analizadas`}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <label className="flex items-center gap-1.5 text-[13px] text-slate-600">
            Sobre-stock sobre
            <select
              value={dias}
              onChange={(e) => setDias(Number(e.target.value))}
              className="rounded-md border border-slate-300 px-2 py-1 text-[13px]"
            >
              {OPCIONES_SOBRE_STOCK.map((d) => (
                <option key={d} value={d}>
                  {d} días
                </option>
              ))}
            </select>
          </label>
          <button
            onClick={() => setDias((d) => d)}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[13px] hover:bg-slate-50"
          >
            <RefreshCw size={14} /> Actualizar
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
      )}

      {/* Tiles: la cifra es el mensaje, no hay grafico que la explique mejor. */}
      <div className="grid grid-cols-2 gap-px bg-ink-200 lg:grid-cols-3">
        <Tile
          index="01"
          icon={<Boxes size={16} />}
          label="Valor del inventario"
          valor={v(formatoCLPCorto(r?.valor_inventario_clp))}
          nota={v(`${formatoNumero(r?.unidades)} unidades`)}
        />
        <Tile
          index="02"
          icon={<Snowflake size={16} />}
          label="Inmovilizado"
          valor={v(formatoCLPCorto(r?.inmovilizado_clp))}
          nota={v(`${formatoNumero(r?.inmovilizado_pct, 1)}% del valor · ${formatoNumero(r?.inmovilizado_n)} productos`)}
          acento
        />
        <Tile
          index="03"
          icon={<TrendingUp size={16} />}
          label={`Sobre-stock (+${data?.dias_sobre_stock ?? dias} días)`}
          valor={v(formatoCLPCorto(r?.sobre_stock_clp))}
          nota={v(`${formatoNumero(r?.sobre_stock_pct, 1)}% del valor · ${formatoNumero(r?.sobre_stock_n)} productos`)}
        />
        <Tile
          index="04"
          icon={<PackageX size={16} />}
          label="Quiebre con demanda"
          valor={v(formatoNumero(r?.quiebre_con_demanda_n))}
          nota="Sin stock y con venta viva"
        />
        <Tile
          index="05"
          icon={<AlertTriangle size={16} />}
          label="Bajo punto de pedido"
          valor={v(formatoNumero(r?.bajo_punto_pedido_n))}
          nota="Contando lo que viene en tránsito"
        />
        <Tile
          index="06"
          icon={<Clock size={16} />}
          label="Cobertura mediana"
          valor={v(
            r?.cobertura_dias_mediana != null
              ? `${formatoNumero(r.cobertura_dias_mediana, 0)} días`
              : "—"
          )}
          nota="Lo que alcanza el stock al ritmo actual"
        />
      </div>

      {r && r.sin_costo_n > 0 && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          {formatoNumero(r.sin_costo_n)} productos con stock no tienen costo unitario: su
          valorización no está incluida en las cifras de arriba.
        </p>
      )}

      {grafico.length > 0 && (
        <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <h2 className="mb-3 text-[14px] font-semibold text-slate-900">
            Plata inmovilizada por sucursal
          </h2>
          <div style={{ height: Math.max(180, grafico.length * 34) }}>
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={grafico} layout="vertical" margin={{ left: 8, right: 24 }}>
                <CartesianGrid horizontal={false} stroke="#ebe9dd" />
                <XAxis
                  type="number"
                  tickFormatter={(x: number) => formatoCLPCorto(x)}
                  tick={{ fontSize: 11 }}
                  stroke="#94a3b8"
                />
                <YAxis
                  type="category"
                  dataKey="nombre"
                  width={130}
                  tick={{ fontSize: 11 }}
                  stroke="#94a3b8"
                />
                <Tooltip
                  formatter={(x: number) => [formatoCLP(x), "Inmovilizado"]}
                  cursor={{ fill: "#fff7ed" }}
                  contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #ebe9dd" }}
                />
                <Bar dataKey="valor" radius={[0, 4, 4, 0]} isAnimationActive={false}>
                  {grafico.map((g) => (
                    <Cell key={g.nombre} fill="#1e40af" />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </section>
      )}

      <section>
        <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
          Detalle por sucursal
        </h2>
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Sucursal</th>
                <th className="px-4 py-2 text-right">Valor</th>
                <th className="px-4 py-2 text-right">Inmovilizado</th>
                <th className="px-4 py-2 text-right">Sobre-stock</th>
                <th className="px-4 py-2 text-right">Quiebres</th>
                <th className="px-4 py-2 text-right">Bajo PP</th>
                <th className="px-4 py-2 text-right">Productos</th>
              </tr>
            </thead>
            <tbody>
              {(data?.por_sucursal ?? []).map((s) => (
                <tr key={s.sucursal_id} className="border-t border-slate-100">
                  <td className="px-4 py-2 font-medium text-slate-900">{s.nombre_sucursal}</td>
                  <td className="px-4 py-2 text-right tabular">{formatoCLP(s.valor_clp)}</td>
                  <td className="px-4 py-2 text-right tabular text-accent-700">
                    {formatoCLP(s.inmovilizado_clp)}
                  </td>
                  <td className="px-4 py-2 text-right tabular">{formatoCLP(s.sobre_stock_clp)}</td>
                  <td className="px-4 py-2 text-right tabular">
                    {formatoNumero(s.quiebre_con_demanda_n)}
                  </td>
                  <td className="px-4 py-2 text-right tabular">
                    {formatoNumero(s.bajo_punto_pedido_n)}
                  </td>
                  <td className="px-4 py-2 text-right tabular text-slate-500">
                    {formatoNumero(s.n_productos)}
                  </td>
                </tr>
              ))}
              {!cargando && (data?.por_sucursal ?? []).length === 0 && (
                <tr>
                  <td colSpan={7} className="px-4 py-6 text-center text-slate-400">
                    Sin datos de inventario.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>

      <section>
        <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
          Top inmovilizado (mayor plata detenida)
        </h2>
        <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
              <tr>
                <th className="px-4 py-2">Producto</th>
                <th className="px-4 py-2">Descripción</th>
                <th className="px-4 py-2">Sucursal</th>
                <th className="px-4 py-2 text-right">Unidades</th>
                <th className="px-4 py-2 text-right">Valor</th>
              </tr>
            </thead>
            <tbody>
              {(data?.top_inmovilizado ?? []).map((p) => (
                <tr key={`${p.producto}-${p.sucursal_id}`} className="border-t border-slate-100">
                  <td className="px-4 py-2 font-medium">
                    <Link
                      href={`/producto/${encodeURIComponent(p.producto)}?sucursal=${encodeURIComponent(p.sucursal_id)}`}
                      className="text-brand hover:underline"
                    >
                      {p.producto}
                    </Link>
                  </td>
                  <td className="px-4 py-2 text-slate-600">{p.descripcion ?? "—"}</td>
                  <td className="px-4 py-2 text-slate-600">{p.nombre_sucursal}</td>
                  <td className="px-4 py-2 text-right tabular">{formatoNumero(p.unidades)}</td>
                  <td className="px-4 py-2 text-right tabular font-medium">
                    {formatoCLP(p.valor_clp)}
                  </td>
                </tr>
              ))}
              {!cargando && (data?.top_inmovilizado ?? []).length === 0 && (
                <tr>
                  <td colSpan={5} className="px-4 py-6 text-center text-slate-400">
                    No hay productos inmovilizados.
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

function Tile({
  index,
  icon,
  label,
  valor,
  nota,
  acento,
}: {
  index: string;
  icon: React.ReactNode;
  label: string;
  valor: string;
  nota?: string;
  acento?: boolean;
}) {
  return (
    <div className="group relative overflow-hidden border border-ink-200 bg-white p-5 transition-colors hover:border-ink-300">
      <span className="absolute left-5 top-4 font-mono text-[10px] text-ink-400">{index}</span>
      <span className="absolute right-4 top-4 text-ink-300 transition-colors group-hover:text-ink-500">
        {icon}
      </span>
      <p className="kicker mt-6">{label}</p>
      <p
        className={`figure mt-2 text-[30px] leading-none ${
          acento ? "text-accent-700" : "text-ink-900"
        }`}
      >
        {valor}
      </p>
      {nota && <p className="mt-1.5 text-[11px] text-ink-500">{nota}</p>}
      <span
        className={`absolute bottom-0 left-0 h-px transition-all ${
          acento ? "w-12 bg-accent-700" : "w-8 bg-ink-300 group-hover:w-16"
        }`}
      />
    </div>
  );
}
