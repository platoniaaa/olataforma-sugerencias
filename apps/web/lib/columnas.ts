// Definicion central de las columnas del sugerido: etiqueta, tipo y si se ven por defecto.
import type { SugeridoRow } from "./types";

export type TipoColumna = "texto" | "numero" | "decimal" | "clp" | "abc" | "porcentaje";

export interface DefColumna {
  key: keyof SugeridoRow;
  label: string;
  tipo: TipoColumna;
  visiblePorDefecto: boolean;
  pin?: "left" | "right";
  /** Texto que se muestra al pasar el mouse por el icono de info del encabezado. */
  info?: string;
}

export const COLUMNAS: DefColumna[] = [
  { key: "producto", label: "Producto", tipo: "texto", visiblePorDefecto: true, pin: "left",
    info: "Código del producto (SKU maestro del grupo de reemplazos)." },
  { key: "descripcion", label: "Descripcion", tipo: "texto", visiblePorDefecto: true, pin: "left",
    info: "Descripción del producto según el catálogo maestro." },
  { key: "clasificacion_abc", label: "ABC", tipo: "abc", visiblePorDefecto: true,
    info: "Clase ABC de la sucursal según en cuántos meses hubo venta (A = más frecuente … D = esporádica). Define la ventana de demanda y el nivel de servicio." },
  { key: "clasificacion_abc_agregada", label: "ABC Agregada", tipo: "abc", visiblePorDefecto: false,
    info: "Clase ABC del producto a nivel nacional (todas las sucursales juntas). Se usa para decidir la compra centralizada en el CD." },
  { key: "nombre_sucursal", label: "Sucursal", tipo: "texto", visiblePorDefecto: true,
    info: "Sucursal a la que corresponde esta fila." },
  { key: "total_sugerido_suc", label: "Total Sugerido", tipo: "numero", visiblePorDefecto: true, pin: "right",
    info: "Unidades sugeridas a comprar para la sucursal. = Demanda × (ciclo de orden + lead time) + stock de seguridad − stock actual − tránsito." },
  // Ocultas por defecto:
  { key: "empresa", label: "Empresa", tipo: "texto", visiblePorDefecto: false,
    info: "Origen de las ventas del producto en esta sucursal: Solo Curifor, Solo Frontera o Ambas." },
  { key: "proveedor", label: "Proveedor", tipo: "texto", visiblePorDefecto: false,
    info: "Proveedor de la orden de compra más reciente para este producto y sucursal." },
  { key: "filtro1_final", label: "Marca", tipo: "texto", visiblePorDefecto: false,
    info: "Marca del producto." },
  { key: "tipo_origen", label: "Tipo Origen", tipo: "texto", visiblePorDefecto: false,
    info: "Si el producto es Nacional o Importado." },
  { key: "total_valor_sugerido_clp", label: "Valor Total CLP", tipo: "clp", visiblePorDefecto: false,
    info: "Valor en pesos del sugerido = unidades sugeridas × costo unitario." },
  { key: "sugerido_traslado", label: "Sugerido traslado desde el CD", tipo: "numero", visiblePorDefecto: false,
    info: "Unidades a traer desde el CD REPUESTOS (en vez de comprarlas), repartiendo el stock del CD según la prioridad de cada sucursal." },
  { key: "sugerido_compra_neto", label: "Sug. Compra Neto", tipo: "numero", visiblePorDefecto: false,
    info: "Unidades a comprar al proveedor tras descontar lo que se puede traer desde el CD. = Total Sugerido − Traslado." },
  { key: "stock_activo_suc", label: "Stock Activo", tipo: "numero", visiblePorDefecto: false,
    info: "Stock disponible hoy en la sucursal (incluye todo el grupo de reemplazos)." },
  { key: "stock_en_transito_suc", label: "Stock Transito", tipo: "numero", visiblePorDefecto: false,
    info: "Unidades ya pedidas y en camino (órdenes de compra pendientes y vigentes)." },
  { key: "stock_en_cd", label: "Stock CD", tipo: "numero", visiblePorDefecto: false,
    info: "Stock disponible del producto en el CD REPUESTOS." },
  { key: "stock_seguridad", label: "Stock Seguridad", tipo: "numero", visiblePorDefecto: false,
    info: "Colchón de unidades para cubrir la variabilidad de la demanda durante el lead time." },
  { key: "punto_de_pedido", label: "Punto de Pedido", tipo: "numero", visiblePorDefecto: false,
    info: "Nivel de stock que gatilla la reposición. = Demanda × lead time + stock de seguridad." },
  { key: "demanda_mensual", label: "Demanda Mensual", tipo: "decimal", visiblePorDefecto: false,
    info: "Demanda mensual promedio, suavizada: se recortan los meses atípicos con mediana + MAD para no inflar por peaks." },
  { key: "demanda_diaria", label: "Demanda Diaria", tipo: "decimal", visiblePorDefecto: false,
    info: "Demanda diaria = demanda mensual ÷ 22 días hábiles." },
  { key: "desv_std_mensual", label: "Desv Std Mensual", tipo: "decimal", visiblePorDefecto: false,
    info: "Desviación estándar mensual de la demanda (qué tan variable es). Alimenta el stock de seguridad." },
  { key: "lead_time_dias", label: "Lead Time (dias)", tipo: "numero", visiblePorDefecto: false,
    info: "Días que tarda el proveedor en entregar (histórico OC → recepción; 8 por defecto si no hay dato)." },
  { key: "lt_efectivo", label: "LT Efectivo", tipo: "numero", visiblePorDefecto: false,
    info: "Lead time usado en el cálculo: el del CD si la sucursal se abastece del CD, si no el del proveedor." },
  { key: "abastece_cd", label: "Abastece CD", tipo: "texto", visiblePorDefecto: false,
    info: "Si la sucursal se abastece de este producto vía el CD (compra centralizada) en vez de comprarlo directo." },
  { key: "comprar_en_el_cd", label: "¿Comprar en CD?", tipo: "texto", visiblePorDefecto: false,
    info: "Si al llegar el turno de esta sucursal el stock del CD ya se agotó y el CD debe comprar más para cubrirla." },
  { key: "prioridad_cd", label: "Prioridad CD", tipo: "numero", visiblePorDefecto: false,
    info: "Orden en que la sucursal recibe el stock del CD (1 = primera en abastecerse)." },
  { key: "costo_unitario", label: "Costo Unitario", tipo: "clp", visiblePorDefecto: false,
    info: "Costo unitario del producto (según Stock Bodegas)." },
  { key: "unidad_medida", label: "Unidad", tipo: "texto", visiblePorDefecto: false,
    info: "Unidad de medida del producto (UNIDAD, LITRO, etc.)." },
  { key: "pedir", label: "Pedir", tipo: "texto", visiblePorDefecto: false,
    info: "Sí / No: si hay algo que comprar para esta fila (Total Sugerido > 0)." },
  { key: "reemplazos", label: "Reemplazos", tipo: "texto", visiblePorDefecto: false,
    info: "Otros códigos que forman el mismo grupo de reemplazo (se agrupan para stock y demanda)." },
  { key: "trasladar_desde", label: "Trasladar desde", tipo: "texto", visiblePorDefecto: false,
    info: "Sugerencia de traslado lateral: otras sucursales con stock del producto y cuánto podrían enviar." },
  // Stock por bodega/sucursal (espejo de las columnas del BI; incluye grupo de reemplazo).
  { key: "stock_linderos", label: "Stock Linderos", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Linderos." },
  { key: "stock_curico", label: "Stock Curico", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Curicó." },
  { key: "stock_talca", label: "Stock Talca", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Talca." },
  { key: "stock_rancagua", label: "Stock Rancagua", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Rancagua." },
  { key: "stock_diez_de_julio_2", label: "Stock Diez de Julio (2)", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Diez de Julio (2)." },
  { key: "stock_chillan", label: "Stock Chillan", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Chillán." },
  { key: "stock_cd_repuestos", label: "Stock CD Repuestos", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en el CD REPUESTOS." },
  { key: "stock_brasil_18", label: "Stock Brasil 18", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Brasil 18." },
  { key: "stock_placilla", label: "Stock Placilla", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Placilla." },
  { key: "stock_chillan_viejo", label: "Stock Chillan Viejo", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Chillán Viejo." },
  { key: "stock_talca_2", label: "Stock Talca (2)", tipo: "numero", visiblePorDefecto: false,
    info: "Stock del producto (y su grupo de reemplazos) en la bodega de Talca (2)." },
  // Precios FORD (cruce por codigo con la tabla Precios; en blanco si el codigo no esta en la lista de FORD).
  { key: "precio_flota_ford", label: "Precio Flota FORD", tipo: "clp", visiblePorDefecto: false,
    info: "Precio de flota de FORD para el repuesto (cruce por código). En blanco si el código no está en la lista de precios de FORD." },
  { key: "precio_dealer_ford", label: "Precio Dealer FORD", tipo: "clp", visiblePorDefecto: false,
    info: "Precio dealer (concesionario) de FORD para el repuesto. En blanco si el código no está en la lista de FORD." },
  { key: "precio_publico_ford", label: "Precio Público FORD", tipo: "clp", visiblePorDefecto: false,
    info: "Precio público de lista de FORD (neto). En blanco si el código no está en la lista de FORD." },
  { key: "precio_publico_iva_ford", label: "Precio Público c/IVA FORD", tipo: "clp", visiblePorDefecto: false,
    info: "Precio público de FORD con impuestos incluidos. En blanco si el código no está en la lista de FORD." },
  { key: "precio_reposicion_ford", label: "Precio Reposición FORD", tipo: "clp", visiblePorDefecto: false,
    info: "Precio de reposición de FORD para el repuesto. En blanco si el código no está en la lista de FORD." },
  { key: "precio_urgente_vor_ford", label: "Precio Urgente VOR FORD", tipo: "clp", visiblePorDefecto: false,
    info: "Precio de FORD en pedido urgente VOR (Vehicle Off Road). En blanco si el código no está en la lista de FORD." },
  { key: "precio_promociones_ford", label: "Precio Promociones FORD", tipo: "clp", visiblePorDefecto: false,
    info: "Precio de FORD en promoción para el repuesto. En blanco si el código no está en la lista de FORD." },
  { key: "precio_urgente_recargo15_ford", label: "Precio Urgente +15% FORD", tipo: "clp", visiblePorDefecto: false,
    info: "Precio de FORD en pedido urgente con recargo del 15%. En blanco si el código no está en la lista de FORD." },
  // Margen: precio de lista FORD contra el costo unitario. En blanco si falta alguno de los dos.
  { key: "margen_pct", label: "Margen %", tipo: "porcentaje", visiblePorDefecto: false,
    info: "Margen sobre el precio público de FORD: (precio público − costo unitario) / precio público. En blanco si el producto no tiene precio FORD o no tiene costo." },
  { key: "margen_unitario_clp", label: "Margen Unitario CLP", tipo: "clp", visiblePorDefecto: false,
    info: "Pesos que deja cada unidad vendida al precio público de FORD: precio público − costo unitario." },
  { key: "margen_sugerido_clp", label: "Margen del Sugerido CLP", tipo: "clp", visiblePorDefecto: false,
    info: "Margen potencial de lo que el modelo sugiere comprar: margen unitario × total sugerido. Sirve para priorizar la compra." },
  { key: "margen_flota_pct", label: "Margen Flota %", tipo: "porcentaje", visiblePorDefecto: false,
    info: "Margen si la venta se hace al precio de flota (más bajo que el público)." },
  { key: "sobrecosto_vs_dealer_pct", label: "Sobrecosto vs Dealer %", tipo: "porcentaje", visiblePorDefecto: false,
    info: "Cuánto está el costo unitario por encima del precio dealer de FORD. Positivo = se está comprando más caro que la lista dealer; conviene revisar." },
];

export const KEYS_POR_DEFECTO = COLUMNAS.filter((c) => c.visiblePorDefecto).map((c) => c.key as string);

// Columnas por defecto de la vista "distribucion" (traslado CD -> sucursales).
// Prioriza el set operativo del jefe de compras: cuanto trasladar, stock del CD,
// lo que aun hay que comprar y si el CD debe comprarlo (el "Total Sugerido" se
// omite porque estas filas lo traen en cero: la sucursal se abastece via CD).
const COLS_DISTRIBUCION = [
  "producto", "descripcion", "clasificacion_abc", "nombre_sucursal",
  "sugerido_traslado", "stock_en_cd", "sugerido_compra_neto",
  "comprar_en_el_cd", "prioridad_cd",
];

// Set de columnas por defecto segun la vista del proceso de compras.
export function columnasPorDefectoVista(vista: string): string[] {
  return vista === "distribucion" ? COLS_DISTRIBUCION : KEYS_POR_DEFECTO;
}
