// Manejo de sesion del lado del cliente (token en localStorage).

const TOKEN = "sugerido_token";
const EMAIL = "sugerido_email";
const NOMBRE = "sugerido_nombre";
const ES_ADMIN = "sugerido_es_admin";
const SOLO_LECTURA = "sugerido_solo_lectura";
const PUEDE_CALIBRAR = "sugerido_puede_calibrar";
const PUEDE_ACTUALIZAR = "sugerido_puede_actualizar";
const ES_VENDEDOR = "sugerido_es_vendedor";
const SUCURSALES = "sugerido_sucursales";
const PUEDE_PRECIOS = "sugerido_puede_precios";

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN);
}

export function getEmail(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(EMAIL);
}

export function getNombre(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(NOMBRE);
}

export function getEsAdmin(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(ES_ADMIN) === "1";
}

/** True si el usuario es de solo lectura (no puede crear/editar sugerencias). */
export function getSoloLectura(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(SOLO_LECTURA) === "1";
}

/** True si puede entrar a Calibracion (admin o autorizado). Lo decide el BACKEND
 *  y viaja en el login, para no duplicar la lista de autorizados en el cliente.
 *  El gate real es el 403 del servidor; esto solo decide si mostrar la seccion. */
export function getPuedeCalibrar(): boolean {
  if (typeof window === "undefined") return false;
  const v = localStorage.getItem(PUEDE_CALIBRAR);
  // Sesion abierta ANTES de que existiera este flag: la clave no esta. Se cae a
  // es_admin para no quitarle Calibracion a un admin que ya estaba dentro; al
  // volver a entrar queda el valor real que manda el backend.
  if (v === null) return getEsAdmin();
  return v === "1";
}

/** True si puede apretar "Actualizar ahora" (admin o autorizado en EMAILS_ACTUALIZAR).
 *  Lo decide el BACKEND y viaja en el login; el gate real es el 403 del servidor. */
export function getPuedeActualizar(): boolean {
  if (typeof window === "undefined") return false;
  const v = localStorage.getItem(PUEDE_ACTUALIZAR);
  // Sesion abierta antes de que existiera el flag: caer a es_admin (mismo criterio
  // que Calibracion) para no esconderle el boton a un admin que ya estaba dentro.
  if (v === null) return getEsAdmin();
  return v === "1";
}

/** True si puede editar la lista de precios (fijar, congelar, crear productos):
 *  admin o autorizado en EMAILS_PRECIOS. Lo decide el BACKEND y viaja en el
 *  login; el gate real es el 403 del servidor. Ver la lista puede cualquiera de
 *  Abastecimiento; esto solo decide si se muestran los controles de edicion. */
export function getPuedePrecios(): boolean {
  if (typeof window === "undefined") return false;
  const v = localStorage.getItem(PUEDE_PRECIOS);
  // Sesion abierta antes de que existiera el flag: caer a es_admin, como Calibracion.
  if (v === null) return getEsAdmin();
  return v === "1";
}

/** True si el usuario es un vendedor de sucursal: la plataforma se le recorta a
 *  armar y seguir sus requerimientos. El gate real es el 403 del backend
 *  (`requiere_comprador`); esto solo decide que se le muestra. */
export function getEsVendedor(): boolean {
  if (typeof window === "undefined") return false;
  return localStorage.getItem(ES_VENDEDOR) === "1";
}

/** Sucursales del usuario. Para el vendedor son por las que puede pedir: nunca
 *  las escribe a mano, que es lo que evita el requerimiento cargado a la sucursal
 *  equivocada. */
export function getSucursales(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const v = JSON.parse(localStorage.getItem(SUCURSALES) ?? "[]");
    return Array.isArray(v) ? (v as string[]) : [];
  } catch {
    return [];
  }
}

export function setSession(
  token: string, email: string, nombre: string | null, esAdmin = false, soloLectura = false,
  puedeCalibrar = false, puedeActualizar = false, esVendedor = false, sucursales: string[] = [],
  puedePrecios = false
) {
  localStorage.setItem(TOKEN, token);
  localStorage.setItem(EMAIL, email);
  if (nombre) localStorage.setItem(NOMBRE, nombre);
  else localStorage.removeItem(NOMBRE);
  localStorage.setItem(ES_ADMIN, esAdmin ? "1" : "0");
  localStorage.setItem(SOLO_LECTURA, soloLectura ? "1" : "0");
  localStorage.setItem(PUEDE_CALIBRAR, puedeCalibrar ? "1" : "0");
  localStorage.setItem(PUEDE_ACTUALIZAR, puedeActualizar ? "1" : "0");
  localStorage.setItem(ES_VENDEDOR, esVendedor ? "1" : "0");
  localStorage.setItem(SUCURSALES, JSON.stringify(sucursales ?? []));
  localStorage.setItem(PUEDE_PRECIOS, puedePrecios ? "1" : "0");
}

export function clearSession() {
  localStorage.removeItem(TOKEN);
  localStorage.removeItem(EMAIL);
  localStorage.removeItem(NOMBRE);
  localStorage.removeItem(ES_ADMIN);
  localStorage.removeItem(SOLO_LECTURA);
  localStorage.removeItem(PUEDE_CALIBRAR);
  localStorage.removeItem(PUEDE_ACTUALIZAR);
  localStorage.removeItem(ES_VENDEDOR);
  localStorage.removeItem(SUCURSALES);
  localStorage.removeItem(PUEDE_PRECIOS);
}

export function estaAutenticado(): boolean {
  return !!getToken();
}

// Emails no-admin que pueden ver la pestana "Accesos" de auditoria. El backend es el
// gate real (403); esto solo decide si mostrar la pestana. Mantener en sync con
// EMAILS_VER_ACCESOS del backend (config.emails_ver_accesos).
const EMAILS_VER_ACCESOS = ["mramos@curifor.com"];

/** True si el usuario puede ver la vista de accesos (admin o email autorizado). */
export function puedeVerAccesos(): boolean {
  if (getEsAdmin()) return true;
  const email = getEmail()?.toLowerCase();
  return !!email && EMAILS_VER_ACCESOS.includes(email);
}

/** Cierra sesion y manda al login. */
export function logout() {
  clearSession();
  if (typeof window !== "undefined") window.location.href = "/login";
}
