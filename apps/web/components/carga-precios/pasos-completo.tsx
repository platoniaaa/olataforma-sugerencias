"use client";

// Los pasos 1 y 2 del Excel completo: se baja el archivo con toda la lista, y se edita en Excel
// solo lo que esta permitido. El paso 3 (subirlo) y la vista previa son iguales para los dos
// modos y viven en el dialogo.
//
// El archivo para editar trae 25 columnas: las 16 de "Exportar completa", mas las de decision y
// la Referencia. Once se editan; el resto es de solo lectura y, si se cambia, se ignora. Las dos
// listas de abajo son lo que ve la persona antes de abrir Excel: que se puede tocar y que no.
import { Download, Loader2, Lock } from "lucide-react";
import type { Ref } from "react";
import { Button } from "@/components/ui/button";

/** Las once columnas que se pueden editar, en el orden del archivo, y que hace cada una. */
export const COLUMNAS_EDITABLES = [
  { columna: "Tipo", hace: "Escribe el tipo a mano en ese producto.", vacia: "Vuelve a seguir al rubro." },
  { columna: "Procedencia", hace: "Escribe la procedencia a mano (Nacional o Importado).", vacia: "Vuelve a la regla de compras." },
  { columna: "Factor", hace: "Le da al producto un factor propio (margen fijo).", vacia: "Lo quita: vuelve al factor de la política." },
  { columna: "Precio final", hace: "Lo deja como precio fijo.", vacia: "Quita el precio fijo." },
  { columna: "Obs", hace: "Cambia la observación.", vacia: "La borra." },
  { columna: "Congelar", hace: "Sí congela el precio de hoy; No lo descongela.", vacia: "Cuenta como No." },
  { columna: "No es producto", hace: "Sí lo saca del cálculo (servicios, mano de obra).", vacia: "Cuenta como No." },
  {
    columna: "Precio fijo",
    hace: "Fija el precio. Muestra lo que hay guardado, aunque su periodo no rija hoy.",
    vacia: "Quita el precio fijo.",
  },
  {
    columna: "Margen fijo %",
    hace: "Fija el margen en % sobre la venta (35 = 35 %, factor 1,5385); el precio sigue al costo.",
    vacia: "Quita el margen fijo.",
  },
  {
    columna: "Desde",
    hace: "Primer día en que rigen el precio fijo, el margen fijo y el congelado. Antes sigue la regla.",
    vacia: "Rige desde que cargas el archivo.",
  },
  {
    columna: "Hasta",
    hace: "Último día (incluido) en que rigen. Al día siguiente vuelve a la regla.",
    vacia: "Sin vencimiento: quita la fecha que tuviera.",
  },
] as const;

/** Las trece columnas de solo lectura, en el orden del archivo, y por que no se editan. Los
 *  nombres son los del encabezado del archivo, tal cual (con "En transito" sin tilde). */
export const COLUMNAS_SOLO_LECTURA = [
  { columna: "Producto", motivo: "es el código; viene del maestro del ERP" },
  { columna: "Glosa", motivo: "viene del maestro del ERP" },
  { columna: "Rubro", motivo: "viene del maestro del ERP" },
  { columna: "Costo", motivo: "lo trae el ERP cada día" },
  { columna: "Precio ERP", motivo: "es el precio que tiene hoy el ERP" },
  { columna: "Precio calculado", motivo: "lo calcula la regla" },
  { columna: "Estado", motivo: "lo calcula la regla" },
  { columna: "Stock", motivo: "lo trae el ERP cada día" },
  { columna: "En transito", motivo: "lo trae el ERP cada día" },
  { columna: "Ultima venta", motivo: "sale de las ventas" },
  { columna: "Descuento máximo", motivo: "sale de la política (se cambia en Política)" },
  { columna: "Descuento+1", motivo: "sale de la política (se cambia en Política)" },
  { columna: "Vigencia", motivo: "es el texto del periodo (Desde y Hasta)" },
] as const;

