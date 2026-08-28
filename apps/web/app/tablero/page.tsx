"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, AlertTriangle, Check, Loader2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type { Tablero } from "@/lib/types";

/**
 * El tablero mensual de Abastecimiento.
 *
 * Dos decisiones que explican cómo se ve:
 *
 * 1. **Los indicadores que no se pueden calcular se muestran igual, vacíos.**
 *    Esconderlos haría creer que el tablero está completo. Hoy la orden de compra
 *    no se registra en la plataforma, así que adherencia, lead time real y
 *    cumplimiento de proveedor no tienen de dónde salir — y eso es justamente la
 *    decisión de fondo que la gerencia tiene que tomar.
 *
 * 2. **Si al mes le faltan días medidos, el bloque de servicio lo dice.** Cuarenta
 *    días de quiebre sobre doce días medidos no se comparan con los del mes
 *    anterior, y callarlo es la forma más fácil de que alguien concluya al revés.
 */
const MESES = ["enero", "febrero", "marzo", "abril", "mayo", "junio", "julio",
  "agosto", "septiembre", "octubre", "noviembre", "diciembre"];

function nombreMes(periodo: string): string {
  const [a, m] = periodo.split("-");
  return `${MESES[Number(m) - 1] ?? m} ${a}`;
}

/** Los últimos 12 meses hasta el período con datos, para el selector. */
function opcionesMes(hasta: string): string[] {
  const [a, m] = hasta.split("-").map(Number);
  const base = a * 12 + (m - 1);
  return Array.from({ length: 12 }, (_, i) => {
    const t = base - i;
    return `${Math.floor(t / 12)}-${String((t % 12) + 1).padStart(2, "0")}`;
  });
}

