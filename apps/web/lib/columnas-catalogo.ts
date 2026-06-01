// Definición central de las columnas del catálogo maestro.
import type { CatalogoRow } from "./types";

export type TipoColCat = "texto" | "numero" | "decimal" | "clp";

export interface DefColCat {
  key: keyof CatalogoRow;
  label: string;
  tipo: TipoColCat;
  visiblePorDefecto: boolean;
  pin?: "left" | "right";
}

export const COLUMNAS_CAT: DefColCat[] = [
  { key: "producto", label: "Producto", tipo: "texto", visiblePorDefecto: true, pin: "left" },
  { key: "glosa", label: "Descripción", tipo: "texto", visiblePorDefecto: true, pin: "left" },
  { key: "familia", label: "Familia", tipo: "texto", visiblePorDefecto: true },
  { key: "procedencia", label: "Procedencia", tipo: "texto", visiblePorDefecto: true },
  { key: "costo", label: "Costo", tipo: "clp", visiblePorDefecto: true },
  { key: "stock_total", label: "Stock Total", tipo: "numero", visiblePorDefecto: true, pin: "right" },
  // Ocultas por defecto
  { key: "subfamilia", label: "Subfamilia", tipo: "texto", visiblePorDefecto: false },
  { key: "categoria", label: "Categoría", tipo: "texto", visiblePorDefecto: false },
  { key: "sub_categoria", label: "Sub Categoría", tipo: "texto", visiblePorDefecto: false },
  { key: "tipo_repuesto", label: "Tipo Repuesto", tipo: "texto", visiblePorDefecto: false },
  { key: "tipo_producto", label: "Tipo Producto", tipo: "texto", visiblePorDefecto: false },
  { key: "clasificacion_stock", label: "Clasificación Stock", tipo: "texto", visiblePorDefecto: false },
  { key: "precio", label: "Precio", tipo: "clp", visiblePorDefecto: false },
  { key: "stock_minimo", label: "Stock Mínimo", tipo: "numero", visiblePorDefecto: false },
  { key: "stock_maximo", label: "Stock Máximo", tipo: "numero", visiblePorDefecto: false },
  { key: "sub_modelo", label: "Sub-Modelo", tipo: "texto", visiblePorDefecto: false },
  { key: "cilindrada", label: "Cilindrada", tipo: "texto", visiblePorDefecto: false },
  { key: "combustible", label: "Combustible", tipo: "texto", visiblePorDefecto: false },
  { key: "anio", label: "Año", tipo: "texto", visiblePorDefecto: false },
  { key: "unidad", label: "Unidad", tipo: "texto", visiblePorDefecto: false },
  { key: "reemplazo", label: "Reemplazo", tipo: "texto", visiblePorDefecto: false },
];

export const KEYS_CAT_DEFAULT = COLUMNAS_CAT
  .filter((c) => c.visiblePorDefecto)
  .map((c) => c.key as string);
