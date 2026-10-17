"use client";

// Panel de Fuentes de datos, en el orden de la pantalla: franja superior (modo,
// ultima corrida y alertas), las fuentes que lee el motor de la peor a la mejor,
// y las carpetas que encontro cada PC. Todo viene calculado del servidor.
import { useState } from "react";
import { CheckCircle2, Monitor, XCircle } from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { formatoNumero } from "@/lib/formato";
import { cn } from "@/lib/utils";
import {
  NIVELES,
  TEXTO_ORIGEN,
  TEXTO_PRUEBA,
  TEXTO_TIPO_CORRIDA,
  cuando,
  de,
  fechaHora,
  fuentesApi,
  nombrePc,
  type Corrida,
  type FuentePanel,
  type Guardado,
  type Panel,
  type PcPanel,
  type SembrarDesde,
} from "@/lib/fuentes-datos";
import { DialogoNota, NivelBadge } from "./comun";

const EXPLICACION_MODO: Record<Panel["modo"], string> = {
  sin_configurar:
    "El motor usa la configuración escrita en el PC, como siempre. Para empezar, usa la configuración de un PC como punto de partida: queda en prueba y no cambia nada todavía.",
  prueba:
    "El motor sigue usando la configuración escrita en el PC y además revisa qué tomaría con la de esta pantalla. Lo que cambies acá es un ensayo hasta activar.",
  activa: "El motor lee los archivos que dice esta pantalla. Cada cambio rige desde la corrida siguiente.",
};

const CLASE_MODO: Record<Panel["modo"], string> = {
  sin_configurar: "border border-ink-200 bg-white text-ink-600",
  prueba: "border border-brand-200 bg-brand-50 text-brand-800",
  activa: "border border-emerald-200 bg-emerald-50 text-emerald-800",
};

// Los valores que manda el motor en `metodo` (`config_fuentes.resolver_carpeta`).
const TEXTO_METODO: Record<string, string> = {
  env: "ruta escrita en el PC",
  ruta_por_pc: "ruta de este PC",
  onedrive: "OneDrive",
  atajo: "acceso directo a SharePoint",
};

type Accion =
  | { tipo: "sembrar"; desde: SembrarDesde }
  | { tipo: "activar" }
  | { tipo: "prueba" }
  | { tipo: "titular"; pc: PcPanel }
  | { tipo: "alias"; pc: PcPanel };

interface Props {
  panel: Panel;
  onAbrirFuente: (clave: string) => void;
  /** Despues de cada escritura: la pantalla recarga y muestra el resultado. */
  onGuardado: (g: Guardado, texto?: string) => void | Promise<void>;
}

