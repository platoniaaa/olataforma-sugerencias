"use client";

// Boton "Actualizar ahora": recalcula el sugerido con los Excel de "Bases de datos".
//
// El motor no corre en la nube -necesita los Excel, que viven en un PC de la empresa-,
// asi que este boton NO recalcula: deja pedido el trabajo en la plataforma. Un agente
// instalado en ese PC lo toma en menos de un minuto, corre el motor (~3 min) y reporta
// el resultado, que es lo que esta tarjeta va mostrando.
//
// Por eso el boton sirve desde cualquier equipo o telefono. Antes abria el protocolo
// `sugerido://`, que solo funcionaba sentado frente al PC del administrador.
import { useCallback, useEffect, useState } from "react";
import { AlertTriangle, CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoFechaHora } from "@/lib/formato";
import type { EstadoActualizacion } from "@/lib/types";

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

function minutosDesde(iso: string | null): number {
  if (!iso) return 0;
  return Math.floor(Math.max(0, Date.now() - new Date(iso).getTime()) / 60000);
}

export function SincronizacionManual({ compacto = false }: { compacto?: boolean }) {
  const [est, setEst] = useState<EstadoActualizacion | null>(null);
  const [pidiendo, setPidiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const enMarcha = est?.estado === "pendiente" || est?.estado === "en_curso";

  const cargar = useCallback(async () => {
    try {
      setEst(await api.actualizacionEstado());
    } catch {
      /* el backend puede estar despertando (cold start); se reintenta al siguiente ciclo */
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Solo se consulta seguido mientras hay algo en marcha: en reposo no tiene sentido
  // golpear la API cada 5 segundos desde todas las pestanias abiertas.
  useEffect(() => {
    if (!enMarcha) return;
    const id = setInterval(cargar, 5000);
    return () => clearInterval(id);
  }, [enMarcha, cargar]);

  const pedir = async () => {
    setPidiendo(true);
    setError(null);
    try {
      setEst(await api.solicitarActualizacion());
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo pedir la actualización");
    } finally {
      setPidiendo(false);
    }
  };

  const boton = (
    <button
      type="button"
      onClick={pedir}
      disabled={pidiendo || enMarcha}
      className="inline-flex items-center gap-2 rounded-sm bg-ink-900 px-4 py-2 text-[13px] font-semibold uppercase tracking-wider text-paper transition-colors hover:bg-accent-700 disabled:cursor-not-allowed disabled:opacity-60"
    >
      {pidiendo || enMarcha ? (
        <>
          <Loader2 size={14} className="animate-spin" /> Actualizando…
        </>
      ) : (
        <>
          <RefreshCw size={14} /> Actualizar ahora
        </>
      )}
    </button>
  );

  const avisos = (
    <>
      {est?.estado === "pendiente" && (
        <p className="rounded-sm bg-brand-50 px-3 py-2 text-[12px] text-brand-800">
          Pedido enviado. Esperando al computador que calcula el sugerido…
        </p>
      )}

      {est?.estado === "en_curso" && (
        <p className="rounded-sm bg-brand-50 px-3 py-2 text-[12px] text-brand-800">
          Recalculando con los Excel de <b>Bases de datos</b>. Tarda unos 3 minutos
          {minutosDesde(est.creado_en) > 0 && ` (van ${minutosDesde(est.creado_en)})`}. Puedes
          cerrar esta página: el trabajo sigue igual.
        </p>
      )}

      {est?.estado === "ok" && (
        <p className="inline-flex items-start gap-1.5 rounded-sm bg-emerald-50 px-3 py-2 text-[12.5px] font-medium text-emerald-700">
          <CheckCircle2 size={14} className="mt-px shrink-0" />
          <span>Listo — el equipo ya ve los datos actualizados. {est.mensaje}</span>
        </p>
      )}

      {(est?.estado === "error" || est?.estado === "expirada") && (
        <p className="inline-flex items-start gap-1.5 rounded-sm bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          <AlertTriangle size={14} className="mt-px shrink-0" />
          <span>{est.mensaje ?? "La actualización no se pudo completar."}</span>
        </p>
      )}

      {error && (
        <p className="rounded-sm bg-amber-50 px-3 py-2 text-[12px] text-amber-800">{error}</p>
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
        <div className="w-full empty:hidden">{avisos}</div>
      </div>
    );
  }

  return (
    <div className="mt-4 space-y-3 rounded-sm border border-accent-700/20 bg-white p-3">
      <div>
        <p className="kicker">Actualizar ahora</p>
        <p className="mt-1.5 text-[12.5px] text-ink-700">
          Si la tarea de las 10:00 no corrió, esto la ejecuta a mano: el motor recalcula
          con los Excel de <b>Bases de datos</b> y publica para todo el equipo. Tarda unos
          3 minutos.
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
        El cálculo corre en el computador donde están los Excel. Si está apagado, el
        pedido caduca y esta tarjeta lo avisa.
      </p>
    </div>
  );
}
