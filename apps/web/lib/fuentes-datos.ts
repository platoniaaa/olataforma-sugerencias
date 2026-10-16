// Cliente de Fuentes de datos (/api/admin/fuentes): de donde lee el motor cada
// archivo y si esta al dia. Solo admin. El semaforo y los textos los arma el
// servidor (`fuentes_service.semaforo`): la pantalla solo los muestra.
import { mensajeError, req } from "./api-client";

export type Nivel = "rojo" | "amarillo" | "verde" | "gris";
export type ModoPanel = "sin_configurar" | "prueba" | "activa";
export type ModoConfig = "prueba" | "activa";
export type AlVencer = "frena" | "avisa";
export type ModoEleccion = "archivo_exacto" | "mas_reciente" | "por_descarte";

export interface Alerta {
  nivel: Nivel;
  etiqueta: string;
  texto: string;
  regla: string;
}

export interface Archivo {
  carpeta: string | null;
  carpeta_nombre: string | null;
  ruta_relativa: string;
  nombre: string;
  modificado_en: string | null;
  tamano: number | null;
  onedrive: string | null;
}

export interface Prueba {
  resultado: string; // coincide | difiere | difiere_esperado | falta
  archivo: string | null;
  texto: string;
  frenaria: boolean;
}

export interface FuentePanel {
  clave: string;
  nombre: string;
  nivel: Nivel;
  etiqueta: string;
  texto: string;
  regla: string;
  alertas: Alerta[];
  hecho: string | null;
  archivo: string | null;
  archivos: Archivo[];
  modificado_en: string | null;
  edad_dias_habiles: number | null;
  filas: number | null;
  carpeta: string | null;
  carpeta_nombre: string | null;
  obligatoria: boolean;
  frecuencia_dias: number | null;
  al_vencer: string | null;
  activa: boolean;
  prueba: Prueba | null;
  dato_de: string | null;
}

export interface FuenteReconoce {
  clave: string;
  nombre: string;
  incluye: string[];
  excluye: string[];
  archivos: Archivo[];
}

export interface Corrida {
  id: string;
  pc: string;
  alias: string | null;
  tipo: string;
  titular: boolean;
  publico: boolean;
  iniciada_en: string;
  terminada_en: string | null;
  duracion_min: number | null;
  resultado: string;
  resultado_texto: string;
  motivo_texto: string | null;
  config_origen: string | null;
  config_version: number | null;
  version_motor: string | null;
  resumen: Partial<Record<Nivel, number>>;
}

export interface CarpetaPc {
  clave: string;
  nombre: string;
  tipo: string | null;
  ruta_portable: string | null;
  metodo: string | null;
  existe: boolean;
  archivos: number;
  truncado: boolean;
}

export interface PcPanel {
  pc: string;
  alias: string | null;
  es_titular: boolean;
  corrida_id: string;
  tipo: string;
  iniciada_en: string;
  carpetas: CarpetaPc[];
}

export interface Activacion {
  puede_activar: boolean;
  motivo: string | null;
  corridas_necesarias: number;
  corridas_en_verde: number;
}

export interface SembrarDesde {
  corrida_id: string;
  pc: string;
  alias: string | null;
  tipo: string;
  iniciada_en: string;
}

export interface Panel {
  modo: ModoPanel;
  modo_texto: string;
  version: number | null;
  pc_titular: string | null;
  pc_titular_alias: string | null;
  ahora: string;
  franja: { nivel: Nivel; ultima_corrida: Corrida | null; alertas: Alerta[] };
  corrida_id: string | null;
  dato_de_corrida: string | null;
  fuentes: FuentePanel[];
  reconoce: FuenteReconoce[];
  carpetas_por_pc: PcPanel[];
  activacion: Activacion;
  sembrar_desde: SembrarDesde[];
}

export interface Ubicacion {
  carpeta: string;
  subcarpeta: string;
  recursiva: boolean;
}

