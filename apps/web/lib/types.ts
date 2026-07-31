// Tipos compartidos con el backend (espejo de los schemas Pydantic).

export interface SugeridoRow {
  id: number;
  origen?: "sugerido" | "catalogo" | "manual" | "instock";
  producto: string;
  descripcion: string | null;
  sucursal_id: string;
  nombre_sucursal: string | null;
  empresa: string | null;
  clasificacion_abc: string | null;
  proveedor: string | null;
  filtro1_final: string | null;
  tipo_origen: string | null;
  es_importado: boolean | null;
  unidad_medida: string | null;
  lead_time_dias: number | null;
  lt_efectivo: number | null;
  lt_cd_a_sucursal_dias: number | null;
  lt_origen: string | null;
  abastece_cd: string | null;
  prioridad_cd: number | null;
  comprar_en_el_cd: string | null;
  tiene_stock_cd: boolean | null;
  demanda_mensual: number | null;
  demanda_diaria: number | null;
  desv_std_mensual: number | null;
  stock_seguridad: number | null;
  punto_de_pedido: number | null;
  nivel_maximo: number | null;
  costo_unitario: number | null;
  pedir: string | null;
  reemplazos: string | null;
  clasificacion_abc_agregada: string | null;
  sucursales_origen_cd: string | null;
  sugerido_suc: number | null;
  stock_activo_suc: number | null;
  stock_en_transito_suc: number | null;
  stock_en_cd: number | null;
  sugerido_traslado: number | null;
  sugerido_compra_neto: number | null;
  total_sugerido_suc: number | null;
  total_valor_sugerido_clp: number | null;
  pedir_flag: string | null;
  trasladar_desde: string | null;
  // Stock por bodega/sucursal (espejo de las columnas del BI).
  stock_linderos: number | null;
  stock_curico: number | null;
  stock_talca: number | null;
  stock_rancagua: number | null;
  stock_diez_de_julio_2: number | null;
  stock_chillan: number | null;
  stock_cd_repuestos: number | null;
  stock_brasil_18: number | null;
  stock_placilla: number | null;
  stock_chillan_viejo: number | null;
  stock_talca_2: number | null;
  // Precios FORD (cruce por codigo con la tabla Precios del BI; null si no esta en la lista).
  precio_flota_ford: number | null;
  precio_dealer_ford: number | null;
  precio_publico_ford: number | null;
  precio_publico_iva_ford: number | null;
  precio_reposicion_ford: number | null;
  precio_urgente_vor_ford: number | null;
  precio_promociones_ford: number | null;
  precio_urgente_recargo15_ford: number | null;
  // Lista de Gildemeister (Hyundai, JAC, Mahindra...): tres conceptos, no los ocho de FORD.
  precio_sugerido_gilde: number | null;
  precio_dealer_gilde: number | null;
  precio_final_dealer_gilde: number | null;
  // Margen calculado en el backend (services/margen.py).
  margen_unitario_clp: number | null;
  margen_pct: number | null;
  margen_flota_pct: number | null;
  margen_sugerido_clp: number | null;
  sobrecosto_vs_dealer_pct: number | null;
  /** Unidades ya marcadas como pedidas (services/pedidos_service.py). */
  unidades_pedidas: number | null;
  /** Repuesto de pauta de mantención que no puede faltar (services/instock_service.py). */
  instock: boolean | null;
  /** Modelos de la pauta que lo usan ("F-150, Ranger"). */
  instock_modelos: string | null;
  /** Unidades que nunca pueden faltar en una sucursal con taller. */
  instock_minimo: number | null;
  /** Cuánto sumó la regla del mínimo a esta fila. */
  instock_agregado: number | null;
}

export interface SugeridoPage {
  items: SugeridoRow[];
  total: number;
  page: number;
  limit: number;
}

export interface SugeridoKpis {
  /** Incluyen las sugerencias manuales vigentes (igual que la tabla). */
  total_sugerido: number;
  valor_total_clp: number;
  n_productos: number;
  n_proveedores: number;
  /** Conteo exacto de filas que cumplen los filtros (incluidos los de columna). */
  n_filas?: number;
  /** Cuánto de los totales de arriba viene de sugerencias manuales. */
  total_sugerido_manual?: number;
  valor_manual_clp?: number;
  /** Cuánto viene de la regla InStock (mínimo de repuestos de pauta). */
  total_sugerido_instock?: number;
  valor_instock_clp?: number;
}

