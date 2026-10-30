// Cliente del API. Centraliza las llamadas al backend FastAPI.
import { clearSession, getToken, setSession } from "./auth";
import type {
  AbcStockFila,
  AbcStockResumen,
  AgrupadoRow,
  AuditoriaPage,
  CargaPegadaResultado,
  ContextoVendedor,
  CargaResultado,
  CarrosResponse,
  CatalogoDetalle,
  ConsultaDetalle,
  ConsultaPage,
  CatalogoFiltros,
  CatalogoOpciones,
  CatalogoPage,
  DetalleProducto,
  DetalleSugerencia,
  DimensionAgrupado,
  EstadoActualizacion,
  GrupoVentas,
  InstockResumen,
  MisSucursales,
  NotificacionesResponse,
  Producto,
  ProductoBuscado,
  Requerimiento,
  RepuestoInstock,
  Tablero,
  RequerimientosPage,
  Sucursal,
  SugerenciaManual,
  SugeridoFiltros,
  RequerimientoResponse,
  SugeridoKpis,
  SugeridoOpciones,
  SugeridoPage,
  TipoActualizacion,
  Recurrente,
  RecurrenteCreate,
  VentasResponse,
} from "./types";

const BASE = process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000";

function authHeaders(): Record<string, string> {
  const t = getToken();
  return t ? { Authorization: `Bearer ${t}` } : {};
}

/** fetch con token, sin cache, y manejo de sesion expirada (401 -> login). */
export async function req(path: string, init: RequestInit = {}): Promise<Response> {
  const res = await fetch(`${BASE}${path}`, {
    ...init,
    cache: "no-store",
    headers: { ...authHeaders(), ...(init.headers as Record<string, string> | undefined) },
  });
  if (
    res.status === 401 &&
    typeof window !== "undefined" &&
    !window.location.pathname.startsWith("/login")
  ) {
    clearSession();
    window.location.href = "/login";
  }
  return res;
}

/** La carga de precios escribe: si la respuesta se pierde no se sabe si quedo cargada. */
export const MENSAJE_CARGA_SIN_CONFIRMAR =
  "No se pudo confirmar la carga: se cortó la conexión. Vuelve a subir el archivo: si ya se cargó, dirá que no hay cambios.";

/** Nombre del error de una carga cuya respuesta se perdio: puede haber quedado cargada. */
export const NOMBRE_CARGA_SIN_CONFIRMAR = "CargaSinConfirmar";

function errorCargaSinConfirmar(): Error {
  const e = new Error(MENSAJE_CARGA_SIN_CONFIRMAR);
  e.name = NOMBRE_CARGA_SIN_CONFIRMAR;
  return e;
}

/** Lo que se le dice a la persona cuando el servidor no contesta. */
export const MENSAJE_SIN_SERVIDOR =
  "No se pudo conectar con el servidor. Puede estar reiniciándose: espera un minuto y vuelve a intentar.";

/** Error de una solicitud al buzon del PC del motor, con el codigo HTTP (0 = sin
 *  respuesta). La tarjeta distingue el 409: ya hay otra solicitud viva. */
export class ErrorSolicitud extends Error {
  constructor(public status: number, mensaje: string) {
    super(mensaje);
    this.name = "ErrorSolicitud";
  }
}

// Cuánto se espera antes de cada reintento. Render (plan gratis) tarda hasta un
// minuto en volver cuando se reinicia, y suma ~76 s en total.
const ESPERAS_REINTENTO_MS = [3_000, 8_000, 20_000, 45_000];

/**
 * `req`, pero reintenta los cortes de conexión y las caídas del proxy (502, 503,
 * 504). `fetch` rechaza con TypeError ("Failed to fetch") cuando no hay respuesta
 * utilizable: el servidor se está reiniciando, se cortó la red, o respondió un
 * error sin cabeceras de CORS. Sirve para pedidos que se pueden repetir sin
 * efectos; los que escriben necesitan además un identificador (ver `lote` en
 * `exportarPrecios`).
 */
export async function reqConReintentos(
  path: string,
  init: RequestInit = {},
  opciones: {
    esperasMs?: number[];
    alReintentar?: (intento: number, total: number) => void;
    /** Cancela el pedido y los reintentos que faltan (la lectura ya no interesa). */
    signal?: AbortSignal;
  } = {}
): Promise<Response> {
  const esperas = opciones.esperasMs ?? ESPERAS_REINTENTO_MS;
  const { signal } = opciones;
  for (let intento = 0; ; intento++) {
    const ultimo = intento >= esperas.length;
    try {
      const res = await req(path, signal ? { ...init, signal } : init);
      if (ultimo || ![502, 503, 504].includes(res.status)) return res;
    } catch (e) {
      if (signal?.aborted || ultimo || !(e instanceof TypeError)) throw e;
    }
    opciones.alReintentar?.(intento + 1, esperas.length);
    await esperar(esperas[intento], signal);
  }
}

/** Espera `ms`, pero se corta de inmediato si se cancela: el temporizador no queda vivo. */
function esperar(ms: number, signal?: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const cancelado = () => signal?.reason ?? new DOMException("Cancelado", "AbortError");
    if (signal?.aborted) {
      reject(cancelado());
      return;
    }
    const alCancelar = () => {
      clearTimeout(t);
      reject(cancelado());
    };
    const t = setTimeout(() => {
      signal?.removeEventListener("abort", alCancelar);
      resolve();
    }, ms);
    signal?.addEventListener("abort", alCancelar, { once: true });
  });
}

/** Identificador de una descarga. `randomUUID` solo existe en contextos seguros. */
function nuevoIdentificador(): string {
  const c = typeof crypto !== "undefined" ? crypto : undefined;
  if (c && typeof c.randomUUID === "function") return c.randomUUID();
  return "xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx".replace(/[xy]/g, (ch) => {
    const r = (Math.random() * 16) | 0;
    return (ch === "x" ? r : (r & 0x3) | 0x8).toString(16);
  });
}

// El identificador de la descarga del archivo del ERP que sigue sin completarse.
// Se mantiene entre clics hasta que el archivo llega: si el servidor ya la
// registró pero la respuesta se perdió, el próximo intento recibe el MISMO archivo
// en vez de uno vacío.
let loteErpEnCurso: string | null = null;