export interface FuenteCfg {
  clave: string;
  nombre: string;
  ubicaciones: Ubicacion[];
  modo: string;
  nombre_archivo: string | null;
  incluye: string[];
  excluye: string[];
  extensiones: string[];
  frecuencia_dias: number | null;
  al_vencer: AlVencer;
  obligatoria: boolean;
  activa: boolean;
  diferencia_esperada: boolean;
  hoja: string | number | null;
  fila_encabezado: number | null;
}

export interface CatalogoFuente {
  uso: "lee" | "reconoce";
  requerida: boolean;
  modos: string[];
  frecuencia_max: number | null;
  al_vencer_fijo: AlVencer | null;
  efecto_si_falta: string | null;
  controla_filas?: boolean | null;
}

export interface CarpetaCfg {
  clave: string;
  nombre: string;
  tipo: string;
  params: Record<string, string | null | undefined>;
  rutas_por_pc: Record<string, string>;
  activa: boolean;
}

/** `GET /config`: lo mismo que lee el motor. Sin configurar solo trae el modo. */
export interface ConfigVigente {
  modo: ModoPanel;
  version?: number;
  hash?: string;
  pc_titular?: string | null;
  pcs?: Record<string, { alias: string | null }>;
  catalogo?: Record<string, CatalogoFuente>;
  carpetas?: CarpetaCfg[];
  fuentes?: FuenteCfg[];
}

export interface ArchivoCarpeta {
  ruta_relativa: string;
  nombre: string;
  subcarpeta: string;
  tamano: number | null;
  modificado_en: string | null;
  onedrive: string | null;
  fuente: string | null;
  elegido: boolean;
  patron_propuesto: string;
}

export interface ArchivosCarpeta {
  clave: string;
  nombre: string | null;
  pc: string | null;
  alias: string | null;
  corrida_id?: string | null;
  iniciada_en?: string | null;
  existe: boolean;
  metodo?: string | null;
  ruta_portable?: string | null;
  ruta_absoluta?: string | null;
  truncado: boolean;
  subcarpetas: string[];
  archivos: ArchivoCarpeta[];
}

export interface CorridaFuente {
  corrida_id: string;
  pc: string;
  alias: string | null;
  tipo: string;
  iniciada_en: string;
  resultado: string;
  hecho: string | null;
  nivel: Nivel;
  etiqueta: string;
  archivos: Archivo[];
  filas: number | null;
  hoja_leida: string | number | null;
  prueba: Prueba | null;
}

export interface Competencia {
  carpeta: string;
  carpeta_nombre: string | null;
  ruta_absoluta: string | null;
  candidatos: ArchivoCarpeta[];
}

export interface Descartado {
  nombre: string;
  motivo: string | null;
  nuevo: boolean;
}

export interface Version {
  version: number;
  creado_por: string | null;
  creado_en: string;
  nota: string;
  revierte_a: number | null;
  claves_cambiadas: string[];
}

export interface FuenteDetalle {
  clave: string;
  nombre: string;
  uso: string | null;
  modo: ModoPanel;
  version: number | null;
  config: FuenteCfg;
  catalogo: CatalogoFuente | null;
  bloqueos: Partial<Record<"obligatoria" | "activa" | "frecuencia_dias" | "al_vencer" | "modo", string>>;
  hoja_texto: string;
  estado: FuentePanel | null;
  corridas: CorridaFuente[];
  competencia: Competencia[];
  descartados: Descartado[];
  versiones: Version[];
}

/** Solo se mandan los campos que cambian. `frecuencia_dias: null` = sin plazo. */
export interface CambiosFuente {
  nombre?: string;
  ubicaciones?: Ubicacion[];
  modo?: string;
  nombre_archivo?: string | null;
  incluye?: string[];
  excluye?: string[];
  extensiones?: string[];
  frecuencia_dias?: number | null;
  al_vencer?: AlVencer;
  obligatoria?: boolean;
  activa?: boolean;
  diferencia_esperada?: boolean;
}

