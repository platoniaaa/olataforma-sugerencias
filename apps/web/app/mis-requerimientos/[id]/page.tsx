"use client";

/**
 * Un requerimiento visto por el vendedor: de solo lectura.
 *
 * Muestra lo que pidió y, si el comprador ya lo revisó, lo que aprobó de cada
 * línea. Cuando la cantidad aprobada difiere de la pedida se dice explícito: que
 * el vendedor se entere al recibir la caja es peor que decírselo acá.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";
import { EstadoRequerimientoBadge } from "@/components/estado-requerimiento";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { Requerimiento } from "@/lib/types";

export default function MiRequerimientoPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params?.id);
  const [req, setReq] = useState<Requerimiento | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    api
      .requerimiento(id)
      .then(setReq)
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudo cargar"));
  }, [id]);

  if (error) {
    return (
      <div className="rounded-sm border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
        {error}
      </div>
    );
  }
  if (!req) {
    return (
      <div className="flex items-center gap-2 px-4 py-10 text-[13.5px] text-ink-400">
        <Loader2 size={15} className="animate-spin" /> Cargando…
      </div>
    );
  }

  const revisado = req.estado === "procesado" || req.estado === "rechazado";

  return (
    <div className="space-y-5">
      <div>
        <Link
          href="/mis-requerimientos"
          className="inline-flex items-center gap-1 text-[13px] text-ink-500 hover:text-accent-700"
        >
          <ArrowLeft size={14} /> Mis requerimientos
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="display text-[30px] leading-tight">Requerimiento #{req.id}</h1>
          <EstadoRequerimientoBadge estado={req.estado} />
        </div>
        <p className="mt-1 text-[13.5px] text-ink-500">
          {req.nombre_sucursal} · enviado el {formatoFechaHora(req.creado_en)}
          {req.revisado_en && ` · revisado el ${formatoFechaHora(req.revisado_en)}`}
        </p>
      </div>

      {req.nota && (
        <div className="rounded-sm border border-ink-200 bg-paper-50 px-4 py-3 text-[13px]">
          <p className="text-[11.5px] uppercase tracking-wide text-ink-400">Tu nota</p>
          <p className="mt-1 text-ink-700">{req.nota}</p>
        </div>
      )}

      {req.nota_comprador && (
        <div
          className={`rounded-sm border px-4 py-3 text-[13px] ${
            req.estado === "rechazado"
              ? "border-red-200 bg-red-50 text-red-900"
              : "border-emerald-200 bg-emerald-50 text-emerald-900"
          }`}
        >
          <p className="text-[11.5px] uppercase tracking-wide opacity-70">
            Respuesta del comprador
          </p>
          <p className="mt-1">{req.nota_comprador}</p>
        </div>
      )}

      <div className="overflow-x-auto rounded-sm border border-ink-200 bg-white shadow-card">
        <table className="w-full min-w-[720px] text-[13px]">
          <thead>
            <tr className="border-b border-ink-200 bg-paper-50 text-left text-[11.5px] uppercase tracking-wide text-ink-500">
              <th className="px-3 py-2">Código</th>
              <th className="px-3 py-2">Descripción</th>
              <th className="px-3 py-2 text-right">Pediste</th>
              {revisado && <th className="px-3 py-2 text-right">Te aprobaron</th>}
              <th className="px-3 py-2 text-right">Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {req.lineas.map((l) => {
              const aprobada = l.cantidad_aprobada;
              const recortada = revisado && aprobada !== null && aprobada < l.cantidad_pedida;
              return (
                <tr key={l.id} className="border-b border-ink-100">
                  <td className="px-3 py-2 font-mono font-medium">{l.producto}</td>
                  <td className="max-w-[320px] truncate px-3 py-2 text-ink-600">
                    {l.descripcion ?? "—"}
                    {l.comentario && (
                      <span className="block text-[12px] text-ink-400">{l.comentario}</span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular">
                    {formatoNumero(l.cantidad_pedida)}
                  </td>
                  {revisado && (
                    <td
                      className={`px-3 py-2 text-right tabular ${
                        recortada ? "font-medium text-amber-700" : ""
                      }`}
                    >
                      {aprobada === null ? (
                        <span className="text-ink-300">—</span>
                      ) : (
                        formatoNumero(aprobada)
                      )}
                      {aprobada === 0 && (
                        <span className="ml-1 text-[11.5px] text-red-700">no va</span>
                      )}
                    </td>
                  )}
                  <td className="px-3 py-2 text-right tabular text-ink-600">
                    {formatoCLP(
                      (aprobada ?? l.cantidad_pedida) * (l.precio_lista ?? 0)
                    )}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="bg-paper-50 text-[13px] font-medium">
              <td className="px-3 py-2" colSpan={revisado ? 4 : 3}>
                Total
              </td>
              <td className="px-3 py-2 text-right tabular">
                {formatoCLP(req.total_estimado ?? 0)}
              </td>
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
