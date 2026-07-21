"use client";

// Modal para reportar un problema de la plataforma. Se abre desde donde el
// usuario vio la falla, asi el contexto (pantalla, producto, sucursal) viaja
// solo y quien revisa no tiene que adivinar de que se trataba.
import { useState } from "react";
import { AlertCircle, Check, X } from "lucide-react";
import { api } from "@/lib/api-client";

interface Props {
  abierto: boolean;
  onCerrar: () => void;
  /** Contexto opcional: si se pasa, se envia con el reporte. */
  producto?: string | null;
  sucursalId?: string | null;
  pantalla?: string | null;
  onEnviada?: () => void;
}

export function ModalIncidencia({
  abierto,
  onCerrar,
  producto,
  sucursalId,
  pantalla,
  onEnviada,
}: Props) {
  const [titulo, setTitulo] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [enviando, setEnviando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [listo, setListo] = useState(false);

  if (!abierto) return null;

  const cerrar = () => {
    setTitulo("");
    setDescripcion("");
    setError(null);
    setListo(false);
    onCerrar();
  };

  const enviar = async () => {
    setEnviando(true);
    setError(null);
    try {
      await api.crearIncidencia({
        titulo: titulo.trim(),
        descripcion: descripcion.trim() || null,
        producto: producto ?? null,
        sucursal_id: sucursalId ?? null,
        pantalla:
          pantalla ?? (typeof window !== "undefined" ? window.location.pathname : null),
      });
      setListo(true);
      onEnviada?.();
      setTimeout(cerrar, 1400);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      <div className="absolute inset-0 bg-ink-900/40 backdrop-blur-sm" onClick={cerrar} />
      <div className="relative w-full max-w-lg rounded-xl border border-slate-200 bg-white p-5 shadow-xl">
        <div className="mb-3 flex items-start justify-between">
          <div>
            <h2 className="flex items-center gap-2 text-[15px] font-semibold text-slate-900">
              <AlertCircle size={17} className="text-accent-700" /> Reportar un problema
            </h2>
            <p className="mt-0.5 text-[12px] text-slate-500">
              Contanos qué viste raro. Queda registrado con la pantalla
              {producto ? " y el producto" : ""} para poder revisarlo.
            </p>
          </div>
          <button
            onClick={cerrar}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
            aria-label="Cerrar"
          >
            <X size={16} />
          </button>
        </div>

        {listo ? (
          <p className="flex items-center gap-2 rounded-md bg-emerald-50 px-3 py-3 text-[13px] text-emerald-800">
            <Check size={16} /> Reporte enviado. Te avisamos cuando lo revisemos.
          </p>
        ) : (
          <>
            {(producto || sucursalId) && (
              <p className="mb-3 rounded-md bg-slate-50 px-3 py-2 text-[12px] text-slate-600">
                Se adjunta: {producto && <strong>{producto}</strong>}
                {producto && sucursalId && " · "}
                {sucursalId && <strong>{sucursalId}</strong>}
              </p>
            )}
            <label className="mb-3 block">
              <span className="mb-1 block text-[12px] font-medium text-slate-600">
                ¿Qué pasó? *
              </span>
              <input
                value={titulo}
                onChange={(e) => setTitulo(e.target.value)}
                placeholder="El sugerido no considera el stock del CD"
                autoFocus
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px] focus:border-brand focus:outline-none"
              />
            </label>
            <label className="mb-3 block">
              <span className="mb-1 block text-[12px] font-medium text-slate-600">
                Detalle (opcional)
              </span>
              <textarea
                value={descripcion}
                onChange={(e) => setDescripcion(e.target.value)}
                rows={4}
                placeholder="Qué esperabas ver, qué viste, y cualquier dato que ayude a reproducirlo."
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px] focus:border-brand focus:outline-none"
              />
            </label>
            {error && (
              <p className="mb-2 rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">
                {error}
              </p>
            )}
            <div className="flex justify-end gap-2">
              <button
                onClick={cerrar}
                className="rounded-md border border-slate-200 px-3 py-1.5 text-[13px] hover:bg-slate-50"
              >
                Cancelar
              </button>
              <button
                onClick={enviar}
                disabled={enviando || !titulo.trim()}
                className="rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
              >
                {enviando ? "Enviando…" : "Enviar reporte"}
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
