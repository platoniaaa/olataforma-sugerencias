"use client";

/**
 * Lo que el vendedor mandó y en qué quedó.
 *
 * Es la mitad que el correo nunca dio: saber si lo leyeron, si lo compraron o si
 * lo rechazaron y por qué. Sin esto el vendedor termina llamando por teléfono,
 * que es el problema que se está resolviendo.
 */

import { useEffect, useState } from "react";
import Link from "next/link";
import { Inbox, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EstadoRequerimientoBadge } from "@/components/estado-requerimiento";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { Requerimiento } from "@/lib/types";

export default function MisRequerimientosPage() {
  const [items, setItems] = useState<Requerimiento[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .requerimientos()
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudo cargar"));
  }, []);

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="kicker">Sucursal</p>
          <h1 className="display text-[30px] leading-tight">Mis requerimientos</h1>
          <p className="mt-1 text-[13.5px] text-ink-500">
            Todo lo que le pediste al comprador y en qué quedó cada uno.
          </p>
        </div>
        <Link href="/mis-requerimientos/nuevo">
          <Button>
            <Plus size={15} /> Nuevo requerimiento
          </Button>
        </Link>
      </div>

      {error && (
        <div className="rounded-sm border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
          {error}
        </div>
      )}

      {items === null && !error && (
        <div className="flex items-center gap-2 px-4 py-10 text-[13.5px] text-ink-400">
          <Loader2 size={15} className="animate-spin" /> Cargando…
        </div>
      )}

      {items !== null && items.length === 0 && (
        <div className="rounded-sm border border-ink-200 bg-white px-4 py-14 text-center shadow-card">
          <Inbox size={28} className="mx-auto text-ink-300" />
          <p className="mt-3 text-[14px] font-medium text-ink-700">
            Todavía no has enviado ninguno
          </p>
          <p className="mt-1 text-[13px] text-ink-400">
            Arma tu primera lista y el comprador la recibe al tiro.
          </p>
          <Link href="/mis-requerimientos/nuevo" className="mt-4 inline-block">
            <Button>
              <Plus size={15} /> Nuevo requerimiento
            </Button>
          </Link>
        </div>
      )}

      {items !== null && items.length > 0 && (
        <div className="overflow-x-auto rounded-sm border border-ink-200 bg-white shadow-card">
          <table className="w-full min-w-[720px] text-[13px]">
            <thead>
              <tr className="border-b border-ink-200 bg-paper-50 text-left text-[11.5px] uppercase tracking-wide text-ink-500">
                <th className="px-3 py-2">N°</th>
                <th className="px-3 py-2">Enviado</th>
                <th className="px-3 py-2 text-right">Repuestos</th>
                <th className="px-3 py-2 text-right">Total aprox.</th>
                <th className="px-3 py-2">Estado</th>
                <th className="px-3 py-2">Respuesta del comprador</th>
              </tr>
            </thead>
            <tbody>
              {items.map((r) => (
                <tr key={r.id} className="border-b border-ink-100 hover:bg-paper-50">
                  <td className="px-3 py-2">
                    <Link
                      href={`/mis-requerimientos/${r.id}`}
                      className="font-medium text-accent-700 hover:underline"
                    >
                      #{r.id}
                    </Link>
                  </td>
                  <td className="px-3 py-2 text-ink-600">{formatoFechaHora(r.creado_en)}</td>
                  <td className="px-3 py-2 text-right tabular">{formatoNumero(r.n_lineas)}</td>
                  <td className="px-3 py-2 text-right tabular">
                    {formatoCLP(r.total_estimado ?? 0)}
                  </td>
                  <td className="px-3 py-2">
                    <EstadoRequerimientoBadge estado={r.estado} />
                  </td>
                  <td className="max-w-[280px] truncate px-3 py-2 text-ink-500">
                    {r.nota_comprador ?? <span className="text-ink-300">—</span>}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
