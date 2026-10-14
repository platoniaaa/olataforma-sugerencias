"use client";

// La politica de precios: los factores por (tipo, procedencia) y el tipo de
// cada rubro.
//
// Desde el 14-10-2026 se puede crear un tipo y asignarselo a un rubro. Ese dia
// la politica dijo "el rubro 35 va con factor 1,88" y no se podia: el factor es
// por tipo, el rubro 35 compartia "Liviano" con otros 30 rubros, y cambiar
// "Liviano" movia los 31. Antes de guardar se ve que precios cambian, y se guarda
// todo junto con UN recalculo (antes eran dos botones y dos recalculos de ~5 min).
//
// La edita quien mantiene la lista de precios, no solo el admin (23-09-2026, a
// pedido del usuario): quien decide un precio fijo es quien sabe cuando hay que
// mover el factor. Lo que contiene el riesgo es la trazabilidad -cada cambio
// queda en la auditoria con el usuario y el valor anterior-, no el permiso.
// Quien no edita precios la ve igual, para entender de donde sale cada precio.
import { Fragment, useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, ArrowLeft, Loader2, Plus, Save, Sigma, X } from "lucide-react";
import { api } from "@/lib/api-client";
import { getPuedePrecios } from "@/lib/auth";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import {
  TIPO_NUEVO_VACIO,
  type TipoNuevoForm,
  cambioPolitica,
  errorTipoNuevo,
  factorValido,
  filasTipoNuevo,
} from "@/lib/politica-precios";
import type { PoliticaFactor, PoliticaRubro, ResultadoPolitica, VistaPreviaPolitica } from "@/lib/types";

const PROCEDENCIAS = ["Nacional", "Importado"] as const;

/** Margen que deja un factor: (F - 1) / F. Es lo que responde "¿cuanto gano?". */
function margen(factor: number): string {
  if (!factorValido(factor)) return "—";
  return `${formatoNumero(((factor - 1) / factor) * 100, 1)} %`;
}

const dosDecimales = (n: number | null | undefined) => (n == null ? "—" : formatoNumero(n, 2));

function resumenGuardado(r: ResultadoPolitica): string {
  if (!r.recalculo) return "Guardado. Ningún precio cambia con esto.";
  // Los precios, no "productos con cambios": el recalculo cuenta tambien el cambio
  // de tipo, y el numero no cuadraba con el que mostro la vista previa.
  const precios = r.recalculo.precios_distintos ?? r.recalculo.por_campo?.precio ?? 0;
  const partes = [`Guardado. Cambiaron ${formatoNumero(precios)} precios`];
  if (r.seguir_al_rubro.productos) {
    partes.push(`${formatoNumero(r.seguir_al_rubro.productos)} productos dejaron su tipo escrito a mano y siguen al rubro`);
  }
  return `${partes.join("; ")}. Los precios nuevos salen en el próximo "Solo diferencias".`;
}