export function PanelFuentes({ panel, onAbrirFuente, onGuardado }: Props) {
  const [accion, setAccion] = useState<Accion | null>(null);
  const [alias, setAlias] = useState("");
  const base = panel.version ?? 0;
  const configurado = panel.modo !== "sin_configurar";

  const abrirAlias = (pc: PcPanel) => {
    setAlias(pc.alias ?? "");
    setAccion({ tipo: "alias", pc });
  };

  const confirmar = async (nota: string) => {
    if (!accion) return;
    let g: Guardado;
    let texto: string | undefined;
    if (accion.tipo === "sembrar") {
      g = await fuentesApi.sembrar(accion.desde.corrida_id, nota || undefined);
      texto = "Listo: la configuración quedó en prueba. El motor sigue usando la del PC y desde la próxima corrida compara.";
    } else if (accion.tipo === "activar") {
      g = await fuentesApi.cambiarModo("activa", nota, base);
      texto = "Activada: desde la próxima corrida el motor lee los archivos que dice esta pantalla.";
    } else if (accion.tipo === "prueba") {
      g = await fuentesApi.cambiarModo("prueba", nota, base);
      texto = "Volvió a prueba: desde la próxima corrida el motor usa otra vez la configuración del PC.";
    } else if (accion.tipo === "titular") {
      g = await fuentesApi.cambiarTitular(accion.pc.pc, nota, base);
      texto = `Desde la próxima corrida solo publica ${nombrePc(accion.pc.pc, accion.pc.alias)}.`;
    } else {
      if (!alias.trim()) throw new Error("Escribe el nombre del PC.");
      g = await fuentesApi.nombrarPc(accion.pc.pc, alias.trim(), base, nota || undefined);
    }
    setAccion(null);
    await onGuardado(g, texto);
  };

  return (
    <div className="space-y-6">
      <Franja panel={panel} onAccion={setAccion} />
      <TablaFuentes panel={panel} onAbrirFuente={onAbrirFuente} />
      <CarpetasPorPc
        panel={panel}
        configurado={configurado}
        onTitular={(pc) => setAccion({ tipo: "titular", pc })}
        onAlias={abrirAlias}
      />

      <DialogoNota
        open={accion?.tipo === "sembrar"}
        titulo="Usar esta configuración como punto de partida"
        descripcion={
          accion?.tipo === "sembrar"
            ? `Se copia lo que usa hoy ${nombrePc(accion.desde.pc, accion.desde.alias)}, el modo queda en prueba y ese PC queda como titular. El motor sigue usando la configuración del PC: no cambia nada todavía.`
            : undefined
        }
        boton="Usar como punto de partida"
        notaOpcional
        onClose={() => setAccion(null)}
        onConfirmar={confirmar}
      />
      <DialogoNota
        open={accion?.tipo === "activar"}
        titulo="Activar la configuración"
        descripcion="Desde la próxima corrida el motor lee los archivos que dice esta pantalla, y las fuentes obligatorias que falten frenan la publicación. Para volver atrás está «Volver a prueba»."
        boton="Activar"
        onClose={() => setAccion(null)}
        onConfirmar={confirmar}
      />
      <DialogoNota
        open={accion?.tipo === "prueba"}
        titulo="Volver a prueba"
        descripcion="Desde la próxima corrida el motor vuelve a usar la configuración escrita en el PC y solo compara con la de esta pantalla."
        boton="Volver a prueba"
        onClose={() => setAccion(null)}
        onConfirmar={confirmar}
      />
      <DialogoNota
        open={accion?.tipo === "titular"}
        titulo="Cambiar el PC titular"
        descripcion={
          accion?.tipo === "titular"
            ? `Desde la próxima corrida solo publica ${nombrePc(accion.pc.pc, accion.pc.alias)}. Si el otro PC tiene la tarea diaria, deshabilítala ese mismo día: no va a publicar, pero cada día aparecería la alerta «Hoy corrieron dos PCs».`
            : undefined
        }
        boton="Hacer titular"
        onClose={() => setAccion(null)}
        onConfirmar={confirmar}
      />
      <DialogoNota
        open={accion?.tipo === "alias"}
        titulo="Nombre del PC"
        descripcion={accion?.tipo === "alias" ? `Cómo se muestra el PC ${accion.pc.pc} en esta pantalla.` : undefined}
        boton="Guardar nombre"
        notaOpcional
        onClose={() => setAccion(null)}
        onConfirmar={confirmar}
      >
        <div>
          <Label htmlFor="alias-pc">Nombre</Label>
          <Input
            id="alias-pc"
            value={alias}
            maxLength={60}
            placeholder="PC de Abastecimiento"
            onChange={(e) => setAlias(e.target.value)}
          />
        </div>
      </DialogoNota>
    </div>
  );
}

function textoCorrida(c: Corrida, ahora: string): string {
  const partes = [`${TEXTO_TIPO_CORRIDA[c.tipo] ?? c.tipo} ${de(cuando(c.iniciada_en, ahora))}, ${nombrePc(c.pc, c.alias)}`];
  if (c.duracion_min != null) partes.push(`duró ${c.duracion_min} min`);
  if (c.config_origen) partes.push(`usó la ${TEXTO_ORIGEN[c.config_origen] ?? c.config_origen}`);
  return partes.join(" · ");
}