/** Filtro de una columna del grid (traducido del multi-select). Se usa el campo
 *  que venga: `contiene` (ILIKE %texto%) o `valores` (IN exacto; "(en blanco)" = nulo). */
export interface ColumnaFiltro {
  campo: string;
  contiene?: string;
  valores?: string[];
}

export interface AgrupadoRow {
  grupo: string;
  total_sugerido: number;
  valor_clp: number;
  n_productos: number;
}

export type DimensionAgrupado = "sucursal" | "marca" | "proveedor";

export interface VentaMes {
  mes: string; // YYYYMM
  cantidad: number;
}

export interface VentasResponse {
  producto: string;
  sucursal_id: string;
  meses_general: VentaMes[];
  meses_sucursal: VentaMes[];
  total_general: number;
  total_sucursal: number;
}

export interface SugeridoFiltros {
  q?: string;
  sucursales?: string[];
  abc?: string[];
  filtro1?: string[];
  tipo_origen?: string[];
  /** Busqueda parcial por nombre de proveedor (legacy, ILIKE %valor%). */
  proveedor?: string;
  /** Multi-seleccion exacta de proveedores (modal sugerencia manual). */
  proveedores?: string[];
  solo_pedir?: boolean;
  solo_nacionales?: boolean;
  vista?: "todas" | "sucursales" | "cd" | "distribucion";
  /** Filtros de columna del grid. El front los manda a KPIs y export (no al
   *  listado de filas) para que los agregados sean exactos sobre el total. */
  filtros_columna?: ColumnaFiltro[];
}

export interface Sucursal {
  sucursal_id: string;
  nombre: string | null;
  region: string | null;
  abastece_desde_cd: string | null;
  prioridad_cd: number | null;
}

export interface Producto {
  producto: string;
  descripcion: string | null;
  filtro1_final: string | null;
  unidad_medida: string | null;
  costo_unitario: number | null;
  proveedor: string | null;
  es_importado: boolean | null;
}

export interface SugerenciaManual {
  id: string;
  producto: string;
  sucursal_id: string;
  unidades: number;
  motivo: string | null;
  creado_por: string | null;
  creado_en: string;
  aprobado: boolean;
  usado_en_compra: boolean;
  /** UUID compartido por las filas de una misma carga masiva. */
  lote_id?: string | null;
  /** Fecha (ISO) en que se archiva automáticamente. null = no vence. */
  expira_en?: string | null;
  archivada?: boolean;
  /** Cómo se pidió (null los dos = unidades directas). */
  dias_inventario?: number | null;
  stock_objetivo?: number | null;
  /** Si vino de una regla que se repite sola. */
  recurrente_id?: string | null;
}

/**
 * Regla InStock: repuestos de pauta que no pueden faltar en las sucursales con
 * taller. No la crea nadie desde la interfaz —sale de las pautas del fabricante—,
 * pero se muestra junto a las recurrentes porque hace lo mismo que una de
 * "mantener N unidades" y no vence nunca.
 */
export interface InstockResumen {
  /** false cuando no hay repuestos cargados: la regla existe pero no hace nada. */
  activo: boolean;
  n_repuestos: number;
  minimo: number;
  /** false si algún repuesto tiene un mínimo distinto. */
  minimo_uniforme: boolean;
  sucursales: string[];
  por_marca: Record<string, number>;
}

/** Vista previa del modo "mantener stock": de dónde sale el número. */
export interface PreviewObjetivo {
  objetivo: number;
  stock: number;
  transito: number;
  sugerido_sistema: number;
  cubierto: number;
  faltante: number;
  /** Si el producto está en el sugerido de esa sucursal (si no, el stock sale de bodega). */
  en_sugerido: boolean;
  desglose: string;
  /** En qué bodegas está ese stock, para poder comprobarlo. */
  bodegas: { bodega: string; stock: number; origen: string | null }[];
}

/**
 * Vista previa del modo "días de inventario". Mismas partes que el objetivo (el
 * nivel se descuenta igual), más la demanda y los días que ya cubre lo que hay.
 */
export interface PreviewDias extends PreviewObjetivo {
  dias: number;
  demanda_diaria: number;
  /** Cuántos días alcanza a cubrir hoy el stock + tránsito + sugerido del sistema. */
  dias_cubiertos: number;
  /** Sin demanda diaria no hay forma de convertir días a unidades. */
  sin_demanda: boolean;
}

