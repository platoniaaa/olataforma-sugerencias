// Definicion central de las columnas de la lista de precios.
import { formatoCLP, formatoNumero } from "./formato";
import type { PrecioDetalle, PrecioRow } from "./types";
import { fechaCorta, hoyLocal, type TonoVigencia } from "./vigencia";

export type TipoColPrecio = "texto" | "numero" | "decimal" | "clp" | "pct" | "fecha" | "estado" | "bool" | "vigencia";

export interface DefColPrecio {
  key: keyof PrecioRow;
  label: string;
  tipo: TipoColPrecio;
  visiblePorDefecto: boolean;
  pin?: "left" | "right";
  /** Texto de ayuda en la cabecera. */
  ayuda?: string;
  /** Ancho inicial en pixeles, para las que traen un chip y no caben en el minimo. */
  ancho?: number;
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
    ayuda: "Todas las bodegas de Curifor menos dañados, devolución, scrap y la bodega sin nombre (el desglose está en la ficha)" },
  { key: "precio_erp", label: "Precio ERP", tipo: "clp", visiblePorDefecto: true, ayuda: "El precio que tiene hoy el ERP" },
  { key: "precio_final", label: "Precio final", tipo: "clp", visiblePorDefecto: true, pin: "right",
    ayuda: "Lo que se manda al ERP: precio fijo o congelado si hay, calculado si no" },
  { key: "estado", label: "Estado", tipo: "estado", visiblePorDefecto: true, pin: "right" },
  // La fecha de termino manda: ordenar por esta columna es ordenar por lo que vence primero.
  { key: "vigente_hasta", label: "Vigencia", tipo: "vigencia", visiblePorDefecto: true, pin: "right", ancho: 180,
    ayuda: "Hasta cuándo rige el precio fijo, el margen fijo o el congelado. «Programado»: todavía no empieza. «Vencido»: ya terminó y el producto volvió a la regla." },
  { key: "cambios_pendientes", label: "Cambios", tipo: "numero", visiblePorDefecto: true, pin: "right",
    ayuda: "Diferencias detectadas en el ultimo recalculo que nadie reviso" },
  // Ocultas por defecto
  { key: "precio_calculado", label: "Precio calculado", tipo: "clp", visiblePorDefecto: false,
    ayuda: "Lo que da la regla sin mirar precio fijo ni congelado" },
  // Estas dos solo se llenan si la decision RIGE hoy: una programada o vencida sigue guardada
  // (se ve en la ficha, con «Renovar») pero no es el precio de nadie.
  { key: "precio_fijo", label: "Precio fijo", tipo: "clp", visiblePorDefecto: false,
    ayuda: "Solo si rige hoy. Si está programado o vencido queda guardado, pero no se muestra acá (ver Vigencia)" },
  { key: "congelar", label: "Congelado", tipo: "bool", visiblePorDefecto: false,
    ayuda: "Solo si rige hoy. Si está vencido queda guardado, pero no se muestra acá (ver Vigencia)" },
  { key: "vigente_desde", label: "Vigente desde", tipo: "fecha", visiblePorDefecto: false,
    ayuda: "Primer día en que rigen el precio fijo, el margen fijo o el congelado. Vacío: desde que se guardaron" },
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

/** Columnas visibles por defecto que se agregaron DESPUES de que alguien pudo guardar su
 *  propia seleccion. La seleccion guardada manda sobre los defaults, asi que sin esto quien ya
 *  uso la pantalla nunca veria una columna nueva. */
export const COLUMNAS_NUEVAS_VISIBLES = ["vigente_hasta"];

/**
 * Suma a la seleccion guardada las columnas visibles por defecto que la persona todavia no ha
 * visto, UNA sola vez: despues quedan registradas como vistas, y si las oculta no vuelven.
 *
 * `vistas` son las claves que la persona ya conocia (null = nunca se registraron: se asume que
 * conocia todas menos las nuevas). Devuelve la seleccion y las vistas a guardar.
 */
