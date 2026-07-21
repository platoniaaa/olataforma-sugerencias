"use client";

// Mesa de incidencias: cada usuario ve sus reportes; el admin ve todos y los
// gestiona (revisar, responder, cerrar).
import { useEffect, useState } from "react";
import Link from "next/link";
import { AlertCircle, Plus, RefreshCw } from "lucide-react";
import { api } from "@/lib/api-client";
import { getEsAdmin } from "@/lib/auth";
import { formatoFechaHora } from "@/lib/formato";
import { ModalIncidencia } from "@/components/modal-incidencia";
import type { EstadoIncidencia, Incidencia } from "@/lib/types";

const ESTADOS: Record<EstadoIncidencia, { label: string; clase: string }> = {
  abierta: { label: "Abierta", clase: "bg-amber-50 text-amber-800" },
  en_revision: { label: "En revisión", clase: "bg-blue-50 text-blue-800" },
  resuelta: { label: "Resuelta", clase: "bg-emerald-50 text-emerald-800" },
  descartada: { label: "Descartada", clase: "bg-slate-100 text-slate-600" },
};

export default function IncidenciasPage() {
  const esAdmin = getEsAdmin();
  const [items, setItems] = useState<Incidencia[]>([]);
  const [abiertas, setAbiertas] = useState(0);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [modal, setModal] = useState(false);
  const [respondiendo, setRespondiendo] = useState<string | null>(null);
  const [respuesta, setRespuesta] = useState("");

  const cargar = async () => {
    setCargando(true);
    setError(null);
    try {
      const r = await api.incidencias();
      setItems(r.items);
      setAbiertas(r.abiertas);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    cargar();
  }, []);

  const cambiarEstado = async (inc: Incidencia, estado: EstadoIncidencia) => {
    try {
      await api.actualizarIncidencia(inc.id, { estado });
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo actualizar");
    }
  };

  const enviarRespuesta = async (inc: Incidencia) => {
    try {
      await api.actualizarIncidencia(inc.id, {
        respuesta: respuesta.trim(),
        estado: "resuelta",
      });
      setRespondiendo(null);
      setRespuesta("");
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo responder");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">Incidencias</h1>
          <p className="text-[13px] text-slate-500">
            {cargando
              ? "Cargando…"
              : esAdmin
                ? `${items.length} reportes · ${abiertas} sin cerrar`
                : "Tus reportes y su estado"}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setModal(true)}
            className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700"
          >
            <Plus size={14} /> Reportar problema
          </button>
          <button
            onClick={cargar}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[13px] hover:bg-slate-50"
          >
            <RefreshCw size={14} /> Actualizar
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
      )}

      {!cargando && items.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center">
          <AlertCircle className="mx-auto mb-2 text-slate-300" size={28} />
          <p className="text-[13px] text-slate-500">
            No hay reportes. Si ves algo raro en la plataforma, usa “Reportar problema”.
          </p>
        </div>
      ) : (
        <ul className="space-y-2">
          {items.map((inc) => {
            const meta = ESTADOS[inc.estado] ?? ESTADOS.abierta;
            return (
              <li
                key={inc.id}
                className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm"
              >
                <div className="flex flex-wrap items-start justify-between gap-2">
                  <div className="min-w-0">
                    <p className="text-[14px] font-medium text-slate-900">{inc.titulo}</p>
                    {inc.descripcion && (
                      <p className="mt-1 whitespace-pre-wrap text-[13px] text-slate-600">
                        {inc.descripcion}
                      </p>
                    )}
                    <p className="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1 text-[11px] text-slate-500">
                      <span>{formatoFechaHora(inc.creado_en)}</span>
                      {inc.reportado_por && <span>· {inc.reportado_por}</span>}
                      {inc.producto && (
                        <>
                          <span>·</span>
                          <Link
                            href={`/producto/${encodeURIComponent(inc.producto)}${
                              inc.sucursal_id
                                ? `?sucursal=${encodeURIComponent(inc.sucursal_id)}`
                                : ""
                            }`}
                            className="text-brand hover:underline"
                          >
                            {inc.producto}
                            {inc.sucursal_id ? ` · ${inc.sucursal_id}` : ""}
                          </Link>
                        </>
                      )}
                      {inc.pantalla && <span>· {inc.pantalla}</span>}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded px-2 py-0.5 text-[11px] font-semibold ${meta.clase}`}
                  >
                    {meta.label}
                  </span>
                </div>

                {inc.respuesta && (
                  <div className="mt-3 rounded-md border-l-2 border-brand bg-slate-50 px-3 py-2">
                    <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">
                      Respuesta
                    </p>
                    <p className="mt-0.5 whitespace-pre-wrap text-[13px] text-slate-700">
                      {inc.respuesta}
                    </p>
                  </div>
                )}

                {esAdmin && (
                  <div className="mt-3 border-t border-slate-100 pt-2">
                    {respondiendo === inc.id ? (
                      <div className="space-y-2">
                        <textarea
                          value={respuesta}
                          onChange={(e) => setRespuesta(e.target.value)}
                          rows={3}
                          autoFocus
                          placeholder="Qué se encontró y qué se hizo."
                          className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px] focus:border-brand focus:outline-none"
                        />
                        <div className="flex justify-end gap-2">
                          <button
                            onClick={() => setRespondiendo(null)}
                            className="rounded-md border border-slate-200 px-3 py-1 text-[12px] hover:bg-slate-50"
                          >
                            Cancelar
                          </button>
                          <button
                            onClick={() => enviarRespuesta(inc)}
                            disabled={!respuesta.trim()}
                            className="rounded-md bg-brand px-3 py-1 text-[12px] font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                          >
                            Responder y cerrar
                          </button>
                        </div>
                      </div>
                    ) : (
                      <div className="flex flex-wrap gap-2">
                        {inc.estado !== "en_revision" && inc.estado === "abierta" && (
                          <button
                            onClick={() => cambiarEstado(inc, "en_revision")}
                            className="rounded-md border border-slate-200 px-2.5 py-1 text-[12px] hover:bg-slate-50"
                          >
                            Marcar en revisión
                          </button>
                        )}
                        {inc.estado !== "resuelta" && (
                          <button
                            onClick={() => {
                              setRespondiendo(inc.id);
                              setRespuesta(inc.respuesta ?? "");
                            }}
                            className="rounded-md border border-slate-200 px-2.5 py-1 text-[12px] hover:bg-slate-50"
                          >
                            Responder y cerrar
                          </button>
                        )}
                        {inc.estado !== "descartada" && inc.estado !== "resuelta" && (
                          <button
                            onClick={() => cambiarEstado(inc, "descartada")}
                            className="rounded-md border border-slate-200 px-2.5 py-1 text-[12px] text-slate-500 hover:bg-slate-50"
                          >
                            Descartar
                          </button>
                        )}
                      </div>
                    )}
                  </div>
                )}
              </li>
            );
          })}
        </ul>
      )}

      <ModalIncidencia abierto={modal} onCerrar={() => setModal(false)} onEnviada={cargar} />
    </div>
  );
}
