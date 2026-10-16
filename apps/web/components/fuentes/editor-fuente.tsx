"use client";

// Editor de una fuente. Nada se aplica hasta la corrida siguiente del motor.
//
// Las listas (carpeta, subcarpeta, archivos) salen del ultimo listado del PC
// titular. Mientras se edita se pide la vista previa al servidor, que corre la
// misma regla del motor: "Con este cambio el motor tomaria X. Hoy toma Y." Los
// conflictos salen en rojo y con ellos el servidor no deja guardar (422).
// Los patrones crudos y las exclusiones van plegados en "Avanzado".
import { useEffect, useMemo, useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import {
  ErrorFuentes,
  MODOS_ELECCION,
  archivosEnUbicacion,
  cambiosFuente,
  extensiones,
  fechaHora,
  formDesde,
  fuentesApi,
  lineas,
  nombrePc,
  plazoDe,
  type ArchivoCarpeta,
  type ArchivosCarpeta,
  type CarpetaCfg,
  type FormFuente,
  type FuenteDetalle,
  type Guardado,
  type VistaPrevia,
} from "@/lib/fuentes-datos";
import { MensajeError } from "./comun";

interface Props {
  detalle: FuenteDetalle | null;
  carpetas: CarpetaCfg[];
  /** Version vigente: si otro admin guardo despues, el servidor responde 409. */
  version: number;
  onClose: () => void;
  onGuardado: (g: Guardado, texto?: string) => void | Promise<void>;
  /** Tras un 409: cierra y vuelve a cargar todo. */
  onRecargar: () => void;
}

const MANO = "__a_mano__";

export function EditorFuente({ detalle, carpetas, version, onClose, onGuardado, onRecargar }: Props) {
  if (!detalle) return null;
  return (
    <EditorAbierto
      key={`${detalle.clave}-${detalle.version}`}
      detalle={detalle}
      carpetas={carpetas}
      version={version}
      onClose={onClose}
      onGuardado={onGuardado}
      onRecargar={onRecargar}
    />
  );
}

function EditorAbierto({ detalle, carpetas, version, onClose, onGuardado, onRecargar }: Props & { detalle: FuenteDetalle }) {
  const original = detalle.config;
  const [form, setForm] = useState<FormFuente>(() => formDesde(original));
  const [listados, setListados] = useState<Record<string, ArchivosCarpeta | null>>({});
  const [vista, setVista] = useState<VistaPrevia | null>(null);
  const [errorVista, setErrorVista] = useState<string | null>(null);
  const [calculando, setCalculando] = useState(false);
  const [nota, setNota] = useState("");
  const [errorNota, setErrorNota] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [conflicto, setConflicto] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [aMano, setAMano] = useState(false);

  const bloqueos = detalle.bloqueos;
  const enPrueba = detalle.modo === "prueba";
  const modos = (detalle.catalogo?.modos ?? ["archivo_exacto", "mas_reciente"]).filter((m) => m in MODOS_ELECCION);
  const plazo = plazoDe(form);
  const cambios = useMemo(() => cambiosFuente(original, form), [original, form]);
  const claveCambios = JSON.stringify(cambios);
  const hayCambios = Object.keys(cambios).length > 0;
  const activas = carpetas.filter((c) => c.activa || form.ubicaciones.some((u) => u.carpeta === c.clave));
  const nombreCarpeta = (c: string) => carpetas.find((x) => x.clave === c)?.nombre ?? c;

  const set = <K extends keyof FormFuente>(k: K, v: FormFuente[K]) => {
    setForm((f) => ({ ...f, [k]: v }));
    setError(null);
    setConflicto(false);
  };
  const setUbicacion = (i: number, cambio: Partial<FormFuente["ubicaciones"][number]>) =>
    set("ubicaciones", form.ubicaciones.map((u, j) => (j === i ? { ...u, ...cambio } : u)));

  // Listado de cada carpeta en uso (una vez por carpeta), para armar los selectores.
  const carpetasEnUso = Array.from(new Set(form.ubicaciones.map((u) => u.carpeta).filter(Boolean)));
  const claveCarpetas = carpetasEnUso.join("|");
  useEffect(() => {
    for (const c of carpetasEnUso) {
      if (c in listados) continue;
      setListados((l) => ({ ...l, [c]: null }));
      fuentesApi
        .archivosCarpeta(c)
        .then((r) => setListados((l) => ({ ...l, [c]: r })))
        .catch(() => setListados((l) => ({ ...l, [c]: { clave: c, nombre: null, pc: null, alias: null, existe: false, truncado: false, subcarpetas: [], archivos: [] } })));
    }
    // claveCarpetas resume carpetasEnUso; listados se mira adentro para no repetir pedidos.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claveCarpetas]);

  // Archivos que caen en las ubicaciones elegidas (para "Siempre este archivo" y
  // para proponer un patron).
  const exts = extensiones(form.extensiones);
  const archivos: { carpeta: string; a: ArchivoCarpeta }[] = [];
  for (const u of form.ubicaciones) {
    const l = listados[u.carpeta];
    if (!l) continue;
    for (const a of archivosEnUbicacion(l.archivos, u, exts)) archivos.push({ carpeta: u.carpeta, a });
  }
  const nombresArchivos = Array.from(new Set(archivos.map((x) => x.a.nombre))).sort((x, y) => x.localeCompare(y, "es"));
  const listadoDe = Object.values(listados).find((l) => l?.iniciada_en);

  // Vista previa: se pide sola mientras se edita, con una pausa para no pedir una por tecla.
  useEffect(() => {
    if (plazo.error) {
      setVista(null);
      setCalculando(false);
      return;
    }
    let vigente = true;
    setCalculando(true);
    const t = setTimeout(() => {
      fuentesApi
        .vistaPrevia(detalle.clave, cambios)
        .then((v) => {
          if (!vigente) return;
          setVista(v);
          setErrorVista(null);
        })
        .catch((e) => {
          if (!vigente) return;
          setVista(null);
          setErrorVista(e instanceof Error ? e.message : "No se pudo calcular qué archivo tomaría.");
        })
        .finally(() => {
          if (vigente) setCalculando(false);
        });
    }, 400);
    return () => {
      vigente = false;
      clearTimeout(t);
    };
    // claveCambios resume `cambios`: pedirla por referencia la repetiria en cada render.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [claveCambios, plazo.error, detalle.clave]);

  const cerrar = () => {
    if (guardando) return;
    if ((hayCambios || nota.trim()) && !window.confirm("Hay cambios sin guardar. ¿Cerrar igual?")) return;
    onClose();
  };

  const guardar = async () => {
    if (!nota.trim()) {
      setErrorNota("Escribe una nota: qué cambias y por qué. Queda en el historial de la fuente.");
      return;
    }
    if (plazo.error) {
      setError(plazo.error);
      return;
    }
    if (!hayCambios) {
      setError("No hay cambios para guardar.");
      return;
    }
    setGuardando(true);
    setError(null);
    setConflicto(false);
    try {
      const g = await fuentesApi.guardar(detalle.clave, cambios, nota.trim(), version);
      await onGuardado(
        g,
        `${form.nombre.trim() || detalle.nombre}: guardado como versión ${g.version}. Rige desde la próxima corrida del motor.`
      );
    } catch (e) {
      setConflicto(e instanceof ErrorFuentes && e.status === 409);
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setGuardando(false);
    }
  };

  const radio = "h-4 w-4 accent-brand";

  return (
    <Dialog open onClose={cerrar} title={`Editar: ${detalle.nombre}`} description="Nada cambia hasta la próxima corrida del motor." className="max-w-3xl">
      <div className="space-y-5 text-[13px] text-ink-700">
        <fieldset className="space-y-2">
          <legend className="mb-1 text-[14px] font-semibold text-ink-900">Dónde busca</legend>
          {form.ubicaciones.map((u, i) => {
            const l = listados[u.carpeta];
            const subs = Array.from(new Set(["", ...(l?.subcarpetas ?? []), u.subcarpeta]));
            return (
              <div key={i} className="grid items-end gap-2 rounded-sm border border-ink-200 p-2 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto_auto]">
                <div>
                  <Label htmlFor={`carpeta-${i}`}>Carpeta</Label>
                  <select
                    id={`carpeta-${i}`}
                    className="h-9 w-full rounded-sm border border-ink-200 bg-white px-2 text-[13px]"
                    value={u.carpeta}
                    onChange={(e) => setUbicacion(i, { carpeta: e.target.value, subcarpeta: "" })}
                  >
                    {/* La de hoy va siempre, aunque la configuracion no haya cargado. */}
                    {Array.from(new Set([...activas.map((c) => c.clave), u.carpeta])).map((c) => (
                      <option key={c} value={c}>{nombreCarpeta(c)}</option>
                    ))}
                  </select>
                </div>
                <div>
                  <Label htmlFor={`subcarpeta-${i}`}>Subcarpeta</Label>
                  <select
                    id={`subcarpeta-${i}`}
                    className="h-9 w-full rounded-sm border border-ink-200 bg-white px-2 text-[13px]"
                    value={u.subcarpeta}
                    onChange={(e) => setUbicacion(i, { subcarpeta: e.target.value })}
                  >
                    {subs.map((s) => (
                      <option key={s || "(raiz)"} value={s}>{s ? s.split("/").join(" › ") : "(toda la carpeta)"}</option>
                    ))}
                  </select>
                </div>
                <label className="flex h-9 items-center gap-1.5 whitespace-nowrap">
                  <input type="checkbox" checked={u.recursiva} onChange={(e) => setUbicacion(i, { recursiva: e.target.checked })} />
                  Incluir subcarpetas
                </label>
                <Button
                  variant="ghost"
                  size="sm"
                  aria-label={`Quitar ${nombreCarpeta(u.carpeta)}`}
                  disabled={form.ubicaciones.length <= 1}
                  onClick={() => set("ubicaciones", form.ubicaciones.filter((_, j) => j !== i))}
                >
                  <X className="h-4 w-4" aria-hidden="true" />
                </Button>
                {l && !l.existe && l.pc && (
                  <p className="text-[12px] text-amber-800 sm:col-span-4">
                    {nombrePc(l.pc, l.alias)} no tiene esta carpeta en su último listado.
                  </p>
                )}
              </div>
            );
          })}
          {activas.length > 0 && (
            <Button
              variant="outline"
              size="sm"
              onClick={() => set("ubicaciones", [...form.ubicaciones, { carpeta: activas[0].clave, subcarpeta: "", recursiva: false }])}
            >
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Agregar otra carpeta
            </Button>
          )}
          {form.ubicaciones.length > 1 && (
            <p className="text-[12px] text-ink-500">Si el archivo está en varias carpetas, gana el más reciente.</p>
          )}
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="mb-1 text-[14px] font-semibold text-ink-900">Cómo elegir el archivo</legend>
          {bloqueos.modo && <p className="text-[12px] text-ink-500">{bloqueos.modo}</p>}
          <div className="space-y-1.5">
            {modos.map((m) => (
              <label key={m} className="flex items-center gap-2">
                <input
                  type="radio"
                  name="modo"
                  className={radio}
                  checked={form.modo === m}
                  disabled={!!bloqueos.modo}
                  onChange={() => set("modo", m)}
                />
                {MODOS_ELECCION[m]}
              </label>
            ))}
          </div>

          {form.modo === "archivo_exacto" && (
            <div className="pl-6">
              <Label htmlFor="nombre-archivo">Archivo</Label>
              {nombresArchivos.length > 0 && !aMano ? (
                <select
                  id="nombre-archivo"
                  className="h-9 w-full rounded-sm border border-ink-200 bg-white px-2 text-[13px]"
                  value={form.nombre_archivo}
                  onChange={(e) => {
                    if (e.target.value === MANO) setAMano(true);
                    else set("nombre_archivo", e.target.value);
                  }}
                >
                  <option value="">Elige un archivo…</option>
                  {Array.from(new Set([...nombresArchivos, form.nombre_archivo].filter(Boolean))).map((n) => (
                    <option key={n} value={n}>{n}</option>
                  ))}
                  <option value={MANO}>Escribir el nombre a mano…</option>
                </select>
              ) : (
                <Input
                  id="nombre-archivo"
                  value={form.nombre_archivo}
                  maxLength={100}
                  placeholder="Stock bodegas.xlsx"
                  onChange={(e) => set("nombre_archivo", e.target.value)}
                />
              )}
              <p className="mt-1 text-[12px] text-ink-500">El nombre completo, con la extensión. Mayúsculas y tildes dan lo mismo.</p>
            </div>
          )}

          {form.modo === "mas_reciente" && (
            <div className="space-y-2 pl-6">
              <p>
                Busca nombres como:{" "}
                {lineas(form.incluye).length === 0 ? (
                  <span className="text-rose-700">(ninguno todavía)</span>
                ) : (
                  lineas(form.incluye).map((p) => (
                    <code key={p} className="mr-1 rounded-sm bg-paper-100 px-1 font-mono text-[12px] text-accent-700">{p}</code>
                  ))
                )}
              </p>
              {archivos.length > 0 && (
                <div>
                  <Label htmlFor="proponer">Proponer a partir de un archivo de la carpeta</Label>
                  <select
                    id="proponer"
                    className="h-9 w-full rounded-sm border border-ink-200 bg-white px-2 text-[13px]"
                    value=""
                    onChange={(e) => e.target.value && set("incluye", e.target.value)}
                  >
                    <option value="">Elige un archivo…</option>
                    {archivos.map(({ carpeta, a }) => (
                      <option key={`${carpeta}/${a.ruta_relativa}`} value={a.patron_propuesto}>
                        {a.nombre} ({fechaHora(a.modificado_en)}) → {a.patron_propuesto}
                      </option>
                    ))}
                  </select>
                </div>
              )}
              <p className="text-[12px] text-ink-500">
                El asterisco (*) reemplaza cualquier texto: las fechas y los números del nombre quedan como comodín.
                Si varios archivos calzan, gana el más reciente. Los patrones se editan en «Avanzado».
              </p>
            </div>
          )}

          {form.modo === "por_descarte" && (
            <p className="pl-6 text-[12.5px] text-ink-600">
              Toma los .xlsx cuyo nombre lleva el año en curso o el anterior y que no son de ninguna otra fuente. El motor
              además revisa que tengan forma de respaldo de venta.
            </p>
          )}
        </fieldset>

        <fieldset className="space-y-2">
          <legend className="mb-1 text-[14px] font-semibold text-ink-900">Plazo</legend>
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="frecuencia">Se actualiza cada</label>
            <Input
              id="frecuencia"
              type="number"
              inputMode="numeric"
              min={1}
              max={detalle.catalogo?.frecuencia_max ?? 365}
              className="w-20"
              value={form.frecuencia_dias}
              disabled={form.sin_plazo}
              aria-invalid={!!plazo.error}
              aria-describedby="frecuencia-ayuda"
              onChange={(e) => set("frecuencia_dias", e.target.value)}
            />
            <span>días hábiles</span>
            <label className="ml-2 flex items-center gap-1.5">
              <input
                type="checkbox"
                checked={form.sin_plazo}
                disabled={!!bloqueos.frecuencia_dias}
                onChange={(e) => set("sin_plazo", e.target.checked)}
              />
              Sin plazo
            </label>
          </div>
          <div id="frecuencia-ayuda">
            {plazo.error && <p className="text-[12px] text-rose-700">{plazo.error}</p>}
            {bloqueos.frecuencia_dias && <p className="text-[12px] text-ink-500">{bloqueos.frecuencia_dias}</p>}
          </div>
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1">
            <span>Si se atrasa:</span>
            {(["frena", "avisa"] as const).map((v) => (
              <label key={v} className="flex items-center gap-1.5">
                <input
                  type="radio"
                  name="al_vencer"
                  className={radio}
                  checked={form.al_vencer === v}
                  disabled={!!bloqueos.al_vencer || form.sin_plazo}
                  onChange={() => set("al_vencer", v)}
                />
                {v === "frena" ? "Frenar la publicación" : "Solo avisar"}
              </label>
            ))}
          </div>
          {bloqueos.al_vencer && <p className="text-[12px] text-ink-500">{bloqueos.al_vencer}</p>}
          <label className="flex items-center gap-1.5">
            <input
              type="checkbox"
              checked={form.obligatoria}
              disabled={!!bloqueos.obligatoria}
              onChange={(e) => set("obligatoria", e.target.checked)}
            />
            Obligatoria: si falta, el sugerido no se publica{enPrueba ? " (solo cuando la configuración esté activa)" : ""}
          </label>
          {bloqueos.obligatoria && <p className="text-[12px] text-ink-500">{bloqueos.obligatoria}</p>}
          <p className="text-[12.5px] text-ink-500">Hoja y fila: {detalle.hoja_texto}</p>
        </fieldset>

        <details className="rounded-sm border border-ink-200 px-3 py-2">
          <summary className="cursor-pointer font-medium text-ink-800">Avanzado</summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label htmlFor="nombre-fuente">Nombre de la fuente</Label>
              <Input id="nombre-fuente" value={form.nombre} maxLength={100} onChange={(e) => set("nombre", e.target.value)} />
            </div>
            <div>
              <Label htmlFor="incluye">Patrones (uno por línea)</Label>
              <Textarea id="incluye" rows={4} className="font-mono text-[12.5px]" value={form.incluye} onChange={(e) => set("incluye", e.target.value)} />
            </div>
            <div>
              <Label htmlFor="excluye">Exclusiones (uno por línea)</Label>
              <Textarea id="excluye" rows={4} className="font-mono text-[12.5px]" value={form.excluye} onChange={(e) => set("excluye", e.target.value)} />
            </div>
            <div>
              <Label htmlFor="extensiones">Extensiones</Label>
              <Input id="extensiones" className="font-mono" value={form.extensiones} onChange={(e) => set("extensiones", e.target.value)} />
            </div>
            <div>
              <label className="mt-6 flex items-center gap-1.5">
                <input
                  type="checkbox"
                  checked={form.activa}
                  disabled={!!bloqueos.activa}
                  onChange={(e) => set("activa", e.target.checked)}
                />
                Activa (si se desactiva, el motor no la busca)
              </label>
              {bloqueos.activa && <p className="text-[12px] text-ink-500">{bloqueos.activa}</p>}
            </div>
          </div>
        </details>

        <section aria-label="Vista previa" className="space-y-1.5 rounded-sm border border-ink-200 bg-paper-50 p-3">
          <h3 className="text-[14px] font-semibold text-ink-900">Vista previa</h3>
          {calculando && (
            <p className="flex items-center gap-2 text-ink-500">
              <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> Calculando qué archivo tomaría…
            </p>
          )}
          {errorVista && !calculando && <p className="text-rose-700">{errorVista}</p>}
          {vista && !calculando && (
            <>
              <p className="font-medium text-ink-900">{vista.elegiria.texto}</p>
              <p className="text-ink-600">{vista.hoy_toma.texto}</p>
              {vista.conflictos.map((c) => (
                <p key={c} role="alert" className="text-rose-700">{c}</p>
              ))}
              {vista.avisos.map((a) => (
                <p key={a} className="text-amber-800">{a}</p>
              ))}
              {vista.listado && (
                <p className="text-[12px] text-ink-500">
                  Probado contra el listado de {nombrePc(vista.listado.pc, vista.listado.alias)} del {fechaHora(vista.listado.iniciada_en)}.
                </p>
              )}
            </>
          )}
          {!vista && !calculando && !errorVista && listadoDe == null && (
            <p className="text-ink-500">Sin listado del PC titular todavía.</p>
          )}
        </section>

        <div className="space-y-2">
          <div>
            <Label htmlFor="nota-fuente">Nota del cambio</Label>
            <Textarea
              id="nota-fuente"
              rows={2}
              maxLength={500}
              placeholder="Qué cambias y por qué"
              value={nota}
              aria-invalid={!!errorNota}
              onChange={(e) => {
                setNota(e.target.value);
                setErrorNota(null);
              }}
            />
            {errorNota && <p role="alert" className="mt-1 text-[12px] text-rose-700">{errorNota}</p>}
          </div>
          {enPrueba && (
            <label className="flex items-start gap-1.5">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={form.diferencia_esperada}
                onChange={(e) => set("diferencia_esperada", e.target.checked)}
              />
              <span>
                Es una diferencia esperada (ensayo): si con esto el motor toma otro archivo que el de hoy, la comparación no lo
                cuenta como error.
              </span>
            </label>
          )}
          {error && (
            <MensajeError>
              {error}
              {conflicto && (
                <button type="button" className="ml-2 font-semibold underline" onClick={onRecargar}>
                  Recargar
                </button>
              )}
            </MensajeError>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={cerrar} disabled={guardando}>
              Cancelar
            </Button>
            <Button onClick={() => void guardar()} disabled={guardando}>
              {guardando && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
              Guardar
            </Button>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