export interface Seleccion {
  archivos: Archivo[];
  candidatos: number;
  texto: string;
}

export interface VistaPrevia {
  elegiria: Seleccion;
  hoy_toma: Seleccion;
  conflictos: string[];
  avisos: string[];
  listado: { pc: string; alias: string | null; corrida_id: string; iniciada_en: string } | null;
}

export interface Guardado {
  version: number;
  modo: ModoConfig;
  hash: string;
  claves_cambiadas: string[];
  avisos: string[];
}

export interface CarpetaNueva {
  clave: string;
  nombre: string;
  tipo: "sharepoint" | "onedrive";
  params: Record<string, string>;
  rutas_por_pc: Record<string, string>;
  activa: boolean;
}

export interface CambiosCarpeta {
  nombre?: string;
  tipo?: "sharepoint" | "onedrive";
  params?: Record<string, string>;
  rutas_por_pc?: Record<string, string>;
  activa?: boolean;
}

/** El texto que manda el servidor cuando otro admin guardo antes (409). */
export const MSG_OTRO_ADMIN = "Otro admin guardó un cambio; recarga";

/** Error con el codigo HTTP: la pantalla distingue el 403 (sin permiso) y el 409. */
export class ErrorFuentes extends Error {
  constructor(public status: number, mensaje: string) {
    super(mensaje);
    this.name = "ErrorFuentes";
  }
}

const RUTA = "/api/admin/fuentes";

async function json<T>(path: string, init?: RequestInit, fallback = "No se pudo completar"): Promise<T> {
  const res = await req(path, init);
  if (!res.ok) {
    const porDefecto = res.status === 409 ? MSG_OTRO_ADMIN : fallback;
    throw new ErrorFuentes(res.status, await mensajeError(res, porDefecto));
  }
  return res.json() as Promise<T>;
}

function enviar<T>(path: string, method: "POST" | "PUT", body: unknown, fallback = "No se pudo guardar"): Promise<T> {
  return json<T>(
    path,
    { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) },
    fallback
  );
}

const seg = encodeURIComponent;

export const fuentesApi = {
  panel: () => json<Panel>(RUTA, undefined, "No se pudo cargar el panel de fuentes"),

  config: () => json<ConfigVigente>(`${RUTA}/config`, undefined, "No se pudo cargar la configuración"),

  corridas: (limit = 30) => json<{ items: Corrida[] }>(`${RUTA}/corridas?limit=${limit}`),

  archivosCarpeta: (clave: string, pc?: string | null) =>
    json<ArchivosCarpeta>(`${RUTA}/carpetas/${seg(clave)}/archivos${pc ? `?pc=${seg(pc)}` : ""}`),

  detalle: (clave: string) => json<FuenteDetalle>(`${RUTA}/${seg(clave)}`, undefined, "No se pudo cargar la fuente"),

  vistaPrevia: (clave: string, cambios: CambiosFuente) =>
    enviar<VistaPrevia>(`${RUTA}/${seg(clave)}/vista-previa`, "POST", { cambios }, "No se pudo calcular la vista previa"),

  guardar: (clave: string, cambios: CambiosFuente, nota: string, base_version: number) =>
    enviar<Guardado>(`${RUTA}/${seg(clave)}`, "PUT", { cambios, nota, base_version }),

  crearCarpeta: (carpeta: CarpetaNueva, nota: string, base_version: number) =>
    enviar<Guardado>(`${RUTA}/carpetas`, "POST", { carpeta, nota, base_version }),

  editarCarpeta: (clave: string, cambios: CambiosCarpeta, nota: string, base_version: number) =>
    enviar<Guardado>(`${RUTA}/carpetas/${seg(clave)}`, "PUT", { cambios, nota, base_version }),

  nombrarPc: (hostname: string, alias: string, base_version: number, nota?: string) =>
    enviar<Guardado>(`${RUTA}/pcs/${seg(hostname)}`, "PUT", { alias, base_version, ...(nota ? { nota } : {}) }),

  cambiarTitular: (pc: string, nota: string, base_version: number) =>
    enviar<Guardado>(`${RUTA}/titular`, "POST", { pc, nota, base_version }),

  cambiarModo: (modo: ModoConfig, nota: string, base_version: number) =>
    enviar<Guardado>(`${RUTA}/modo`, "POST", { modo, nota, base_version }),

  sembrar: (corrida_id: string, nota?: string) =>
    enviar<Guardado>(`${RUTA}/sembrar`, "POST", { corrida_id, ...(nota ? { nota } : {}) }),

  revertir: (version: number, base_version: number, opciones: { clave?: string; nota?: string } = {}) =>
    enviar<Guardado>(`${RUTA}/revertir/${version}`, "POST", {
      base_version,
      ...(opciones.clave ? { clave: opciones.clave } : {}),
      ...(opciones.nota ? { nota: opciones.nota } : {}),
    }),
};

