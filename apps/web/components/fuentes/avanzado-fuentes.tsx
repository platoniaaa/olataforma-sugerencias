"use client";

// "Avanzado" (plegado): las fuentes que el motor solo reconoce, los patrones
// crudos de cada fuente, las carpetas configuradas, el listado completo de una
// carpeta y las ultimas corridas. Lo que pesa se pide recien al abrirlo.
import { useEffect, useState } from "react";
import { Plus } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatoNumero } from "@/lib/formato";
import {
  MODOS_ELECCION,
  NIVELES,
  TEXTO_TIPO_CORRIDA,
  fechaHora,
  fuentesApi,
  nombrePc,
  tamano,
  type ArchivosCarpeta,
  type CarpetaCfg,
  type ConfigVigente,
  type Corrida,
  type Guardado,
  type Nivel,
  type Panel,
} from "@/lib/fuentes-datos";
import { Cargando, MensajeError } from "./comun";
import { EditorCarpeta } from "./editor-carpeta";

const ONEDRIVE: Record<string, string> = {
  solo_nube: "Solo en la nube",
  fijado: "Siempre en el PC",
  liberable: "En el PC",
  local: "En el PC",
};

interface Props {
  panel: Panel;
  config: ConfigVigente | null;
  onGuardado: (g: Guardado, texto?: string) => void | Promise<void>;
}

