"use client";

// Detalle de una fuente: como elige el archivo, que archivos compiten entre
// carpetas, los descartados, las ultimas 20 corridas y las versiones que la
// cambiaron, con "Volver a esta versión". La ruta absoluta (trae el usuario de
// Windows) se ve solo aca.
import { useCallback, useEffect, useState } from "react";
import { Pencil } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatoNumero } from "@/lib/formato";
import {
  MODOS_ELECCION,
  TEXTO_PRUEBA,
  TEXTO_TIPO_CORRIDA,
  cuando,
  fechaHora,
  fuentesApi,
  nombrePc,
  tamano,
  textoPlazo,
  type CarpetaCfg,
  type FuenteDetalle,
  type Guardado,
  type Version,
} from "@/lib/fuentes-datos";
import { Cargando, DialogoNota, MensajeError, NivelBadge } from "./comun";

interface Props {
  clave: string | null;
  ahora: string;
  /** Version vigente (la del panel): contra ella se revierte. */
  version: number;
  carpetas: CarpetaCfg[];
  /** Cambia cada vez que se guarda algo: vuelve a pedir el detalle. */
  recarga: number;
  onClose: () => void;
  onEditar: (d: FuenteDetalle) => void;
  onGuardado: (g: Guardado, texto?: string) => void | Promise<void>;
}