// --------------------------------------------------------------------------- //
// Textos y formato
// --------------------------------------------------------------------------- //
export const NIVELES: Record<Nivel, { label: string; fila: string; punto: string; franja: string }> = {
  rojo: {
    label: "Rojo",
    fila: "border-rose-200 bg-rose-50 text-rose-800",
    punto: "bg-rose-600",
    franja: "border-rose-300 bg-rose-50",
  },
  amarillo: {
    label: "Amarillo",
    fila: "border-amber-200 bg-amber-50 text-amber-900",
    punto: "bg-amber-500",
    franja: "border-amber-300 bg-amber-50",
  },
  verde: {
    label: "Verde",
    fila: "border-emerald-200 bg-emerald-50 text-emerald-800",
    punto: "bg-emerald-600",
    franja: "border-emerald-300 bg-emerald-50",
  },
  gris: {
    label: "Gris",
    fila: "border-ink-200 bg-ink-100 text-ink-600",
    punto: "bg-ink-400",
    franja: "border-ink-200 bg-paper-100",
  },
};

export const MODOS_ELECCION: Record<string, string> = {
  archivo_exacto: "Siempre este archivo",
  mas_reciente: "El más reciente cuyo nombre contenga…",
  por_descarte: "Los respaldos de la carpeta",
};

export const TEXTO_PRUEBA: Record<string, string> = {
  coincide: "Coincide",
  difiere: "Difiere",
  difiere_esperado: "Diferencia esperada",
  falta: "No lo encuentra",
};

export const TEXTO_TIPO_CORRIDA: Record<string, string> = {
  oficial: "Diaria",
  probar: "Revisión",
  comparacion: "Comparación",
};

export const TEXTO_ORIGEN: Record<string, string> = {
  plataforma: "configuración de esta pantalla",
  cache: "configuración guardada en el PC",
  env: "configuración escrita en el PC",
};

const DIAS = ["domingo", "lunes", "martes", "miércoles", "jueves", "viernes", "sábado"];

const FMT_CHILE = new Intl.DateTimeFormat("en-US", {
  timeZone: "America/Santiago",
  year: "numeric",
  month: "2-digit",
  day: "2-digit",
  hour: "2-digit",
  minute: "2-digit",
  hourCycle: "h23",
});

interface PartesChile {
  anio: number;
  mes: number;
  dia: number;
  hora: string;
  minuto: string;
}

/** Fecha y hora en Chile, sea cual sea la zona del navegador. */
function partesChile(iso: string): PartesChile | null {
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return null;
  const p: Record<string, string> = {};
  for (const x of FMT_CHILE.formatToParts(d)) p[x.type] = x.value;
  return { anio: Number(p.year), mes: Number(p.month), dia: Number(p.day), hora: p.hour, minuto: p.minute };
}

const dd = (n: number) => String(n).padStart(2, "0");

/** "16-10-2026 09:34", en hora de Chile. */
export function fechaHora(iso: string | null | undefined): string {
  const p = iso ? partesChile(iso) : null;
  if (!p) return "—";
  return `${dd(p.dia)}-${dd(p.mes)}-${p.anio} ${p.hora}:${p.minuto}`;
}