export function migrarColumnasGuardadas(
  guardadas: string[],
  vistas: string[] | null,
): { columnas: string[]; vistas: string[] } {
  const todas = COLUMNAS_PRECIOS.map((c) => c.key as string);
  const yaVistas = vistas ?? todas.filter((k) => !COLUMNAS_NUEVAS_VISIBLES.includes(k));
  const nuevas = COLUMNAS_PRECIOS
    .filter((c) => c.visiblePorDefecto && !yaVistas.includes(c.key as string) && !guardadas.includes(c.key as string))
    .map((c) => c.key as string);
  return {
    columnas: nuevas.length ? [...guardadas, ...nuevas] : guardadas,
    vistas: Array.from(new Set([...yaVistas, ...todas])),
  };
}

export const LS_COLUMNAS_PRECIOS = "precios_columnas_visibles";
export const LS_COLUMNAS_PRECIOS_VISTAS = "precios_columnas_vistas";

type Almacen = Pick<Storage, "getItem" | "setItem">;

function leerLista(almacen: Almacen, clave: string): string[] | null {
  try {
    const crudo = almacen.getItem(clave);
    if (!crudo) return null;
    const valor: unknown = JSON.parse(crudo);
    return Array.isArray(valor) && valor.every((x) => typeof x === "string") ? (valor as string[]) : null;
  } catch {
    return null;   // un valor roto se ignora, como si no hubiera nada guardado
  }
}

/**
 * La seleccion de columnas que la persona dejo en este navegador, ya migrada: le suma las
 * columnas nuevas visibles por defecto y deja registrado que ya las vio. null si no hay nada
 * guardado (o el navegador no deja leer): la pantalla usa los defaults. Nunca lanza: en una
 * ventana privada o con el almacenamiento bloqueado la lista tiene que abrir igual.
 */
export function leerColumnasGuardadas(almacen?: Almacen): string[] | null {
  try {
    const a = almacen ?? window.localStorage;
    const guardadas = leerLista(a, LS_COLUMNAS_PRECIOS);
    // Las vistas se registran tambien cuando no hay seleccion guardada: quien oculte una
    // columna despues de esto no debe verla reaparecer en la visita siguiente.
    const migrado = migrarColumnasGuardadas(
      guardadas && guardadas.length ? guardadas : KEYS_PRECIOS_DEFAULT,
      leerLista(a, LS_COLUMNAS_PRECIOS_VISTAS),
    );
    try {
      a.setItem(LS_COLUMNAS_PRECIOS_VISTAS, JSON.stringify(migrado.vistas));
    } catch {
      /* no se pudo registrar: la seleccion de esta visita sirve igual */
    }
    return guardadas && guardadas.length ? migrado.columnas : null;
  } catch {
    return null;
  }
}

/** Colores de la etiqueta de estado. Semantica, no decoracion: rojo es lo que
 *  hay que mirar antes de mandar al ERP. */