async function getJSON<T>(path: string): Promise<T> {
  const res = await req(path);
  if (!res.ok) throw new Error(`Error ${res.status} en ${path}`);
  return res.json() as Promise<T>;
}

async function postJSON<T>(path: string, body: unknown): Promise<T> {
  const res = await req(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!res.ok) throw new Error(await mensajeError(res, `Error ${res.status} en ${path}`));
  return res.json() as Promise<T>;
}

/** Construye los query params a partir de los filtros del dashboard. */
function filtrosToParams(f: SugeridoFiltros): URLSearchParams {
  const p = new URLSearchParams();
  if (f.q) p.set("q", f.q);
  (f.sucursales ?? []).forEach((s) => p.append("sucursal", s));
  (f.abc ?? []).forEach((s) => p.append("abc", s));
  (f.filtro1 ?? []).forEach((s) => p.append("filtro1", s));
  (f.tipo_origen ?? []).forEach((s) => p.append("tipo_origen", s));
  if (f.proveedor) p.set("proveedor", f.proveedor);
  (f.proveedores ?? []).forEach((s) => p.append("proveedores", s));
  p.set("solo_pedir", String(f.solo_pedir ?? true));
  if (f.solo_nacionales) p.set("solo_nacionales", "true");
  if (f.vista && f.vista !== "todas") p.set("vista", f.vista);
  return p;
}

/** Mensaje legible del error del backend (FastAPI manda `detail` string o array). */
export async function mensajeError(res: Response, fallback: string): Promise<string> {
  const err = await res.json().catch(() => ({}));
  const d = (err as { detail?: unknown })?.detail;
  if (typeof d === "string") return d;
  if (Array.isArray(d) && d.length) {
    const msg = (d[0] as { msg?: string })?.msg;
    if (msg) return msg.replace(/^Value error, /, "");
  }
  return fallback;
}

async function descargar(path: string, body: unknown, fallbackNombre: string): Promise<void> {
  const res = await req(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  // El motivo del servidor si lo dio: un 503 dice que se esta cargando el sugerido.
  if (!res.ok) throw new Error(await mensajeError(res, "No se pudo generar el archivo"));
  const blob = await res.blob();
  const dispo = res.headers.get("Content-Disposition") ?? "";
  const match = dispo.match(/filename="?([^"]+)"?/);
  const nombre = match?.[1] ?? fallbackNombre;
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(url);
}

/** Entrega un archivo ya descargado al navegador, como si se hubiera hecho clic en un enlace. */
function guardarBlob(blob: Blob, nombre: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = nombre;
  a.click();
  URL.revokeObjectURL(url);
}

