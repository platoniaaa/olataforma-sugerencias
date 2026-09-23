// Cliente del modulo Inventario ciclico (/api/inventario-ciclico).
import { mensajeError, req } from "./api-client";

export type RolInventario = "admin" | "bodega" | null;

export type EstadoItem = "pendiente" | "falta_evidencia" | "con_diferencia" | "sin_diferencia";

export interface Evidencia {
  id: string;
  nombre: string;
  content_type: string;
  tamano: number;
  subido_por: string | null;
  subido_en: string;
}

export interface ItemInventario {
  id: string;
  semana: string;
  sucursal_id: string;
  producto: string;
  descripcion: string | null;
  clase: string;
  cantidad_sistema: number;
  costo_unitario: number;
  requiere_evidencia: boolean;
  cantidad_contada: number | null;
  observacion: string | null;
  contado_por: string | null;
  contado_en: string | null;
  diferencia: number | null;
  diferencia_valor: number | null;
  estado: EstadoItem;
  evidencias: Evidencia[];
}

export interface ResumenSucursal {
  sucursal_id: string;
  asignados: number;
  contados: number;
  pendientes: number;
  falta_evidencia: number;
  con_diferencia: number;
  diferencia_unidades: number;
  diferencia_sobrante: number;
  diferencia_faltante: number;
  clases_faltantes: string[];
  cuota_sugerida: number;
  productos_con_stock: number;
  contados_en_el_ano: number;
}

export interface ResultadoCarga {
  semana: string;
  sucursales: string[];
  insertados: number;
  actualizados: number;
  conservados: number;
  eliminados: number;
  avisos: string[];
}

export interface RolFila {
  email: string;
  rol: "admin" | "bodega";
  sucursales: string[] | null;
  nombre: string | null;
  tiene_usuario: boolean;
}

/** Error de carga con la lista de filas malas que devuelve el backend. */
export class ErrorCarga extends Error {
  constructor(public errores: string[]) {
    super(errores[0] ?? "No se pudo cargar el archivo");
  }
}

export const ESTADOS: Record<EstadoItem, { label: string; clase: string }> = {
  pendiente: { label: "Pendiente", clase: "bg-slate-100 text-slate-600" },
  falta_evidencia: { label: "Falta evidencia", clase: "bg-amber-50 text-amber-800" },
  con_diferencia: { label: "Con diferencia", clase: "bg-red-50 text-red-700" },
  sin_diferencia: { label: "Sin diferencia", clase: "bg-emerald-50 text-emerald-700" },
};

const RUTA = "/api/inventario-ciclico";
const CLAVE_ROL = "sugerido_rol_inventario";

async function json<T>(path: string, init?: RequestInit, fallback = "No se pudo completar"): Promise<T> {
  const res = await req(path, init);
  if (!res.ok) throw new Error(await mensajeError(res, fallback));
  return res.json() as Promise<T>;
}

function qs(params: Record<string, string | undefined>): string {
  const p = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => v && p.set(k, v));
  const s = p.toString();
  return s ? `?${s}` : "";
}

/** Rol guardado de la ultima consulta (para decidir si mostrar el menu sin esperar). */
export function rolGuardado(): RolInventario {
  if (typeof window === "undefined") return null;
  const v = localStorage.getItem(CLAVE_ROL);
  return v === "admin" || v === "bodega" ? v : null;
}

