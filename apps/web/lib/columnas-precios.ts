// Definicion central de las columnas de la lista de precios.
import { formatoCLP, formatoNumero } from "./formato";
import type { PrecioDetalle, PrecioRow } from "./types";

export type TipoColPrecio = "texto" | "numero" | "decimal" | "clp" | "pct" | "fecha" | "estado" | "bool";

export interface DefColPrecio {
  key: keyof PrecioRow;
  label: string;
  tipo: TipoColPrecio;
  visiblePorDefecto: boolean;
  pin?: "left" | "right";
  /** Texto de ayuda en la cabecera. */
  ayuda?: string;
}

export const COLUMNAS_PRECIOS: DefColPrecio[] = [
  { key: "producto", label: "Producto", tipo: "texto", visiblePorDefecto: true, pin: "left" },
  { key: "glosa", label: "Glosa", tipo: "texto", visiblePorDefecto: true },
  { key: "rubro", label: "Rubro", tipo: "texto", visiblePorDefecto: true },
  { key: "tipo", label: "Tipo", tipo: "texto", visiblePorDefecto: true },
  { key: "procedencia_final", label: "Procedencia", tipo: "texto", visiblePorDefecto: true,
    ayuda: "Manual > rubro forzado > ultima compra (importado/nacional) > maestro > SIN REVISION" },
  { key: "factor", label: "Factor", tipo: "decimal", visiblePorDefecto: true },
  { key: "costo", label: "Costo", tipo: "clp", visiblePorDefecto: true },
  { key: "stock", label: "Stock", tipo: "numero", visiblePorDefecto: true,
    ayuda: "Solo bodegas reales: no cuenta dañados, devolución, scrap ni bodegas dadas de baja" },
  { key: "precio_erp", label: "Precio ERP", tipo: "clp", visiblePorDefecto: true, ayuda: "El precio que tiene hoy el ERP" },
  { key: "precio_final", label: "Precio final", tipo: "clp", visiblePorDefecto: true, pin: "right",
    ayuda: "Lo que se manda al ERP: precio fijo o congelado si hay, calculado si no" },
  { key: "estado", label: "Estado", tipo: "estado", visiblePorDefecto: true, pin: "right" },
  { key: "cambios_pendientes", label: "Cambios", tipo: "numero", visiblePorDefecto: true, pin: "right",
    ayuda: "Diferencias detectadas en el ultimo recalculo que nadie reviso" },
  // Ocultas por defecto
  { key: "precio_calculado", label: "Precio calculado", tipo: "clp", visiblePorDefecto: false,
    ayuda: "Lo que da la regla sin mirar precio fijo ni congelado" },
  { key: "precio_fijo", label: "Precio fijo", tipo: "clp", visiblePorDefecto: false },
  { key: "congelar", label: "Congelado", tipo: "bool", visiblePorDefecto: false },
  { key: "obs", label: "Obs precio", tipo: "texto", visiblePorDefecto: false },
  { key: "desviacion_pesos", label: "Desviacion $", tipo: "clp", visiblePorDefecto: false, ayuda: "Precio ERP menos precio final" },
  { key: "desviacion_pct", label: "Desviacion %", tipo: "pct", visiblePorDefecto: false },
  { key: "stock_transito", label: "En transito", tipo: "numero", visiblePorDefecto: false },
  { key: "procedencia_maestro", label: "Procedencia maestro", tipo: "texto", visiblePorDefecto: false },
  { key: "procedencia_origen", label: "Origen procedencia", tipo: "texto", visiblePorDefecto: false },
  { key: "tipo_origen", label: "Origen tipo", tipo: "texto", visiblePorDefecto: false },
  { key: "ult_recep_importado", label: "Ult. recep. importado", tipo: "fecha", visiblePorDefecto: false },
  { key: "ult_pe_nacional", label: "Ult. P/E nacional", tipo: "fecha", visiblePorDefecto: false },
  { key: "ultima_venta", label: "Ultima venta", tipo: "fecha", visiblePorDefecto: false },
  { key: "precio_sugerido", label: "Precio proveedor", tipo: "clp", visiblePorDefecto: false },
  { key: "origen", label: "Origen", tipo: "texto", visiblePorDefecto: false, ayuda: "maestro = vino del ERP; manual = creado aca" },
  { key: "editado_por", label: "Editado por", tipo: "texto", visiblePorDefecto: false },
  { key: "editado_en", label: "Editado el", tipo: "fecha", visiblePorDefecto: false },
  { key: "actualizado_en", label: "Recalculado el", tipo: "fecha", visiblePorDefecto: false },
];

export const KEYS_PRECIOS_DEFAULT = COLUMNAS_PRECIOS
  .filter((c) => c.visiblePorDefecto)
  .map((c) => c.key as string);

/** Colores de la etiqueta de estado. Semantica, no decoracion: rojo es lo que
 *  hay que mirar antes de mandar al ERP. */
export function claseEstado(estado: string | null | undefined): string {
  switch ((estado ?? "").toUpperCase()) {
    case "OK":
      return "bg-emerald-50 text-emerald-700";
    case "FIJO":
      return "bg-sky-50 text-sky-700";
    case "CONGELADO":
      return "bg-indigo-50 text-indigo-700";
    case "SUGERIDO":
      return "bg-violet-50 text-violet-700";
    case "SIN STOCK":
      return "bg-ink-100 text-ink-500";
    case "NO PRODUCTO":
      return "bg-ink-100 text-ink-500";
    case "SIN REVISION":
      return "bg-rose-50 text-rose-700";
    default:
      return "bg-ink-100 text-ink-500";
  }
}


/**
 * La cuenta que dio el precio, en una línea.
 *
 * Antes había que armarla mentalmente saltando entre "Costo", "Factor" y
 * "Precio calculado", tres filas separadas de una lista de once. Y cuando el
 * precio NO salía de esa cuenta —fijo, congelado, sin stock— nada lo decía: el
 * factor y el costo seguían ahí, invitando a multiplicarlos y a no cuadrar.
 */
export function explicacionPrecio(d: PrecioDetalle): string {
  if (d.precio_fijo !== null && d.precio_fijo !== undefined) return "Precio fijo puesto a mano";
  if (d.congelar) return "Congelado: no sigue al costo";
  if (d.no_producto) return "No es un producto: sin precio";
  if ((d.stock ?? 0) <= 0 && (d.stock_transito ?? 0) <= 0) return "Sin stock ni tránsito → 0";
  if ((d.tipo ?? "").toLowerCase() === "sugerido") return "Precio de lista del proveedor";
  if (d.costo && d.factor) {
    return `${formatoCLP(d.costo)} × ${formatoNumero(d.factor, 2)} = ${formatoCLP(d.precio_calculado)}`;
  }
  if (!d.factor) return "Sin factor para este tipo y procedencia";
  return "Sin costo cargado";
}
