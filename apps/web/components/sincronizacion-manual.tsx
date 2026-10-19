"use client";

// Boton "Actualizar ahora": recalcula el sugerido con los Excel de "Bases de datos".
//
// El motor no corre en la nube -necesita los Excel, que viven en un PC de la empresa-,
// asi que este boton NO recalcula: deja pedido el trabajo en la plataforma. Un agente
// instalado en ese PC lo toma en menos de un minuto, corre el motor (22 a 35 min en
// las corridas de octubre) y reporta el resultado, que es lo que esta tarjeta muestra.
//
// Por eso el boton sirve desde cualquier equipo o telefono. Antes abria el protocolo
// `sugerido://`, que solo funcionaba sentado frente al PC del administrador.
//
// Por el mismo buzon pasa "Actualizar motor" (components/motor-pc-titular.tsx, solo
// admin). Nunca hay dos solicitudes vivas a la vez: mientras una esta pendiente o en
// curso, el boton de la otra queda desactivado y dice por que. `useBuzonActualizacion`
// es el estado comun; en /cargar lo comparten las dos tarjetas.
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoFechaHora } from "@/lib/formato";
import { cuando } from "@/lib/fuentes-datos";
import type { EstadoActualizacion, TipoActualizacion } from "@/lib/types";

function tiempoRelativo(iso: string | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  const segs = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (segs < 60) return "hace segundos";
  const mins = Math.floor(segs / 60);
  if (mins < 60) return `hace ${mins} min`;
  const hs = Math.floor(mins / 60);
  if (hs < 24) return `hace ${hs} h`;
  return `hace ${Math.floor(hs / 24)} d`;
}

export function minutosDesde(iso: string | null): number {
  if (!iso) return 0;
  return Math.floor(Math.max(0, Date.now() - new Date(iso).getTime()) / 60000);
}

/** El tipo de una solicitud. Una API anterior a "Actualizar motor" no lo manda: es un
 *  recalculo, lo unico que sabia pedir. */
export function tipoDe(est: EstadoActualizacion | null): TipoActualizacion {
  return est?.tipo ?? "recalcular";
}

/** "hoy a las 09:41", "ayer a las 18:02" (hora de Chile). */
export function cuandoFue(iso: string | null): string {
  return iso ? cuando(iso, new Date().toISOString()) : "";
}

/**
 * Por que un boton esta desactivado: la otra solicitud sigue viva. El servidor
 * respondera lo mismo con un 409; esto evita el clic perdido.
 */
export function textoBloqueo(viva: EstadoActualizacion): string {
  // Las mismas palabras que el 409 del servidor (`_ocupado` en routers/actualizacion.py).
  const motor = tipoDe(viva) === "actualizar_motor";
  const estado = viva.estado === "pendiente" ? "esperando al computador del motor" : "en curso";
  const desde = viva.creado_en
    ? ` (${motor ? "pedida" : "pedido"} ${cuandoFue(viva.creado_en)})`
    : "";
  return motor
    ? `Hay una actualización del motor ${estado}${desde}. Tarda 1 a 2 minutos: cuando ` +
        "termine se puede recalcular."
    : `Hay un recálculo ${estado}${desde}. Tarda entre 25 y 40 minutos: cuando termine ` +
        "se puede actualizar el motor.";
}

export interface Buzon {
  /** La ultima solicitud, de cualquier tipo (null mientras carga o si fallo la lectura). */
  est: EstadoActualizacion | null;
  /** La solicitud pendiente o en curso, si hay una. Bloquea pedir otra. */
  viva: EstadoActualizacion | null;
  /** La API ya distingue tipos. Si no, "Actualizar motor" se convertiria en un recalculo. */
  conTipos: boolean;
  /** No se pudo leer el estado y no hay ninguno leido: se reintenta solo cada 15 s. */
  errorEstado: boolean;
  /** Lo que se esta pidiendo en este momento (el POST todavia no vuelve). */
  pidiendo: TipoActualizacion | null;
  /** Por tipo: por que fallo el ultimo pedido (403, sin servidor...). */
  error: Partial<Record<TipoActualizacion, string>>;
  /** Por tipo: el 409 del ultimo intento (habia otra solicitud viva). Lo muestra el
   *  dialogo de ese intento. */
  rechazo: Partial<Record<TipoActualizacion, string>>;
  /** Por que no se puede pedir `tipo` mientras dura `viva`. El texto del 409 solo si
   *  habla de esa misma solicitud en su mismo estado; si no, se arma con la de ahora.
   *  Un 409 viejo decia "en curso" y otra hora sobre una solicitud posterior. */
  motivoBloqueo: (tipo: TipoActualizacion, viva: EstadoActualizacion) => string;
  /** Deja pedido el trabajo. true si el servidor lo acepto. */
  pedir: (tipo: TipoActualizacion) => Promise<boolean>;
}

