"use client";

/**
 * Bandeja del comprador: lo que le pidieron las sucursales.
 *
 * Reemplaza la carpeta de correos. Lo que no está revisado va primero y se ve
 * distinto, porque el costo real acá es que un requerimiento se quede sin
 * responder y la sucursal se entere recién cuando llama.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { ClipboardPaste, Inbox, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EstadoRequerimientoBadge } from "@/components/estado-requerimiento";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { Requerimiento } from "@/lib/types";

type Filtro = "pendientes" | "todos";

export default function RequerimientosPage() {
  const [items, setItems] = useState<Requerimiento[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [filtro, setFiltro] = useState<Filtro>("pendientes");

  useEffect(() => {
    api
      .requerimientos()
      .then((r) => setItems(r.items))
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudo cargar"));
  }, []);

  const pendientes = useMemo(
    () => (items ?? []).filter((r) => r.estado === "enviado" || r.estado === "en_revision"),
    [items]
  );
  const visibles = filtro === "pendientes" ? pendientes : items ?? [];

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="kicker">Compras</p>
          <h1 className="display text-[30px] leading-tight">Requerimientos</h1>
          <p className="mt-1 text-[13.5px] text-ink-500">
            Lo que te pidieron las sucursales, con el contexto para decidir y el archivo
            del portal al final.
          </p>
        </div>
        <Link href="/requerimiento">
          <Button variant="outline">
            <ClipboardPaste size={15} /> Pegar una lista suelta
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

      {items !== null && (
        <>
          <div className="flex items-center gap-1 rounded-sm border border-ink-200 bg-white p-1 shadow-card">
            {(
              [
                ["pendientes", `Por resolver (${pendientes.length})`],
                ["todos", `Todos (${items.length})`],
              ] as [Filtro, string][]
            ).map(([valor, texto]) => (
              <button
                key={valor}
                onClick={() => setFiltro(valor)}
                className={`rounded-sm px-3 py-1.5 text-[13px] transition-colors ${
                  filtro === valor
                    ? "bg-ink-900 font-medium text-paper"
                    : "text-ink-600 hover:bg-ink-100"
                }`}
              >
                {texto}
              </button>
            ))}
          </div>

          {visibles.length === 0 ? (
            <div className="rounded-sm border border-ink-200 bg-white px-4 py-14 text-center shadow-card">
              <Inbox size={28} className="mx-auto text-ink-300" />
              <p className="mt-3 text-[14px] font-medium text-ink-700">
                {filtro === "pendientes"
                  ? "No hay requerimientos por resolver"
                  : "Todavía no llega ninguno"}
              </p>
              <p className="mt-1 text-[13px] text-ink-400">
                Cuando un vendedor envíe uno, aparece acá.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto rounded-sm border border-ink-200 bg-white shadow-card">
              <table className="w-full min-w-[860px] text-[13px]">
                <thead>
                  <tr className="border-b border-ink-200 bg-paper-50 text-left text-[11.5px] uppercase tracking-wide text-ink-500">
                    <th className="px-3 py-2">N°</th>
                    <th className="px-3 py-2">Sucursal</th>
                    <th className="px-3 py-2">Vendedor</th>
                    <th className="px-3 py-2">Recibido</th>
                    <th className="px-3 py-2 text-right">Repuestos</th>
                    <th className="px-3 py-2 text-right">Total aprox.</th>
                    <th className="px-3 py-2">Estado</th>
                  </tr>
                </thead>
                <tbody>
                  {visibles.map((r) => (
                    <tr
                      key={r.id}
                      className={`border-b border-ink-100 hover:bg-paper-50 ${
                        r.estado === "enviado" ? "bg-blue-50/40" : ""
                      }`}
                    >
                      <td className="px-3 py-2">
                        <Link
                          href={`/requerimientos/${r.id}`}
                          className="font-medium text-accent-700 hover:underline"
                        >
                          #{r.id}
                        </Link>
                      </td>
                      <td className="px-3 py-2 font-medium">{r.nombre_sucursal}</td>
                      <td className="px-3 py-2 text-ink-600">
                        {r.creado_por_nombre ?? r.creado_por}
                      </td>
                      <td className="px-3 py-2 text-ink-500">
                        {formatoFechaHora(r.creado_en)}
                      </td>
                      <td className="px-3 py-2 text-right tabular">
                        {formatoNumero(r.n_lineas)}
                      </td>
                      <td className="px-3 py-2 text-right tabular">
                        {formatoCLP(r.total_estimado ?? 0)}
                      </td>
                      <td className="px-3 py-2">
                        <EstadoRequerimientoBadge estado={r.estado} />
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </>
      )}
    </div>
  );
}
