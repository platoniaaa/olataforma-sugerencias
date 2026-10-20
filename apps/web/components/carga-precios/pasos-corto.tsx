"use client";

// Los pasos 1 y 2 del Excel corto: se baja una plantilla vacia (solo los encabezados) y se llena
// con los productos que se quieren tocar. El paso 3 (subirlo) y la vista previa son iguales para
// los dos modos y viven en el dialogo.
//
// La plantilla es corta a proposito: Codigo, Precio fijo, Desde, Hasta y Obs. No trae la lista, asi
// que no hay nada contra lo cual comparar: lo que dice cada celda es lo que queda, solo en los
// codigos que se ponen. Por eso las reglas de abajo son lo que hay que tener claro antes de llenarla.
import { Download, Loader2 } from "lucide-react";
import type { Ref } from "react";
import { Button } from "@/components/ui/button";

const VACIO = <span className="italic text-slate-600">(vacío)</span>;

function Ejemplo() {
  return <span className="ml-2 rounded-sm bg-slate-100 px-1 py-0.5 text-[10px] font-medium uppercase tracking-wide text-slate-600">ejemplo</span>;
}

export function PasosCorto({ descargando, deshabilitado, aviso, onDescargar, botonRef }: {
  /** Hay una descarga en curso: el boton muestra que trabaja. */
  descargando: boolean;
  /** No se puede pedir la plantilla (descargando, leyendo un archivo o guardando). */
  deshabilitado: boolean;
  aviso: string | null;
  onDescargar: () => void;
  botonRef: Ref<HTMLButtonElement>;
}) {
  return (
    <>
      <section className="space-y-2">
        <h3 className="text-[13px] font-semibold text-slate-900">1. Baja la plantilla</h3>
        <p>Es una plantilla vacía, solo con los encabezados. No incluye la lista.</p>
        <Button ref={botonRef} variant="outline" size="sm" className="[@media(pointer:coarse)]:h-11" onClick={onDescargar} disabled={deshabilitado}>
          {descargando ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
          Descargar plantilla
        </Button>
        {aviso && (
          <p role="status" className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700">{aviso}</p>
        )}
      </section>

      <section className="space-y-2">
        <h3 className="text-[13px] font-semibold text-slate-900">2. Escribe tus productos</h3>
        <p>Una fila por producto, así:</p>
        <div className="overflow-x-auto rounded-md border border-slate-200">
          <table aria-label="Ejemplo de la plantilla" className="w-full text-[12px]">
            <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-3 py-1.5">Código</th>
                <th className="px-3 py-1.5">Precio fijo</th>
                <th className="px-3 py-1.5">Desde</th>
                <th className="px-3 py-1.5">Hasta</th>
              </tr>
            </thead>
            <tbody>
              <tr className="border-t border-slate-100">
                <td className="px-3 py-1.5"><span className="font-mono">71 AAA1</span><Ejemplo /></td>
                <td className="px-3 py-1.5 tabular-nums">12990</td>
                <td className="px-3 py-1.5 tabular-nums">20-10-2026</td>
                <td className="px-3 py-1.5 tabular-nums">31-10-2026</td>
              </tr>
              <tr className="border-t border-slate-100">
                <td className="px-3 py-1.5"><span className="font-mono">13 BBB2</span><Ejemplo /></td>
                <td className="px-3 py-1.5">{VACIO}</td>
                <td className="px-3 py-1.5">{VACIO}</td>
                <td className="px-3 py-1.5 tabular-nums">30-11-2026</td>
              </tr>
            </tbody>
          </table>
        </div>
        <p className="text-[12px] text-slate-500">
          La primera fila es un precio de campaña con fechas. La segunda solo renueva el Hasta del precio fijo que el producto ya tiene.
        </p>
        <ul className="list-disc space-y-0.5 pl-5 text-[12px] text-slate-600">
          <li>Una fila por producto. Solo se tocan los códigos que pongas: el resto de la lista queda igual.</li>
          <li>Código como aparece en la lista, con el rubro adelante (por ejemplo 71 AAA1). Los que no estén se ignoran y se listan.</li>
          <li>Precio fijo en pesos, sin decimales. Un precio fijo sin Hasta queda sin vencimiento: fijo hasta que alguien lo cambie.</li>
          <li>Fechas como dd-mm-aaaa. Hasta es el último día incluido: al día siguiente el producto vuelve a la regla.</li>
          <li>Celda vacía: no cambia nada. Para quitar un valor escribe QUITAR en Precio fijo, Desde o Hasta.</li>
          <li>
            Si el producto tenía margen fijo o estaba congelado, tu precio fijo lo reemplaza: lo verás en la vista previa.
            Obs es una nota opcional.
          </li>
        </ul>
      </section>
    </>
  );
}