/** Cada cuanto se reintenta leer el estado si la lectura fallo y no hay ninguno. */
export const REINTENTO_ESTADO_MS = 15_000;

/** La solicitud viva y su estado: un 409 vale mientras sigan siendo los mismos. */
function claveViva(e: EstadoActualizacion | null): string | null {
  return e && (e.estado === "pendiente" || e.estado === "en_curso") ? `${e.id}|${e.estado}` : null;
}

interface Rechazo {
  texto: string;
  /** `claveViva` del estado leido justo despues del 409 (null si no se pudo leer). */
  de: string | null;
}

/** Estado del buzon y como pedir. Consulta cada 5 s solo mientras hay algo vivo. */
export function useBuzonActualizacion(): Buzon {
  const [est, setEst] = useState<EstadoActualizacion | null>(null);
  const [fallo, setFallo] = useState(false);
  const [pidiendo, setPidiendo] = useState<TipoActualizacion | null>(null);
  const [error, setError] = useState<Buzon["error"]>({});
  const [rechazos, setRechazos] = useState<Partial<Record<TipoActualizacion, Rechazo>>>({});

  const viva = est && (est.estado === "pendiente" || est.estado === "en_curso") ? est : null;
  const enMarcha = viva !== null;
  const errorEstado = est === null && fallo;

  const cargar = useCallback(async (): Promise<EstadoActualizacion | null> => {
    try {
      const leido = await api.actualizacionEstado();
      setEst(leido);
      setFallo(false);
      return leido;
    } catch {
      // El backend puede estar reiniciandose (deploy, cold start). Con algo vivo lo
      // repite la consulta de cada 5 s; sin nada leido, la de REINTENTO_ESTADO_MS.
      setFallo(true);
      return null;
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  // Solo se consulta seguido mientras hay algo en marcha: en reposo no tiene sentido
  // golpear la API cada 5 segundos desde todas las pestanias abiertas.
  useEffect(() => {
    if (!enMarcha) return;
    const id = setInterval(cargar, 5000);
    return () => clearInterval(id);
  }, [enMarcha, cargar]);

  // Si la primera lectura fallo no hay nada en marcha que la repita: sin esto,
  // "Actualizar motor" quedaba desactivado sin motivo hasta recargar la pagina.
  useEffect(() => {
    if (!errorEstado) return;
    const id = setInterval(cargar, REINTENTO_ESTADO_MS);
    return () => clearInterval(id);
  }, [errorEstado, cargar]);

  const pedir = useCallback(
    async (tipo: TipoActualizacion) => {
      setPidiendo(tipo);
      setError((e) => ({ ...e, [tipo]: undefined }));
      setRechazos((r) => ({ ...r, [tipo]: undefined }));
      try {
        setEst(await api.solicitarActualizacion(tipo));
        return true;
      } catch (e) {
        const mensaje = e instanceof Error ? e.message : "No se pudo pedir la actualización";
        // Otra persona (u otra pestania) pudo pedir algo que esta no conocia: se lee
        // el estado para mostrarlo y seguirlo.
        if ((e as { status?: number }).status === 409) {
          const leido = await cargar();
          setRechazos((r) => ({ ...r, [tipo]: { texto: mensaje, de: claveViva(leido) } }));
        } else {
          setError((prev) => ({ ...prev, [tipo]: mensaje }));
          void cargar();
        }
        return false;
      } finally {
        setPidiendo(null);
      }
    },
    [cargar]
  );

  const rechazo: Buzon["rechazo"] = {
    recalcular: rechazos.recalcular?.texto,
    actualizar_motor: rechazos.actualizar_motor?.texto,
  };
  const motivoBloqueo = (tipo: TipoActualizacion, v: EstadoActualizacion) => {
    const r = rechazos[tipo];
    return r && r.de !== null && r.de === claveViva(v) ? r.texto : textoBloqueo(v);
  };

  return {
    est, viva, conTipos: est !== null && "tipo" in est, errorEstado, pidiendo, error, rechazo,
    motivoBloqueo, pedir,
  };
}

/** "Actualizar ahora" con su propio estado. Es la de la portada. */
export function SincronizacionManual({ compacto = false }: { compacto?: boolean }) {
  const buzon = useBuzonActualizacion();
  return <ActualizarAhora buzon={buzon} compacto={compacto} />;
}

/** "Actualizar ahora" sobre un buzon compartido (en /cargar, con "Actualizar motor"). */
export function ActualizarAhora({ buzon, compacto = false }: { buzon: Buzon; compacto?: boolean }) {
  const { est, viva, pidiendo } = buzon;
  const mia = tipoDe(est) === "recalcular";
  const enCursoMia = viva !== null && mia;
  const bloqueada = viva !== null && !mia;
  const error = buzon.error.recalcular;

  const boton = (
    <button
      type="button"
      onClick={() => void buzon.pedir("recalcular")}
      disabled={pidiendo !== null || viva !== null}
      aria-describedby={bloqueada ? "bloqueo-recalcular" : undefined}
      className="inline-flex items-center gap-2 rounded-sm bg-ink-900 px-4 py-2 text-[13px] font-semibold uppercase tracking-wider text-paper transition-colors hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {pidiendo === "recalcular" || enCursoMia ? (
        <>
          <Loader2 size={14} className="animate-spin" aria-hidden="true" /> Actualizando…
        </>
      ) : (
        <>
          <RefreshCw size={14} aria-hidden="true" /> Actualizar ahora
        </>
      )}
    </button>
  );

  const avisos = (
    <>
      {enCursoMia && est?.estado === "pendiente" && (
        <p role="status" className="rounded-sm bg-brand-50 px-3 py-2 text-[12px] text-brand-800">
          Pedido enviado. Esperando al computador que calcula el sugerido…
        </p>
      )}

      {enCursoMia && est?.estado === "en_curso" && (
        <p role="status" className="rounded-sm bg-brand-50 px-3 py-2 text-[12px] text-brand-800">
          Recalculando con los Excel de las carpetas de <b>Fuentes de datos</b>. Tarda entre
          25 y 40 minutos
          {minutosDesde(est.creado_en) > 0 && ` (van ${minutosDesde(est.creado_en)})`}. Puedes
          cerrar esta página: el trabajo sigue igual.
        </p>
      )}

      {/* La otra solicitud sigue viva: el texto del 409 si el servidor lo dio sobre
          esta misma solicitud, o el mismo motivo armado aca para no esperar al clic
          perdido. */}
      {bloqueada && viva && (
        <p
          id="bloqueo-recalcular"
          role="status"
          className="rounded-sm bg-paper-100 px-3 py-2 text-[12px] text-ink-700"
        >
          {buzon.motivoBloqueo("recalcular", viva)}
        </p>
      )}

      {!viva && mia && est?.estado === "ok" && (
        <p role="status" className="inline-flex items-start gap-1.5 rounded-sm bg-emerald-50 px-3 py-2 text-[12.5px] font-medium text-emerald-700">
          <CheckCircle2 size={14} className="mt-px shrink-0" aria-hidden="true" />
          <span>Listo — el equipo ya ve los datos actualizados. {est.mensaje}</span>
        </p>
      )}

      {!viva && mia && (est?.estado === "error" || est?.estado === "expirada") && (
        <p role="alert" className="inline-flex items-start gap-1.5 rounded-sm bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          <AlertTriangle size={14} className="mt-px shrink-0" aria-hidden="true" />
          <span>{est.mensaje ?? "La actualización no se pudo completar."}</span>
        </p>
      )}

      {error && (
        <p role="alert" className="rounded-sm bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          {error}
        </p>
      )}
    </>
  );

  // Quien no tiene permiso no ve el boton (el gate real es el 403 del servidor).
  if (est && !est.puede_actualizar) return null;

  if (compacto) {
    return (
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-sm border border-accent-700/20 bg-white px-3 py-2">
        {boton}
        <span className="text-[12px] text-ink-600">
          <span className="kicker">Datos al</span>{" "}
          {est?.ultima_sincronizacion ? (
            <>
              <b className="font-mono">{formatoFechaHora(est.ultima_sincronizacion)}</b>{" "}
              <span className="text-ink-500">({tiempoRelativo(est.ultima_sincronizacion)})</span>
            </>
          ) : (
            <span className="text-ink-500">sin registros aún</span>
          )}
        </span>
        <div className="w-full space-y-2 empty:hidden">{avisos}</div>
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-3 rounded-sm border border-accent-700/20 bg-white p-3">
      <div>
        <p className="kicker">Actualizar ahora</p>
        <p className="mt-1.5 text-[12.5px] text-ink-700">
          Si la tarea de las 09:30 no corrió, esto la ejecuta a mano: el motor recalcula
          con los Excel de las carpetas de <b>Fuentes de datos</b> y publica para todo el
          equipo. Tarda entre 25 y 40 minutos.
        </p>
      </div>

      {boton}

      <div className="flex flex-wrap items-center gap-3 text-[12px]">
        <span className="kicker">Última actualización</span>
        {est?.ultima_sincronizacion ? (
          <span className="text-ink-700">
            <b className="font-mono">{formatoFechaHora(est.ultima_sincronizacion)}</b>{" "}
            <span className="text-ink-500">({tiempoRelativo(est.ultima_sincronizacion)})</span>
          </span>
        ) : (
          <span className="text-ink-500">sin registros aún</span>
        )}
      </div>

      {avisos}

      <p className="text-[11px] text-ink-500">
        El cálculo corre en el computador donde están los Excel. Si está apagado o sin
        sesión iniciada, el pedido caduca a los 5 minutos y esta tarjeta lo avisa.
      </p>
    </div>
  );
}