/**
 * Lo mismo que `_cuando` del servidor: "hoy a las 09:34", "ayer a las 10:29",
 * "el martes a las 09:30", "el 05-10 a las 09:30". `ahora` es la hora del panel.
 */
export function cuando(iso: string | null | undefined, ahora: string): string {
  const p = iso ? partesChile(iso) : null;
  const h = partesChile(ahora);
  if (!p || !h) return "—";
  const dia = Date.UTC(p.anio, p.mes - 1, p.dia);
  const dias = Math.round((Date.UTC(h.anio, h.mes - 1, h.dia) - dia) / 86_400_000);
  const hora = `${p.hora}:${p.minuto}`;
  if (dias === 0) return `hoy a las ${hora}`;
  if (dias === 1) return `ayer a las ${hora}`;
  if (dias > 1 && dias < 7) return `el ${DIAS[new Date(dia).getUTCDay()]} a las ${hora}`;
  if (p.anio === h.anio) return `el ${dd(p.dia)}-${dd(p.mes)} a las ${hora}`;
  return `el ${dd(p.dia)}-${dd(p.mes)}-${p.anio} a las ${hora}`;
}

/** "de hoy a las 09:34", "del martes a las 09:30" (como `_de` del servidor). */
export function de(texto: string): string {
  return texto.startsWith("el ") ? `del ${texto.slice(3)}` : `de ${texto}`;
}

/** "2,1 MB", "340 KB". */
export function tamano(bytes: number | null | undefined): string {
  if (bytes == null) return "—";
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1).replace(".", ",")} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

/** "PC de la jefa" o el hostname si no tiene nombre. */
export function nombrePc(pc: string | null | undefined, alias: string | null | undefined): string {
  return alias || pc || "—";
}

/** Plazo en palabras: "Cada 2 días hábiles; si se atrasa, frena la publicación". */
export function textoPlazo(frecuencia: number | null | undefined, alVencer: string | null | undefined): string {
  if (frecuencia == null) return "Sin plazo";
  const cada = frecuencia === 1 ? "Cada 1 día hábil" : `Cada ${frecuencia} días hábiles`;
  return `${cada}; si se atrasa, ${alVencer === "avisa" ? "solo avisa" : "frena la publicación"}`;
}

// --------------------------------------------------------------------------- //
// Editor: del formulario a los cambios que viajan
// --------------------------------------------------------------------------- //
export interface FormFuente {
  nombre: string;
  ubicaciones: Ubicacion[];
  modo: string;
  nombre_archivo: string;
  /** Un patron por linea. */
  incluye: string;
  excluye: string;
  /** Separadas por coma. */
  extensiones: string;
  sin_plazo: boolean;
  frecuencia_dias: string;
  al_vencer: AlVencer;
  obligatoria: boolean;
  activa: boolean;
  diferencia_esperada: boolean;
}

export function formDesde(f: FuenteCfg): FormFuente {
  return {
    nombre: f.nombre,
    ubicaciones: f.ubicaciones.map((u) => ({ ...u })),
    modo: f.modo,
    nombre_archivo: f.nombre_archivo ?? "",
    incluye: f.incluye.join("\n"),
    excluye: f.excluye.join("\n"),
    extensiones: f.extensiones.join(", "),
    sin_plazo: f.frecuencia_dias == null,
    frecuencia_dias: f.frecuencia_dias == null ? "" : String(f.frecuencia_dias),
    al_vencer: f.al_vencer,
    obligatoria: f.obligatoria,
    activa: f.activa,
    diferencia_esperada: f.diferencia_esperada,
  };
}

export const lineas = (s: string): string[] =>
  s.split(/\r?\n/).map((x) => x.trim()).filter(Boolean);

export const extensiones = (s: string): string[] =>
  s.split(/[,\s]+/).map((x) => x.trim().toLowerCase()).filter(Boolean).map((x) => (x.startsWith(".") ? x : `.${x}`));