function Franja({ panel, onAccion }: { panel: Panel; onAccion: (a: Accion) => void }) {
  const { franja, activacion } = panel;
  const u = franja.ultima_corrida;
  return (
    <section aria-label="Estado general" className={cn("space-y-3 rounded-sm border p-4", NIVELES[franja.nivel].franja)}>
      <div className="flex flex-wrap items-center gap-2">
        <Badge className={CLASE_MODO[panel.modo]}>{panel.modo_texto}</Badge>
        {panel.pc_titular && (
          <span className="inline-flex items-center gap-1 text-[13px] text-ink-700">
            <Monitor className="h-3.5 w-3.5" aria-hidden="true" />
            PC titular: <b>{nombrePc(panel.pc_titular, panel.pc_titular_alias)}</b>
            {panel.pc_titular_alias && <span className="text-ink-500">({panel.pc_titular})</span>}
          </span>
        )}
        {panel.version != null && <span className="text-[12px] text-ink-500">Versión {panel.version}</span>}
      </div>
      <p className="max-w-3xl text-[13px] text-ink-600">{EXPLICACION_MODO[panel.modo]}</p>

      {u ? (
        <div className="rounded-sm border border-ink-200 bg-white px-3 py-2 text-[13px] text-ink-700">
          <p>
            <span className="kicker mr-2">Última corrida</span>
            <b className="text-ink-900">{u.resultado_texto}</b>
            <span className="text-ink-500"> · {textoCorrida(u, panel.ahora)}</span>
          </p>
          {u.motivo_texto && <p className="mt-1 text-ink-700">{u.motivo_texto}</p>}
        </div>
      ) : null}

      {franja.alertas.length > 0 ? (
        <ul className="space-y-2" aria-label="Alertas">
          {franja.alertas.map((a) => (
            <li key={a.regla} className="flex flex-col gap-1 sm:flex-row sm:items-start sm:gap-2">
              <NivelBadge nivel={a.nivel} etiqueta={a.etiqueta} className="shrink-0 self-start" />
              <span className="text-[13px] text-ink-800">{a.texto}</span>
            </li>
          ))}
        </ul>
      ) : (
        u && <p className="text-[13px] text-emerald-800">Sin alertas.</p>
      )}

      {panel.modo === "sin_configurar" && (
        <div className="space-y-2 border-t border-ink-200/70 pt-3">
          {panel.sembrar_desde.length === 0 ? (
            <p className="text-[13px] text-ink-600">
              Todavía no llega ninguna corrida con la configuración de un PC. Aparece después de la próxima corrida del motor.
            </p>
          ) : (
            panel.sembrar_desde.map((s) => (
              <div key={s.corrida_id} className="flex flex-wrap items-center gap-2">
                <Button size="sm" onClick={() => onAccion({ tipo: "sembrar", desde: s })}>
                  Usar la configuración del PC {nombrePc(s.pc, s.alias)} como punto de partida
                </Button>
                <span className="text-[12px] text-ink-500">
                  {TEXTO_TIPO_CORRIDA[s.tipo] ?? s.tipo}, {cuando(s.iniciada_en, panel.ahora)}
                </span>
              </div>
            ))
          )}
        </div>
      )}

      {panel.modo === "prueba" && (
        <div className="flex flex-wrap items-center gap-3 border-t border-ink-200/70 pt-3">
          <Button
            size="sm"
            variant="secondary"
            disabled={!activacion.puede_activar}
            onClick={() => onAccion({ tipo: "activar" })}
          >
            Activar
          </Button>
          <p className="max-w-2xl text-[12.5px] text-ink-600">
            {activacion.corridas_en_verde} de {activacion.corridas_necesarias} corridas diarias seguidas en verde.
            {activacion.motivo ? ` ${activacion.motivo}` : " Ya se puede activar; rige desde la corrida siguiente."}
          </p>
        </div>
      )}

      {panel.modo === "activa" && (
        <div className="flex flex-wrap items-center gap-3 border-t border-ink-200/70 pt-3">
          <Button size="sm" variant="outline" onClick={() => onAccion({ tipo: "prueba" })}>
            Volver a prueba
          </Button>
          <p className="text-[12.5px] text-ink-600">Rige desde la corrida siguiente.</p>
        </div>
      )}
    </section>
  );
}