export default function PoliticasPreciosPage() {
  const [factores, setFactores] = useState<PoliticaFactor[] | null>(null);
  const [rubros, setRubros] = useState<PoliticaRubro[] | null>(null);
  // Lo que vino del servidor: contra esto se mide que cambio.
  const [original, setOriginal] = useState<{ factores: PoliticaFactor[]; rubros: PoliticaRubro[] }>(
    { factores: [], rubros: [] },
  );
  const [tiposNuevos, setTiposNuevos] = useState<string[]>([]);
  const [seguir, setSeguir] = useState<string[]>([]);
  const [form, setForm] = useState<TipoNuevoForm>(TIPO_NUEVO_VACIO);
  const [errorNuevo, setErrorNuevo] = useState<string | null>(null);
  const [vista, setVista] = useState<VistaPreviaPolitica | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [errorVista, setErrorVista] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [puedeEditar, setPuedeEditar] = useState(false);

  useEffect(() => {
    setPuedeEditar(getPuedePrecios());
  }, []);

  const cargar = useCallback(async () => {
    try {
      const [f, r] = await Promise.all([api.politicaFactores(), api.politicaRubros()]);
      setFactores(f);
      setRubros(r);
      setOriginal({ factores: f, rubros: r });
      setTiposNuevos([]);
      setSeguir([]);
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

  const setFactor = (tipo: string, proc: string, valor: string) => {
    if (!factores) return;
    const num = valor.trim() === "" ? Number.NaN : Number(valor.replace(",", "."));
    const existe = factorDe(tipo, proc);
    const estaba = original.factores.some((f) => f.tipo === tipo && f.procedencia === proc);
    if (existe) {
      // Una celda que no existia y se vuelve a vaciar desaparece; una que existia
      // -o la de un tipo nuevo, que necesita las dos procedencias- queda vacia y
      // marcada como error hasta que se corrija. Borrarla dejaba guardar el tipo
      // con una sola procedencia y los productos de la otra sin precio.
      if (Number.isNaN(num) && !estaba && !tiposNuevos.includes(tipo)) {
        setFactores(factores.filter((f) => !(f.tipo === tipo && f.procedencia === proc)));
        return;
      }
      setFactores(factores.map((f) => (f.tipo === tipo && f.procedencia === proc ? { ...f, factor: num } : f)));
    } else if (!Number.isNaN(num)) {
      // La procedencia que le faltaba a un tipo: hereda el descuento de la otra.
      const hermano = factores.find((f) => f.tipo === tipo);
      setFactores([...factores, {
        tipo, procedencia: proc, factor: num, descuento_max: hermano?.descuento_max ?? null, margen_post: null,
      }]);
    }
  };

  const setRubro = (rubro: string, campo: "tipo" | "procedencia_forzada", valor: string) => {
    if (!rubros) return;
    setRubros(rubros.map((r) => (r.rubro === rubro ? { ...r, [campo]: valor || null } : r)));
  };

  const invalidos = useMemo(
    () => (factores ?? []).filter((f) => !factorValido(f.factor)),
    [factores],
  );

  const cambio = useMemo(
    () => cambioPolitica(factores ?? [], original.factores, rubros ?? [], original.rubros, seguir),
    [factores, rubros, original, seguir],
  );
  const hayCambios = cambio.factores.length > 0 || cambio.rubros.length > 0;
  const claveCambio = JSON.stringify(cambio);
  // Un tipo creado que ningun rubro usa todavia: guardarlo no mueve precios. El
  // 14-10-2026 se guardo asi y parecio que el cambio "no habia funcionado".
  // Solo cuando la vista previa confirma que no cambia ningun precio: un producto
  // puede tener ese tipo escrito a mano y si cambiar, aunque ningun rubro lo use.
  const tiposSinRubro = vista && !calculando && vista.cambian === 0
    ? tiposNuevos.filter((t) => !(rubros ?? []).some((r) => r.tipo === t))
    : [];

  // La vista previa se pide sola mientras se edita, con una pausa para no pedir
  // una por tecla. Corre la misma regla que el recalculo: lo que muestra es lo
  // que va a pasar al guardar.
  useEffect(() => {
    if (!puedeEditar || !hayCambios) {
      setVista(null);
      setErrorVista(null);
      setCalculando(false);
      return;
    }
    let vigente = true;
    setCalculando(true);
    const t = setTimeout(() => {
      api.vistaPreviaPolitica(cambio)
        .then((v) => {
          if (!vigente) return;
          setVista(v);
          setErrorVista(null);
        })
        .catch((e) => {
          if (!vigente) return;
          setVista(null);
          setErrorVista(e instanceof Error ? e.message : "No se pudo calcular qué cambia.");
        })
        .finally(() => {
          if (vigente) setCalculando(false);
        });
    }, 400);
    return () => {
      vigente = false;
      clearTimeout(t);
    };
    // claveCambio resume `cambio`: pedirla por referencia la repetiria en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claveCambio, puedeEditar]);

  function agregarTipo() {
    const problema = errorTipoNuevo(form, tipos);
    if (problema) {
      setErrorNuevo(problema);
      return;
    }
    const filas = filasTipoNuevo(form);
    setFactores([...(factores ?? []), ...filas]);
    setTiposNuevos([...tiposNuevos, filas[0].tipo]);
    setForm(TIPO_NUEVO_VACIO);
    setErrorNuevo(null);
    setAviso(`Tipo "${filas[0].tipo}" agregado. Asígnaselo a un rubro en la tabla de Rubros y guarda.`);
  }

  function quitarTipoNuevo(tipo: string) {
    setFactores((factores ?? []).filter((f) => f.tipo !== tipo));
    // Los rubros que ya lo tenian elegido vuelven a lo que decian.
    setRubros((rubros ?? []).map((r) =>
      r.tipo === tipo ? { ...r, tipo: original.rubros.find((o) => o.rubro === r.rubro)?.tipo ?? null } : r));
    setTiposNuevos(tiposNuevos.filter((t) => t !== tipo));
    setAviso(null);
  }

  function descartar() {
    setFactores(original.factores);
    setRubros(original.rubros);
    setTiposNuevos([]);
    setSeguir([]);
    setForm(TIPO_NUEVO_VACIO);
    setErrorNuevo(null);
    setAviso(null);
    setError(null);
  }

  // Guardar recalcula DENTRO de la peticion solo los productos que el cambio
  // puede mover (los que muestra la vista previa): un rubro son segundos; un
  // factor de un tipo que usan muchos rubros puede llegar a los ~5 minutos de la
  // lista entera. Mientras guarda la pantalla queda bloqueada: el 14-10-2026 un
  // rubro elegido durante el guardado se perdio al recargar, sin aviso.
  async function guardar() {
    if (invalidos.length) {
      setError(`Corrige el factor de ${invalidos.map((f) => `${f.tipo} / ${f.procedencia}`).join(", ")}: tiene que ser mayor que 1 y hasta 10.`);
      return;
    }
    if (!hayCambios) {
      setAviso("No hay cambios para guardar.");
      return;
    }
    const sinRubro = tiposSinRubro.length
      ? `${tiposSinRubro.map((t) => `"${t}"`).join(", ")} todavía no está en ningún rubro: guardarlo no cambia precios.\n\n`
      : "";
    const cuantos = vista && !calculando
      ? `Cambian ${formatoNumero(vista.cambian)} precios. Se recalculan ${formatoNumero(vista.productos_revisados)} productos, no la lista entera.\n\n`
      : "";
    const ok = confirm(
      `${sinRubro}${cuantos}` +
      "Mientras guarda, la pantalla queda bloqueada. No cierres la pestaña ni vuelvas a apretar Guardar.\n\n" +
      "El cambio queda registrado en Auditoría con tu nombre."
    );
    if (!ok) return;
    setGuardando(true);
    setError(null);
    setAviso(null);
    try {
      const r = await api.guardarPolitica(cambio);
      await cargar();
      setAviso(resumenGuardado(r));
    } catch (e) {
      // La respuesta pudo perderse con el servidor ya guardado (corte de red o de
      // Render): si lo que hay en el servidor ya es lo que se queria guardar, se
      // dice eso. El servidor guarda la politica y los precios juntos, asi que si
      // la politica esta, los precios tambien.
      try {
        const [f, r] = await Promise.all([api.politicaFactores(), api.politicaRubros()]);
        const pendiente = cambioPolitica(factores ?? [], f, rubros ?? [], r, []);
        if (!pendiente.factores.length && !pendiente.rubros.length) {
          await cargar();
          setAviso("El cambio quedó guardado, aunque la respuesta del servidor no llegó. Revisa los precios en la lista.");
          return;
        }
      } catch {
        // Sin servidor no hay como saberlo: queda el error de abajo.
      }
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setGuardando(false);
    }
  }

  const campoCls = "h-8 w-24 rounded-md border border-ink-200 px-2 text-right text-sm tabular-nums outline-none focus:border-brand disabled:bg-ink-50 disabled:text-ink-500";
  const inputForm = "mt-1 h-8 w-full rounded-md border border-ink-200 px-2 text-sm text-ink-900 outline-none focus:border-brand";
  const rubroCambio = (r: PoliticaRubro) => {
    const o = original.rubros.find((x) => x.rubro === r.rubro);
    return !o || (o.tipo ?? null) !== (r.tipo ?? null) || (o.procedencia_forzada ?? null) !== (r.procedencia_forzada ?? null);
  };

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
          de cada producto sale de su rubro, salvo que alguien lo haya escrito a mano. Para darle a
          un rubro un factor propio, crea un tipo y asígnaselo en la tabla de Rubros.
          {puedeEditar
            ? " Antes de guardar ves qué precios cambian. Cada cambio queda en Auditoría con tu nombre y el valor anterior."
            : " Tu usuario puede verla pero no editarla."}
        </p>
      </header>

      {guardando && (
        <p className="flex items-center gap-2 rounded-md border border-brand/30 bg-brand-50 px-3 py-2 text-sm text-ink-700">
          <Loader2 className="h-4 w-4 shrink-0 animate-spin text-brand" />
          Guardando y recalculando los productos afectados. Deja esta pestaña abierta.
        </p>
      )}

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
            <h2 className="text-base font-semibold text-ink-900">Factores</h2>
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
                  {tipos.map((tipo) => {
                    const nuevo = tiposNuevos.includes(tipo);
                    return (
                      <tr key={tipo} className={`border-t border-ink-100 ${nuevo ? "bg-emerald-50/60" : ""}`}>
                        <td className="px-3 py-2 font-medium text-ink-800">
                          <span className="inline-flex items-center gap-2">
                            {tipo}
                            {nuevo && (
                              <>
                                <span className="rounded bg-emerald-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-emerald-800">
                                  nuevo · sin guardar
                                </span>
                                <button
                                  type="button"
                                  onClick={() => quitarTipoNuevo(tipo)}
                                  disabled={guardando}
                                  aria-label={`Quitar el tipo nuevo ${tipo}`}
                                  className="rounded p-0.5 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
                                >
                                  <X className="h-3.5 w-3.5" />
                                </button>
                              </>
                            )}
                          </span>
                        </td>
                        {PROCEDENCIAS.map((p) => {
                          const f = factorDe(tipo, p);
                          const malo = f !== undefined && !factorValido(f.factor);
                          return (
                            <Fragment key={`${tipo}-${p}`}>
                              <td className="px-3 py-1.5 text-right">
                                <input
                                  type="number" step="0.01" min="1.01" max="10"
                                  aria-label={`Factor ${tipo} ${p}`}
                                  className={`${campoCls} ${malo ? "border-rose-400" : ""}`}
                                  disabled={!puedeEditar || guardando}
                                  value={f === undefined || Number.isNaN(f.factor) ? "" : f.factor}
                                  onChange={(e) => setFactor(tipo, p, e.target.value)}
                                />
                              </td>
                              <td className="px-3 py-1.5 text-right tabular-nums text-ink-500">
                                {margen(f?.factor ?? 0)}
                              </td>
                            </Fragment>
                          );
                        })}
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
            <p className="text-[12px] text-ink-400">
              Margen = (factor − 1) / factor. Un factor de 1,78 deja 43,8 %; uno de 1,33 no puede pasar de 24,8 %.
            </p>

            {puedeEditar && (
              <div className="rounded-lg border border-dashed border-ink-200 p-3">
                <p className="text-sm font-medium text-ink-800">Agregar tipo</p>
                <p className="mb-2 text-[12px] text-ink-500">
                  Para un factor que no comparte ningún tipo de hoy. Después asígnaselo a uno o más rubros en la tabla de Rubros.
                </p>
                <div className="grid items-end gap-2 sm:grid-cols-[minmax(0,1.6fr)_repeat(3,minmax(0,1fr))_auto]">
                  <label className="text-[12px] text-ink-500">
                    Nombre del tipo
                    <input
                      className={inputForm} value={form.nombre} placeholder="Rubro 35" maxLength={40}
                      disabled={guardando} onChange={(e) => { setForm({ ...form, nombre: e.target.value }); setErrorNuevo(null); }}
                    />
                  </label>
                  <label className="text-[12px] text-ink-500">
                    Factor nacional
                    <input
                      className={`${inputForm} text-right tabular-nums`} inputMode="decimal" value={form.nacional} placeholder="1,88"
                      disabled={guardando} onChange={(e) => { setForm({ ...form, nacional: e.target.value }); setErrorNuevo(null); }}
                    />
                  </label>
                  <label className="text-[12px] text-ink-500">
                    Factor importado
                    <input
                      className={`${inputForm} text-right tabular-nums`} inputMode="decimal" value={form.importado} placeholder="1,88"
                      disabled={guardando} onChange={(e) => { setForm({ ...form, importado: e.target.value }); setErrorNuevo(null); }}
                    />
                  </label>
                  <label className="text-[12px] text-ink-500">
                    Descuento máx. %
                    <input
                      className={`${inputForm} text-right tabular-nums`} inputMode="decimal" value={form.descuento} placeholder="20"
                      disabled={guardando} onChange={(e) => { setForm({ ...form, descuento: e.target.value }); setErrorNuevo(null); }}
                    />
                  </label>
                  <button
                    type="button"
                    onClick={agregarTipo}
                    disabled={guardando}
                    className="inline-flex h-8 items-center gap-1.5 rounded-md border border-ink-200 bg-white px-3 text-sm font-medium text-ink-800 hover:bg-ink-50 disabled:opacity-60"
                  >
                    <Plus className="h-4 w-4" /> Agregar tipo
                  </button>
                </div>
                {errorNuevo && <p role="alert" className="mt-2 text-[12px] text-rose-700">{errorNuevo}</p>}
              </div>
            )}
          </section>

          <section className="space-y-3">
            <h2 className="text-base font-semibold text-ink-900">Rubros</h2>
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
                    <tr key={r.rubro} className={`border-t border-ink-100 ${rubroCambio(r) ? "bg-brand-50/60" : ""}`}>
                      <td className="px-3 py-1.5 font-mono text-[12px] text-ink-700">{r.rubro}</td>
                      <td className="px-3 py-1.5">
                        <select
                          aria-label={`Tipo del rubro ${r.rubro}`}
                          className="h-8 rounded-md border border-ink-200 px-2 text-sm outline-none focus:border-brand disabled:bg-ink-50 disabled:text-ink-500"
                          disabled={!puedeEditar || guardando}
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
                          aria-label={`Procedencia forzada del rubro ${r.rubro}`}
                          className="h-8 rounded-md border border-ink-200 px-2 text-sm outline-none focus:border-brand disabled:bg-ink-50 disabled:text-ink-500"
                          disabled={!puedeEditar || guardando}
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

          {puedeEditar && (hayCambios || invalidos.length > 0) && (
            <section
              aria-label="Cambios sin guardar"
              className="sticky bottom-0 z-10 -mx-6 max-h-[55vh] space-y-3 overflow-y-auto border-t border-ink-200 bg-white px-6 py-4"
            >
              <h2 className="text-base font-semibold text-ink-900">Qué cambia al guardar</h2>

              {invalidos.length > 0 && (
                <p className="text-sm text-rose-700">
                  Factor fuera de rango en {invalidos.map((f) => `${f.tipo} / ${f.procedencia}`).join(", ")}: tiene que ser mayor que 1 y hasta 10.
                </p>
              )}
              {tiposSinRubro.length > 0 && (
                <p className="text-sm text-amber-700">
                  {tiposSinRubro.map((t) => `"${t}"`).join(", ")} todavía no está en ningún rubro. Elígelo en la
                  tabla de Rubros antes de guardar: guardarlo solo no cambia ningún precio.
                </p>
              )}
              {calculando && (
                <p className="flex items-center gap-2 text-sm text-ink-500">
                  <Loader2 className="h-4 w-4 animate-spin" /> Calculando qué precios cambian…
                </p>
              )}
              {errorVista && !calculando && <p className="text-sm text-rose-700">{errorVista}</p>}

              {vista && !calculando && (
                <div className="space-y-3 text-sm text-ink-700">
                  <p className="font-medium text-ink-900">
                    {vista.cambian === 0
                      ? "Ningún precio cambia con esto."
                      : `${formatoNumero(vista.cambian)} productos cambian de precio: ${formatoNumero(vista.suben)} suben y ${formatoNumero(vista.bajan)} bajan` +
                        (vista.variacion_mediana != null
                          ? `, en general ${vista.variacion_mediana >= 0 ? "+" : ""}${formatoNumero(vista.variacion_mediana * 100, 1)} %.`
                          : ".")}
                  </p>

                  {vista.rubros.map((r) => {
                    const manuales = r.manuales.reduce((s, m) => s + m.productos, 0);
                    const procs = PROCEDENCIAS.filter((p) => (r.procedencias[p] ?? 0) > 0);
                    return (
                      <div key={r.rubro} className="rounded-md border border-ink-100 bg-ink-50/60 p-3">
                        <p className="font-medium text-ink-900">
                          Rubro {r.rubro}: {r.tipo_antes ?? "(sin tipo)"} → {r.tipo_despues ?? "(sin tipo)"}
                        </p>
                        <p>
                          {formatoNumero(r.productos)} productos; {formatoNumero(r.siguen_al_rubro)} toman el tipo del rubro
                          {r.cambian ? ` y ${formatoNumero(r.cambian)} cambian de precio` : ""}.
                        </p>
                        {procs.map((p) => (
                          <p key={p} className={r.factor_despues[p] == null ? "text-amber-700" : ""}>
                            Factor {p.toLowerCase()} ({formatoNumero(r.procedencias[p])} productos): {dosDecimales(r.factor_antes[p])} →{" "}
                            {r.factor_despues[p] == null
                              ? "sin factor: quedarían sin precio (SIN REVISION)"
                              : dosDecimales(r.factor_despues[p])}
                          </p>
                        ))}
                        {manuales > 0 && (
                          <label className="mt-2 flex items-start gap-2 text-ink-800">
                            <input
                              type="checkbox"
                              className="mt-0.5"
                              checked={seguir.includes(r.rubro)}
                              disabled={guardando}
                              onChange={(e) =>
                                setSeguir(e.target.checked ? [...seguir, r.rubro] : seguir.filter((x) => x !== r.rubro))}
                            />
                            <span>
                              Que también sigan al rubro los {formatoNumero(manuales)} con tipo escrito a mano
                              ({r.manuales.map((m) => `${m.tipo}: ${formatoNumero(m.productos)}`).join(", ")};{" "}
                              {formatoNumero(r.manuales_con_precio)} con precio). Si no, se quedan con el factor de su tipo.
                            </span>
                          </label>
                        )}
                        {(r.por_glosa > 0 || r.decididos > 0) && (
                          <p className="mt-1 text-[12px] text-ink-500">
                            No cambian
                            {r.por_glosa > 0 ? ` ${formatoNumero(r.por_glosa)} neumáticos (por su glosa)` : ""}
                            {r.por_glosa > 0 && r.decididos > 0 ? " ni" : ""}
                            {r.decididos > 0 ? ` ${formatoNumero(r.decididos)} con precio fijo, congelado o margen fijo` : ""}.
                          </p>
                        )}
                      </div>
                    );
                  })}

                  {vista.ejemplos.length > 0 && (
                    <div>
                      <p className="text-[12px] text-ink-500">Por ejemplo:</p>
                      <ul className="text-[13px] tabular-nums">
                        {vista.ejemplos.map((e) => (
                          <li key={e.producto}>
                            <span className="font-mono">{e.producto}</span>
                            {e.glosa ? ` · ${e.glosa}` : ""}: {formatoCLP(e.precio_antes)} → {formatoCLP(e.precio_despues)}
                          </li>
                        ))}
                      </ul>
                    </div>
                  )}
                </div>
              )}

              <div className="flex flex-wrap items-center gap-2 pt-1">
                <button
                  type="button"
                  onClick={() => void guardar()}
                  disabled={guardando}
                  className="inline-flex h-9 items-center gap-1.5 rounded-md bg-brand px-3 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-60"
                >
                  {guardando ? <Loader2 className="h-4 w-4 animate-spin" /> : <Save className="h-4 w-4" />}
                  Guardar cambios
                </button>
                <button
                  type="button"
                  onClick={descartar}
                  disabled={guardando}
                  className="inline-flex h-9 items-center rounded-md border border-ink-200 px-3 text-sm text-ink-700 hover:bg-ink-50 disabled:opacity-60"
                >
                  Descartar
                </button>
              </div>
            </section>
          )}
        </>
      )}
    </div>
  );
}
