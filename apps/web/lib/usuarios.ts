// Administracion de usuarios (solo admin): la pantalla /usuarios.
//
// Hasta el 16-10-2026 los usuarios se manejaban solo por la API
// (POST /api/admin/usuarios), y eso lo sabia hacer una persona. Esta pantalla es
// para que cualquier admin pueda crear, editar, desactivar y cambiar claves sin
// tocar la base ni un script.
//
// El POST es idempotente por correo y cambia SOLO los campos que llegan: por eso
// al editar se manda unicamente lo que cambio (`cambiosUsuario`), y editar el
// nombre de alguien no puede quitarle el admin de rebote.
import { MENSAJE_SIN_SERVIDOR, mensajeError, req, reqConReintentos } from "./api-client";

const RUTA = "/api/admin/usuarios";

/** Permisos que da la configuracion del servidor por correo, no la base. */
export type PermisoEspecial = "precios" | "calibracion" | "ver_accesos" | "actualizar";

export interface UsuarioAdmin {
  email: string;
  nombre: string | null;
  activo: boolean;
  es_admin: boolean;
  solo_lectura: boolean;
  es_vendedor: boolean;
  sucursales: string[];
  creado_en: string | null;
  /** La usa el motor para publicar (EMAILS_MOTOR del servidor). */
  es_cuenta_motor: boolean;
  permisos_especiales: string[];
}

/** Lo que se manda al guardar. Lo que no viene, el servidor lo deja como estaba. */
export interface UsuarioGuardar {
  email: string;
  password?: string;
  nombre?: string;
  es_admin?: boolean;
  solo_lectura?: boolean;
  es_vendedor?: boolean;
  activo?: boolean;
  sucursales?: string[];
}

/** Los campos que se editan en la pantalla (sin correo ni clave). */
export interface DatosUsuario {
  nombre: string;
  es_admin: boolean;
  solo_lectura: boolean;
  es_vendedor: boolean;
  activo: boolean;
  sucursales: string[];
}

export const PERMISOS_ESPECIALES: { clave: PermisoEspecial; etiqueta: string }[] = [
  { clave: "precios", etiqueta: "Editar la lista de precios" },
  { clave: "calibracion", etiqueta: "Configurar el modelo" },
  { clave: "ver_accesos", etiqueta: "Ver los accesos en Auditoría" },
  { clave: "actualizar", etiqueta: "Pedir “Actualizar ahora”" },
];

export const NOTA_PERMISOS_ESPECIALES = "Se definen en la configuración del servidor.";

export const AVISO_MOTOR =
  "Si cambias esto, el motor deja de publicar hasta que se actualice la clave en el PC donde corre.";

export function etiquetaPermiso(clave: string): string {
  return PERMISOS_ESPECIALES.find((p) => p.clave === clave)?.etiqueta ?? clave;
}

/** Una API anterior a la pantalla no manda los campos nuevos: se leen como "no". */
function normalizar(u: Partial<UsuarioAdmin> & { email: string }): UsuarioAdmin {
  return {
    email: u.email,
    nombre: u.nombre ?? null,
    activo: u.activo ?? true,
    es_admin: Boolean(u.es_admin),
    solo_lectura: Boolean(u.solo_lectura),
    es_vendedor: Boolean(u.es_vendedor),
    sucursales: Array.isArray(u.sucursales) ? u.sucursales : [],
    creado_en: u.creado_en ?? null,
    es_cuenta_motor: Boolean(u.es_cuenta_motor),
    permisos_especiales: Array.isArray(u.permisos_especiales) ? u.permisos_especiales : [],
  };
}

export function datosDe(u: UsuarioAdmin): DatosUsuario {
  return {
    nombre: u.nombre ?? "",
    es_admin: u.es_admin,
    solo_lectura: u.solo_lectura,
    es_vendedor: u.es_vendedor,
    activo: u.activo,
    sucursales: [...u.sucursales],
  };
}

function mismaLista(a: string[], b: string[]): boolean {
  if (a.length !== b.length) return false;
  const ob = [...b].sort();
  return [...a].sort().every((x, i) => x === ob[i]);
}