export function AvanzadoFuentes({ panel, config, onGuardado }: Props) {
  const [editando, setEditando] = useState<CarpetaCfg | "nueva" | null>(null);
  const carpetas = config?.carpetas ?? [];
  const configurado = panel.modo !== "sin_configurar";
  const pcs = panel.carpetas_por_pc.map((p) => p.pc);
  const nombreCarpeta = (c: string) => carpetas.find((x) => x.clave === c)?.nombre ?? c;

  return (
    <details className="rounded-sm border border-ink-200 bg-white px-4 py-3">
      <summary className="cursor-pointer text-base font-semibold text-ink-900">Avanzado</summary>
      <div className="mt-4 space-y-6 text-[13px] text-ink-700">
        <section className="space-y-2">
          <h3 className="text-[14px] font-semibold text-ink-900">Fuentes que el motor solo reconoce</h3>
          <p className="text-[12px] text-ink-500">
            No se leen: existen para que esos archivos no se confundan con los respaldos de venta.
          </p>
          {panel.reconoce.length === 0 ? (
            <p className="text-ink-500">—</p>
          ) : (
            <ul className="space-y-1">
              {panel.reconoce.map((r) => (
                <li key={r.clave}>
                  <b className="text-ink-800">{r.nombre}</b>{" "}
                  <span className="font-mono text-[12px] text-ink-500">
                    {r.incluye.join("  ·  ")}
                    {r.excluye.length > 0 ? `  (excepto ${r.excluye.join(", ")})` : ""}
                  </span>
                  {r.archivos.length > 0 && <span className="text-ink-500"> · hoy: {r.archivos.map((a) => a.nombre).join(", ")}</span>}
                </li>
              ))}
            </ul>
          )}
        </section>

        {(config?.fuentes?.length ?? 0) > 0 && (
          <section className="space-y-2">
            <h3 className="text-[14px] font-semibold text-ink-900">Patrones de cada fuente</h3>
            <div className="overflow-x-auto rounded-sm border border-ink-200">
              <table className="w-full text-[12.5px]">
                <thead className="bg-paper-100 text-left text-[11px] uppercase tracking-wide text-ink-500">
                  <tr>
                    <th className="px-2 py-1.5">Fuente</th>
                    <th className="px-2 py-1.5">Forma</th>
                    <th className="px-2 py-1.5">Incluye</th>
                    <th className="px-2 py-1.5">Excluye</th>
                    <th className="px-2 py-1.5">Dónde</th>
                  </tr>
                </thead>
                <tbody>
                  {config!.fuentes!.map((f) => (
                    <tr key={f.clave} className="border-t border-ink-100 align-top">
                      <td className="px-2 py-1.5">
                        {f.nombre}
                        <span className="block font-mono text-[11px] text-ink-400">{f.clave}</span>
                      </td>
                      <td className="px-2 py-1.5">
                        {MODOS_ELECCION[f.modo] ?? f.modo}
                        {f.nombre_archivo && <span className="block font-mono">{f.nombre_archivo}</span>}
                      </td>
                      <td className="px-2 py-1.5 font-mono">{f.incluye.join(" · ") || "—"}</td>
                      <td className="px-2 py-1.5 font-mono">{f.excluye.join(" · ") || "—"}</td>
                      <td className="px-2 py-1.5">
                        {f.ubicaciones.map((u) => `${nombreCarpeta(u.carpeta)}${u.subcarpeta ? ` › ${u.subcarpeta}` : ""}${u.recursiva ? " (+subcarpetas)" : ""}`).join("; ") || "—"}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>
        )}

        {configurado && (
          <section className="space-y-2">
            <div className="flex flex-wrap items-center justify-between gap-2">
              <h3 className="text-[14px] font-semibold text-ink-900">Carpetas configuradas</h3>
              <Button size="sm" variant="outline" onClick={() => setEditando("nueva")}>
                <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Agregar carpeta
              </Button>
            </div>
            <ul className="divide-y divide-ink-100 rounded-sm border border-ink-200">
              {carpetas.map((c) => (
                <li key={c.clave} className="flex flex-wrap items-start justify-between gap-2 px-3 py-2">
                  <div className="min-w-0">
                    <p className="text-ink-800">
                      <b>{c.nombre}</b> <span className="text-ink-500">· {c.tipo === "sharepoint" ? "SharePoint" : "OneDrive"}</span>
                      {!c.activa && <Badge className="ml-1 border border-ink-200 bg-ink-100 text-ink-500">Desactivada</Badge>}
                    </p>
                    <p className="break-all font-mono text-[11.5px] text-ink-500">
                      {[c.params.ruta, c.params.nombre_atajo ? `acceso directo: ${c.params.nombre_atajo}` : null].filter(Boolean).join(" · ")}
                    </p>
                    {Object.keys(c.rutas_por_pc ?? {}).length > 0 && (
                      <p className="text-[12px] text-ink-500">Ruta propia en: {Object.keys(c.rutas_por_pc).join(", ")}</p>
                    )}
                  </div>
                  <Button size="sm" variant="ghost" onClick={() => setEditando(c)}>Editar</Button>
                </li>
              ))}
            </ul>
          </section>
        )}

        <ListadoCompleto panel={panel} carpetas={carpetas} />
        <UltimasCorridas />
      </div>

      <EditorCarpeta
        open={editando !== null}
        carpeta={editando === "nueva" ? null : editando}
        pcs={pcs}
        version={panel.version ?? 0}
        onClose={() => setEditando(null)}
        onGuardado={async (g, t) => {
          setEditando(null);
          await onGuardado(g, t);
        }}
      />
    </details>
  );
}

function ListadoCompleto({ panel, carpetas }: { panel: Panel; carpetas: CarpetaCfg[] }) {
  const pcs = panel.carpetas_por_pc;
  const [pc, setPc] = useState(pcs[0]?.pc ?? "");
  const claves = Array.from(new Set([
    ...carpetas.map((c) => c.clave),
    ...(pcs.find((p) => p.pc === pc)?.carpetas.map((c) => c.clave) ?? []),
  ]));
  const [elegida, setCarpeta] = useState("");
  const carpeta = elegida || claves[0] || "";
  const [listado, setListado] = useState<ArchivosCarpeta | null>(null);
  const [abierto, setAbierto] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!abierto || !carpeta) return;
    let vigente = true;
    setListado(null);
    setError(null);
    fuentesApi
      .archivosCarpeta(carpeta, pc || null)
      .then((r) => vigente && setListado(r))
      .catch((e) => vigente && setError(e instanceof Error ? e.message : "No se pudo cargar el listado."));
    return () => {
      vigente = false;
    };
  }, [abierto, carpeta, pc]);

  if (pcs.length === 0) return null;
  const nombre = (c: string) => carpetas.find((x) => x.clave === c)?.nombre ?? pcs.flatMap((p) => p.carpetas).find((x) => x.clave === c)?.nombre ?? c;

  return (
    <details onToggle={(e) => setAbierto((e.currentTarget as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-[14px] font-semibold text-ink-900">Listado completo de una carpeta</summary>
      <div className="mt-2 space-y-2">
        <div className="flex flex-wrap gap-2">
          <label className="text-[12px] text-ink-500">
            PC
            <select className="ml-1 h-8 rounded-sm border border-ink-200 bg-white px-2 text-[13px]" value={pc} onChange={(e) => setPc(e.target.value)}>
              {pcs.map((p) => <option key={p.pc} value={p.pc}>{nombrePc(p.pc, p.alias)}</option>)}
            </select>
          </label>
          <label className="text-[12px] text-ink-500">
            Carpeta
            <select className="ml-1 h-8 rounded-sm border border-ink-200 bg-white px-2 text-[13px]" value={carpeta} onChange={(e) => setCarpeta(e.target.value)}>
              {claves.map((c) => <option key={c} value={c}>{nombre(c)}</option>)}
            </select>
          </label>
        </div>
        {error && <MensajeError>{error}</MensajeError>}
        {abierto && !listado && !error && <Cargando />}
        {listado && (
          <>
            {listado.ruta_absoluta && <p className="break-all font-mono text-[11.5px] text-ink-500">{listado.ruta_absoluta}</p>}
            {listado.corrida_id == null ? (
              <p className="text-ink-500">Ese PC no ha mandado el listado de esta carpeta.</p>
            ) : !listado.existe ? (
              <p className="text-rose-700">Esa carpeta no está en ese PC.</p>
            ) : (
              <div className="max-h-96 overflow-auto rounded-sm border border-ink-200">
                <table className="w-full text-[12.5px]">
                  <thead className="sticky top-0 bg-paper-100 text-left text-[11px] uppercase tracking-wide text-ink-500">
                    <tr>
                      <th className="px-2 py-1.5">Archivo</th>
                      <th className="px-2 py-1.5">Modificado</th>
                      <th className="px-2 py-1.5 text-right">Tamaño</th>
                      <th className="px-2 py-1.5">OneDrive</th>
                      <th className="px-2 py-1.5">Fuente</th>
                    </tr>
                  </thead>
                  <tbody>
                    {listado.archivos.map((a) => (
                      <tr key={a.ruta_relativa} className="border-t border-ink-100">
                        <td className="px-2 py-1">{a.ruta_relativa}</td>
                        <td className="tabular whitespace-nowrap px-2 py-1">{fechaHora(a.modificado_en)}</td>
                        <td className="tabular whitespace-nowrap px-2 py-1 text-right">{tamano(a.tamano)}</td>
                        <td className="px-2 py-1">{a.onedrive ? ONEDRIVE[a.onedrive] ?? a.onedrive : "—"}</td>
                        <td className="px-2 py-1">
                          {a.fuente ?? "—"}
                          {a.elegido && <Badge className="ml-1 border border-emerald-200 bg-emerald-50 text-emerald-800">Elegido</Badge>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {listado.truncado && <p className="text-[12px] text-amber-800">El listado está recortado (hasta 500 archivos y 3 niveles).</p>}
          </>
        )}
      </div>
    </details>
  );
}

function UltimasCorridas() {
  const [abierto, setAbierto] = useState(false);
  const [items, setItems] = useState<Corrida[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!abierto || items) return;
    fuentesApi
      .corridas(30)
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudieron cargar las corridas."));
  }, [abierto, items]);

  return (
    <details onToggle={(e) => setAbierto((e.currentTarget as HTMLDetailsElement).open)}>
      <summary className="cursor-pointer text-[14px] font-semibold text-ink-900">Últimas 30 corridas</summary>
      <div className="mt-2">
        {error && <MensajeError>{error}</MensajeError>}
        {abierto && !items && !error && <Cargando />}
        {items && items.length === 0 && <p className="text-ink-500">Todavía no hay corridas.</p>}
        {items && items.length > 0 && (
          <div className="overflow-x-auto rounded-sm border border-ink-200">
            <table className="w-full text-[12.5px]">
              <thead className="bg-paper-100 text-left text-[11px] uppercase tracking-wide text-ink-500">
                <tr>
                  <th className="px-2 py-1.5">Inicio</th>
                  <th className="px-2 py-1.5">PC</th>
                  <th className="px-2 py-1.5">Tipo</th>
                  <th className="px-2 py-1.5">Resultado</th>
                  <th className="px-2 py-1.5">Fuentes</th>
                </tr>
              </thead>
              <tbody>
                {items.map((c) => (
                  <tr key={c.id} className="border-t border-ink-100 align-top">
                    <td className="tabular whitespace-nowrap px-2 py-1">
                      {fechaHora(c.iniciada_en)}
                      {c.duracion_min != null && <span className="block text-ink-500">{c.duracion_min} min</span>}
                    </td>
                    <td className="px-2 py-1">{nombrePc(c.pc, c.alias)}</td>
                    <td className="px-2 py-1">{TEXTO_TIPO_CORRIDA[c.tipo] ?? c.tipo}</td>
                    <td className="px-2 py-1">
                      {c.resultado_texto}
                      {c.motivo_texto && <span className="block text-ink-500">{c.motivo_texto}</span>}
                      {c.avisos?.map((a) => (
                        <span key={a} className="block text-[11.5px] text-ink-500">· {a}</span>
                      ))}
                    </td>
                    <td className="px-2 py-1">
                      <Resumen resumen={c.resumen} />
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="mt-1 text-[11.5px] text-ink-400">Hora de Chile. El color de las fuentes es el que tenían a la hora de cada corrida.</p>
      </div>
    </details>
  );
}

function Resumen({ resumen }: { resumen: Partial<Record<Nivel, number>> }) {
  const niveles = (["rojo", "amarillo", "gris", "verde"] as Nivel[]).filter((n) => resumen[n]);
  if (niveles.length === 0) return <span className="text-ink-400">—</span>;
  return (
    <span className="flex flex-wrap gap-2">
      {niveles.map((n) => (
        <span key={n} className="inline-flex items-center gap-1">
          <span className={`h-2 w-2 rounded-full ${NIVELES[n].punto}`} aria-hidden="true" />
          {formatoNumero(resumen[n])} {NIVELES[n].label.toLowerCase()}
        </span>
      ))}
    </span>
  );
}