export const inventarioApi = {
  async yo(): Promise<{ rol: RolInventario; sucursales: string[] | null }> {
    const r = await json<{ rol: RolInventario; sucursales: string[] | null }>(`${RUTA}/yo`);
    try {
      if (r.rol) localStorage.setItem(CLAVE_ROL, r.rol);
      else localStorage.removeItem(CLAVE_ROL);
    } catch {
      /* sin localStorage: solo se pierde el atajo del menu */
    }
    return r;
  },

  semanas: () => json<string[]>(`${RUTA}/semanas`),

  resumen: (semana?: string) => json<ResumenSucursal[]>(`${RUTA}/resumen${qs({ semana })}`),

  items: (semana?: string, sucursal?: string) =>
    json<ItemInventario[]>(`${RUTA}/items${qs({ semana, sucursal })}`),

  actualizar: (
    id: string,
    cambios: Partial<Pick<ItemInventario, "cantidad_contada" | "observacion" | "requiere_evidencia">>
  ) =>
    json<ItemInventario>(
      `${RUTA}/items/${id}`,
      { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(cambios) },
      "No se pudo guardar"
    ),

  async subirEvidencia(id: string, archivo: File): Promise<ItemInventario> {
    const fd = new FormData();
    const listo = await reducirImagen(archivo);
    fd.append("archivo", listo, listo.name);
    return json<ItemInventario>(`${RUTA}/items/${id}/evidencias`, { method: "POST", body: fd }, "No se pudo subir");
  },

  async borrarEvidencia(id: string): Promise<void> {
    const res = await req(`${RUTA}/evidencias/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo borrar"));
  },

  /** URL local (blob) de una evidencia: el endpoint exige token, un <img src> directo no lo manda. */
  async urlEvidencia(id: string): Promise<string> {
    const res = await req(`${RUTA}/evidencias/${id}`);
    if (!res.ok) throw new Error("No se pudo abrir la evidencia");
    return URL.createObjectURL(await res.blob());
  },

  async descargarPlantilla(): Promise<void> {
    const res = await req(`${RUTA}/plantilla`);
    if (!res.ok) throw new Error("No se pudo descargar la plantilla");
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = "plantilla_inventario_ciclico.xlsx";
    a.click();
    URL.revokeObjectURL(url);
  },

  roles: () => json<RolFila[]>(`${RUTA}/roles`),

  sucursales: () => json<string[]>(`${RUTA}/sucursales`),

  guardarRol: (email: string, rol: "admin" | "bodega", sucursales: string[]) =>
    json<RolFila>(
      `${RUTA}/roles/${encodeURIComponent(email)}`,
      { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ rol, sucursales }) },
      "No se pudo guardar"
    ),

  async quitarRol(email: string): Promise<void> {
    const res = await req(`${RUTA}/roles/${encodeURIComponent(email)}`, { method: "DELETE" });
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo quitar"));
  },

  async cargar(semana: string, archivo: File): Promise<ResultadoCarga> {
    const fd = new FormData();
    fd.append("archivo", archivo);
    const res = await req(`${RUTA}/carga${qs({ semana })}`, { method: "POST", body: fd });
    if (!res.ok) {
      const body = await res.json().catch(() => ({}));
      const errores = (body as { detail?: { errores?: string[] } })?.detail?.errores;
      if (Array.isArray(errores)) throw new ErrorCarga(errores);
      throw new ErrorCarga([typeof body?.detail === "string" ? body.detail : "No se pudo cargar el archivo"]);
    }
    return res.json();
  },
};

/** Lunes (YYYY-MM-DD) de la semana de una fecha, en hora local. */
export function lunesDe(d: Date): string {
  const x = new Date(d.getFullYear(), d.getMonth(), d.getDate());
  x.setDate(x.getDate() - ((x.getDay() + 6) % 7));
  const mm = String(x.getMonth() + 1).padStart(2, "0");
  const dd = String(x.getDate()).padStart(2, "0");
  return `${x.getFullYear()}-${mm}-${dd}`;
}

/** "Semana del 21-09-2026". */
export function etiquetaSemana(iso: string): string {
  const [y, m, d] = iso.split("-");
  return `Semana del ${d}-${m}-${y}`;
}

/**
 * Reduce una foto del celular (3-8 MB) a JPEG de ~1600 px antes de subirla.
 * El backend acepta hasta 4 MB. PDFs y archivos que no son imagen pasan tal cual.
 */
export async function reducirImagen(archivo: File, ladoMax = 1600, calidad = 0.8): Promise<File> {
  if (!archivo.type.startsWith("image/") || typeof document === "undefined") return archivo;
  try {
    const bitmap = await createImageBitmap(archivo);
    const escala = Math.min(1, ladoMax / Math.max(bitmap.width, bitmap.height));
    const canvas = document.createElement("canvas");
    canvas.width = Math.round(bitmap.width * escala);
    canvas.height = Math.round(bitmap.height * escala);
    canvas.getContext("2d")?.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
    const blob = await new Promise<Blob | null>((ok) => canvas.toBlob(ok, "image/jpeg", calidad));
    if (!blob || blob.size >= archivo.size) return archivo;
    const nombre = archivo.name.replace(/\.[^.]+$/, "") + ".jpg";
    return new File([blob], nombre, { type: "image/jpeg" });
  } catch {
    // HEIC en navegadores que no lo decodifican, etc.: se sube el original.
    return archivo;
  }
}