function TablaFuentes({ panel, onAbrirFuente }: { panel: Panel; onAbrirFuente: (clave: string) => void }) {
  if (panel.fuentes.length === 0) {
    return (
      <section className="space-y-2">
        <h2 className="text-base font-semibold text-ink-900">Fuentes</h2>
        <p className="text-sm text-ink-500">Las fuentes aparecen cuando llegue el primer reporte del motor.</p>
      </section>
    );
  }
  return (
    <section className="space-y-2" aria-labelledby="titulo-fuentes">
      <h2 id="titulo-fuentes" className="text-base font-semibold text-ink-900">
        Fuentes <span className="text-[12px] font-normal text-ink-500">({panel.fuentes.length}, de la peor a la mejor)</span>
      </h2>
      <div className="overflow-hidden rounded-sm border border-ink-200 bg-white">
        <div className="hidden grid-cols-[9.5rem_minmax(0,1.2fr)_minmax(0,1.4fr)_10rem_5.5rem] gap-3 border-b border-ink-200 bg-paper-100 px-3 py-2 text-[11px] font-semibold uppercase tracking-wide text-ink-500 md:grid">
          <span>Estado</span>
          <span>Fuente</span>
          <span>Archivo y carpeta</span>
          <span>Modificado</span>
          <span className="text-right">Filas</span>
        </div>
        <ul>
          {panel.fuentes.map((f) => (
            <FilaFuente key={f.clave} f={f} ahora={panel.ahora} onAbrir={() => onAbrirFuente(f.clave)} />
          ))}
        </ul>
      </div>
    </section>
  );
}

function FilaFuente({ f, ahora, onAbrir }: { f: FuentePanel; ahora: string; onAbrir: () => void }) {
  return (
    <li
      className="cursor-pointer border-b border-ink-100 px-3 py-3 last:border-b-0 hover:bg-paper-50"
      onClick={onAbrir}
      data-testid={`fuente-${f.clave}`}
    >
      <div className="grid gap-x-3 gap-y-1 md:grid-cols-[9.5rem_minmax(0,1.2fr)_minmax(0,1.4fr)_10rem_5.5rem] md:items-start">
        <div>
          <NivelBadge nivel={f.nivel} etiqueta={f.etiqueta} />
        </div>
        <div className="min-w-0">
          <button
            type="button"
            className="text-left text-[14px] font-medium text-ink-900 underline-offset-2 hover:text-brand hover:underline focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-700/40"
            onClick={(e) => {
              e.stopPropagation();
              onAbrir();
            }}
          >
            {f.nombre}
          </button>
          <div className="mt-0.5 flex flex-wrap gap-1">
            {f.obligatoria && <Badge className="border border-ink-200 bg-paper-100 text-ink-600">Obligatoria</Badge>}
            {!f.activa && <Badge className="border border-ink-200 bg-ink-100 text-ink-500">Desactivada</Badge>}
          </div>
        </div>
        <div className="min-w-0 text-[13px]">
          <p className="break-words text-ink-800">{f.archivo ?? "—"}</p>
          {f.archivos.length > 1 && <p className="text-[12px] text-ink-500">y {f.archivos.length - 1} archivo(s) más</p>}
          {f.carpeta_nombre && <p className="text-[12px] text-ink-500">{f.carpeta_nombre}</p>}
        </div>
        <div className="text-[13px]">
          {f.modificado_en ? (
            <>
              <p className="text-ink-800">{cuando(f.modificado_en, ahora)}</p>
              <p className="tabular text-[11.5px] text-ink-500">{fechaHora(f.modificado_en)}</p>
            </>
          ) : (
            <p className="text-ink-500">—</p>
          )}
        </div>
        <div className="tabular text-[13px] text-ink-800 md:text-right">
          {f.filas != null ? <><span className="md:hidden text-ink-500">Filas: </span>{formatoNumero(f.filas)}</> : ""}
        </div>
      </div>
      <p className="mt-1.5 text-[13px] text-ink-700">{f.texto}</p>
      {f.prueba && (
        <p className="mt-1 text-[12.5px] text-ink-600">
          <span
            className={cn(
              "mr-1.5 rounded-sm px-1 py-px text-[11px] font-semibold",
              f.prueba.resultado === "coincide" || f.prueba.resultado === "difiere_esperado"
                ? "bg-emerald-50 text-emerald-800"
                : "bg-amber-50 text-amber-900"
            )}
          >
            Prueba: {TEXTO_PRUEBA[f.prueba.resultado] ?? f.prueba.resultado}
          </span>
          {f.prueba.texto}
        </p>
      )}
      {f.dato_de && <p className="mt-1 text-[12px] italic text-ink-500">{f.dato_de}</p>}
    </li>
  );
}