export function claseEstado(estado: string | null | undefined): string {
  switch ((estado ?? "").toUpperCase()) {
    case "OK":
      return "bg-emerald-50 text-emerald-700";
    case "FIJO":
      return "bg-sky-50 text-sky-700";
    case "MARGEN":
      return "bg-teal-50 text-teal-700";
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

/** Colores del chip de vigencia. El color acompaña: el ícono y la palabra son la señal. */
export function claseVigencia(tono: TonoVigencia): string {
  switch (tono) {
    case "pronto":
      return "border-amber-200 bg-amber-50 text-amber-800";
    case "programado":
      return "border-brand/30 bg-brand-50 text-brand";
    case "vencido":
      return "border-ink-200 bg-ink-100 text-ink-600";
    default:
      return "border-ink-200 bg-white text-ink-600";
  }
}


/**
 * La cuenta que dio el precio, en una línea.
 *
 * Antes había que armarla mentalmente saltando entre "Costo", "Factor" y
 * "Precio calculado", tres filas separadas de una lista de once. Y cuando el
 * precio NO salía de esa cuenta —fijo, congelado, sin stock— nada lo decía: el
 * factor y el costo seguían ahí, invitando a multiplicarlos y a no cuadrar.
 *
 * Con vigencia: `precio_fijo`, `margen_fijo` y `congelar` son la decisión GUARDADA, no
 * necesariamente la que rige. Si su periodo está programado o vencido el precio sale de la
 * regla, y decir «Precio fijo puesto a mano» sería falso.
 */
export function explicacionPrecio(d: PrecioDetalle, hoy: string = hoyLocal()): string {
  const estado = d.vigencia ?? null;
  if (estado === "programada" || estado === "vencida") {
    const regla = conMinuscula(cuenta({ ...d, precio_fijo: null, margen_fijo: null, congelar: false }));
    const nombre = conMayuscula(decisionGuardada(d));
    if (estado === "programada") {
      const desde = d.vigente_desde ? ` empieza el ${fechaCorta(d.vigente_desde, hoy)}` : " todavía no empieza";
      return `Hoy sigue la regla: ${regla}. ${nombre}${desde}.`;
    }
    const vencio = d.vigente_hasta ? `Venció el ${fechaCorta(d.vigente_hasta, hoy)}` : "Venció";
    return `${vencio}: volvió a la regla (${regla}). ${nombre} sigue guardado.`;
  }
  const texto = cuenta(d);
  // Rigiendo y con fecha de termino: lo dice, para no abrir las fechas a ver hasta cuando.
  if (estado === "vigente" && d.vigente_hasta && decisionActiva(d, texto)) {
    return `${texto} · hasta el ${fechaCorta(d.vigente_hasta, hoy)}`;
  }
  return texto;
}

/** La decision de una persona que gobierna el periodo, nombrada: precio fijo > congelado > margen. */
function decisionGuardada(d: PrecioDetalle): string {
  if (d.precio_fijo !== null && d.precio_fijo !== undefined) return `el precio fijo de ${formatoCLP(d.precio_fijo)}`;
  if (d.congelar) {
    return `el precio congelado${d.congelado_precio != null ? ` de ${formatoCLP(d.congelado_precio)}` : ""}`;
  }
  if (d.margen_fijo != null) return `el margen fijo de ${formatoNumero(d.margen_fijo, 1)} %`;
  return "la decisión";
}

/** Si la linea que se armo habla de la decision (fijo, congelado o margen) y no de otra cosa
 *  que le gana (no es producto, sin stock). */
function decisionActiva(d: PrecioDetalle, texto: string): boolean {
  return texto === "Precio fijo puesto a mano" || texto === "Congelado: no sigue al costo"
    || (d.margen_fijo != null && /margen/i.test(texto));
}

function conMinuscula(t: string): string {
  return t.charAt(0).toLowerCase() + t.slice(1);
}

function conMayuscula(t: string): string {
  return t.charAt(0).toUpperCase() + t.slice(1);
}

/** La cuenta tal cual, sin mirar la vigencia: el orden es el de `precios_service.calcular`. */
function cuenta(d: PrecioDetalle): string {
  if (d.precio_fijo !== null && d.precio_fijo !== undefined) return "Precio fijo puesto a mano";
  if (d.congelar) return "Congelado: no sigue al costo";
  if (d.no_producto) return "No es un producto: sin precio";
  if ((d.stock ?? 0) <= 0 && (d.stock_transito ?? 0) <= 0) return "Sin stock ni tránsito → 0";
  if (d.margen_fijo != null && d.costo && d.factor) {
    return `${formatoCLP(d.costo)} × ${formatoNumero(d.factor, 2)} (margen ${formatoNumero(d.margen_fijo, 1)} %) = ${formatoCLP(d.precio_calculado)}`;
  }
  if (d.margen_fijo != null) return "Margen fijo sin costo cargado";
  if ((d.tipo ?? "").toLowerCase() === "sugerido") return "Precio de lista del proveedor";
  if (d.costo && d.factor) {
    return `${formatoCLP(d.costo)} × ${formatoNumero(d.factor, 2)} = ${formatoCLP(d.precio_calculado)}`;
  }
  if (!d.factor) return "Sin factor para este tipo y procedencia";
  return "Sin costo cargado";
}
