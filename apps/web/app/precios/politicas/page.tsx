"use client";

// La politica de precios: los factores por (tipo, procedencia) y el tipo de
// cada rubro. Cambiar un factor recalcula la lista entera al guardar, asi que
// solo edita el admin; el resto la ve para entender de donde sale cada precio.
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Loader2, Save, Sigma } from "lucide-react";
import { api } from "@/lib/api-client";
import { getEsAdmin } from "@/lib/auth";
import { formatoNumero } from "@/lib/formato";
import type { PoliticaFactor, PoliticaRubro } from "@/lib/types";

const PROCEDENCIAS = ["Nacional", "Importado"] as const;

/** Margen que deja un factor: (F - 1) / F. Es lo que responde "¿cuanto gano?". */
function margen(factor: number): string {
  if (!factor || factor <= 1) return "—";
  return `${formatoNumero(((factor - 1) / factor) * 100, 1)} %`;
}

export default function PoliticasPreciosPage() {
  const [factores, setFactores] = useState<PoliticaFactor[] | null>(null);
  const [rubros, setRubros] = useState<PoliticaRubro[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [guardando, setGuardando] = useState<"factores" | "rubros" | null>(null);
  const [esAdmin, setEsAdmin] = useState(false);

  useEffect(() => {
    setEsAdmin(getEsAdmin());
  }, []);

  const cargar = useCallback(async () => {
    try {
      const [f, r] = await Promise.all([api.politicaFactores(), api.politicaRubros()]);
      setFactores(f);
      setRubros(r);
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la politica.");
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // Los factores se muestran como una grilla tipo x procedencia, que es como
  // estan en la hoja Politica del Excel y como los piensa Abastecimiento.
  const tipos = useMemo(() => {
    const s = new Set<string>();
    (factores ?? []).forEach((f) => s.add(f.tipo));
    return Array.from(s).sort();
  }, [factores]);

  const factorDe = (tipo: string, proc: string) =>
    (factores ?? []).find((f) => f.tipo === tipo && f.procedencia === proc);

  const setFactor = (tipo: string, proc: string, campo: keyof PoliticaFactor, valor: string) => {
    if (!factores) return;
    const num = valor === "" ? null : Number(valor.replace(",", "."));
    const existe = factorDe(tipo, proc);
    if (existe) {
      setFactores(factores.map((f) =>
        f.tipo === tipo && f.procedencia === proc ? { ...f, [campo]: num } : f
      ));
    } else {
      setFactores([...factores, { tipo, procedencia: proc, factor: 0, descuento_max: null, margen_post: null, [campo]: num }]);
    }
  };

  async function guardarFactores() {
    if (!factores) return;
    setGuardando("factores");
    setError(null);
    setAviso(null);
    try {
      const filas = factores.filter((f) => f.factor && f.factor > 1);
      const r = await api.guardarPoliticaFactores(filas);
      setAviso(r.cambios.length
        ? `Guardado. ${r.cambios.length} factor(es) cambiaron y la lista se recalculo.`
        : "Guardado. No habia cambios.");
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setGuardando(null);
    }
  }

  const setRubro = (rubro: string, campo: "tipo" | "procedencia_forzada", valor: string) => {
    if (!rubros) return;
    setRubros(rubros.map((r) => (r.rubro === rubro ? { ...r, [campo]: valor || null } : r)));
  };

  async function guardarRubros() {
    if (!rubros) return;
    setGuardando("rubros");
    setError(null);
    setAviso(null);
    try {
      const r = await api.guardarPoliticaRubros(rubros);
      setAviso(r.cambios.length
        ? `Guardado. ${r.cambios.length} rubro(s) cambiaron y la lista se recalculo.`
        : "Guardado. No habia cambios.");
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setGuardando(null);
    }
  }

  const campoCls = "h-8 w-24 rounded-md border border-ink-200 px-2 text-right text-sm tabular-nums outline-none focus:border-brand disabled:bg-ink-50 disabled:text-ink-500";

  return (
    <div className="space-y-6 p-6">
      <header className="space-y-1">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
          <Link href="/precios" className="inline-flex items-center gap-1 hover:text-brand">
            <ArrowLeft className="h-3 w-3" /> Lista de precios
          </Link>
        </p>
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-ink-900">
          <Sigma className="h-5 w-5 text-brand" /> Política de precios
        </h1>
        <p className="max-w-3xl text-sm text-ink-500">
          El precio es <b>costo × factor</b>. El factor sale del par (tipo, procedencia); el tipo
          de cada producto sale de su rubro, salvo que alguien lo haya escrito a mano. Guardar
          recalcula toda la lista.
          {!esAdmin && " Solo el administrador puede editarla."}
        </p>
      </header>

      {error && (
        <p className="flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          <AlertCircle className="h-4 w-4 shrink-0" /> {error}
        </p>
      )}
      {aviso && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{aviso}</p>
      )}

      {factores === null || rubros === null ? (
        <p className="flex items-center gap-2 text-sm text-ink-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
        </p>
      ) : (
        <>
          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-ink-900">Factores</h2>
              {esAdmin && (
                <button
                  onClick={() => void guardarFactores()}
                  disabled={guardando !== null}
                  className="inline-flex h-9 items-center gap-1.5 rounded-md bg-brand px-3 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-60"
                >
                  {guardando === "factores" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Guardar factores
                </button>
              )}
            </div>
            <div className="overflow-x-auto rounded-lg border border-ink-100">
              <table className="w-full text-sm">
                <thead className="bg-ink-50 text-left text-[11px] uppercase tracking-wide text-ink-500">
                  <tr>
                    <th className="px-3 py-2">Tipo</th>
                    {PROCEDENCIAS.map((p) => (
                      <th key={p} className="px-3 py-2 text-right" colSpan={2}>{p}</th>
                    ))}
                  </tr>
                  <tr className="text-[10px] normal-case tracking-normal text-ink-400">
                    <th />
                    {PROCEDENCIAS.map((p) => (
                      <Fragment key={p}>
                        <th className="px-3 pb-1 text-right font-normal">Factor</th>
                        <th className="px-3 pb-1 text-right font-normal">Margen</th>
                      </Fragment>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {tipos.map((tipo) => (
                    <tr key={tipo} className="border-t border-ink-100">
                      <td className="px-3 py-2 font-medium text-ink-800">{tipo}</td>
                      {PROCEDENCIAS.map((p) => {
                        const f = factorDe(tipo, p);
                        return (
                          <Fragment key={`${tipo}-${p}`}>
                            <td className="px-3 py-1.5 text-right">
                              <input
                                type="number" step="0.01" min="1.01" max="10"
                                className={campoCls}
                                disabled={!esAdmin}
                                value={f?.factor ?? ""}
                                onChange={(e) => setFactor(tipo, p, "factor", e.target.value)}
                              />
                            </td>
                            <td className="px-3 py-1.5 text-right tabular-nums text-ink-500">
                              {margen(f?.factor ?? 0)}
                            </td>
                          </Fragment>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="text-[12px] text-ink-400">
              Margen = (factor − 1) / factor. Un factor de 1,78 deja 43,8 %; uno de 1,33 no puede pasar de 24,8 %.
            </p>
          </section>

          <section className="space-y-3">
            <div className="flex items-center justify-between">
              <h2 className="text-base font-semibold text-ink-900">Rubros</h2>
              {esAdmin && (
                <button
                  onClick={() => void guardarRubros()}
                  disabled={guardando !== null}
                  className="inline-flex h-9 items-center gap-1.5 rounded-md bg-brand px-3 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-60"
                >
                  {guardando === "rubros" ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Guardar rubros
                </button>
              )}
            </div>
            <div className="overflow-x-auto rounded-lg border border-ink-100">
              <table className="w-full text-sm">
                <thead className="bg-ink-50 text-left text-[11px] uppercase tracking-wide text-ink-500">
                  <tr>
                    <th className="px-3 py-2">Rubro</th>
                    <th className="px-3 py-2">Tipo</th>
                    <th className="px-3 py-2">Procedencia forzada</th>
                    <th className="px-3 py-2">Editado</th>
                  </tr>
                </thead>
                <tbody>
                  {rubros.map((r) => (
                    <tr key={r.rubro} className="border-t border-ink-100">
                      <td className="px-3 py-1.5 font-mono text-[12px] text-ink-700">{r.rubro}</td>
                      <td className="px-3 py-1.5">
                        <select
                          className="h-8 rounded-md border border-ink-200 px-2 text-sm outline-none focus:border-brand disabled:bg-ink-50 disabled:text-ink-500"
                          disabled={!esAdmin}
                          value={r.tipo ?? ""}
                          onChange={(e) => setRubro(r.rubro, "tipo", e.target.value)}
                        >
                          <option value="">(sin tipo)</option>
                          {Array.from(new Set([...tipos, "Sugerido", r.tipo ?? ""].filter(Boolean))).sort().map((t) => (
                            <option key={t} value={t}>{t}</option>
                          ))}
                        </select>
                      </td>
                      <td className="px-3 py-1.5">
                        <select
                          className="h-8 rounded-md border border-ink-200 px-2 text-sm outline-none focus:border-brand disabled:bg-ink-50 disabled:text-ink-500"
                          disabled={!esAdmin}
                          value={r.procedencia_forzada ?? ""}
                          onChange={(e) => setRubro(r.rubro, "procedencia_forzada", e.target.value)}
                        >
                          <option value="">(por compras / maestro)</option>
                          {PROCEDENCIAS.map((p) => <option key={p} value={p}>{p}</option>)}
                        </select>
                      </td>
                      <td className="px-3 py-1.5 text-[12px] text-ink-500">
                        {r.actualizado_por ?? "—"}{r.actualizado_en ? ` · ${r.actualizado_en.slice(0, 10)}` : ""}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        </>
      )}
    </div>
  );
}