function CarpetasPorPc({
  panel,
  configurado,
  onTitular,
  onAlias,
}: {
  panel: Panel;
  configurado: boolean;
  onTitular: (pc: PcPanel) => void;
  onAlias: (pc: PcPanel) => void;
}) {
  return (
    <section className="space-y-2" aria-labelledby="titulo-carpetas">
      <h2 id="titulo-carpetas" className="text-base font-semibold text-ink-900">Carpetas por PC</h2>
      {panel.carpetas_por_pc.length === 0 ? (
        <p className="text-sm text-ink-500">Ningún PC ha mandado todavía el listado de sus carpetas.</p>
      ) : (
        <div className="grid gap-3 lg:grid-cols-2">
          {panel.carpetas_por_pc.map((pc) => (
            <div key={pc.pc} className="rounded-sm border border-ink-200 bg-white p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Monitor className="h-4 w-4 text-ink-500" aria-hidden="true" />
                <p className="font-medium text-ink-900">{nombrePc(pc.pc, pc.alias)}</p>
                {pc.alias && <span className="text-[12px] text-ink-500">{pc.pc}</span>}
                {pc.es_titular && <Badge className="border border-brand-200 bg-brand-50 text-brand-800">Titular</Badge>}
              </div>
              <p className="mt-0.5 text-[12px] text-ink-500">
                Listado {de(cuando(pc.iniciada_en, panel.ahora))} · corrida {(TEXTO_TIPO_CORRIDA[pc.tipo] ?? pc.tipo).toLowerCase()}
              </p>
              <ul className="mt-2 space-y-1.5">
                {pc.carpetas.map((c) => (
                  <li key={c.clave} className="flex items-start gap-2 text-[13px]">
                    {c.existe ? (
                      <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" aria-label="Existe" />
                    ) : (
                      <XCircle className="mt-0.5 h-4 w-4 shrink-0 text-rose-600" aria-label="No existe" />
                    )}
                    <div className="min-w-0">
                      <p className="text-ink-800">
                        {c.nombre}{" "}
                        <span className="text-ink-500">
                          · {c.existe ? `${formatoNumero(c.archivos)} archivos${c.truncado ? " (listado recortado)" : ""}` : "no está en este PC"}
                          {c.metodo ? ` · ${TEXTO_METODO[c.metodo] ?? c.metodo}` : ""}
                        </span>
                      </p>
                      {c.ruta_portable && (
                        <p className="break-all font-mono text-[11.5px] text-ink-500">{c.ruta_portable}</p>
                      )}
                    </div>
                  </li>
                ))}
              </ul>
              {configurado && (
                <div className="mt-3 flex flex-wrap gap-2">
                  <Button size="sm" variant="outline" onClick={() => onAlias(pc)}>
                    {pc.alias ? "Cambiar nombre" : "Ponerle nombre"}
                  </Button>
                  {!pc.es_titular && (
                    <Button size="sm" variant="outline" onClick={() => onTitular(pc)}>
                      Hacer titular
                    </Button>
                  )}
                </div>
              )}
            </div>
          ))}
        </div>
      )}
    </section>
  );
}
