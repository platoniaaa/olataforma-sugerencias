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
import { useRouter } from "next/navigation";
import { Inbox, Loader2, Plus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EstadoRequerimientoBadge } from "@/components/estado-requerimiento";
import { api } from "@/lib/api-client";
import { filaNavegable } from "@/lib/tabla";
import { formatoCLP, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { Requerimiento } from "@/lib/types";

export default function MisRequerimientosPage() {
  const router = useRouter();
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
      <div className="flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-end sm:justify-between">
        <div>
          <p className="kicker">Sucursal</p>
          <h1 className="display text-[24px] leading-tight sm:text-[30px]">Mis requerimientos</h1>
          <p className="mt-1 text-[13.5px] text-ink-500">
            Todo lo que le pediste al comprador y en qué quedó cada uno.
          </p>
        </div>
        <Link href="/mis-requerimientos/nuevo" className="block w-full sm:w-auto">
          <Button className="h-11 w-full sm:h-9 sm:w-auto">
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
        <>
          {/* Celular: una tarjeta por requerimiento. Una tabla de 6 columnas en
              375px obliga a scroll lateral, y el vendedor entra desde el mesón. */}
          <ul className="space-y-2 sm:hidden">
            {items.map((r) => (
              <li key={r.id}>
                <Link
                  href={`/mis-requerimientos/${r.id}`}
                  className="block rounded-sm border border-ink-200 bg-white p-3 shadow-card transition-colors active:bg-paper-50"
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-medium text-accent-700">#{r.id}</span>
                    <EstadoRequerimientoBadge estado={r.estado} />
                  </div>
                  <p className="mt-1 text-[13px] text-ink-600">
                    {formatoNumero(r.n_lineas)}{" "}
                    {r.n_lineas === 1 ? "repuesto" : "repuestos"} ·{" "}
                    <span className="tabular">{formatoCLP(r.total_estimado ?? 0)}</span>
                  </p>
                  <p className="mt-0.5 text-[12px] text-ink-400">
                    {formatoFechaHora(r.creado_en)}
                  </p>
                  {r.nota_comprador && (
                    <p className="mt-1.5 border-t border-ink-100 pt-1.5 text-[12.5px] text-ink-600">
                      {r.nota_comprador}
                    </p>
                  )}
                </Link>
              </li>
            ))}
          </ul>

          {/* Escritorio: la tabla de siempre. */}
          <div className="hidden overflow-x-auto rounded-sm border border-ink-200 bg-white shadow-card sm:block">
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
                  <tr
                    key={r.id}
                    onClick={filaNavegable(() => router.push(`/mis-requerimientos/${r.id}`))}
                    className="cursor-pointer border-b border-ink-100 hover:bg-paper-50"
                  >
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
        </>
      )}
    </div>
  );
}