export interface LineaCarro {
  producto: string;
  descripcion: string | null;
  clasificacion_abc: string | null;
  cantidad: number;
  costo_unitario: number | null;
  subtotal_clp: number;
}

export interface CarroProveedor {
  proveedor: string;
  n_productos: number;
  total_unidades: number;
  total_clp: number;
  lineas: LineaCarro[];
}

export interface CarrosResponse {
  carros: CarroProveedor[];
  total_proveedores: number;
  total_clp: number;
  total_unidades: number;
}

export interface RecurrenteCreate {
  modo: "individual" | "grupo";
  producto?: string | null;
  sucursal_id?: string | null;
  filtros?: SugeridoFiltros | null;
  unidades?: number | null;
  dias_inventario?: number | null;
  /** Nivel de stock a mantener: cada ejecución repone solo la brecha que falte. */
  stock_objetivo?: number | null;
  motivo?: string | null;
  cada_dias: number;
  fecha_fin?: string | null; // YYYY-MM-DD
}

export interface Recurrente {
  id: string;
  modo: string;
  resumen: string;
  unidades: number;
  dias_inventario: number | null;
  stock_objetivo: number | null;
  motivo: string | null;
  cada_dias: number;
  proxima_ejecucion: string;
  fecha_fin: string | null;
  activa: boolean;
  ultima_ejecucion: string | null;
}

export interface CatalogoRow {
  id: number;
  producto: string;
  glosa: string | null;
  familia: string | null;
  subfamilia: string | null;
  procedencia: string | null;
  tipo_repuesto: string | null;
  categoria: string | null;
  sub_categoria: string | null;
  tipo_producto: string | null;
  clasificacion_stock: string | null;
  costo: number | null;
  precio: number | null;
  stock_total: number | null;
  stock_minimo: number | null;
  stock_maximo: number | null;
  sub_modelo: string | null;
  cilindrada: string | null;
  combustible: string | null;
  anio: string | null;
  unidad: string | null;
  reemplazo: string | null;
}

export interface CatalogoPage {
  items: CatalogoRow[];
  total: number;
  page: number;
  limit: number;
}

export interface CatalogoFiltros {
  q?: string;
  familia?: string[];
  procedencia?: string[];
  categoria?: string[];
  con_stock?: boolean;
}

export interface CatalogoOpciones {
  familias: string[];
  procedencias: string[];
  categorias: string[];
}

export interface StockSucursalRow {
  bodega: string | null;
  sucursal_id: string | null;
  stock: number;
  origen: string | null;
}

export interface CatalogoDetalle extends CatalogoRow {
  stock_por_sucursal: StockSucursalRow[];
}

export interface CargaResultado {
  filas_cargadas: number;
  productos: number;
  sucursales: number;
  columnas_detectadas: string[];
  advertencias: string[];
}

export interface AuditoriaLog {
  id: string;
  accion: string;
  entidad: string;
  entidad_id: string | null;
  usuario_email: string | null;
  producto: string | null;
  sucursal_id: string | null;
  unidades: number | null;
  dias_inventario: number | null;
  motivo: string | null;
  detalle: string | null;
  creado_en: string;
}

export interface AuditoriaPage {
  items: AuditoriaLog[];
  total: number;
  limit: number;
  offset: number;
}

export interface Notificacion {
  id: string;
  tipo: string;
  titulo: string;
  mensaje: string | null;
  creado_por_email: string | null;
  producto: string | null;
  sucursal_id: string | null;
  creado_en: string;
  leida: boolean;
}

export interface NotificacionesResponse {
  items: Notificacion[];
  no_leidas: number;
}

export interface VentasMes {
  periodo: string;
  clp: number;
  unidades: number;
}

export interface VentasSucursalRow {
  sucursal: string;
  clp: number;
  unidades: number;
  n_lineas: number;
}

export interface VentasPorSucursal {
  periodo: string | null;
  items: VentasSucursalRow[];
}

export interface VentaLinea {
  _id: number;
  [columna: string]: string | number | null;
}

export interface VentasLineasPage {
  items: VentaLinea[];
  total: number;
  page: number;
  limit: number;
  columnas: string[];
}

