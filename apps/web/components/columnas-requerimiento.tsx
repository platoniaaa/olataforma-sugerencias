"use client";

/**
 * Que columnas ve el comprador en el requerimiento.
 *
 * El contexto util no es el mismo para todos ni para todos los requerimientos:
 * a veces la pregunta es de rotacion y a veces es de plata. En vez de elegir por
 * el comprador -o peor, mostrarlo todo y volver la tabla ilegible-, la eleccion
 * es suya y queda guardada en su navegador.
 *
 * Codigo, descripcion, pidio, se compra y subtotal NO se pueden apagar: son la
 * transaccion, no contexto. Poder esconderlas seria poder cerrar un requerimiento
 * sin ver que se esta comprando.
 */

import { useEffect, useState } from "react";
import { Check, SlidersHorizontal } from "lucide-react";

export type ColumnaId =
  | "abc"
  | "frecuencia"
  | "venta_12m"
  | "venta_mensual"
  | "stock_suc"
  | "stock_cd"
  | "stock_nacional"
  | "transito"
  | "ya_sugerido"
  | "cobertura"
  | "margen";

export const COLUMNAS: {
  id: ColumnaId;
  titulo: string;
  ayuda: string;
  defecto: boolean;
}[] = [
  { id: "abc", titulo: "ABC", ayuda: "Clase del repuesto según su rotación", defecto: true },
  // "Frecuencia" no decia que se contaba, y el valor mas comun ("3/6/12") se leia
  // igual que el encabezado. El titulo ahora es literal y el numero trae su
  // denominador. Ver `components/frecuencia-venta.tsx`.
  { id: "frecuencia", titulo: "Meses con venta", ayuda: "De los últimos 12 meses, en cuántos se vendió este repuesto en esa sucursal. Mide cada cuánto se mueve, no cuánto", defecto: true },
  { id: "venta_12m", titulo: "Venta 12m", ayuda: "Unidades vendidas de verdad en esa sucursal, últimos 12 meses", defecto: true },
  { id: "venta_mensual", titulo: "Vta. mensual", ayuda: "Venta mensual promedio en esa sucursal, según el modelo", defecto: true },
  { id: "stock_suc", titulo: "Stock suc.", ayuda: "Stock en la sucursal que pide", defecto: true },
  { id: "stock_cd", titulo: "Stock CD", ayuda: "Stock en el centro de distribución", defecto: true },
  { id: "stock_nacional", titulo: "Stock nacional", ayuda: "Stock en toda la empresa", defecto: true },
  { id: "transito", titulo: "En tránsito", ayuda: "Unidades ya pedidas que todavía no llegan a esa sucursal", defecto: true },
  { id: "ya_sugerido", titulo: "Ya sugerido", ayuda: "Lo que el modelo ya pide para esa sucursal", defecto: true },
  { id: "cobertura", titulo: "Cobertura", ayuda: "Meses que dura el stock (más lo que viene) al ritmo de venta", defecto: false },
  { id: "margen", titulo: "Margen", ayuda: "Margen sobre el precio de lista. Negativo = se vende con pérdida", defecto: false },
];

const CLAVE = "requerimiento.columnas.v1";

function porDefecto(): Set<ColumnaId> {
  return new Set(COLUMNAS.filter((c) => c.defecto).map((c) => c.id));
}

/** Estado de columnas, persistido en el navegador de cada comprador. */
export function useColumnas() {
  // Se parte SIEMPRE del set por defecto: leer localStorage en el primer render
  // haria que el HTML del servidor y el del cliente no calcen (error de hidratación).
  const [visibles, setVisibles] = useState<Set<ColumnaId>>(porDefecto);
  const [listo, setListo] = useState(false);

  useEffect(() => {
    try {
      const guardado = window.localStorage.getItem(CLAVE);
      if (guardado) {
        const ids = JSON.parse(guardado) as string[];
        const validas = COLUMNAS.map((c) => c.id);
        // Se filtra contra la lista actual: una columna que ya no existe no
        // puede dejar la tabla en un estado imposible.
        setVisibles(new Set(ids.filter((i): i is ColumnaId => validas.includes(i as ColumnaId))));
      }
    } catch {
      /* localStorage bloqueado: se usan las de por defecto */
    }
    setListo(true);
  }, []);

  const alternar = (id: ColumnaId) => {
    setVisibles((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      try {
        window.localStorage.setItem(CLAVE, JSON.stringify([...next]));
      } catch {
        /* sin persistencia, pero la sesión sigue funcionando */
      }
      return next;
    });
  };

  const restaurar = () => {
    const base = porDefecto();
    setVisibles(base);
    try {
      window.localStorage.setItem(CLAVE, JSON.stringify([...base]));
    } catch {
      /* idem */
    }
  };

  return { visibles, alternar, restaurar, listo };
}

export function BotonColumnas({
  visibles,
  alternar,
  restaurar,
}: {
  visibles: Set<ColumnaId>;
  alternar: (id: ColumnaId) => void;
  restaurar: () => void;
}) {
  const [abierto, setAbierto] = useState(false);

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setAbierto((v) => !v)}
        aria-expanded={abierto}
        className="inline-flex h-9 items-center gap-2 rounded-sm border border-ink-200 bg-white px-3 text-[13px] text-ink-600 hover:border-ink-300 hover:text-ink-900"
      >
        <SlidersHorizontal size={14} /> Columnas
        <span className="tabular text-ink-400">{visibles.size}</span>
      </button>

      {abierto && (
        <>
          {/* Clic afuera para cerrar, sin atrapar el foco. */}
          <div className="fixed inset-0 z-20" onClick={() => setAbierto(false)} />
          <div className="absolute right-0 z-30 mt-1 w-[290px] rounded-sm border border-ink-200 bg-white p-2 shadow-2xl">
            <p className="px-2 pb-1 pt-1 text-[11px] uppercase tracking-wide text-ink-400">
              Qué mostrar en la tabla
            </p>
            <ul>
              {COLUMNAS.map((c) => {
                const on = visibles.has(c.id);
                return (
                  <li key={c.id}>
                    <button
                      type="button"
                      onClick={() => alternar(c.id)}
                      className="flex w-full items-start gap-2 rounded-sm px-2 py-1.5 text-left hover:bg-paper-50"
                    >
                      <span
                        className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-[3px] border ${
                          on ? "border-accent-700 bg-accent-700 text-white" : "border-ink-300"
                        }`}
                      >
                        {on && <Check size={11} strokeWidth={3} />}
                      </span>
                      <span>
                        <span className="block text-[13px] text-ink-900">{c.titulo}</span>
                        <span className="block text-[11.5px] leading-tight text-ink-500">
                          {c.ayuda}
                        </span>
                      </span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="mt-1 border-t border-ink-100 px-2 pt-2">
              <button
                type="button"
                onClick={restaurar}
                className="text-[12px] text-ink-500 underline underline-offset-2 hover:text-accent-700"
              >
                Volver a las de siempre
              </button>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
