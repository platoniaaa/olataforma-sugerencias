"use client";

import { formatoNumero } from "@/lib/formato";
import type { TransitoSucursal } from "@/lib/types";

/** "2026-06-12" -> "12-06-2026". */
export function fechaCorta(iso: string): string {
  const [a, m, d] = iso.slice(0, 10).split("-");
  return a && m && d ? `${d}-${m}-${a}` : iso;
}

/**
 * Hace cuánto se pidió: "hoy", "hace 12 días", "hace 4 meses". Importa porque 5 unidades pedidas
 * hace 4 meses probablemente no lleguen, y 5 pedidas ayer sí.
 */
export function haceCuanto(iso: string, hoy: Date = new Date()): string {
  const pedido = new Date(`${iso.slice(0, 10)}T00:00:00`);
  if (Number.isNaN(pedido.getTime())) return "";
  const dias = Math.floor((hoy.getTime() - pedido.getTime()) / 86_400_000);
  if (dias <= 0) return "hoy";
  if (dias === 1) return "hace 1 día";
  if (dias < 31) return `hace ${dias} días`;
  const meses = Math.floor(dias / 30);
  return meses === 1 ? "hace 1 mes" : `hace ${meses} meses`;
}

/**
 * Lo que ya está pedido y todavía no llega, por sucursal de destino. Es lo que mira el vendedor
 * antes de pedir: si ya viene, no hay que pedirlo de nuevo.
 */
export function TablaTransito({ filas, hoy }: { filas: TransitoSucursal[]; hoy?: Date }) {
  const con = filas.filter((f) => f.cantidad > 0);
  const total = con.reduce((a, f) => a + f.cantidad, 0);

  return (
    <section className="rounded-xl border border-slate-200 bg-white shadow-sm">
      <div className="border-b border-slate-100 px-4 py-3">
        <h2 className="text-sm font-semibold text-slate-900">Unidades en tránsito</h2>
        <p className="text-xs text-slate-600">
          Ya están pedidas y todavía no llegan. Míralas antes de pedir más.
        </p>
      </div>
      {con.length === 0 ? (
        <p className="px-4 py-6 text-sm text-slate-600">No hay unidades en tránsito de este producto.</p>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-slate-50 text-left text-xs uppercase text-slate-600">
              <tr>
                <th scope="col" className="px-4 py-2">Sucursal</th>
                <th scope="col" className="px-4 py-2 text-right">Unidades</th>
                <th scope="col" className="px-4 py-2">Pedido desde</th>
              </tr>
            </thead>
            <tbody>
              {con.map((f, i) => (
                <tr key={`${f.sucursal_id ?? "x"}-${i}`} className="border-t border-slate-100">
                  <td className="px-4 py-2 font-medium">
                    {(f.sucursal_id ?? "").replace(/^\d+\s+/, "") || "Sin sucursal"}
                  </td>
                  <td className="px-4 py-2 text-right font-semibold tabular-nums text-sky-800">
                    {formatoNumero(f.cantidad)}
                  </td>
                  <td className="px-4 py-2 text-slate-700">
                    {f.pedido_desde ? (
                      <>
                        {fechaCorta(f.pedido_desde)}{" "}
                        <span className="text-slate-600">({haceCuanto(f.pedido_desde, hoy)})</span>
                      </>
                    ) : (
                      <span className="text-slate-600">Sin fecha</span>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot>
              <tr className="border-t border-slate-200 bg-slate-50">
                <td className="px-4 py-2 font-semibold">Total</td>
                <td className="px-4 py-2 text-right font-semibold tabular-nums">{formatoNumero(total)}</td>
                <td className="px-4 py-2" />
              </tr>
            </tfoot>
          </table>
        </div>
      )}
    </section>
  );
}