export interface VentasLineasFiltros {
  periodo_desde?: string;
  periodo_hasta?: string;
  fecha_desde?: string;  // YYYY-MM-DD
  fecha_hasta?: string;  // YYYY-MM-DD
  sucursal?: string;
  q?: string;
}

/** Enlace a un archivo que vive en SharePoint (no lo almacena la plataforma). */
/** Salud del inventario: donde esta la plata detenida y donde falta. */
export interface InventarioResumen {
  valor_inventario_clp: number;
  unidades: number;
  n_filas: number;
  inmovilizado_clp: number;
  inmovilizado_n: number;
  inmovilizado_pct: number;
  sobre_stock_clp: number;
  sobre_stock_n: number;
  sobre_stock_pct: number;
  quiebre_con_demanda_n: number;
  bajo_punto_pedido_n: number;
  sin_costo_n: number;
  cobertura_dias_mediana: number | null;
}

export interface InventarioSucursal {
  sucursal_id: string;
  nombre_sucursal: string;
  valor_clp: number;
  unidades: number;
  inmovilizado_clp: number;
  sobre_stock_clp: number;
  quiebre_con_demanda_n: number;
  bajo_punto_pedido_n: number;
  n_productos: number;
}

export interface InventarioMarca {
  marca: string;
  valor_clp: number;
  inmovilizado_clp: number;
  n_productos: number;
}

export interface InventarioInmovilizado {
  producto: string;
  descripcion: string | null;
  sucursal_id: string;
  nombre_sucursal: string;
  unidades: number;
  valor_clp: number;
}

export interface InventarioSalud {
  resumen: InventarioResumen;
  por_sucursal: InventarioSucursal[];
  por_marca: InventarioMarca[];
  top_inmovilizado: InventarioInmovilizado[];
  dias_sobre_stock: number;
}

/** Incidencia: reporte de un error de la plataforma. */
export type EstadoIncidencia = "abierta" | "en_revision" | "resuelta" | "descartada";

export interface Incidencia {
  id: string;
  titulo: string;
  descripcion: string | null;
  pantalla: string | null;
  producto: string | null;
  sucursal_id: string | null;
  estado: EstadoIncidencia;
  respuesta: string | null;
  reportado_por: string | null;
  resuelto_por: string | null;
  creado_en: string;
  actualizado_en: string | null;
}

export interface IncidenciasResponse {
  items: Incidencia[];
  abiertas: number;
}

export interface IncidenciaCreate {
  titulo: string;
  descripcion?: string | null;
  pantalla?: string | null;
  producto?: string | null;
  sucursal_id?: string | null;
}

/** Comparacion motor propio vs Power BI (modo sombra). */
export interface DivergenciaMotor {
  producto: string;
  sucursal_id: string;
  diferencias: Record<string, { motor: string | number | null; bi: string | number | null }>;
}

export interface ComparacionMotor {
  id: string;
  creado_en: string;
  filas_motor: number;
  filas_bi: number;
  filas_comunes: number;
  filas_solo_motor: number;
  filas_solo_bi: number;
  paridad_pct: number;
  ejecutado_por: string | null;
  detalle: {
    por_columna: Record<string, { iguales: number; distintas: number }>;
    ejemplos: DivergenciaMotor[];
    ejemplos_solo_motor: string[];
    ejemplos_solo_bi: string[];
  } | null;
}

/** Linea del sugerido que ya se pidio (cierre del loop con la OC). */
export interface LineaPedida {
  id: string;
  producto: string;
  sucursal_id: string;
  unidades: number;
  n_oc: string | null;
  proveedor: string | null;
  recibido: boolean;
  fecha_recepcion: string | null;
  creado_por: string | null;
  creado_en: string;
}

/** Resultado del simulador what-if. */
export interface SimulacionSucursal {
  sucursal_id: string;
  nombre_sucursal: string;
  actual_u: number;
  simulado_u: number;
  actual_clp: number;
  simulado_clp: number;
  delta_u: number;
  delta_clp: number;
}

export interface SimulacionCambio {
  producto: string;
  sucursal_id: string;
  actual: number;
  simulado: number;
  delta: number;
  delta_clp: number;
}