/** Solo lo que cambio respecto de lo guardado, mas el correo que identifica al usuario. */
export function cambiosUsuario(original: UsuarioAdmin, editado: DatosUsuario): UsuarioGuardar {
  const out: UsuarioGuardar = { email: original.email };
  if (editado.nombre.trim() !== (original.nombre ?? "").trim()) out.nombre = editado.nombre.trim();
  if (editado.es_admin !== original.es_admin) out.es_admin = editado.es_admin;
  if (editado.solo_lectura !== original.solo_lectura) out.solo_lectura = editado.solo_lectura;
  if (editado.es_vendedor !== original.es_vendedor) out.es_vendedor = editado.es_vendedor;
  if (editado.activo !== original.activo) out.activo = editado.activo;
  if (!mismaLista(editado.sucursales, original.sucursales)) out.sucursales = editado.sucursales;
  return out;
}

export function hayCambios(c: UsuarioGuardar): boolean {
  return Object.keys(c).some((k) => k !== "email");
}

/** El cambio deja al motor sin publicar: clave nueva, sin admin o desactivada. */
export function tocaAlMotor(u: UsuarioAdmin | null, c: UsuarioGuardar): boolean {
  if (!u?.es_cuenta_motor) return false;
  return Boolean(c.password) || c.es_admin === false || c.activo === false;
}

/** Que tiene de malo la clave, o null si sirve. `minimo` null = la regla no llego. */
export function errorClave(clave: string, repetida: string, minimo: number | null): string | null {
  if (!clave) return "Escribe la clave.";
  if (minimo != null && clave.length < minimo) {
    return `La clave tiene que tener al menos ${minimo} caracteres.`;
  }
  if (clave !== repetida) return "Las dos claves no coinciden.";
  return null;
}

// Sin letras que se confunden al dictarlas o copiarlas a mano (0/O, 1/l/I).
const ALFABETO = "abcdefghijkmnpqrstuvwxyzABCDEFGHJKLMNPQRSTUVWXYZ23456789";

/** Clave al azar generada en el navegador. Nunca viaja si no se guarda. */
export function generarClave(largo = 10): string {
  const n = ALFABETO.length;
  // Se descartan los bytes del final del rango para que todas las letras tengan
  // la misma probabilidad (256 no es multiplo de n).
  const tope = 256 - (256 % n);
  let out = "";
  while (out.length < largo) {
    const bytes = new Uint8Array(largo * 2);
    crypto.getRandomValues(bytes);
    for (const b of Array.from(bytes)) {
      if (b < tope && out.length < largo) out += ALFABETO[b % n];
    }
  }
  return out;
}

/** Un corte de red se le dice a la persona igual que en el resto de la plataforma. */
async function conMensaje<T>(fn: () => Promise<T>): Promise<T> {
  try {
    return await fn();
  } catch (e) {
    if (e instanceof TypeError) throw new Error(MENSAJE_SIN_SERVIDOR);
    throw e;
  }
}

export const usuariosApi = {
  async listar(): Promise<UsuarioAdmin[]> {
    return conMensaje(async () => {
      const res = await reqConReintentos(RUTA);
      if (!res.ok) throw new Error(await mensajeError(res, `No se pudo cargar la lista (error ${res.status}).`));
      const filas = (await res.json()) as (Partial<UsuarioAdmin> & { email: string })[];
      return filas.map(normalizar);
    });
  },

  /** El largo minimo de la clave, para avisar antes de mandar. */
  async reglas(): Promise<{ largo_minimo_clave: number }> {
    return conMensaje(async () => {
      const res = await reqConReintentos(`${RUTA}/reglas`);
      if (!res.ok) throw new Error(await mensajeError(res, `Error ${res.status}`));
      return res.json() as Promise<{ largo_minimo_clave: number }>;
    });
  },

  /** Crea o actualiza (por correo). Es seguro repetirlo: el resultado es el mismo. */
  async guardar(datos: UsuarioGuardar): Promise<UsuarioAdmin> {
    return conMensaje(async () => {
      const res = await req(RUTA, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(datos),
      });
      if (!res.ok) throw new Error(await mensajeError(res, `No se pudo guardar (error ${res.status}).`));
      return normalizar(await res.json());
    });
  },
};