export function PasosCompleto({ descargando, deshabilitado, aviso, onDescargar, botonRef }: {
  /** Hay una descarga en curso: el boton muestra que trabaja. */
  descargando: boolean;
  /** No se puede pedir el archivo (descargando, leyendo un archivo o guardando). */
  deshabilitado: boolean;
  aviso: string | null;
  onDescargar: () => void;
  botonRef: Ref<HTMLButtonElement>;
}) {
  return (
    <>
      <section className="space-y-2">
        <h3 className="text-[13px] font-semibold text-slate-900">1. Descarga la lista</h3>
        <p>Baja un archivo con todos los productos y sus precios de hoy.</p>
        <Button ref={botonRef} variant="outline" size="sm" className="[@media(pointer:coarse)]:h-11" onClick={onDescargar} disabled={deshabilitado}>
          {descargando ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
          Descargar para editar
        </Button>
        <p className="text-[12px] text-slate-500">Es un archivo grande (más de 10 MB): puede tardar unos segundos en bajar.</p>
        {aviso && (
          <p role="status" className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700">{aviso}</p>
        )}
      </section>

      <section className="space-y-3">
        <h3 className="text-[13px] font-semibold text-slate-900">2. Edítala en Excel</h3>
        <div className="space-y-2">
          <p>Cambia solo las columnas de esta tabla:</p>
          <div className="overflow-x-auto rounded-md border border-slate-200">
            <table className="w-full text-[12px]">
              <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-1.5">Columna</th>
                  <th className="px-3 py-1.5">Al cargarla</th>
                  <th className="px-3 py-1.5">Si la dejas vacía</th>
                </tr>
              </thead>
              <tbody>
                {COLUMNAS_EDITABLES.map((c) => (
                  <tr key={c.columna} className="border-t border-slate-100">
                    <td className="px-3 py-1.5 font-medium text-slate-900">{c.columna}</td>
                    <td className="px-3 py-1.5">{c.hace}</td>
                    <td className="px-3 py-1.5 text-slate-500">{c.vacia}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>

        <div className="space-y-1.5">
          <h4 className="text-[12px] font-semibold text-slate-800">Solo lectura: si las cambias, se ignoran</h4>
          <ul aria-label="Columnas de solo lectura" className="grid gap-x-4 gap-y-1 text-[12px] text-slate-600 sm:grid-cols-2">
            {COLUMNAS_SOLO_LECTURA.map((c) => (
              <li key={c.columna} className="flex items-start gap-1.5">
                <Lock size={12} className="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
                <span>{`${c.columna}: ${c.motivo}`}</span>
              </li>
            ))}
            <li className="flex items-start gap-1.5">
              <Lock size={12} className="mt-0.5 shrink-0 text-slate-400" aria-hidden="true" />
              <span>Referencia: no la toques; con ella la plataforma sabe qué cambiaste</span>
            </li>
          </ul>
        </div>

        <ul className="list-disc space-y-0.5 pl-5 text-[12px] text-slate-600">
          <li>No toques la última columna, <b>Referencia</b>, ni ordenes columnas sueltas: con ella la plataforma sabe qué cambiaste.</li>
          <li>Guarda el archivo en el formato que quieras: CSV o libro de Excel (.xlsx). Los dos sirven.</li>
          <li>Solo se carga lo que cambies. Lo demás (costo, stock, precio ERP, estado, descuento) viene del ERP y se recalcula cada día.</li>
          <li>
            Factor y Margen fijo % son la misma decisión: cambia solo uno. Lo mismo vale para Precio final y Precio fijo.
            Un producto tampoco puede tener precio fijo y margen fijo a la vez: cambia uno, o deja vacía la celda del otro.
          </li>
          <li>
            Desde y Hasta valen para el precio fijo, el margen fijo y el congelado a la vez: es un solo periodo por producto.
            Escribe las fechas como dd-mm-aaaa.
          </li>
          <li>Un factor para todo un rubro conviene cambiarlo en <b>Política</b>: es un solo cambio y alcanza a los productos nuevos.</li>
        </ul>
      </section>
    </>
  );
}