export default function TableroPage() {
  const [d, setD] = useState<Tablero | null>(null);
  const [periodo, setPeriodo] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);

  const cargar = useCallback(async (p: string | null) => {
    setCargando(true);
    try {
      const t = await api.tablero(p ?? undefined);
      setD(t);
      setPeriodo(t.periodo);
      setError(null);
    } catch {
      setError("No se pudo cargar el tablero.");
    } finally {
      setCargando(false);
    }
  }, []);

  useEffect(() => {
    void cargar(null);
  }, [cargar]);

  if (cargando && !d) {
    return (
      <p className="flex items-center gap-2 p-6 text-sm text-ink-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Calculando el tablero…
      </p>
    );
  }
  if (error && !d) {
    return (
      <p className="m-6 flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
        <AlertCircle className="h-4 w-4" /> {error}
      </p>
    );
  }
  if (!d) return null;

  const s = d.servicio;
  const inv = d.inventario.resumen;
  const maxClase = Math.max(...s.dias_quiebre_por_clase.map((c) => c.dias), 1);
  const maxSuc = Math.max(...d.inventario.por_sucursal.map((x) => x.valor_clp), 1);

  return (
    <div className="space-y-6 p-6">

      <header className="flex flex-wrap items-end gap-3">
        <div>
          <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
            Abastecimiento
          </p>
          <h1 className="text-2xl font-semibold text-ink-900">Tablero mensual</h1>
          <p className="text-sm text-ink-500">Cierre de {nombreMes(d.periodo)}</p>
        </div>
        <select
          value={periodo ?? d.periodo}
          onChange={(e) => void cargar(e.target.value)}
          className="ml-auto h-9 rounded-md border border-ink-200 bg-white px-3 text-sm"
        >
          {opcionesMes(d.periodo).map((p) => (
            <option key={p} value={p}>{nombreMes(p)}</option>
          ))}
        </select>
      </header>

      {/* El mes incompleto se avisa arriba de todo: cambia cómo se leen los
          días de quiebre de más abajo. */}
      {!s.mes_completo && (
        <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[13px] text-amber-900">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0" />
          <span>
            Este mes tiene <b>{s.dias_medidos} de {s.dias_del_mes} días</b> con foto
            guardada. Los días de quiebre se cuentan solo sobre los días medidos, así
            que no se comparan directo con un mes completo.
          </span>
        </p>
      )}

      <Bloque titulo="Servicio" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi
          rot="Días de quiebre · clase A"
          cifra={formatoNumero(s.dias_quiebre_por_clase.find((c) => c.clase === "A")?.dias ?? 0)}
          pie={`Sobre ${s.dias_medidos} días medidos. Total de todas las clases: ${formatoNumero(s.dias_quiebre_total)}.`}
        />
        <Kpi
          rot="Días de quiebre en repuestos InStock"
          cifra={formatoNumero(s.dias_quiebre_instock)}
          estado={s.dias_quiebre_instock > 0 ? "crit" : "good"}
          etiqueta={s.dias_quiebre_instock > 0 ? "Compromiso incumplido" : "Sin quiebres"}
          pie={`${s.repuestos_instock} repuestos de pauta, en las 4 sucursales con taller.`}
        />
        <Kpi
          rot="Quiebre con demanda viva · hoy"
          cifra={formatoNumero(s.quiebre_con_demanda_hoy)}
          pie="Filas sin stock que el modelo sí ve vendiendo."
        />
        <Kpi
          rot="Bajo el punto de pedido"
          cifra={formatoNumero(inv.bajo_punto_pedido_n)}
          pie="Riesgo de quiebre antes de que ocurra, contando el tránsito."
        />
      </div>

      <Bloque titulo="Inversión en inventario" />
      <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
        <Kpi rot="Valor del inventario" cifra={formatoCLPCorto(inv.valor_inventario_clp)}
          pie={`${formatoNumero(inv.unidades)} unidades en toda la red.`} />
        <Kpi rot="Cobertura mediana" cifra={`${formatoNumero(inv.cobertura_dias_mediana ?? 0, 1)} días`}
          pie="Mediana y no promedio: un dato extremo no la mueve." />
        <Kpi rot="Inmovilizado" cifra={formatoCLPCorto(inv.inmovilizado_clp)}
          estado={inv.inmovilizado_pct > 15 ? "crit" : "warn"}
          etiqueta={`${formatoNumero(inv.inmovilizado_pct, 1)}% del inventario`}
          pie={`${formatoNumero(inv.inmovilizado_n)} filas con stock y sin demanda.`} />
        <Kpi rot="Sobre-stock" cifra={formatoCLPCorto(inv.sobre_stock_clp)}
          estado={inv.sobre_stock_pct > 15 ? "warn" : undefined}
          etiqueta={`${formatoNumero(inv.sobre_stock_pct, 1)}% del inventario`}
          pie={`Alcanza para más de ${d.inventario.dias_sobre_stock} días.`} />
      </div>

      <div className="grid gap-3 lg:grid-cols-2">
        <Panel titulo="Días de quiebre por clase" nota={`${s.dias_medidos} días medidos`}>
          {/* Una sola tonalidad: es magnitud, no identidad. La clase A va marcada
              porque es la que importa, no la que tiene la barra más alta. */}
          <div className="flex h-40 items-end gap-4 pt-1">
            {s.dias_quiebre_por_clase.map((c) => (
              <div key={c.clase} className="flex h-full flex-1 flex-col items-center justify-end gap-1.5">
                <span className="text-xs font-semibold tabular-nums text-ink-700">
                  {formatoNumero(c.dias)}
                </span>
                <div
                  className={`w-full rounded-t ${c.clase === "A" ? "bg-rose-600" : "bg-brand"}`}
                  style={{ height: `${Math.max((c.dias / maxClase) * 100, 2)}%` }}
                />
                <span className="text-xs font-semibold text-ink-500">{c.clase}</span>
              </div>
            ))}
          </div>
          <p className="mt-2 text-[11.5px] text-ink-500">
            Que quiebren los de clase D es esperable: casi no se venden. El que
            importa es <b>A</b>, marcado aparte.
          </p>
        </Panel>

        <Panel titulo="Inventario por sucursal" nota="valor a costo">
          <div className="space-y-2">
            {d.inventario.por_sucursal.slice(0, 8).map((x) => (
              <div key={x.sucursal_id} className="grid grid-cols-[7rem_1fr_4.5rem] items-center gap-2">
                <span className="truncate text-xs text-ink-600">{x.nombre_sucursal}</span>
                <div className="h-3.5 rounded bg-ink-100">
                  <div className="h-full rounded bg-brand"
                    style={{ width: `${Math.max((x.valor_clp / maxSuc) * 100, 1)}%` }} />
                </div>
                <span className="text-right text-xs tabular-nums text-ink-600">
                  {formatoCLPCorto(x.valor_clp)}
                </span>
              </div>
            ))}
          </div>
        </Panel>
      </div>

      <Bloque titulo="Ejecución de la compra" />
      <div className="rounded-lg border border-dashed border-accent-700/40 bg-accent-50 p-4">
        <p className="mb-3 flex items-start gap-2 text-[13px] text-ink-700">
          <AlertTriangle className="mt-0.5 h-4 w-4 shrink-0 text-accent-700" />
          <span>{d.ejecucion_compra.motivo}</span>
        </p>
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          {d.ejecucion_compra.indicadores.map((n) => (
            <div key={n} className="rounded-md border border-dashed border-ink-200 bg-white/60 p-3">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-accent-700">
                Falta el dato
              </p>
              <p className="mt-1 text-[13px] text-ink-600">{n}</p>
              <p className="mt-1 font-mono text-xl text-ink-300">—</p>
            </div>
          ))}
        </div>
      </div>

      <Bloque titulo="Lo que hay que mover" />
      <div className="grid gap-3 lg:grid-cols-2">
        <Panel
          titulo="Obsolescencia FORD"
          nota={`${formatoCLPCorto(d.obsolescencia.valor_clp)} en ${d.obsolescencia.n_codigos} códigos`}
        >
          {d.obsolescencia.top.length === 0 ? (
            <p className="py-6 text-center text-sm text-ink-500">
              No hay stock de códigos dados de baja.
            </p>
          ) : (
            <table className="w-full text-[13px]">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wide text-ink-400">
                  <th className="pb-1.5">Código</th>
                  <th className="pb-1.5">Descripción</th>
                  <th className="pb-1.5 text-right">Stock</th>
                  <th className="pb-1.5 text-right">Valor</th>
                </tr>
              </thead>
              <tbody>
                {d.obsolescencia.top.map((o) => (
                  <tr key={o.producto} className="border-t border-ink-100">
                    <td className="py-1.5">
                      <Link href={`/catalogo/${encodeURIComponent(o.producto)}`}
                        className="font-mono text-[12px] text-ink-700 hover:text-brand">
                        {o.producto}
                      </Link>
                    </td>
                    <td className="py-1.5 text-ink-600">{o.descripcion ?? "—"}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatoNumero(o.unidades)}</td>
                    <td className="py-1.5 text-right tabular-nums">{formatoCLPCorto(o.valor_clp)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          )}
        </Panel>

        <Panel titulo="Salud del dato" nota="si esto se descuida, lo de arriba miente">
          <table className="w-full text-[13px]">
            <tbody>
              {d.salud_del_dato.map((f) => (
                <tr key={f.que} className="border-t border-ink-100 first:border-0">
                  <td className="py-2 pr-3 text-ink-600">
                    {f.que}
                    <span className="block text-[11px] text-ink-400">{f.detalle}</span>
                  </td>
                  <td className="whitespace-nowrap py-2 text-right">
                    <span className={`font-mono text-sm font-semibold tabular-nums ${
                      f.alerta ? "text-accent-700" : "text-emerald-700"}`}>
                      {formatoNumero(f.valor)}{f.de != null && ` de ${formatoNumero(f.de)}`}
                    </span>
                    {!f.alerta && <Check className="ml-1 inline h-3.5 w-3.5 text-emerald-700" />}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Panel>
      </div>
    </div>
  );
}

function Bloque({ titulo }: { titulo: string }) {
  return (
    <h2 className="flex items-center gap-3 pt-1 text-[11px] font-semibold uppercase tracking-[0.13em] text-ink-400">
      {titulo}
      <span className="h-px flex-1 bg-ink-200" />
    </h2>
  );
}

function Kpi({
  rot, cifra, pie, estado, etiqueta,
}: {
  rot: string; cifra: string; pie?: string;
  estado?: "good" | "warn" | "crit"; etiqueta?: string;
}) {
  // El estado va con color Y palabra. Solo color deja fuera a quien no lo
  // distingue, y en una impresión en blanco y negro no queda nada.
  const color = estado === "crit" ? "text-rose-700"
    : estado === "warn" ? "text-amber-700"
    : "text-emerald-700";
  return (
    <div className="rounded-lg border border-ink-100 bg-white p-4">
      <p className="text-xs leading-snug text-ink-500">{rot}</p>
      <p className="mt-1 font-mono text-2xl font-semibold tabular-nums tracking-tight text-ink-900">
        {cifra}
      </p>
      {etiqueta && (
        <p className={`mt-0.5 flex items-center gap-1 text-[11px] font-semibold ${color}`}>
          {estado === "good" ? <Check className="h-3 w-3" /> : <AlertTriangle className="h-3 w-3" />}
          {etiqueta}
        </p>
      )}
      {pie && <p className="mt-1.5 text-[11px] text-ink-400">{pie}</p>}
    </div>
  );
}

function Panel({
  titulo, nota, children,
}: {
  titulo: string; nota?: string; children: React.ReactNode;
}) {
  return (
    <div className="rounded-lg border border-ink-100 bg-white p-4">
      <div className="mb-3 flex items-baseline gap-2">
        <h3 className="text-sm font-semibold text-ink-900">{titulo}</h3>
        {nota && <span className="ml-auto text-[11px] text-ink-400">{nota}</span>}
      </div>
      {children}
    </div>
  );
}
