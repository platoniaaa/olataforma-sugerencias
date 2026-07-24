"use client";

// Simulador what-if: cuanto cambiaria la compra si se movieran los parametros,
// ANTES de tocar nada. No modifica ningun dato.
import { useState } from "react";
import { FlaskConical, Play } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type { SimulacionResultado } from "@/lib/types";

// Nivel de servicio por clase: el Z de la formula del stock de seguridad.
const NIVELES = [
  { label: "99% (Z 2,326)", valor: 2.326 },
  { label: "95% (Z 1,645)", valor: 1.645 },
  { label: "90% (Z 1,282)", valor: 1.282 },
  { label: "80% (Z 0,842)", valor: 0.842 },
  { label: "Sin colchón (Z 0)", valor: 0 },
];
const Z_ACTUAL: Record<string, number> = { A: 1.645, B: 1.282, C: 0.842, D: 0 };

export default function SimuladorPage() {
  const [co, setCo] = useState(5);
  const [coCd, setCoCd] = useState(5);
  const [z, setZ] = useState<Record<string, number>>({ ...Z_ACTUAL });
  const [factorLt, setFactorLt] = useState(1);
  const [r, setR] = useState<SimulacionResultado | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const correr = async () => {
    setCargando(true);
    setError(null);
    try {
      setR(
        await api.simular({
          ciclo_orden_dias: co,
          ciclo_orden_dias_cd: coCd,
          z_por_clase: z,
          factor_lead_time: factorLt,
        })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo simular");
    } finally {
      setCargando(false);
    }
  };

  const resetear = () => {
    setCo(5);
    setCoCd(3);
    setZ({ ...Z_ACTUAL });
    setFactorLt(1);
  };

  const delta = r?.resumen.delta_clp ?? 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
          <FlaskConical size={20} /> Simulador
        </h1>
        <p className="text-[13px] text-slate-500">
          Mueve los parámetros y mira el impacto antes de aplicarlos. No cambia ningún dato.
        </p>
      </div>

      <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div className="grid gap-4 md:grid-cols-2">
          <label className="block">
            <span className="mb-1 block text-[12px] font-medium text-slate-600">
              Ciclo de orden — compra directa (días)
            </span>
            <input
              type="number"
              min={1}
              max={60}
              value={co}
              onChange={(e) => setCo(Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px]"
            />
            <span className="mt-1 block text-[11px] text-slate-400">Hoy: 5 días</span>
          </label>
          <label className="block">
            <span className="mb-1 block text-[12px] font-medium text-slate-600">
              Ciclo de orden — abastecido del CD (días)
            </span>
            <input
              type="number"
              min={1}
              max={60}
              value={coCd}
              onChange={(e) => setCoCd(Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px]"
            />
            <span className="mt-1 block text-[11px] text-slate-400">Hoy: 5 días</span>
          </label>
          <label className="block">
            <span className="mb-1 block text-[12px] font-medium text-slate-600">
              Lead time (factor sobre el actual)
            </span>
            <input
              type="number"
              step={0.1}
              min={0.1}
              max={5}
              value={factorLt}
              onChange={(e) => setFactorLt(Number(e.target.value))}
              className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px]"
            />
            <span className="mt-1 block text-[11px] text-slate-400">
              1 = sin cambios · 1,5 = proveedores 50% más lentos
            </span>
          </label>
        </div>

        <div className="mt-4">
          <p className="mb-2 text-[12px] font-medium text-slate-600">
            Nivel de servicio por clase ABC (define el stock de seguridad)
          </p>
          <div className="grid gap-2 sm:grid-cols-4">
            {["A", "B", "C", "D"].map((clase) => (
              <label key={clase} className="block">
                <span className="mb-1 block text-[11px] text-slate-500">Clase {clase}</span>
                <select
                  value={z[clase]}
                  onChange={(e) => setZ({ ...z, [clase]: Number(e.target.value) })}
                  className="w-full rounded-md border border-slate-300 px-2 py-1 text-[12px]"
                >
                  {NIVELES.map((n) => (
                    <option key={n.valor} value={n.valor}>
                      {n.label}
                    </option>
                  ))}
                </select>
              </label>
            ))}
          </div>
        </div>

        <div className="mt-4 flex gap-2">
          <button
            onClick={correr}
            disabled={cargando}
            className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            <Play size={14} /> {cargando ? "Calculando…" : "Simular"}
          </button>
          <button
            onClick={resetear}
            className="rounded-md border border-slate-200 px-3 py-1.5 text-[13px] hover:bg-slate-50"
          >
            Volver a los valores actuales
          </button>
        </div>
        {error && (
          <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
        )}
      </section>

      {r && (
        <>
          <section className="grid grid-cols-2 gap-px bg-ink-200 lg:grid-cols-4">
            <Tile label="Compra actual" valor={formatoCLPCorto(r.resumen.actual_clp)}
              nota={`${formatoNumero(r.resumen.actual_unidades)} unidades`} />
            <Tile label="Compra simulada" valor={formatoCLPCorto(r.resumen.simulado_clp)}
              nota={`${formatoNumero(r.resumen.simulado_unidades)} unidades`} />
            <Tile
              label="Diferencia"
              valor={`${delta >= 0 ? "+" : ""}${formatoCLPCorto(delta)}`}
              nota={`${r.resumen.delta_unidades >= 0 ? "+" : ""}${formatoNumero(r.resumen.delta_unidades)} unidades`}
              acento
            />
            <Tile label="Líneas que cambian" valor={formatoNumero(r.resumen.lineas_que_cambian)}
              nota={`de ${formatoNumero(r.resumen.n_filas)} analizadas`} />
          </section>

          <section>
            <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
              Impacto por sucursal
            </h2>
            <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
              <table className="w-full text-sm">
                <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                  <tr>
                    <th className="px-4 py-2">Sucursal</th>
                    <th className="px-4 py-2 text-right">Actual</th>
                    <th className="px-4 py-2 text-right">Simulado</th>
                    <th className="px-4 py-2 text-right">Diferencia</th>
                  </tr>
                </thead>
                <tbody>
                  {r.por_sucursal.slice(0, 20).map((s) => (
                    <tr key={s.sucursal_id} className="border-t border-slate-100">
                      <td className="px-4 py-2 font-medium text-slate-900">{s.nombre_sucursal}</td>
                      <td className="px-4 py-2 text-right tabular">{formatoCLP(s.actual_clp)}</td>
                      <td className="px-4 py-2 text-right tabular">{formatoCLP(s.simulado_clp)}</td>
                      <td
                        className={`px-4 py-2 text-right tabular font-medium ${
                          s.delta_clp > 0 ? "text-red-700" : s.delta_clp < 0 ? "text-emerald-700" : ""
                        }`}
                      >
                        {s.delta_clp > 0 ? "+" : ""}
                        {formatoCLP(s.delta_clp)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          {r.mayores_cambios.length > 0 && (
            <section>
              <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
                Mayores cambios por producto
              </h2>
              <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
                <table className="w-full text-sm">
                  <thead className="bg-slate-50 text-left text-xs uppercase text-slate-500">
                    <tr>
                      <th className="px-4 py-2">Producto</th>
                      <th className="px-4 py-2">Sucursal</th>
                      <th className="px-4 py-2 text-right">Actual</th>
                      <th className="px-4 py-2 text-right">Simulado</th>
                      <th className="px-4 py-2 text-right">Δ CLP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {r.mayores_cambios.map((c) => (
                      <tr key={`${c.producto}-${c.sucursal_id}`} className="border-t border-slate-100">
                        <td className="px-4 py-2 font-medium">{c.producto}</td>
                        <td className="px-4 py-2 text-slate-600">{c.sucursal_id}</td>
                        <td className="px-4 py-2 text-right tabular">{formatoNumero(c.actual)}</td>
                        <td className="px-4 py-2 text-right tabular">{formatoNumero(c.simulado)}</td>
                        <td
                          className={`px-4 py-2 text-right tabular ${
                            c.delta_clp > 0 ? "text-red-700" : "text-emerald-700"
                          }`}
                        >
                          {c.delta_clp > 0 ? "+" : ""}
                          {formatoCLP(c.delta_clp)}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          )}

          <p className="text-[11px] text-slate-400">
            El simulador recalcula la fórmula del modelo sobre los datos vigentes (demanda,
            desviación y lead time ya calculados). Un cambio que altere la clasificación ABC o
            la demanda requiere volver a correr el motor.
          </p>
        </>
      )}
    </div>
  );
}

function Tile({
  label,
  valor,
  nota,
  acento,
}: {
  label: string;
  valor: string;
  nota?: string;
  acento?: boolean;
}) {
  return (
    <div className="border border-ink-200 bg-white p-5">
      <p className="kicker">{label}</p>
      <p
        className={`figure mt-2 text-[28px] leading-none ${
          acento ? "text-accent-700" : "text-ink-900"
        }`}
      >
        {valor}
      </p>
      {nota && <p className="mt-1.5 text-[11px] text-ink-500">{nota}</p>}
    </div>
  );
}