const igual = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** El plazo escrito, o un error para mostrar junto al campo. */
export function plazoDe(form: FormFuente): { valor: number | null; error: string | null } {
  if (form.sin_plazo) return { valor: null, error: null };
  const n = Number(form.frecuencia_dias.trim());
  if (!form.frecuencia_dias.trim() || !Number.isInteger(n) || n < 1 || n > 365) {
    return { valor: null, error: "Escribe un número entero de 1 a 365 días hábiles, o marca «Sin plazo»." };
  }
  return { valor: n, error: null };
}

/** Lo que cambio respecto de la configuracion guardada: solo eso viaja al servidor. */
export function cambiosFuente(original: FuenteCfg, form: FormFuente): CambiosFuente {
  const c: CambiosFuente = {};
  const nombre = form.nombre.trim();
  if (nombre && nombre !== original.nombre) c.nombre = nombre;
  const ubicaciones = form.ubicaciones.map((u) => ({
    carpeta: u.carpeta,
    subcarpeta: u.subcarpeta.trim().replace(/\\/g, "/").replace(/^\/+|\/+$/g, ""),
    recursiva: u.recursiva,
  }));
  if (!igual(ubicaciones, original.ubicaciones)) c.ubicaciones = ubicaciones;
  if (form.modo !== original.modo) c.modo = form.modo;
  const archivo = form.nombre_archivo.trim() || null;
  if (archivo !== (original.nombre_archivo ?? null)) c.nombre_archivo = archivo;
  const incluye = lineas(form.incluye);
  if (!igual(incluye, original.incluye)) c.incluye = incluye;
  const excluye = lineas(form.excluye);
  if (!igual(excluye, original.excluye)) c.excluye = excluye;
  const exts = extensiones(form.extensiones);
  if (!igual(exts, original.extensiones)) c.extensiones = exts;
  const { valor, error } = plazoDe(form);
  if (!error && valor !== (original.frecuencia_dias ?? null)) c.frecuencia_dias = valor;
  if (form.al_vencer !== original.al_vencer) c.al_vencer = form.al_vencer;
  if (form.obligatoria !== original.obligatoria) c.obligatoria = form.obligatoria;
  if (form.activa !== original.activa) c.activa = form.activa;
  if (form.diferencia_esperada !== original.diferencia_esperada) c.diferencia_esperada = form.diferencia_esperada;
  return c;
}

/** Minusculas y sin tildes, como `_norm` del motor y del servidor. */
export function normalizar(s: string): string {
  return (s ?? "").normalize("NFKD").replace(/[̀-ͯ]/g, "").toLowerCase();
}

/**
 * Los archivos de un listado que caen en una ubicacion (misma regla que
 * `_en_ubicacion` del servidor) y tienen una de las extensiones. Arma los
 * selectores del editor.
 */
export function archivosEnUbicacion(
  archivos: ArchivoCarpeta[],
  ubicacion: Pick<Ubicacion, "subcarpeta" | "recursiva">,
  exts: string[]
): ArchivoCarpeta[] {
  const sub = normalizar(ubicacion.subcarpeta.replace(/\\/g, "/").replace(/^\/+|\/+$/g, ""));
  const permitidas = new Set(exts.map((e) => e.toLowerCase()));
  return archivos.filter((a) => {
    const nombre = a.nombre;
    if (nombre.startsWith("~$") || nombre.toLowerCase() === "desktop.ini") return false;
    const ext = nombre.includes(".") ? `.${nombre.split(".").pop()!.toLowerCase()}` : "";
    if (permitidas.size && !permitidas.has(ext)) return false;
    const carpeta = normalizar(a.subcarpeta);
    if (sub && !(carpeta === sub || carpeta.startsWith(`${sub}/`))) return false;
    const resto = sub ? carpeta.slice(sub.length).replace(/^\/+/, "") : carpeta;
    return ubicacion.recursiva || !resto;
  });
}