/** Parametros calibrables como los guarda la tabla (nombres planos). */
export interface ConfigModeloPlano {
  ciclo_orden_dias: number;
  ciclo_orden_dias_cd: number;
  z_a: number;
  z_b: number;
  z_c: number;
  z_d: number;
  z_imp_cd_a: number;
  z_imp_cd_b: number;
  lead_time_fallback_dias: number;
  winsor_k: number;
  lt_cd_rm_dias: number;
  lt_cd_resto_dias: number;
  lt_tope_dias: number;
  transito_nacional_dias: number;
  transito_importado_dias: number;
  dias_habiles_mes: number;
  reponer_a_maximo: boolean;
  clases_que_reponen: ClasesQueReponen;
  abc_umbral_a_m6: number;
  abc_umbral_b_m6: number;
  abc_umbral_c_m6: number;
  abc_umbral_c_m3: number;
  abc_umbral_c_m12: number;
}

/** A que productos alcanza la reposicion al nivel maximo. */
export type ClasesQueReponen = "AB" | "ABCD";

/** Configuracion del modelo como la devuelve la API (Z en diccionarios). */
export interface ConfigModelo {
  ciclo_orden_dias: number;
  ciclo_orden_dias_cd: number;
  z_por_clase: Record<string, number>;
  z_importado_cd: Record<string, number>;
  lead_time_fallback_dias: number;
  winsor_k: number;
  lt_cd_rm_dias: number;
  lt_cd_resto_dias: number;
  lt_tope_dias: number;
  transito_nacional_dias: number;
  transito_importado_dias: number;
  dias_habiles_mes: number;
  reponer_a_maximo: boolean;
  clases_que_reponen: ClasesQueReponen;
  abc_umbral_a_m6: number;
  abc_umbral_b_m6: number;
  abc_umbral_c_m6: number;
  abc_umbral_c_m3: number;
  abc_umbral_c_m12: number;
  id: string | null;
  creado_en: string | null;
  creado_por: string | null;
  nota: string | null;
  es_default: boolean;
}

/** Lead time que calculo el motor (sucursal_id null = global del proveedor). */
export interface LeadTimeFila {
  proveedor: string;
  sucursal_id: string | null;
  lead_time_dias: number;
  n_muestras: number | null;
}

export interface LeadTimeResponse {
  total: number;
  actualizado_en: string | null;
  items: LeadTimeFila[];
}

export interface SimulacionResultado {
  parametros: {
    ciclo_orden_dias: number;
    ciclo_orden_dias_cd: number;
    z_por_clase: Record<string, number>;
    factor_lead_time: number;
  };
  resumen: {
    actual_unidades: number;
    simulado_unidades: number;
    delta_unidades: number;
    actual_clp: number;
    simulado_clp: number;
    delta_clp: number;
    lineas_que_cambian: number;
    n_filas: number;
  };
  por_sucursal: SimulacionSucursal[];
  mayores_cambios: SimulacionCambio[];
}

/** Histórico de ventas (desde 2018), para consulta sin bajar planillas. */
export interface VentasHistoricasMeta {
  periodo_min: string | null;
  periodo_max: string | null;
  filas: number;
  sucursales: string[];
}

export interface VentasHistoricasFiltros {
  producto?: string;
  sucursal?: string;
  periodo_desde?: string; // YYYYMM
  periodo_hasta?: string; // YYYYMM
  /** Incluir conceptos internos (D&P, insumos, incentivos). */
  incluir_internos?: boolean;
}

export interface VentaHistoricaFila {
  periodo: string;
  producto: string;
  sucursal: string | null;
  cantidad: number;
  neto: number | null;
  n_lineas: number | null;
}

export interface VentasHistoricasResp {
  detalle: { items: VentaHistoricaFila[]; total: number; truncado: boolean };
  por_periodo: { periodo: string; cantidad: number; neto: number }[];
  por_sucursal: { sucursal: string; cantidad: number; neto: number }[];
}

/** Estado del boton "Actualizar ahora". El recalculo lo corre un agente instalado en
 *  el PC que tiene los Excel; la web solo deja pedido y consulta como va. */
export interface EstadoActualizacion {
  id: string | null;
  /** pendiente | en_curso | ok | error | expirada, o null si nunca se ha pedido. */
  estado: "pendiente" | "en_curso" | "ok" | "error" | "expirada" | null;
  /** Resultado en lenguaje de usuario: se muestra tal cual. */
  mensaje: string | null;
  solicitado_por: string | null;
  creado_en: string | null;
  terminado_en: string | null;
  ultima_sincronizacion: string | null;
  puede_actualizar: boolean;
}