export function DetalleFuente({ clave, ahora, version, carpetas, recarga, onClose, onEditar, onGuardado }: Props) {
  const [detalle, setDetalle] = useState<FuenteDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revertir, setRevertir] = useState<Version | null>(null);

  const cargar = useCallback(async (c: string) => {
    setError(null);
    try {
      setDetalle(await fuentesApi.detalle(c));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la fuente.");
    }
  }, []);

  useEffect(() => {
    setDetalle(null);
    if (clave) void cargar(clave);
  }, [clave, recarga, cargar]);

  const nombreCarpeta = (c: string) => carpetas.find((x) => x.clave === c)?.nombre ?? c;
  const d = detalle;

  return (
    <Dialog open={!!clave} onClose={onClose} title={d?.nombre ?? "Fuente"} className="max-w-4xl">
      {error && <MensajeError>{error}</MensajeError>}
      {!d && !error && <Cargando />}
      {d && (
        <div className="space-y-5 text-[13px] text-ink-700">
          {d.estado && (
            <section className="space-y-1.5">
              <div className="flex flex-wrap items-center gap-2">
                <NivelBadge nivel={d.estado.nivel} etiqueta={d.estado.etiqueta} />
                {d.estado.obligatoria && <Badge className="border border-ink-200 bg-paper-100 text-ink-600">Obligatoria</Badge>}
              </div>
              <p className="text-ink-800">{d.estado.texto}</p>
              {d.estado.alertas
                .filter((a) => a.regla !== d.estado?.regla)
                .map((a) => (
                  <p key={a.regla} className="flex flex-wrap items-start gap-2">
                    <NivelBadge nivel={a.nivel} etiqueta={a.etiqueta} />
                    <span>{a.texto}</span>
                  </p>
                ))}
              {d.estado.prueba && (
                <p className="text-ink-600">
                  <b>Prueba: {TEXTO_PRUEBA[d.estado.prueba.resultado] ?? d.estado.prueba.resultado}.</b> {d.estado.prueba.texto}
                </p>
              )}
              {d.estado.dato_de && <p className="italic text-ink-500">{d.estado.dato_de}</p>}
            </section>
          )}

          <section className="space-y-2 rounded-sm border border-ink-200 bg-paper-50 p-3">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-[14px] font-semibold text-ink-900">Cómo se elige el archivo</h3>
              {d.modo === "sin_configurar" ? (
                <span className="text-[12px] text-ink-500">
                  Para editar, primero usa la configuración de un PC como punto de partida.
                </span>
              ) : (
                <Button size="sm" variant="outline" onClick={() => onEditar(d)}>
                  <Pencil className="h-3.5 w-3.5" aria-hidden="true" /> Editar
                </Button>
              )}
            </div>
            <dl className="grid gap-x-4 gap-y-1.5 sm:grid-cols-[10rem_minmax(0,1fr)]">
              <dt className="text-ink-500">Forma</dt>
              <dd>
                {MODOS_ELECCION[d.config.modo] ?? d.config.modo}
                {d.config.modo === "archivo_exacto" && d.config.nombre_archivo && <b> {d.config.nombre_archivo}</b>}
                {d.config.modo === "mas_reciente" && (
                  <span className="ml-1 inline-flex flex-wrap gap-1 align-middle">
                    {d.config.incluye.map((p) => (
                      <code key={p} className="rounded-sm bg-white px-1 font-mono text-[12px] text-accent-700">{p}</code>
                    ))}
                  </span>
                )}
                {d.config.modo === "por_descarte" && (
                  <span className="block text-ink-500">
                    Toma los .xlsx cuyo nombre lleva el año en curso o el anterior y que no son de ninguna otra fuente.
                  </span>
                )}
              </dd>
              <dt className="text-ink-500">Dónde busca</dt>
              <dd>
                {d.config.ubicaciones.length === 0 ? "—" : (
                  <ul>
                    {d.config.ubicaciones.map((u, i) => (
                      <li key={i}>
                        {nombreCarpeta(u.carpeta)}
                        {u.subcarpeta ? ` › ${u.subcarpeta.split("/").join(" › ")}` : ""}
                        <span className="text-ink-500">{u.recursiva ? " (con sus subcarpetas)" : " (sin subcarpetas)"}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </dd>
              <dt className="text-ink-500">Plazo</dt>
              <dd>{textoPlazo(d.config.frecuencia_dias, d.config.al_vencer)}</dd>
              <dt className="text-ink-500">Obligatoria</dt>
              <dd>
                {d.config.obligatoria || d.catalogo?.requerida ? "Sí" : "No"}
                {d.catalogo?.efecto_si_falta && <span className="text-ink-500"> · Si falta: {d.catalogo.efecto_si_falta}</span>}
              </dd>
              {!d.config.activa && (
                <>
                  <dt className="text-ink-500">Estado</dt>
                  <dd>Desactivada: el motor no la busca.</dd>
                </>
              )}
              <dt className="text-ink-500">Hoja y fila</dt>
              <dd>{d.hoja_texto}</dd>
            </dl>
            <details className="text-[12.5px]">
              <summary className="cursor-pointer text-ink-500">Patrones crudos</summary>
              <dl className="mt-1 grid gap-x-4 gap-y-1 sm:grid-cols-[10rem_minmax(0,1fr)]">
                <dt className="text-ink-500">Incluye</dt>
                <dd className="font-mono">{d.config.incluye.join("  ·  ") || "—"}</dd>
                <dt className="text-ink-500">Excluye</dt>
                <dd className="font-mono">{d.config.excluye.join("  ·  ") || "—"}</dd>
                <dt className="text-ink-500">Extensiones</dt>
                <dd className="font-mono">{d.config.extensiones.join(", ") || "—"}</dd>
              </dl>
            </details>
          </section>

          {d.competencia.length > 0 && (
            <section className="space-y-2">
              <h3 className="text-[14px] font-semibold text-ink-900">Archivos que calzan, por carpeta</h3>
              <p className="text-[12px] text-ink-500">Gana el más reciente. Que compitan no cambia el color.</p>
              {d.competencia.map((c) => (
                <div key={c.carpeta} className="rounded-sm border border-ink-200 p-2">
                  <p className="font-medium text-ink-800">{c.carpeta_nombre ?? c.carpeta}</p>
                  {c.ruta_absoluta && <p className="break-all font-mono text-[11.5px] text-ink-500">{c.ruta_absoluta}</p>}
                  <ul className="mt-1 space-y-0.5">
                    {c.candidatos.map((a) => (
                      <li key={a.ruta_relativa} className="flex flex-wrap gap-x-2">
                        <span className={a.elegido ? "font-semibold text-ink-900" : ""}>{a.ruta_relativa}</span>
                        <span className="text-ink-500">{fechaHora(a.modificado_en)} · {tamano(a.tamano)}</span>
                        {a.elegido && <Badge className="border border-emerald-200 bg-emerald-50 text-emerald-800">Elegido</Badge>}
                      </li>
                    ))}
                  </ul>
                </div>
              ))}
            </section>
          )}

          {d.descartados.length > 0 && (
            <section className="space-y-1">
              <h3 className="text-[14px] font-semibold text-ink-900">Descartados</h3>
              <ul className="space-y-0.5">
                {d.descartados.map((x) => (
                  <li key={x.nombre}>
                    <span className="text-ink-800">{x.nombre}</span>
                    {x.motivo && <span className="text-ink-500"> · {x.motivo}</span>}
                    {x.nuevo && <Badge className="ml-1 border border-amber-200 bg-amber-50 text-amber-900">Nuevo</Badge>}
                  </li>
                ))}
              </ul>
            </section>
          )}

          <section className="space-y-1">
            <h3 className="text-[14px] font-semibold text-ink-900">Últimas corridas</h3>
            {d.corridas.length === 0 ? (
              <p className="text-ink-500">Todavía no hay corridas con esta fuente.</p>
            ) : (
              <div className="overflow-x-auto rounded-sm border border-ink-200">
                <table className="w-full text-[12.5px]">
                  <thead className="bg-paper-100 text-left text-[11px] uppercase tracking-wide text-ink-500">
                    <tr>
                      <th className="px-2 py-1.5">Corrida</th>
                      <th className="px-2 py-1.5">PC</th>
                      <th className="px-2 py-1.5">Estado</th>
                      <th className="px-2 py-1.5">Archivo</th>
                      <th className="px-2 py-1.5 text-right">Filas</th>
                      <th className="px-2 py-1.5">Prueba</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.corridas.map((c) => (
                      <tr key={c.corrida_id} className="border-t border-ink-100 align-top">
                        <td className="whitespace-nowrap px-2 py-1.5">
                          {fechaHora(c.iniciada_en)}
                          <span className="block text-ink-500">{TEXTO_TIPO_CORRIDA[c.tipo] ?? c.tipo}</span>
                        </td>
                        <td className="px-2 py-1.5">{nombrePc(c.pc, c.alias)}</td>
                        <td className="px-2 py-1.5">
                          <NivelBadge nivel={c.nivel} etiqueta={c.etiqueta} />
                          {/* El error exacto del motor: solo aquí, puede traer la ruta del PC. */}
                          {c.mensaje && <span className="mt-1 block break-all font-mono text-[11px] text-ink-500">{c.mensaje}</span>}
                        </td>
                        <td className="px-2 py-1.5">
                          {c.archivos.map((a) => a.nombre).join(", ") || "—"}
                          {c.hoja_leida != null && <span className="block text-ink-500">Hoja {String(c.hoja_leida)}</span>}
                        </td>
                        <td className="tabular px-2 py-1.5 text-right">{c.filas != null ? formatoNumero(c.filas) : "—"}</td>
                        <td className="px-2 py-1.5">{c.prueba ? TEXTO_PRUEBA[c.prueba.resultado] ?? c.prueba.resultado : "—"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </section>

          {d.versiones.length > 0 && (
            <section className="space-y-1">
              <h3 className="text-[14px] font-semibold text-ink-900">Versiones que la cambiaron</h3>
              <ul className="divide-y divide-ink-100 rounded-sm border border-ink-200">
                {d.versiones.map((v, i) => (
                  <li key={v.version} className="flex flex-wrap items-start justify-between gap-2 px-3 py-2">
                    <div className="min-w-0">
                      <p className="text-ink-800">
                        <b>Versión {v.version}</b>
                        <span className="text-ink-500"> · {v.creado_por ?? "—"} · {cuando(v.creado_en, ahora)}</span>
                        {v.revierte_a != null && <span className="text-ink-500"> · volvió a la versión {v.revierte_a}</span>}
                      </p>
                      <p className="text-ink-600">{v.nota}</p>
                    </div>
                    {/* La primera es como esta hoy: volver a ella no cambia nada. */}
                    {i > 0 && (
                      <Button size="sm" variant="outline" onClick={() => setRevertir(v)}>
                        Volver a esta versión
                      </Button>
                    )}
                  </li>
                ))}
              </ul>
            </section>
          )}
        </div>
      )}

      <DialogoNota
        open={!!revertir}
        titulo={revertir ? `Volver a la versión ${revertir.version}` : ""}
        descripcion={d && revertir
          ? `${d.nombre} queda como estaba en la versión ${revertir.version}. Solo esta fuente: el modo, el titular y las demás fuentes no cambian. Rige desde la corrida siguiente.`
          : undefined}
        boton="Volver a esta versión"
        notaOpcional
        placeholder={revertir ? `Volver a la versión ${revertir.version}` : undefined}
        onClose={() => setRevertir(null)}
        onConfirmar={async (nota) => {
          if (!revertir || !d) return;
          const g = await fuentesApi.revertir(revertir.version, version, { clave: d.clave, nota: nota || undefined });
          setRevertir(null);
          await onGuardado(g, `${d.nombre} volvió a la versión ${revertir.version}. Rige desde la próxima corrida.`);
        }}
      />
    </Dialog>
  );
}
