"use client";

// Boton para correr la actualizacion a mano cuando la tarea automatica no corrio.
//
// El motor vive en el PC del administrador (lee los Excel de "Bases de datos"), no
// en la nube, asi que el servidor no puede lanzarlo. El puente es el protocolo
// `sugerido://` registrado en Windows, que abre el script del motor. Por eso este
// boton SOLO hace algo en ese PC; en cualquier otro no pasa nada.
import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, Loader2, RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoFechaHora } from "@/lib/formato";

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

export function SincronizacionManual() {
  const [ultimaSync, setUltimaSync] = useState<string | null>(null);
  const [esperando, setEsperando] = useState(false);
  const [exitoReciente, setExitoReciente] = useState(false);
  const [expiro, setExpiro] = useState(false);
  const refUltima = useRef<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      const r = await api.ultimaSincronizacion();
      setUltimaSync(r.creado_en);
      refUltima.current = r.creado_en;
    } catch {
      /* silent */
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  // Tras el click se espera a que cambie el sello de "datos actualizados". El motor
  // tarda ~3 min en leer los Excel y calcular, asi que se espera hasta 8.
  const onClickSincronizar = () => {
    setEsperando(true);
    setExitoReciente(false);
    setExpiro(false);
    const antes = refUltima.current;
    const inicio = Date.now();

    const interval = setInterval(async () => {
      try {
        const r = await api.ultimaSincronizacion();
        if (r.creado_en && r.creado_en !== antes) {
          setUltimaSync(r.creado_en);
          refUltima.current = r.creado_en;
          setEsperando(false);
          setExitoReciente(true);
          clearInterval(interval);
          setTimeout(() => setExitoReciente(false), 10000);
          return;
        }
      } catch {
        /* silent */
      }
      if (Date.now() - inicio > 480_000) {
        setEsperando(false);
        setExpiro(true);
        clearInterval(interval);
      }
    }, 5000);
  };

  return (
    <div className="mt-4 rounded-sm border border-accent-700/20 bg-white p-3">
      <p className="kicker">Actualizar ahora</p>
      <p className="mt-1.5 mb-3 text-[12.5px] text-ink-700">
        Si la tarea de las 10:00 no corrió, esto la ejecuta a mano: el motor recalcula
        con los Excel de <b>Bases de datos</b> y publica. Tarda unos 3 minutos.
      </p>

      <a
        href="sugerido://sync"
        onClick={onClickSincronizar}
        className="inline-flex items-center gap-2 rounded-sm bg-ink-900 px-4 py-2 text-[13px] font-semibold uppercase tracking-wider text-paper transition-colors hover:bg-accent-700"
      >
        {esperando ? (
          <>
            <Loader2 size={14} className="animate-spin" /> Actualizando…
          </>
        ) : (
          <>
            <RefreshCw size={14} /> Actualizar ahora
          </>
        )}
      </a>

      <div className="mt-3 flex flex-wrap items-center gap-3 text-[12px]">
        <span className="kicker">Última actualización</span>
        {ultimaSync ? (
          <span className="text-ink-700">
            <b className="font-mono">{formatoFechaHora(ultimaSync)}</b>{" "}
            <span className="text-ink-500">({tiempoRelativo(ultimaSync)})</span>
          </span>
        ) : (
          <span className="text-ink-500">sin registros aún</span>
        )}
      </div>

      {esperando && (
        <p className="mt-2 rounded-sm bg-brand-50 px-3 py-2 text-[12px] text-brand-800">
          Se abrió una ventana en el PC del administrador: escribe <b>SI</b> para
          confirmar. Cuando termine, esta tarjeta se actualiza sola.
        </p>
      )}

      {exitoReciente && (
        <p className="mt-2 inline-flex items-center gap-1.5 rounded-sm bg-emerald-50 px-3 py-2 text-[12.5px] font-medium text-emerald-700">
          <CheckCircle2 size={14} /> Listo — el equipo ya ve los datos actualizados.
        </p>
      )}

      {expiro && (
        <p className="mt-2 rounded-sm bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          No llegó la confirmación en 8 minutos. Revisa la ventana de PowerShell en el
          PC del administrador (puede haber pedido confirmación o dado un error).
        </p>
      )}

      <p className="mt-3 text-[11px] text-ink-500">
        Solo funciona desde el PC del administrador, que es donde corre el motor.
      </p>
    </div>
  );
}