export const api = {
  baseUrl: BASE,

  /** Inicia sesion. No usa el wrapper (maneja el 401 como credencial incorrecta). */
  async login(email: string, password: string): Promise<void> {
    const res = await fetch(`${BASE}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ email, password }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo iniciar sesión");
    }
    const data = await res.json();
    setSession(data.token, data.email, data.nombre ?? null, Boolean(data.es_admin), Boolean(data.solo_lectura),
      // Si la API todavia no manda el campo (ventana de despliegue), no degradar a
      // un admin: se cae a es_admin en vez de escribir un false que persiste.
      Boolean(data.puede_calibrar ?? data.es_admin),
      Boolean(data.puede_actualizar ?? data.es_admin),
      Boolean(data.es_vendedor),
      Array.isArray(data.sucursales) ? data.sucursales : [],
      Boolean(data.puede_precios ?? data.es_admin));
  },

  async health(): Promise<{ status: string }> {
    return getJSON("/api/health");
  },

  async sugerido(
    f: SugeridoFiltros,
    opts: { page?: number; limit?: number; sort?: string } = {}
  ): Promise<SugeridoPage> {
    const p = filtrosToParams(f);
    p.set("page", String(opts.page ?? 1));
    p.set("limit", String(opts.limit ?? 1000));
    if (opts.sort) p.set("sort", opts.sort);
    return getJSON(`/api/sugerido?${p.toString()}`);
  },

  /** Proveedores, marcas, tipos de origen, clases y sucursales distintos de TODO el
   *  sugerido (con las sucursales del usuario). Para los desplegables: pocos KB, en
   *  vez de bajar 5.000 filas y sacarlos de ahi (dejaba fuera a 57 de 142). */
  async sugeridoOpciones(): Promise<SugeridoOpciones> {
    return getJSON("/api/sugerido/opciones");
  },

  async kpis(f: SugeridoFiltros): Promise<SugeridoKpis> {
    const p = filtrosToParams(f);
    if (f.filtros_columna?.length) p.set("filtros_columna", JSON.stringify(f.filtros_columna));
    return getJSON(`/api/sugerido/kpis?${p.toString()}`);
  },

  async agrupado(f: SugeridoFiltros, por: DimensionAgrupado): Promise<AgrupadoRow[]> {
    const p = filtrosToParams(f);
    if (f.filtros_columna?.length) p.set("filtros_columna", JSON.stringify(f.filtros_columna));
    p.set("por", por);
    return getJSON(`/api/sugerido/agrupado?${p.toString()}`);
  },

  async carros(f: SugeridoFiltros): Promise<CarrosResponse> {
    return getJSON(`/api/compras/carros?${filtrosToParams(f).toString()}`);
  },

  async exportOrden(f: SugeridoFiltros, proveedor?: string): Promise<void> {
    return descargar("/api/compras/export-excel", { filtros: f, proveedor: proveedor ?? null }, "orden_compra.xlsx");
  },

  async detalle(producto: string, sucursalId: string) {
    return getJSON(
      `/api/sugerido/${encodeURIComponent(producto)}/${encodeURIComponent(sucursalId)}`
    );
  },

  async ventas(producto: string, sucursalId: string): Promise<VentasResponse> {
    return getJSON(
      `/api/sugerido/${encodeURIComponent(producto)}/${encodeURIComponent(sucursalId)}/ventas`
    );
  },

  async sucursales(): Promise<Sucursal[]> {
    return getJSON("/api/sucursales");
  },

  // --- Detalle de una sugerencia manual --- //

  /** Qué productos toca una sugerencia y cuánto aporta cada uno. */
  async detalleSugerencia(tipo: string, id: string): Promise<DetalleSugerencia> {
    return getJSON(`/api/sugerencias-manuales/detalle/${tipo}/${encodeURIComponent(id)}`);
  },

  /** Pausa o reactiva una regla recurrente sin borrarla. */
  async pausarRecurrente(id: string, activa: boolean): Promise<{ activa: boolean }> {
    const res = await req(`/api/sugerencias-manuales/recurrentes/${id}/activa`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activa }),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo cambiar el estado"));
    return res.json() as Promise<{ activa: boolean }>;
  },

  /** Baja la lista del detalle en Excel. */
  async detalleSugerenciaExcel(tipo: string, id: string): Promise<void> {
    const res = await req(
      `/api/sugerencias-manuales/detalle/${tipo}/${encodeURIComponent(id)}/excel`
    );
    if (!res.ok) throw new Error("No se pudo generar el Excel");
    const blob = await res.blob();
    const cd = res.headers.get("Content-Disposition") ?? "";
    const nombre = /filename="?([^"]+)"?/.exec(cd)?.[1] ?? `sugerencia_${tipo}.xlsx`;
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombre;
    a.click();
    URL.revokeObjectURL(url);
  },

  // --- Requerimiento de sucursal: pegar la lista, decidir, bajar el archivo ---

  async analizarRequerimiento(
    sucursalId: string,
    texto: string
  ): Promise<RequerimientoResponse> {
    return postJSON("/api/requerimiento/analizar", { sucursal_id: sucursalId, texto });
  },

  async reanalizarRequerimiento(
    sucursalId: string,
    lineas: { producto: string; cantidad: number | null }[]
  ): Promise<RequerimientoResponse> {
    return postJSON("/api/requerimiento/reanalizar", { sucursal_id: sucursalId, lineas });
  },

  /** Descarga el CSV del portal. Devuelve cuántas líneas quedaron fuera. */
  async archivoPortal(
    proveedor: "FORD" | "GILDEMEISTER",
    sucursalId: string | null,
    lineas: { producto: string; cantidad: number | null }[]
  ): Promise<number> {
    const res = await req("/api/requerimiento/archivo-portal", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ proveedor, sucursal_id: sucursalId, lineas }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo generar el archivo");
    }
    const descartadas = Number(res.headers.get("X-Lineas-Descartadas") ?? 0);
    const cd = res.headers.get("Content-Disposition") ?? "";
    const nombre = /filename="?([^"]+)"?/.exec(cd)?.[1] ?? "pedido.csv";
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = nombre;
    a.click();
    URL.revokeObjectURL(url);
    return descartadas;
  },

  // --- Bandeja de requerimientos (vendedor de sucursal <-> comprador) --- //

  /** Sucursales por las que puede pedir el usuario. El vendedor nunca las escribe. */
  async misSucursales(): Promise<MisSucursales> {
    return getJSON("/api/requerimientos/mis-sucursales");
  },

  /** Buscador del carro: solo productos de la lista de precios de Curifor. */
  async buscarProductos(q: string, sucursalId?: string | null): Promise<ProductoBuscado[]> {
    const p = new URLSearchParams({ q });
    if (sucursalId) p.set("sucursal_id", sucursalId);
    return getJSON(`/api/requerimientos/buscar?${p.toString()}`);
  },

  /** Lista pegada -> líneas del carro, resueltas contra la lista de precios. */
  async pegarLista(
    texto: string,
    sucursalId?: string | null
  ): Promise<(ProductoBuscado & { cantidad: number | null; encontrado: boolean; texto_original: string | null })[]> {
    return postJSON("/api/requerimientos/pegar", { texto, sucursal_id: sucursalId });
  },

  /** La bandeja. El vendedor recibe los suyos; el comprador, todos. */
  async requerimientos(estados: string[] = []): Promise<RequerimientosPage> {
    const p = new URLSearchParams();
    estados.forEach((e) => p.append("estado", e));
    const qs = p.toString();
    return getJSON(`/api/requerimientos${qs ? `?${qs}` : ""}`);
  },

  async requerimiento(id: number): Promise<Requerimiento> {
    return getJSON(`/api/requerimientos/${id}`);
  },

  /** Consumo, tránsito, stock y modelo de UNA línea. Se pide al abrir la fila. */
  async detalleProductoRequerimiento(
    id: number,
    producto: string
  ): Promise<DetalleProducto> {
    return getJSON(
      `/api/requerimientos/${id}/producto/${encodeURIComponent(producto)}`
    );
  },

  async crearRequerimiento(body: {
    sucursal_id?: string | null;
    nota?: string | null;
    lineas: { producto: string; cantidad: number; comentario?: string | null }[];
  }): Promise<Requerimiento> {
    return postJSON("/api/requerimientos", body);
  },

  /** Decisión del comprador: cantidades aprobadas, nota y estado final. */
  async actualizarRequerimiento(
    id: number,
    body: {
      estado?: string;
      nota_comprador?: string | null;
      cantidades?: { linea_id: number; cantidad: number | null }[];
    }
  ): Promise<Requerimiento> {
    const res = await req(`/api/requerimientos/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo guardar"));
    return res.json() as Promise<Requerimiento>;
  },

  async productos(q: string): Promise<{ items: Producto[] }> {
    return getJSON(`/api/productos?q=${encodeURIComponent(q)}&limit=20`);
  },

  async catalogo(
    f: CatalogoFiltros,
    opts: { page?: number; limit?: number; sort?: string } = {}
  ): Promise<CatalogoPage> {
    const p = new URLSearchParams();
    if (f.q) p.set("q", f.q);
    (f.familia ?? []).forEach((v) => p.append("familia", v));
    (f.procedencia ?? []).forEach((v) => p.append("procedencia", v));
    (f.categoria ?? []).forEach((v) => p.append("categoria", v));
    if (f.con_stock) p.set("con_stock", "true");
    p.set("page", String(opts.page ?? 1));
    p.set("limit", String(opts.limit ?? 1000));
    if (opts.sort) p.set("sort", opts.sort);
    return getJSON(`/api/catalogo?${p.toString()}`);
  },

  async catalogoFiltros(): Promise<CatalogoOpciones> {
    return getJSON("/api/catalogo/filtros");
  },

  async catalogoDetalle(producto: string): Promise<CatalogoDetalle> {
    return getJSON(`/api/catalogo/${encodeURIComponent(producto)}`);
  },

  async catalogoVentas(producto: string): Promise<VentasResponse> {
    return getJSON(`/api/catalogo/${encodeURIComponent(producto)}/ventas`);
  },

  /** Venta por código del grupo de reemplazos. Sirve entrando por cualquier
   *  miembro: devuelve el grupo entero, no solo ese código. */
  async grupoVentas(producto: string): Promise<GrupoVentas> {
    return getJSON(`/api/catalogo/${encodeURIComponent(producto)}/grupo-ventas`);
  },

  // --- Consulta de productos del vendedor (sin costo) ---------------------
  async consultaProductos(
    f: { q?: string; con_stock?: boolean },
    opts: { page?: number; limit?: number } = {}
  ): Promise<ConsultaPage> {
    const p = new URLSearchParams();
    if (f.q) p.set("q", f.q);
    if (f.con_stock) p.set("con_stock", "true");
    p.set("page", String(opts.page ?? 1));
    p.set("limit", String(opts.limit ?? 50));
    return getJSON(`/api/consulta/productos?${p.toString()}`);
  },

  async consultaDetalle(producto: string): Promise<ConsultaDetalle> {
    return getJSON(`/api/consulta/productos/${encodeURIComponent(producto)}`);
  },

  async consultaVentas(producto: string): Promise<VentasResponse> {
    return getJSON(`/api/consulta/productos/${encodeURIComponent(producto)}/ventas`);
  },

  async consultaGrupoVentas(producto: string): Promise<GrupoVentas> {
    return getJSON(`/api/consulta/productos/${encodeURIComponent(producto)}/grupo-ventas`);
  },

  async sugerenciasManuales(
    opts: { producto?: string; sucursalId?: string; soloUnicas?: boolean } = {}
  ): Promise<SugerenciaManual[]> {
    const p = new URLSearchParams();
    if (opts.producto) p.set("producto", opts.producto);
    if (opts.sucursalId) p.set("sucursal_id", opts.sucursalId);
    if (opts.soloUnicas) p.set("solo_unicas", "true");
    return getJSON(`/api/sugerencias-manuales?${p.toString()}`);
  },

  /** Las de una sola vez que se cerraron solas en los últimos días porque apareció
   *  su OC en el ERP, con la OC que las cerró. */
  async sugerenciasCerradasPorOc(dias = 14): Promise<SugerenciaManual[]> {
    return getJSON(`/api/sugerencias-manuales/cerradas-por-oc?dias=${dias}`);
  },

  async crearSugerenciaManual(payload: {
    producto: string;
    sucursal_id: string;
    unidades?: number;
    dias_inventario?: number;
    stock_objetivo?: number; // nivel de stock a mantener
    expira_en?: string; // fecha límite YYYY-MM-DD; vacío = no vence
    motivo?: string;
    /** Cierra lo que ya hay para ese producto y sucursal en vez de sumarse. */
    reemplazar?: boolean;
  }): Promise<SugerenciaManual> {
    const res = await req("/api/sugerencias-manuales", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo guardar la sugerencia");
    }
    return res.json();
  },

  /** Stock, en camino, lo que pide el sistema, venta diaria y lo que ya hay
   * cargado para un producto en una sucursal: el modal calcula con esto. */
  async contextoSugerencia(
    producto: string,
    sucursalId: string
  ): Promise<import("./types").ContextoSugerencia> {
    const p = new URLSearchParams({ producto, sucursal_id: sucursalId });
    return getJSON(`/api/sugerencias-manuales/contexto?${p.toString()}`);
  },

  /** Que pasaria al pedir ese nivel de stock, antes de guardar. */
  async previsualizarObjetivo(
    producto: string,
    sucursalId: string,
    stockObjetivo: number
  ): Promise<import("./types").PreviewObjetivo> {
    const p = new URLSearchParams({
      producto,
      sucursal_id: sucursalId,
      stock_objetivo: String(stockObjetivo),
    });
    return getJSON(`/api/sugerencias-manuales/previsualizar-objetivo?${p.toString()}`);
  },

  /** Que pasaria al pedir esos dias de cobertura, antes de guardar. */
  async previsualizarDias(
    producto: string,
    sucursalId: string,
    dias: number
  ): Promise<import("./types").PreviewDias> {
    const p = new URLSearchParams({
      producto,
      sucursal_id: sucursalId,
      dias: String(dias),
    });
    return getJSON(`/api/sugerencias-manuales/previsualizar-dias?${p.toString()}`);
  },

  async crearSugerenciaMasiva(
    filtros: SugeridoFiltros,
    cantidad: { unidades?: number; dias_inventario?: number; stock_objetivo?: number },
    motivo?: string,
    expiraEn?: string
  ): Promise<{ creadas: number; omitidas: number; lote_id: string | null }> {
    const res = await req("/api/sugerencias-manuales/masiva", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filtros, ...cantidad, expira_en: expiraEn, motivo }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo crear la carga masiva");
    }
    return res.json();
  },

  /** Carga masiva pegando una lista, con una cantidad por línea.
   *
   * Con `previsualizar` no escribe nada y devuelve lo que se crearía: la lista
   * viene de un Excel armado a mano y conviene mirarla antes de guardarla. */
  async crearSugerenciasPegadas(
    texto: string,
    opciones: { previsualizar?: boolean; motivo?: string; expiraEn?: string } = {}
  ): Promise<CargaPegadaResultado> {
    const res = await req("/api/sugerencias-manuales/pegada", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        texto,
        previsualizar: opciones.previsualizar ?? false,
        motivo: opciones.motivo,
        expira_en: opciones.expiraEn,
      }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo leer la lista");
    }
    return res.json();
  },

  /** Venta, stock de la red y tránsito de un repuesto, para el vendedor que arma
   * su lista. Va sin req_id: se consulta antes de crear el requerimiento. */
  async contextoProducto(producto: string, sucursalId?: string): Promise<ContextoVendedor> {
    const p = sucursalId ? `?sucursal_id=${encodeURIComponent(sucursalId)}` : "";
    return getJSON(`/api/requerimientos/producto/${encodeURIComponent(producto)}${p}`);
  },

  async crearRecurrente(payload: RecurrenteCreate): Promise<Recurrente> {
    const res = await req("/api/sugerencias-manuales/recurrentes", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo crear la recurrencia");
    }
    return res.json();
  },

  async recurrentes(): Promise<Recurrente[]> {
    return getJSON("/api/sugerencias-manuales/recurrentes");
  },

  async tablero(periodo?: string): Promise<Tablero> {
    return getJSON(`/api/tablero${periodo ? `?periodo=${periodo}` : ""}`);
  },

  async abcStock(): Promise<AbcStockResumen> {
    return getJSON("/api/tablero/abc-stock");
  },

  async abcStockDetalle(f: {
    sucursal?: string[];
    clase?: string[];
    base_clase?: string | null;
    q?: string | null;
    page?: number;
    limit?: number;
  }): Promise<{ items: AbcStockFila[]; total: number; page: number; limit: number }> {
    const p = new URLSearchParams();
    (f.sucursal ?? []).forEach((s) => p.append("sucursal", s));
    (f.clase ?? []).forEach((c) => p.append("clase", c));
    if (f.base_clase) p.set("base_clase", f.base_clase);
    if (f.q) p.set("q", f.q);
    p.set("page", String(f.page ?? 1));
    p.set("limit", String(f.limit ?? 200));
    return getJSON(`/api/tablero/abc-stock/detalle?${p.toString()}`);
  },

  async instockLista(soloManuales = false): Promise<RepuestoInstock[]> {
    return getJSON(`/api/instock${soloManuales ? "?solo_manuales=true" : ""}`);
  },

  async agregarInstock(payload: {
    producto: string;
    minimo: number;
    motivo?: string;
  }): Promise<{ producto: string; origen: string; minimo: number; ya_estaba: boolean }> {
    const res = await req("/api/instock", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo agregar el repuesto");
    }
    return res.json();
  },

  async quitarInstock(producto: string): Promise<void> {
    const res = await req(`/api/instock/${encodeURIComponent(producto)}`, {
      method: "DELETE",
    });
    if (!res.ok && res.status !== 204) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo quitar el repuesto");
    }
  },

  async instockResumen(): Promise<InstockResumen> {
    return getJSON("/api/instock/resumen");
  },

  async eliminarRecurrente(id: string): Promise<void> {
    const res = await req(`/api/sugerencias-manuales/recurrentes/${id}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) throw new Error("No se pudo eliminar la recurrencia");
  },

  async contar(filtros: SugeridoFiltros): Promise<number> {
    const page = await this.sugerido(filtros, { limit: 1 });
    return page.total;
  },

  async eliminarSugerenciaManual(id: string): Promise<void> {
    const res = await req(`/api/sugerencias-manuales/${id}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) throw new Error("No se pudo eliminar");
  },

  async eliminarLoteSugerencias(loteId: string): Promise<{ eliminadas: number }> {
    const res = await req(`/api/sugerencias-manuales/lote/${encodeURIComponent(loteId)}`, {
      method: "DELETE",
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo eliminar la carga masiva");
    }
    return res.json();
  },

  async exportExcel(
    filtros: SugeridoFiltros,
    columnas: string[],
    sort?: string,
    ids?: number[]
  ): Promise<void> {
    return descargar(
      "/api/sugerido/export-excel",
      { filtros, columnas, sort, ids: ids && ids.length ? ids : null },
      "sugerido.xlsx"
    );
  },

  async powerbiEstado(): Promise<{ configurado: boolean }> {
    return getJSON("/api/admin/powerbi/estado");
  },

  async sincronizarPowerBI(): Promise<CargaResultado> {
    const res = await req("/api/admin/cargar-desde-powerbi", { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo sincronizar con Power BI");
    }
    return res.json();
  },

  async sincronizarPowerBIDesktop(): Promise<CargaResultado> {
    const res = await req("/api/admin/cargar-desde-powerbi-desktop", { method: "POST" });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo leer Power BI Desktop");
    }
    return res.json();
  },

  async auditoria(limit = 100, offset = 0): Promise<AuditoriaPage> {
    return getJSON(`/api/auditoria?limit=${limit}&offset=${offset}`);
  },

  /** Accesos (login) — solo admin o emails autorizados en el backend. */
  async accesos(limit = 200, offset = 0): Promise<AuditoriaPage> {
    return getJSON(`/api/auditoria/accesos?limit=${limit}&offset=${offset}`);
  },

  async notificaciones(soloNoLeidas = false, limit = 20): Promise<NotificacionesResponse> {
    return getJSON(
      `/api/notificaciones?solo_no_leidas=${soloNoLeidas}&limit=${limit}`
    );
  },

  async ultimaSincronizacion(): Promise<{
    creado_en: string | null;
    detalle: string | null;
    /** Días hábiles desde la última carga (sábado y domingo no cuentan). */
    dias_habiles?: number | null;
    /** El servidor considera que el sugerido quedó viejo (la tarea diaria falló o no corrió). */
    desactualizado?: boolean;
  }> {
    return getJSON("/api/ultima-sincronizacion");
  },

  /** Como va la ultima solicitud del buzon ("Actualizar ahora" o "Actualizar motor").
   *  Lo puede consultar cualquiera. */
  async actualizacionEstado(): Promise<EstadoActualizacion> {
    return getJSON("/api/actualizacion/estado");
  },

  /**
   * Deja pedido un trabajo al PC del motor. No hace nada aca: lo toma el agente.
   * - recalcular ("Actualizar ahora") va SIN cuerpo, como siempre: lo entiende
   *   cualquier version de la API.
   * - actualizar_motor ("Actualizar motor", solo admin) manda el tipo.
   * El error trae `status`: 409 = ya hay otra solicitud viva (el texto del servidor
   * dice cual y desde que hora), 0 = el servidor no contesto.
   */
  async solicitarActualizacion(
    tipo: TipoActualizacion = "recalcular"
  ): Promise<EstadoActualizacion & { ya_en_curso: boolean }> {
    const init: RequestInit =
      tipo === "recalcular"
        ? { method: "POST" }
        : {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ tipo }),
          };
    let res: Response;
    try {
      res = await req("/api/actualizacion/solicitar", init);
    } catch (e) {
      if (e instanceof TypeError) throw new ErrorSolicitud(0, MENSAJE_SIN_SERVIDOR);
      throw e;
    }
    if (!res.ok) {
      const porDefecto =
        tipo === "actualizar_motor"
          ? "No se pudo pedir la actualización del motor"
          : "No se pudo pedir la actualización";
      throw new ErrorSolicitud(res.status, await mensajeError(res, porDefecto));
    }
    return res.json();
  },

  async marcarLeidas(ids?: string[]): Promise<{ actualizadas: number }> {
    const res = await req("/api/notificaciones/marcar-leidas", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ ids: ids ?? null }),
    });
    if (!res.ok) throw new Error("No se pudo marcar como leida");
    return res.json();
  },

  async cargarSugerido(file: File): Promise<CargaResultado> {
    const fd = new FormData();
    fd.append("file", file);
    const res = await req("/api/admin/cargar-sugerido", { method: "POST", body: fd });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "No se pudo cargar el archivo");
    }
    return res.json();
  },

  /** Simulador what-if: recalcula el sugerido con otros parametros. No guarda nada. */
  async simular(payload: {
    sucursales?: string[];
    marcas?: string[];
    ciclo_orden_dias?: number;
    ciclo_orden_dias_cd?: number;
    z_por_clase?: Record<string, number>;
    factor_lead_time?: number;
  }): Promise<import("./types").SimulacionResultado> {
    const res = await req("/api/inventario/simular", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo simular"));
    return res.json();
  },

  /** Configuracion calibrable del modelo vigente (o los defaults). */
  async configModelo(): Promise<import("./types").ConfigModelo> {
    return getJSON("/api/calibracion/config-modelo");
  },

  /** Aplica cambios a la configuracion del modelo (crea una version nueva). Solo admin. */
  async guardarConfigModelo(
    cambios: Partial<import("./types").ConfigModeloPlano> & { nota?: string }
  ): Promise<import("./types").ConfigModelo> {
    const res = await req("/api/calibracion/config-modelo", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cambios),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo guardar la configuración"));
    return res.json();
  },

  /** Versiones anteriores de la configuracion del modelo. */
  async configModeloHistorial(): Promise<import("./types").ConfigModelo[]> {
    return getJSON("/api/calibracion/config-modelo/historial");
  },

  /** Vuelve a una version anterior de la configuracion. Solo admin. */
  async revertirConfigModelo(versionId: string): Promise<import("./types").ConfigModelo> {
    const res = await req(`/api/calibracion/config-modelo/revertir/${versionId}`, { method: "POST" });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo revertir"));
    return res.json();
  },

  /** Lead time que calculo el motor, por proveedor y sucursal. */
  async leadTimeProveedor(params: { buscar?: string; solo_global?: boolean } = {}) {
    const q = new URLSearchParams();
    if (params.buscar) q.set("buscar", params.buscar);
    if (params.solo_global) q.set("solo_global", "true");
    const qs = q.toString();
    return getJSON<import("./types").LeadTimeResponse>(
      `/api/calibracion/lead-time-proveedor${qs ? `?${qs}` : ""}`
    );
  },

  /** Marcar una linea del sugerido como ya pedida (cierra el loop con la OC). */
  async marcarPedido(payload: {
    producto: string;
    sucursal_id: string;
    unidades: number;
    n_oc?: string | null;
    proveedor?: string | null;
  }): Promise<{ id: string }> {
    const res = await req("/api/compras/pedidos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo registrar el pedido"));
    return res.json();
  },

  async pedidos(
    producto?: string,
    sucursalId?: string
  ): Promise<{ items: import("./types").LineaPedida[] }> {
    const p = new URLSearchParams();
    if (producto) p.set("producto", producto);
    if (sucursalId) p.set("sucursal_id", sucursalId);
    return getJSON(`/api/compras/pedidos?${p.toString()}`);
  },

  async eliminarPedido(id: string): Promise<void> {
    const res = await req(`/api/compras/pedidos/${encodeURIComponent(id)}`, { method: "DELETE" });
    if (!res.ok && res.status !== 204) throw new Error("No se pudo eliminar el pedido");
  },

  /** Comparaciones del motor propio contra el Power BI (modo sombra). */
  async comparacionesMotor(
    limit = 10
  ): Promise<{ items: import("./types").ComparacionMotor[] }> {
    return getJSON(`/api/admin/motor/comparaciones?limit=${limit}`);
  },

  /** Evolucion diaria del producto (snapshots guardados tras cada sync). */
  async historiaProducto(
    producto: string,
    sucursalId: string,
    dias = 90
  ): Promise<{ items: { fecha: string; sugerido: number; stock: number; punto_pedido: number }[] }> {
    return getJSON(
      `/api/sugerido/${encodeURIComponent(producto)}/${encodeURIComponent(sucursalId)}/historia?dias=${dias}`
    );
  },

  /** Historico de ventas (desde 2018): que hay cargado. */
  async ventasHistoricasMeta(): Promise<import("./types").VentasHistoricasMeta> {
    return getJSON("/api/ventas-historicas/meta");
  },

  async ventasHistoricas(
    f: import("./types").VentasHistoricasFiltros
  ): Promise<import("./types").VentasHistoricasResp> {
    const p = new URLSearchParams();
    if (f.producto) p.set("producto", f.producto);
    if (f.sucursal) p.set("sucursal", f.sucursal);
    if (f.periodo_desde) p.set("periodo_desde", f.periodo_desde);
    if (f.periodo_hasta) p.set("periodo_hasta", f.periodo_hasta);
    if (f.incluir_internos) p.set("incluir_internos", "true");
    return getJSON(`/api/ventas-historicas?${p.toString()}`);
  },

  async exportarVentasHistoricas(
    f: import("./types").VentasHistoricasFiltros
  ): Promise<void> {
    const p = new URLSearchParams();
    if (f.producto) p.set("producto", f.producto);
    if (f.sucursal) p.set("sucursal", f.sucursal);
    if (f.periodo_desde) p.set("periodo_desde", f.periodo_desde);
    if (f.periodo_hasta) p.set("periodo_hasta", f.periodo_hasta);
    const res = await req(`/api/ventas-historicas/export-csv?${p.toString()}`);
    if (!res.ok) throw new Error("No se pudo generar el archivo");
    const blob = await res.blob();
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "ventas_historicas.csv";
    a.click();
    URL.revokeObjectURL(url);
  },

  /** Mesa de incidencias: reportes de errores de la plataforma. */
  async incidencias(estado?: string): Promise<import("./types").IncidenciasResponse> {
    const q = estado ? `?estado=${encodeURIComponent(estado)}` : "";
    return getJSON(`/api/incidencias${q}`);
  },

  async crearIncidencia(
    payload: import("./types").IncidenciaCreate
  ): Promise<import("./types").Incidencia> {
    const res = await req("/api/incidencias", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo enviar el reporte"));
    return res.json();
  },

  async actualizarIncidencia(
    id: string,
    payload: { estado?: string; respuesta?: string }
  ): Promise<import("./types").Incidencia> {
    const res = await req(`/api/incidencias/${encodeURIComponent(id)}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo actualizar la incidencia"));
    return res.json();
  },

  /** Salud del inventario: inmovilizado, sobre-stock, quiebres. */
  async inventarioSalud(
    opts: { sucursales?: string[]; marcas?: string[]; diasSobreStock?: number } = {}
  ): Promise<import("./types").InventarioSalud> {
    const p = new URLSearchParams();
    (opts.sucursales ?? []).forEach((s) => p.append("sucursal", s));
    (opts.marcas ?? []).forEach((m) => p.append("filtro1", m));
    if (opts.diasSobreStock) p.set("dias_sobre_stock", String(opts.diasSobreStock));
    return getJSON(`/api/inventario/salud?${p.toString()}`);
  },


  async chat(
    pregunta: string,
    historial: { role: "user" | "model"; text: string }[] = []
  ): Promise<{ respuesta: string }> {
    const res = await req("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ pregunta, historial }),
    });
    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "El asistente no respondio");
    }
    return res.json();
  },

  // ------------------------------------------------------- Lista de precios

  async precios(
    f: import("./types").PrecioFiltros,
    opts: { page?: number; limit?: number; sort?: string } = {}
  ): Promise<import("./types").PrecioPage> {
    const p = new URLSearchParams();
    if (f.q) p.set("q", f.q);
    (f.rubro ?? []).forEach((v) => p.append("rubro", v));
    (f.tipo ?? []).forEach((v) => p.append("tipo", v));
    (f.procedencia ?? []).forEach((v) => p.append("procedencia", v));
    (f.estado ?? []).forEach((v) => p.append("estado", v));
    // Repetido, como estado: la API lo toma como una union (vigente, programada, vencida,
    // vence_7d). Sin valores no viaja nada.
    (f.vigencia ?? []).forEach((v) => p.append("vigencia", v));
    if (f.origen) p.set("origen", f.origen);
    if (f.con_cambios) p.set("con_cambios", "true");
    if (f.con_stock) p.set("con_stock", "true");
    if (opts.page) p.set("page", String(opts.page));
    if (opts.limit) p.set("limit", String(opts.limit));
    if (opts.sort) p.set("sort", opts.sort);
    return getJSON(`/api/precios?${p.toString()}`);
  },

  async preciosFiltros(): Promise<import("./types").PrecioOpciones> {
    return getJSON("/api/precios/filtros");
  },

  async preciosResumen(): Promise<import("./types").PrecioResumen> {
    return getJSON("/api/precios/resumen");
  },

  async precioDetalle(producto: string): Promise<import("./types").PrecioDetalle> {
    return getJSON(`/api/precios/${encodeURIComponent(producto)}`);
  },

  async guardarPrecioOverride(
    producto: string,
    payload: import("./types").PrecioOverrideIn
  ): Promise<import("./types").PrecioRow> {
    const res = await req(`/api/precios/${encodeURIComponent(producto)}/override`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo guardar el precio"));
    return res.json();
  },

  /** Saca el producto de la lista de precios. No lo da de baja en el ERP. */
  async eliminarPrecioProducto(producto: string): Promise<{ eliminados: number; overrides_conservados: number }> {
    const res = await req(`/api/precios/${encodeURIComponent(producto)}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo sacar de la lista"));
    return res.json();
  },

  async quitarPrecioOverride(producto: string): Promise<import("./types").PrecioRow> {
    const res = await req(`/api/precios/${encodeURIComponent(producto)}/override`, {
      method: "DELETE",
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo volver a la regla"));
    return res.json();
  },

  async crearPrecioProducto(
    payload: import("./types").PrecioProductoNuevo
  ): Promise<import("./types").PrecioRow> {
    const res = await req("/api/precios", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo crear el producto"));
    return res.json();
  },

  async recalcularPrecios(): Promise<{ productos: number; cambios: number; productos_con_cambios: number }> {
    const res = await req("/api/precios/recalcular", { method: "POST" });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo recalcular"));
    return res.json();
  },

  async marcarPreciosVistos(productos: string[] | null): Promise<{ vistos: number }> {
    const res = await req("/api/precios/cambios/vistos", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ productos }),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo marcar como visto"));
    return res.json();
  },

  /** Descarga el Excel para el ERP. Devuelve cuantas filas salieron. */
  async exportarPrecios(
    opts: { soloDiferencias: boolean; formato: "erp" | "completa" | "editable" },
    alReintentar?: (intento: number, total: number) => void
  ): Promise<number> {
    const p = new URLSearchParams();
    if (opts.soloDiferencias) p.set("solo_diferencias", "true");
    p.set("formato", opts.formato);
    // Solo el archivo del ERP registra un envío, y es el que necesita identificador.
    const esErp = opts.formato === "erp";
    if (esErp) {
      loteErpEnCurso ??= nuevoIdentificador();
      p.set("lote", loteErpEnCurso);
    }
    let res: Response;
    try {
      res = await reqConReintentos(`/api/precios/exportar?${p.toString()}`, {}, { alReintentar });
    } catch (e) {
      if (e instanceof TypeError) throw new Error(MENSAJE_SIN_SERVIDOR);
      throw e;
    }
    if (!res.ok) {
      if ([502, 503, 504].includes(res.status)) throw new Error(MENSAJE_SIN_SERVIDOR);
      throw new Error(await mensajeError(res, "No se pudo generar el archivo"));
    }
    const filas = Number(res.headers.get("X-Filas") ?? "0");
    let blob: Blob;
    try {
      blob = await res.blob();
    } catch (e) {
      if (e instanceof TypeError) throw new Error(MENSAJE_SIN_SERVIDOR);
      throw e;
    }
    // Si el servidor no declara Content-Disposition en expose_headers, el
    // navegador lo esconde y esto queda vacio. El respaldo tiene que coincidir
    // con lo que de verdad viene -un CSV-: con ".xlsx" el archivo baja igual
    // pero Excel lo rechaza por "formato o extension no validos".
    const cd = res.headers.get("Content-Disposition") ?? "";
    const nombre = /filename="?([^"]+)"?/.exec(cd)?.[1] ?? `precios_${new Date().toISOString().slice(0, 10)}.csv`;
    guardarBlob(blob, nombre);
    // El archivo llegó: la próxima descarga es otra.
    if (esErp) loteErpEnCurso = null;
    return filas;
  },

  /** Baja la plantilla vacía del Excel corto (Código, Precio fijo, Desde, Hasta, Obs). Pesa unos
   *  KB y no escribe nada: se puede repetir si el servidor se reinicia. Devuelve el nombre con
   *  que quedó guardada. */
  async descargarPlantillaCarga(
    archivo: "xlsx" | "csv" = "xlsx",
    alReintentar?: (intento: number, total: number) => void
  ): Promise<string> {
    let res: Response;
    try {
      res = await reqConReintentos(`/api/precios/carga/plantilla?archivo=${archivo}`, {}, { alReintentar });
    } catch (e) {
      if (e instanceof TypeError) throw new Error(MENSAJE_SIN_SERVIDOR);
      throw e;
    }
    if (!res.ok) {
      if ([502, 503, 504].includes(res.status)) throw new Error(MENSAJE_SIN_SERVIDOR);
      throw new Error(await mensajeError(res, "No se pudo bajar la plantilla"));
    }
    let blob: Blob;
    try {
      blob = await res.blob();
    } catch (e) {
      if (e instanceof TypeError) throw new Error(MENSAJE_SIN_SERVIDOR);
      throw e;
    }
    // Si el navegador esconde Content-Disposition, el respaldo coincide con el formato pedido:
    // un CSV con nombre ".xlsx" baja igual, pero Excel lo rechaza.
    const cd = res.headers.get("Content-Disposition") ?? "";
    const nombre = /filename="?([^"]+)"?/.exec(cd)?.[1] ?? `plantilla_precios_corta.${archivo}`;
    guardarBlob(blob, nombre);
    return nombre;
  },

  async politicaFactores(): Promise<import("./types").PoliticaFactor[]> {
    return getJSON("/api/precios/politica/factores");
  },

  async politicaRubros(): Promise<import("./types").PoliticaRubro[]> {
    return getJSON("/api/precios/politica/rubros");
  },

  /** Lee el archivo de la lista editado en Excel y dice qué cambiaría. No guarda nada.
   *  `modo` declara qué archivo es ("corto": la plantilla; "completo": el que se bajó para
   *  editar). Sin él no viaja nada y el servidor lo deduce por las columnas. */
  async vistaPreviaCargaPrecios(
    archivo: File,
    alReintentar?: (intento: number, total: number) => void,
    signal?: AbortSignal,
    modo?: import("./types").ModoCarga
  ): Promise<import("./types").CargaPreciosVistaPrevia> {
    const fd = new FormData();
    fd.append("archivo", archivo);
    if (modo) fd.append("modo", modo);
    let res: Response;
    try {
      // Leer el archivo no escribe nada: se puede repetir si el servidor se reinicia.
      res = await reqConReintentos("/api/precios/carga/vista-previa", { method: "POST", body: fd }, { alReintentar, signal });
    } catch (e) {
      if (e instanceof TypeError) throw new Error(MENSAJE_SIN_SERVIDOR);
      throw e;
    }
    if (!res.ok) {
      if ([502, 503, 504].includes(res.status)) throw new Error(MENSAJE_SIN_SERVIDOR);
      throw new Error(await mensajeError(res, "No se pudo leer el archivo"));
    }
    try {
      return await res.json();
    } catch (e) {
      // Un 200 con el cuerpo cortado (o una pagina del proxy) no es un resultado.
      if (e instanceof Error && e.name === "AbortError") throw e;
      throw new Error(MENSAJE_SIN_SERVIDOR);
    }
  },

  /** Carga los cambios del archivo, todos o ninguno. Sin reintentos automáticos: si
   *  la respuesta se pierde, volver a subir el archivo dice 0 cambios. */
  async cargarPrecios(
    archivo: File,
    opts: { confirmarQuitas?: boolean; confirmarMasiva?: boolean; modo?: import("./types").ModoCarga } = {}
  ): Promise<import("./types").CargaPreciosResultado> {
    const fd = new FormData();
    fd.append("archivo", archivo);
    // El mismo modo con que se leyo la vista previa: si el archivo no es de ese modo, el servidor
    // responde 422 en vez de cargarlo como otra cosa.
    if (opts.modo) fd.append("modo", opts.modo);
    // La carga que quita muchas decisiones (celdas vacias), o que pone muchos precios
    // fijos o factores propios, pide confirmacion al servidor.
    if (opts.confirmarQuitas) fd.append("confirmar_quitas", "true");
    if (opts.confirmarMasiva) fd.append("confirmar_masiva", "true");
    let res: Response;
    try {
      res = await req("/api/precios/carga", { method: "POST", body: fd });
    } catch (e) {
      if (e instanceof TypeError) throw errorCargaSinConfirmar();
      throw e;
    }
    if (!res.ok) {
      // El servidor sigue procesando aunque el proxy corte la respuesta (el endpoint es
      // sincrono y hace commit): un 502/503/504 es lo mismo que una conexion cortada.
      if ([502, 503, 504].includes(res.status)) throw errorCargaSinConfirmar();
      throw new Error(await mensajeError(res, "No se pudo cargar el archivo"));
    }
    try {
      return await res.json();
    } catch {
      // El servidor ya hizo commit: un cuerpo cortado o ilegible tampoco confirma nada.
      throw errorCargaSinConfirmar();
    }
  },

  /** Qué precios cambiarían con este cambio de política. No guarda nada. */
  async vistaPreviaPolitica(
    cambio: import("./types").CambioPolitica
  ): Promise<import("./types").VistaPreviaPolitica> {
    const res = await req("/api/precios/politica/vista-previa", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cambio),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo calcular qué cambia"));
    return res.json();
  },

  /** Guarda factores, tipos nuevos y rubros juntos, y recalcula la lista una vez. */
  async guardarPolitica(
    cambio: import("./types").CambioPolitica
  ): Promise<import("./types").ResultadoPolitica> {
    const res = await req("/api/precios/politica", {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cambio),
    });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo guardar la politica"));
    return res.json();
  },
};
