"use client";

// "Motor del PC titular" (/cargar, solo admin): que version del motor tiene el PC que
// calcula el sugerido, y un boton para que baje la ultima desde GitHub.
//
// - La version instalada es la que informo el motor en su ultima corrida (la de la
//   franja de Fuentes de datos: `franja.ultima_corrida.version_motor`, "<sha> <rama>").
// - "Actualizar motor" deja pedido `actualizar_motor` en el mismo buzon de
//   "Actualizar ahora" (routers/actualizacion.py). El agente del PC hace git fetch y
//   avance rapido de su rama y, si cambiaron las librerias, las reinstala. No
//   recalcula nada. Se niega si el motor esta calculando o si el codigo del PC tiene
//   cambios locales, y lo dice en el mensaje que se muestra aca.
// - Nunca hay dos solicitudes vivas: mientras corre un recalculo el boton queda
//   desactivado, y al reves.
// - La toma el agente que pregunte primero, que puede no ser el del PC titular (el PC
//   de la jefa tiene agente antes de pasar a ser titular). El resultado dice que PC la
//   atendio y, si no fue el titular, que el titular sigue con su version.
import { useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, CloudDownload, Cpu, Loader2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { getEsAdmin } from "@/lib/auth";
import { cuando, de, fuentesApi, nombrePc, type Panel } from "@/lib/fuentes-datos";
import { cuandoFue, minutosDesde, tipoDe, type Buzon } from "@/components/sincronizacion-manual";

/** El alias de un PC si el panel lo conoce (el titular o uno que ya corrio el motor). */
function aliasDe(panel: Panel | null, pc: string): string | null {
  if (!panel) return null;
  const mismo = (otro: string | null | undefined) => !!otro && otro.toUpperCase() === pc.toUpperCase();
  if (mismo(panel.pc_titular)) return panel.pc_titular_alias;
  return panel.carpetas_por_pc.find((p) => mismo(p.pc))?.alias ?? null;
}

/** Lo que dice la confirmacion antes de pedir. */
export const TEXTO_CONFIRMAR_MOTOR =
  "El PC del motor baja la última versión desde GitHub. No recalcula nada. Tarda 1 a 2 " +
  "minutos; tiene que estar prendido y con sesión iniciada.";

export function MotorPcTitular({ buzon }: { buzon: Buzon }) {
  const [esAdmin, setEsAdmin] = useState(false);
  const [panel, setPanel] = useState<Panel | null>(null);
  const [errorPanel, setErrorPanel] = useState<string | null>(null);
  const [cargandoPanel, setCargandoPanel] = useState(true);
  const [confirmando, setConfirmando] = useState(false);
  // El error del dialogo es el de ESTE intento, no el de uno anterior.
  const [intentado, setIntentado] = useState(false);

  useEffect(() => {
    setEsAdmin(getEsAdmin());
  }, []);

  useEffect(() => {
    if (!esAdmin) return;
    let vigente = true;
    fuentesApi
      .panel()
      .then((p) => {
        if (vigente) setPanel(p);
      })
      .catch((e: unknown) => {
        if (vigente) setErrorPanel(e instanceof Error ? e.message : "No se pudo leer la versión.");
      })
      .finally(() => {
        if (vigente) setCargandoPanel(false);
      });
    return () => {
      vigente = false;
    };
  }, [esAdmin]);

  // Cambiar el programa que calcula para todo el equipo es cosa de admin (el gate
  // real es el 403 del servidor). /cargar ya manda al inicio a quien no lo es.
  if (!esAdmin) return null;

  const { est, viva, pidiendo, conTipos, errorEstado } = buzon;
  const mia = tipoDe(est) === "actualizar_motor";
  const enCursoMia = viva !== null && mia;
  const bloqueada = viva !== null && !mia;
  const rechazo = buzon.rechazo.actualizar_motor;
  const error = buzon.error.actualizar_motor;
  const pidiendoMia = pidiendo === "actualizar_motor";
  // Una API anterior a "Actualizar motor" ignoraria el tipo y recalcularia: el boton
  // espera a que la plataforma nueva este publicada.
  const sinSoporte = est !== null && !conTipos;

  const corrida = panel?.franja.ultima_corrida ?? null;
  const versionInstalada = corrida?.version_motor ?? null;
  const titular = panel?.pc_titular ?? null;
  const nombreTitular = titular ? nombrePc(titular, panel?.pc_titular_alias) : null;
  const ahora = panel?.ahora ?? new Date().toISOString();
  // Que PC atendio la ultima actualizacion, y si era el titular. Sin el dato (API de
  // antes) o sin titular conocido, no se puede decir que no lo fuera.
  const agente = mia ? est?.agente ?? null : null;
  const nombreAgente = agente ? nombrePc(agente, aliasDe(panel, agente)) : null;
  const atendioOtroPc = !!agente && !!titular && agente.toUpperCase() !== titular.toUpperCase();
  const motivoBoton = bloqueada
    ? "bloqueo-motor"
    : sinSoporte
      ? "motor-sin-soporte"
      : errorEstado
        ? "motor-sin-estado"
        : undefined;

  const abrir = () => {
    setIntentado(false);
    setConfirmando(true);
  };
  const cerrar = () => {
    if (!pidiendoMia) setConfirmando(false);
  };
  const confirmar = async () => {
    setIntentado(true);
    if (await buzon.pedir("actualizar_motor")) setConfirmando(false);
  };

  return (
    <Card>
      <CardContent className="space-y-3 text-[13px] text-ink-700">
        <div className="flex items-start gap-3">
          <Cpu size={20} className="mt-0.5 shrink-0 text-brand" aria-hidden="true" />
          <div className="min-w-0">
            <p className="font-display text-[15px] font-medium text-ink-900">
              Motor del PC titular
            </p>
            <p className="mt-1 text-[12.5px] text-ink-600">
              El programa que calcula el sugerido
              {nombreTitular ? (
                <>
                  , instalado en <b>{nombreTitular}</b>
                </>
              ) : null}
              . Actualizarlo baja la última versión desde GitHub: no cambia los datos ni
              recalcula.
            </p>
          </div>
        </div>

        <div className="rounded-sm border border-ink-200 bg-paper-50 px-3 py-2.5">
          <p className="kicker">Versión instalada</p>
          {cargandoPanel ? (
            <p className="mt-1 inline-flex items-center gap-1.5 text-[12.5px] text-ink-500">
              <Loader2 size={13} className="animate-spin" aria-hidden="true" /> Leyendo la versión…
            </p>
          ) : errorPanel ? (
            <p role="alert" className="mt-1 text-[12.5px] text-amber-800">
              No se pudo leer la versión instalada: {errorPanel}
            </p>
          ) : !corrida ? (
            <p className="mt-1 text-[12.5px] text-ink-600">
              Todavía no llega ninguna corrida del motor. La versión aparece después de la
              próxima.
            </p>
          ) : (
            <>
              {versionInstalada ? (
                <p className="mt-1 font-mono text-[13px] font-semibold text-ink-900">
                  {versionInstalada}
                </p>
              ) : (
                <p className="mt-1 text-[12.5px] text-ink-600">
                  Esa corrida no informó la versión del motor.
                </p>
              )}
              <p className="mt-0.5 text-[12px] text-ink-500">
                Según la corrida {de(cuando(corrida.iniciada_en, ahora))} en{" "}
                {nombrePc(corrida.pc, corrida.alias)}.
              </p>
              {titular && corrida.pc !== titular && (
                <p className="mt-1 text-[12px] text-amber-800">
                  Esa corrida no es del PC titular ({nombreTitular}): el titular todavía no
                  informa su versión.
                </p>
              )}
            </>
          )}
        </div>

        <Button
          variant="outline"
          onClick={abrir}
          disabled={pidiendo !== null || viva !== null || !conTipos}
          aria-describedby={motivoBoton}
        >
          {pidiendoMia || enCursoMia ? (
            <>
              <Loader2 size={15} className="animate-spin" aria-hidden="true" /> Actualizando motor…
            </>
          ) : (
            <>
              <CloudDownload size={15} aria-hidden="true" /> Actualizar motor
            </>
          )}
        </Button>

        {sinSoporte && (
          <p id="motor-sin-soporte" className="rounded-sm bg-paper-100 px-3 py-2 text-[12px] text-ink-700">
            La plataforma todavía no tiene publicada esta función. Recarga la página en unos
            minutos.
          </p>
        )}

        {/* La API no contesto al abrir la pagina (Render reiniciandose): sin estado no se
            sabe si hay algo vivo, asi que el boton espera y dice por que. */}
        {errorEstado && (
          <p id="motor-sin-estado" role="status" className="rounded-sm bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
            No se pudo leer el estado del PC del motor. Se reintenta solo.
          </p>
        )}

        {enCursoMia && est?.estado === "pendiente" && (
          <p role="status" className="rounded-sm bg-brand-50 px-3 py-2 text-[12px] text-brand-800">
            Pedido enviado. Esperando al computador del motor (lo toma en menos de un minuto
            si está prendido y con sesión iniciada).
          </p>
        )}

        {enCursoMia && est?.estado === "en_curso" && (
          <p role="status" className="rounded-sm bg-brand-50 px-3 py-2 text-[12px] text-brand-800">
            Bajando la última versión desde GitHub. Tarda 1 a 2 minutos
            {minutosDesde(est.creado_en) > 0 && ` (van ${minutosDesde(est.creado_en)})`}. No
            recalcula nada.
          </p>
        )}

        {bloqueada && viva && (
          <p
            id="bloqueo-motor"
            role="status"
            className="rounded-sm bg-paper-100 px-3 py-2 text-[12px] text-ink-700"
          >
            {buzon.motivoBloqueo("actualizar_motor", viva)}
          </p>
        )}

        {!viva && mia && est?.estado === "ok" && (
          <div role="status" className="space-y-1 rounded-sm bg-emerald-50 px-3 py-2 text-[12.5px] text-emerald-800">
            <p className="inline-flex items-start gap-1.5 font-medium">
              <CheckCircle2 size={14} className="mt-px shrink-0" aria-hidden="true" />
              <span>
                {est.mensaje ?? "Motor actualizado."}
                {est.terminado_en && ` Terminó ${cuandoFue(est.terminado_en)}.`}
              </span>
            </p>
            {nombreAgente && <p>Lo atendió {nombreAgente}.</p>}
            {est.version && (
              <p>
                Versión en ese PC: <b className="font-mono">{est.version}</b>
                {est.version !== versionInstalada && !atendioOtroPc &&
                  ". La versión instalada de arriba cambia con la próxima corrida del motor."}
              </p>
            )}
          </div>
        )}

        {/* La tomo el agente de otro PC: ese se actualizo, el titular no. */}
        {!viva && mia && est?.estado === "ok" && atendioOtroPc && (
          <p role="status" className="rounded-sm bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
            Se actualizó {nombreAgente}, que no es el titular. El titular sigue con{" "}
            {versionInstalada ?? "la versión de su última corrida"}.
          </p>
        )}

        {!viva && mia && (est?.estado === "error" || est?.estado === "expirada") && (
          <div role="alert" className="space-y-1 rounded-sm bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
            <p className="inline-flex items-start gap-1.5">
              <AlertTriangle size={14} className="mt-px shrink-0" aria-hidden="true" />
              <span>{est.mensaje ?? "No se pudo actualizar el motor."}</span>
            </p>
            {nombreAgente && <p>Lo atendió {nombreAgente}.</p>}
            {est.version && (
              <p>
                Versión en ese PC: <b className="font-mono">{est.version}</b>
              </p>
            )}
          </div>
        )}

        {error && !confirmando && (
          <p role="alert" className="rounded-sm bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
            {error}
          </p>
        )}

        <p className="text-[11px] text-ink-500">
          Lo atiende el mismo programa del PC que «Actualizar ahora». Si el motor está
          calculando o el código de ese PC tiene cambios sin subir, no actualiza y lo avisa
          acá.
        </p>
      </CardContent>

      <Dialog open={confirmando} onClose={cerrar} title="¿Actualizar el motor?">
        <div className="space-y-4 text-[13px] text-ink-700">
          <p>{TEXTO_CONFIRMAR_MOTOR}</p>
          {intentado && (rechazo || error) && (
            <p role="alert" className="rounded-sm bg-amber-50 px-3 py-2 text-[12.5px] text-amber-800">
              {rechazo ?? error}
            </p>
          )}
          <div className="flex justify-end gap-2">
            <Button variant="outline" onClick={cerrar} disabled={pidiendoMia}>
              Cancelar
            </Button>
            <Button onClick={() => void confirmar()} disabled={pidiendoMia || viva !== null}>
              {pidiendoMia && <Loader2 size={15} className="animate-spin" aria-hidden="true" />}
              Actualizar motor
            </Button>
          </div>
        </div>
      </Dialog>
    </Card>
  );
}
