"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowDown,
  ArrowUp,
  Download,
  FileSpreadsheet,
} from "lucide-react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Legend,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoCLPCorto, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type {
  PostVentaMeta,
  VentasKpis,
  VentasMes,
  VentasPorSucursal,
} from "@/lib/types";

const MESES = ["Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic"];

function etiquetaPeriodo(yyyymm: string): string {
  if (!yyyymm || yyyymm.length < 6) return yyyymm;
  const anio = yyyymm.slice(0, 4);
  const mes = parseInt(yyyymm.slice(4, 6), 10);
  return `${MESES[mes - 1] ?? yyyymm.slice(4, 6)} ${anio}`;
}

function etiquetaCorta(yyyymm: string): string {
  if (!yyyymm || yyyymm.length < 6) return yyyymm;
  const mes = parseInt(yyyymm.slice(4, 6), 10);
  const anio = yyyymm.slice(2, 4);
  return `${MESES[mes - 1] ?? ""} ${anio}`;
}

const EXCEL_MAX = 1_048_575;

export default function VentasPage() {
  const [kpis, setKpis] = useState<VentasKpis | null>(null);
  const [serie, setSerie] = useState<VentasMes[]>([]);
  const [porSucursal, setPorSucursal] = useState<VentasPorSucursal | null>(null);
  const [meta, setMeta] = useState<PostVentaMeta | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Export
  const [desde, setDesde] = useState("");
  const [hasta, setHasta] = useState("");
  const [sucursal, setSucursal] = useState("");
  const [conteo, setConteo] = useState<number | null>(null);
  const [contando, setContando] = useState(false);
  const [descargando, setDescargando] = useState(false);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const [k, s, ps, m] = await Promise.all([
        api.ventasKpis(),
        api.ventasMensual(12),
        api.ventasPorSucursal(),
        api.postVentaMeta(),
      ]);
      setKpis(k);
      setSerie(s);
      setPorSucursal(ps);
      setMeta(m);
      if (m.periodos.length > 0) {
        setDesde(m.periodos[0]);
        setHasta(m.periodos[m.periodos.length - 1]);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const filtros = useMemo(
    () => ({
      periodo_desde: desde || null,
      periodo_hasta: hasta || null,
      sucursal: sucursal || null,
    }),
    [desde, hasta, sucursal]
  );

  useEffect(() => {
    if (!meta || meta.filas === 0) return;
    let activo = true;
    setContando(true);
    const t = setTimeout(() => {
      api
        .postVentaContar(filtros)
        .then((n) => activo && setConteo(n))
        .catch(() => activo && setConteo(null))
        .finally(() => activo && setContando(false));
    }, 250);
    return () => {
      activo = false;
      clearTimeout(t);
    };
  }, [filtros, meta]);

  const descargar = useCallback(async () => {
    setDescargando(true);
    try {
      await api.exportPostVenta(filtros);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo generar el Excel");
    } finally {
      setDescargando(false);
    }
  }, [filtros]);

  const excedido = conteo !== null && conteo > EXCEL_MAX;
  const sinFilas = conteo === 0;
  const periodoInvalido = Boolean(desde && hasta && desde > hasta);

  const serieParaGrafico = serie.map((m) => ({ ...m, etiqueta: etiquetaCorta(m.periodo) }));

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="kicker mb-1">Operación</p>
          <h1 className="editorial-rule font-display text-[28px] font-medium leading-none tracking-tight text-ink-900">
            Ventas
          </h1>
          <p className="mt-3 text-[13px] text-ink-500">
            {cargando ? "Cargando…" : null}
            {meta && !cargando && (
              <>
                {formatoNumero(meta.filas)} líneas ·{" "}
                {meta.periodos.length} mes{meta.periodos.length === 1 ? "" : "es"} ·{" "}
                actualizado{" "}
                <b className="font-mono">
                  {meta.actualizado_en ? formatoFechaHora(meta.actualizado_en) : "—"}
                </b>
              </>
            )}
          </p>
        </div>
      </div>

      {error && (
        <p className="rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {error}
        </p>
      )}

      {/* KPIs (CLP + Unidades) */}
      {kpis && kpis.periodo_actual && (
        <>
          <p className="kicker">Mes en curso · {etiquetaPeriodo(kpis.periodo_actual)}</p>
          <div className="grid grid-cols-2 gap-px bg-ink-200 lg:grid-cols-4">
            <KpiCard
              index="01"
              label="Venta CLP"
              valor={formatoCLPCorto(kpis.actual.clp)}
              variacion={kpis.var_clp_pct}
              acento
            />
            <KpiCard
              index="02"
              label="Unidades"
              valor={formatoNumero(kpis.actual.unidades)}
              variacion={kpis.var_unidades_pct}
            />
            <KpiCard
              index="03"
              label="Líneas / transacciones"
              valor={formatoNumero(kpis.actual.n_lineas)}
            />
            <KpiCard
              index="04"
              label={`Mes anterior · ${
                kpis.periodo_anterior ? etiquetaPeriodo(kpis.periodo_anterior) : "—"
              }`}
              valor={formatoCLPCorto(kpis.anterior.clp)}
            />
          </div>
        </>
      )}

      {/* Grafico mensual */}
      {serieParaGrafico.length > 0 && (
        <div className="rounded-sm border border-ink-200 bg-white shadow-card">
          <div className="border-b border-ink-100 px-5 py-3">
            <p className="kicker">Histórico</p>
            <h2 className="font-display text-[16px] font-medium text-ink-900">
              Venta mensual ({serieParaGrafico.length} meses)
            </h2>
          </div>
          <div className="p-3">
            <ResponsiveContainer width="100%" height={260}>
              <BarChart data={serieParaGrafico} margin={{ top: 8, right: 16, left: 0, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#ebe9dd" vertical={false} />
                <XAxis
                  dataKey="etiqueta"
                  tick={{ fontSize: 11, fill: "#57534e" }}
                  axisLine={false}
                  tickLine={false}
                />
                <YAxis
                  yAxisId="left"
                  tick={{ fontSize: 11, fill: "#a8a29e" }}
                  axisLine={false}
                  tickLine={false}
                  width={56}
                  tickFormatter={(v: number) => formatoCLPCorto(v)}
                />
                <Tooltip
                  formatter={(v: number, name: string) => {
                    if (name === "CLP") return [formatoCLP(v), "CLP"];
                    return [formatoNumero(v), "Unidades"];
                  }}
                  cursor={{ fill: "#fff7ed" }}
                  contentStyle={{ fontSize: 12, borderRadius: 4, border: "1px solid #ebe9dd" }}
                />
                <Legend iconType="square" wrapperStyle={{ fontSize: 11, paddingTop: 8 }} />
                <Bar
                  yAxisId="left"
                  dataKey="clp"
                  name="CLP"
                  fill="#1e40af"
                  radius={[2, 2, 0, 0]}
                  isAnimationActive={false}
                />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      )}

      {/* Tabla por sucursal */}
      {porSucursal && porSucursal.items.length > 0 && (
        <div className="rounded-sm border border-ink-200 bg-white shadow-card">
          <div className="border-b border-ink-100 px-5 py-3">
            <p className="kicker">Detalle</p>
            <h2 className="font-display text-[16px] font-medium text-ink-900">
              Por sucursal · {etiquetaPeriodo(porSucursal.periodo ?? "")}
            </h2>
          </div>
          <table className="w-full text-sm">
            <thead className="bg-paper-100 text-left text-xs uppercase tracking-wider text-ink-500">
              <tr>
                <th className="px-5 py-2">Sucursal</th>
                <th className="px-5 py-2 text-right">CLP</th>
                <th className="px-5 py-2 text-right">Unidades</th>
                <th className="px-5 py-2 text-right">Líneas</th>
              </tr>
            </thead>
            <tbody>
              {porSucursal.items.map((s) => (
                <tr key={s.sucursal} className="border-t border-ink-100 hover:bg-paper-100/50">
                  <td className="px-5 py-2 font-medium text-ink-900">{s.sucursal}</td>
                  <td className="px-5 py-2 text-right tabular font-semibold">
                    {formatoCLP(s.clp)}
                  </td>
                  <td className="px-5 py-2 text-right tabular">{formatoNumero(s.unidades)}</td>
                  <td className="px-5 py-2 text-right tabular text-ink-500">
                    {formatoNumero(s.n_lineas)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Descarga Excel */}
      {meta && meta.filas > 0 && (
        <div className="rounded-sm border border-ink-200 bg-white shadow-card">
          <div className="border-b border-ink-100 px-5 py-3">
            <p className="kicker">Descarga</p>
            <h2 className="flex items-center gap-2 font-display text-[16px] font-medium text-ink-900">
              <FileSpreadsheet size={18} className="text-accent-700" /> Planilla Post Venta
              completa
            </h2>
          </div>
          <div className="space-y-4 p-5">
            <div className="grid gap-4 sm:grid-cols-3">
              <FieldSelect
                label="Desde"
                value={desde}
                onChange={setDesde}
                options={meta.periodos.map((p) => ({ value: p, label: etiquetaPeriodo(p) }))}
              />
              <FieldSelect
                label="Hasta"
                value={hasta}
                onChange={setHasta}
                options={meta.periodos.map((p) => ({ value: p, label: etiquetaPeriodo(p) }))}
              />
              <FieldSelect
                label="Sucursal"
                value={sucursal}
                onChange={setSucursal}
                options={[
                  { value: "", label: "Todas" },
                  ...meta.sucursales.map((s) => ({ value: s, label: s })),
                ]}
              />
            </div>

            <div className="text-[13px] text-ink-700">
              {periodoInvalido ? (
                <span className="text-amber-700">
                  El mes &ldquo;desde&rdquo; es posterior al &ldquo;hasta&rdquo;.
                </span>
              ) : contando ? (
                "Calculando filas…"
              ) : conteo !== null ? (
                <>
                  Selección: <b className="tabular text-ink-900">{formatoNumero(conteo)}</b>{" "}
                  líneas
                </>
              ) : null}
            </div>

            {excedido && (
              <p className="flex items-start gap-2 rounded-sm border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
                <AlertTriangle size={16} className="mt-0.5 shrink-0" />
                Demasiadas líneas para un Excel (máx {formatoNumero(EXCEL_MAX)}). Acotá el
                rango o elegí una sucursal.
              </p>
            )}

            <button
              onClick={descargar}
              disabled={descargando || excedido || sinFilas || periodoInvalido}
              className="flex items-center gap-2 rounded-sm bg-ink-900 px-4 py-2 text-[13px] font-semibold uppercase tracking-wider text-paper transition-colors hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              <Download size={14} className={descargando ? "animate-pulse" : ""} />
              {descargando ? "Generando…" : "Descargar Excel"}
            </button>
          </div>
        </div>
      )}

      {meta && meta.filas === 0 && (
        <div className="rounded-sm border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          Aún no hay datos de Post Venta cargados. Ejecutá la sincronización con Power BI
          Desktop abierto.
        </div>
      )}
    </div>
  );
}

function KpiCard({
  index,
  label,
  valor,
  variacion,
  acento,
}: {
  index: string;
  label: string;
  valor: string;
  variacion?: number | null;
  acento?: boolean;
}) {
  const positivo = variacion !== null && variacion !== undefined && variacion >= 0;
  return (
    <div className="group relative overflow-hidden border border-ink-200 bg-white p-5 transition-colors hover:border-ink-300">
      <span className="absolute left-5 top-4 font-mono text-[10px] text-ink-400">{index}</span>
      <p className="kicker mt-6">{label}</p>
      <p
        className={`figure mt-2 text-[28px] leading-none ${
          acento ? "text-accent-700" : "text-ink-900"
        }`}
      >
        {valor}
      </p>
      {variacion !== null && variacion !== undefined && (
        <p
          className={`mt-2 inline-flex items-center gap-1 text-[12px] font-semibold ${
            positivo ? "text-emerald-700" : "text-red-600"
          }`}
        >
          {positivo ? <ArrowUp size={12} /> : <ArrowDown size={12} />}
          {Math.abs(variacion).toFixed(1)}% vs mes anterior
        </p>
      )}
      <span
        className={`absolute bottom-0 left-0 h-px transition-all ${
          acento ? "w-12 bg-accent-700" : "w-8 bg-ink-300 group-hover:w-16"
        }`}
      />
    </div>
  );
}

function FieldSelect({
  label,
  value,
  onChange,
  options,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  options: { value: string; label: string }[];
}) {
  return (
    <label className="flex flex-col gap-1">
      <span className="kicker">{label}</span>
      <select
        value={value}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-sm border border-ink-200 bg-white px-3 py-2 text-[13px] text-ink-900 focus:border-accent-700 focus:outline-none focus:ring-2 focus:ring-accent-700/30"
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </label>
  );
}
