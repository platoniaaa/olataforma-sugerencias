// La vigencia de una decision de precio: desde y hasta cuando rigen el precio fijo, el
// margen fijo o el congelado. Despues del Hasta (o antes del Desde) el producto sigue la
// regla; la decision queda guardada para poder renovarla.
//
// Todo sobre PARTES de fecha ("2026-11-30" -> 2026, 11, 30), nunca sobre `new Date("2026-11-30")`
// ni `toISOString()`: esos interpretan la fecha como UTC y en Chile corren un dia (de noche,
// UTC ya es mañana). La aritmetica va sobre `Date.UTC`, que no tiene huso ni horario de
// verano. La unica lectura del reloj es `hoyLocal`, y el servidor manda su propio `hoy`
// (fecha de Chile) para que el estado de la vigencia nunca dependa del reloj del navegador.
import { formatoCLP, formatoFecha, formatoNumero } from "./formato";
import { fechaEnDias } from "./pedido-especial";
import type { EstadoVigencia, PrecioRow } from "./types";

/** Un periodo: "aaaa-mm-dd" o "" (sin limite de ese lado). */
export interface Periodo {
  desde: string;
  hasta: string;
}

const ISO = /^(\d{4})-(\d{2})-(\d{2})$/;
const MS_DIA = 86_400_000;

/** Cuantos dias adelante se ve como "fecha muy lejana" (aviso, no error). */
const DIAS_AVISO = 366;
/** Lo mismo que rechaza la API: una fecha a mas de 3 años de hoy. */
const ANIOS_MAXIMO = 3;
/** Un precio fijo que vence en esta cantidad de dias o menos se marca como "pronto". */
export const DIAS_PRONTO = 7;

// ----------------------------------------------------------------- fechas

function dosDigitos(n: number): string {
  return String(n).padStart(2, "0");
}

function aIso(utc: number): string {
  const d = new Date(utc);
  return `${String(d.getUTCFullYear()).padStart(4, "0")}-${dosDigitos(d.getUTCMonth() + 1)}-${dosDigitos(d.getUTCDate())}`;
}

/** Las partes de una fecha aaaa-mm-dd, o null si no es una fecha de calendario real. */
export function partesFecha(iso: string): { anio: number; mes: number; dia: number } | null {
  const m = ISO.exec(iso ?? "");
  if (!m) return null;
  const [anio, mes, dia] = [Number(m[1]), Number(m[2]), Number(m[3])];
  if (mes < 1 || mes > 12 || dia < 1) return null;
  // El 31 de abril o el 30 de febrero no existen: Date.UTC los correria al mes siguiente.
  if (dia > new Date(Date.UTC(anio, mes, 0)).getUTCDate()) return null;
  return { anio, mes, dia };
}

export function esFechaIso(iso: string): boolean {
  return partesFecha(iso) !== null;
}

function utcDe(iso: string): number {
  const p = partesFecha(iso);
  if (!p) throw new Error(`Fecha invalida: ${iso}`);
  return Date.UTC(p.anio, p.mes - 1, p.dia);
}

/** La fecha de hoy en hora LOCAL del navegador (no UTC). Es el respaldo: lo normal es usar
 *  la que manda el servidor en `resumen.vigencias.hoy`. */
export function hoyLocal(ahora: Date = new Date()): string {
  return fechaEnDias(0, ahora);
}

/** `iso` mas `n` dias (n puede ser negativo). Cruza mes, año y bisiestos. */
export function sumarDias(iso: string, n: number): string {
  return aIso(utcDe(iso) + n * MS_DIA);
}

/** Dias que hay de `desde` a `hasta` (negativo si hasta es anterior). */
export function diasEntre(desde: string, hasta: string): number {
  return Math.round((utcDe(hasta) - utcDe(desde)) / MS_DIA);
}

/** El ultimo dia del mes de `iso`. Si `iso` ya ES el ultimo dia, el del mes siguiente: un
 *  atajo "Fin de mes" que devuelve el dia en que ya estas no sirve de nada. */
export function finDeMes(iso: string): string {
  const p = partesFecha(iso);
  if (!p) throw new Error(`Fecha invalida: ${iso}`);
  const ultimo = aIso(Date.UTC(p.anio, p.mes, 0));
  if (iso !== ultimo) return ultimo;
  return aIso(Date.UTC(p.anio, p.mes + 1, 0));
}

/** dd-mm sin año si es el de `hoy`; con año si no ("30-11" / "30-11-2027"). */
export function fechaCorta(iso: string, hoy: string): string {
  const largo = formatoFecha(iso);
  return iso.slice(0, 4) === hoy.slice(0, 4) ? largo.slice(0, 5) : largo;
}

// ------------------------------------------------------------------ estado

/** El estado de un periodo en la fecha `hoy`. Desde y Hasta son inclusivos: el dia del Hasta
 *  todavia rige. Es la misma cuenta del servidor; sirve para la vista previa viva del
 *  formulario (lo que ya esta guardado trae su `vigencia` del servidor). */
export function estadoDe(p: Periodo, hoy: string): EstadoVigencia | null {
  if (!p.desde && !p.hasta) return null;
  if (p.desde && p.hasta && p.desde > p.hasta) return "vencida";
  if (p.desde && hoy < p.desde) return "programada";
  if (p.hasta && hoy > p.hasta) return "vencida";
  return "vigente";
}

/** Si la decision guardada rige hoy. Una programada o vencida NO rige: el precio es el de
 *  la regla y mostrarla como si rigiera (explicacion, margen, columnas) seria falso. */
export function decisionRige(fila: Pick<PrecioRow, "vigencia"> | null | undefined): boolean {
  return fila?.vigencia !== "programada" && fila?.vigencia !== "vencida";
}

// ----------------------------------------------------------------- atajos

export type AtajoId = "30" | "60" | "90" | "mes" | "sin";

export const ATAJOS: { id: AtajoId; etiqueta: string }[] = [
  { id: "30", etiqueta: "30 días" },
  { id: "60", etiqueta: "60 días" },
  { id: "90", etiqueta: "90 días" },
  { id: "mes", etiqueta: "Fin de mes" },
  { id: "sin", etiqueta: "Sin vencimiento" },
];

/** El Hasta que da un atajo. Se cuenta desde el Desde si es futuro (un precio que empieza
 *  el 05-11 por 30 dias termina a fines de noviembre, no en noviembre-menos-algo) y si no
 *  desde hoy. "Sin vencimiento" es vacio. */
export function atajo(id: AtajoId, desde: string, hoy: string): string {
  const base = desde && esFechaIso(desde) && desde > hoy ? desde : hoy;
  switch (id) {
    case "30": return sumarDias(base, 30);
    case "60": return sumarDias(base, 60);
    case "90": return sumarDias(base, 90);
    case "mes": return finDeMes(base);
    default: return "";
  }
}

// ------------------------------------------------------------- validacion

export interface ErroresPeriodo {
  desde: string | null;
  hasta: string | null;
  /** Aviso que no bloquea (una fecha muy lejana). */
  aviso: string | null;
}

export interface OpcionesValidacion {
  /** La persona toco el Desde / el Hasta en esta sesion. Un Hasta que ya venia vencido del
   *  servidor y nadie toco no es un error: es el estado "Vencido" de la decision. */
  desdeTocado?: boolean;
  hastaTocado?: boolean;
  /** La persona pone o cambia un precio fijo, un margen o el congelado. La API no deja
   *  guardar eso con un periodo ya terminado: tiene que renovarlo en la misma llamada. */
  decisionCambiada?: boolean;
  /** Congelar esta marcado: toma el precio de HOY, asi que no se puede programar. */
  congelar?: boolean;
  /** Al guardar: una fecha con el año a medio escribir (0002) es un error. Mientras se
   *  escribe se deja pasar para no gritar a cada tecla. */
  estricto?: boolean;
}

const SIN_ERRORES: ErroresPeriodo = { desde: null, hasta: null, aviso: null };

function aniosDesde(hoy: string, n: number): string {
  const p = partesFecha(hoy);
  if (!p) return hoy;
  // 29 de febrero + N años puede no existir: el 28.
  const dia = p.mes === 2 && p.dia === 29 ? 28 : p.dia;
  return `${String(p.anio + n).padStart(4, "0")}-${dosDigitos(p.mes)}-${dosDigitos(dia)}`;
}

/** Lo que esta mal en un periodo, junto al campo que lo causa. Los mensajes dicen la causa y
 *  como arreglarlo; los de la API dicen lo mismo con las mismas palabras. */
export function validarPeriodo(p: Periodo, hoy: string, op: OpcionesValidacion = {}): ErroresPeriodo {
  const errores: ErroresPeriodo = { ...SIN_ERRORES };
  const ejemplo = "Escribe una fecha válida, por ejemplo 30-11-2026.";

  for (const campo of ["desde", "hasta"] as const) {
    const v = p[campo];
    if (!v) continue;
    if (!esFechaIso(v)) {
      errores[campo] = ejemplo;
    } else if (Number(v.slice(0, 4)) < 1000) {
      // Año a medio escribir: el selector de fecha entrega 0002-.. al teclear el primer dígito.
      if (op.estricto) errores[campo] = ejemplo;
      // Y en cualquier caso no se sigue validando contra otras fechas con una a medias.
      else return { ...errores };
    }
  }
  if (errores.desde || errores.hasta) return errores;

  const bajo = aniosDesde(hoy, -ANIOS_MAXIMO);
  const alto = aniosDesde(hoy, ANIOS_MAXIMO);
  const tocado = { desde: op.desdeTocado, hasta: op.hastaTocado };
  for (const campo of ["desde", "hasta"] as const) {
    const v = p[campo];
    if (v && tocado[campo] && (v < bajo || v > alto)) {
      errores[campo] = `La fecha está a más de ${ANIOS_MAXIMO} años de hoy.`;
    }
  }
  if (errores.desde || errores.hasta) return errores;

  if (p.desde && p.hasta && p.desde > p.hasta) {
    errores.hasta = `El Hasta no puede ser antes del Desde (${formatoFecha(p.desde)}).`;
    return errores;
  }
  if (op.congelar && p.desde && p.desde > hoy) {
    errores.desde = "Congelar toma el precio de hoy: no se puede programar con un Desde futuro (usa precio fijo).";
  }
  if (p.hasta && p.hasta < hoy && (op.hastaTocado || op.desdeTocado || op.decisionCambiada)) {
    errores.hasta = `Ese Hasta ya pasó (${formatoFecha(p.hasta)}): la decisión quedaría vencida y el producto `
      + "seguiría la regla. Pon un Hasta de hoy en adelante o déjalo vacío.";
  }
  if (!errores.hasta && p.hasta && diasEntre(hoy, p.hasta) > DIAS_AVISO) {
    errores.aviso = "¿Seguro? Es dentro de más de un año.";
  }
  return errores;
}

export function hayErrores(e: ErroresPeriodo): boolean {
  return Boolean(e.desde || e.hasta);
}

// ---------------------------------------------------------------- etiqueta

type FilaConVigencia = Pick<
  PrecioRow,
  "vigencia" | "vigente_desde" | "vigente_hasta" | "vigencia_dias" | "precio_fijo" | "margen_fijo" | "congelar"
>;

export type TonoVigencia = "lejos" | "pronto" | "programado" | "vencido";
export type IconoVigencia = "calendario-reloj" | "reloj-arena" | "calendario-rango" | "calendario-x";

export interface EtiquetaVigencia {
  estado: EstadoVigencia;
  /** Lo que dice el chip: "Fijo hasta 30-11", "Programado desde 05-11", "Vencido 12-10". */
  texto: string;
  /** La frase completa, para el title y para quien lee con un lector de pantalla. */
  titulo: string;
  tono: TonoVigencia;
  icono: IconoVigencia;
  /** Dias hasta el Hasta (vigente con Hasta). */
  dias: number | null;
}

/** Que decision gobierna el periodo, para nombrarla: precio fijo > congelado > margen. */
function decisionDe(f: Partial<FilaConVigencia>): { corto: string; largo: string } {
  if (f.precio_fijo !== null && f.precio_fijo !== undefined) return { corto: "Fijo", largo: "Precio fijo" };
  if (f.congelar) return { corto: "Congelado", largo: "Precio congelado" };
  if (f.margen_fijo !== null && f.margen_fijo !== undefined) return { corto: "Margen", largo: "Margen fijo" };
  return { corto: "Fijo", largo: "Precio fijo" };
}

/** El chip de la vigencia de una fila, o null si no hay nada que mostrar: sin periodo, o
 *  vigente sin Hasta (queda fijo hasta que alguien lo cambie, como los 342 de hoy). */
export function etiquetaVigencia(fila: Partial<FilaConVigencia>, hoy: string = hoyLocal()): EtiquetaVigencia | null {
  const estado = fila.vigencia;
  if (!estado) return null;
  const desde = fila.vigente_desde ?? "";
  const hasta = fila.vigente_hasta ?? "";
  const { corto, largo } = decisionDe(fila);

  if (estado === "programada") {
    if (!desde) return null;
    return {
      estado, dias: null, tono: "programado", icono: "calendario-rango",
      texto: `Programado desde ${fechaCorta(desde, hoy)}`,
      titulo: `${largo} programado desde el ${formatoFecha(desde)}`
        + `${hasta ? ` hasta el ${formatoFecha(hasta)}` : ""}. Hasta entonces el producto sigue la regla.`,
    };
  }
  if (estado === "vencida") {
    return {
      estado, dias: null, tono: "vencido", icono: "calendario-x",
      texto: hasta ? `Vencido ${fechaCorta(hasta, hoy)}` : "Vencido",
      titulo: hasta
        ? `${largo} vencido el ${formatoFecha(hasta)}: el producto volvió a la regla.`
        : `${largo} vencido: el producto volvió a la regla.`,
    };
  }
  if (!hasta) return null;
  const dias = typeof fila.vigencia_dias === "number" ? fila.vigencia_dias : diasEntre(hoy, hasta);
  const texto = dias <= 0 ? `${corto} hasta hoy`
    : dias === 1 ? `${corto} hasta mañana`
    : dias <= DIAS_PRONTO ? `${corto} hasta ${fechaCorta(hasta, hoy)} (${dias} días)`
    : `${corto} hasta ${fechaCorta(hasta, hoy)}`;
  return {
    estado, dias, texto,
    tono: dias <= DIAS_PRONTO ? "pronto" : "lejos",
    icono: dias <= DIAS_PRONTO ? "reloj-arena" : "calendario-reloj",
    titulo: `${largo} hasta el ${formatoFecha(hasta)} incluido. El ${formatoFecha(sumarDias(hasta, 1))} vuelve a la regla.`,
  };
}

// ----------------------------------------------------------------- envio

export interface PeriodoEnviado {
  vigente_desde?: string | null;
  vigente_hasta?: string | null;
}

/** Los extremos que hay que mandar al guardar. Solo viajan los que la persona cambio
 *  ("ausente = no tocar" para la API; y una API sin vigencia rechaza campos que no conoce).
 *  Si no queda ninguna decision que vigilar, las fechas no tienen sentido: se mandan vacias
 *  (y solo si habia algo guardado que borrar). */
export function armarPeriodoParaEnviar(actual: Periodo, cargado: Periodo, hayDecision: boolean): PeriodoEnviado {
  if (!hayDecision) {
    if (!cargado.desde && !cargado.hasta) return {};
    return { vigente_desde: null, vigente_hasta: null };
  }
  const salida: PeriodoEnviado = {};
  if (actual.desde !== cargado.desde) salida.vigente_desde = actual.desde || null;
  if (actual.hasta !== cargado.hasta) salida.vigente_hasta = actual.hasta || null;
  return salida;
}

// ---------------------------------------------------------------- resumen

export interface DecisionPeriodo {
  tipo: "fijo" | "congelado" | "margen";
  /** Lo que vale la decision: el precio fijo, el congelado o el que da el margen con el costo
   *  de hoy. null si no se sabe. */
  precio: number | null;
  /** El % del margen fijo. */
  margen?: number | null;
}

export interface EntradaResumen {
  periodo: Periodo;
  /** El periodo que ya esta guardado: si difiere, la linea dice "Al guardar:". */
  guardado: Periodo;
  hoy: string;
  /** La decision que gobierna el periodo; null = ninguna (las fechas se borran al guardar). */
  decision: DecisionPeriodo | null;
  /** El precio que daria la regla sin la decision, si se sabe. */
  precioRegla: number | null;
}

export interface ResumenVigencia {
  texto: string;
  /** "Al vencer pasaria de $X a $Y": va aparte para poder destacarlo cuando el salto es grande. */
  vencimiento: string | null;
  /** El salto al vencer es de 20 % o mas: se destaca (con la palabra «baja» o «sube»). */
  fuerte: boolean;
}

/** Desde este salto (en %) al vencer, la ficha lo destaca. Es el mismo umbral que ya usa para
 *  la desviacion contra el precio del ERP. */
export const UMBRAL_SALTO_PCT = 20;

function nombreDecision(d: DecisionPeriodo): string {
  if (d.tipo === "fijo") return `el precio fijo${d.precio != null ? ` de ${formatoCLP(d.precio)}` : ""}`;
  if (d.tipo === "congelado") return `el precio congelado${d.precio != null ? ` de ${formatoCLP(d.precio)}` : ""}`;
  return `el margen fijo${d.margen != null ? ` de ${formatoNumero(d.margen, 1)} %` : ""}`;
}

function conMinuscula(t: string): string {
  return t.charAt(0).toLowerCase() + t.slice(1);
}

function vencimientoDe(decision: DecisionPeriodo | null, regla: number | null): { texto: string; fuerte: boolean } | null {
  if (!decision || decision.precio == null || regla == null) return null;
  const actual = decision.precio;
  if (actual <= 0) return { texto: `Al vencer pasaría de ${formatoCLP(actual)} a ${formatoCLP(regla)}.`, fuerte: false };
  const pct = Math.round((regla / actual - 1) * 100);
  if (pct === 0 && Math.round(regla) === Math.round(actual)) return { texto: "Al vencer el precio no cambia.", fuerte: false };
  const signo = pct < 0 ? "−" : "+";
  const cuanto = `${signo}${formatoNumero(Math.abs(pct))} %`;
  if (Math.abs(pct) >= UMBRAL_SALTO_PCT) {
    return {
      texto: `Al vencer el precio ${pct < 0 ? "baja" : "sube"} de ${formatoCLP(actual)} a ${formatoCLP(regla)} (${cuanto}).`,
      fuerte: true,
    };
  }
  return { texto: `Al vencer pasaría de ${formatoCLP(actual)} a ${formatoCLP(regla)} (${cuanto}).`, fuerte: false };
}

/** La linea viva bajo las fechas: que va a pasar con este periodo, en palabras. */
export function resumenVigencia(e: EntradaResumen): ResumenVigencia | null {
  const { periodo: p, hoy, decision, precioRegla } = e;
  const cambiado = p.desde !== e.guardado.desde || p.hasta !== e.guardado.hasta;
  const alGuardar = (t: string) => (cambiado ? `Al guardar: ${conMinuscula(t)}` : t);

  if (!decision) {
    if (!p.desde && !p.hasta) return null;
    return {
      texto: "Al guardar se borran las fechas: sin precio fijo, margen ni congelado no hay nada que vigilar.",
      vencimiento: null, fuerte: false,
    };
  }
  const nombre = nombreDecision(decision);
  const regla = precioRegla != null ? ` (${formatoCLP(precioRegla)})` : "";
  const estado = estadoDe(p, hoy);

  if (estado === null) {
    return { texto: alGuardar("Rige desde que guardes, sin vencimiento."), vencimiento: null, fuerte: false };
  }
  if (estado === "programada") {
    const hasta = p.hasta ? ` hasta el ${formatoFecha(p.hasta)}` : ", sin vencimiento";
    return {
      texto: alGuardar(`Hoy el producto sigue la regla${regla}. Desde el ${formatoFecha(p.desde)} rige ${nombre}${hasta}.`),
      vencimiento: null, fuerte: false,
    };
  }
  if (estado === "vencida") {
    return {
      texto: alGuardar(
        `Venció el ${formatoFecha(p.hasta)} y hoy sigue la regla${regla}. Para aplicar de nuevo ${nombre} `
        + "elige un nuevo Hasta y guarda; o usa «Volver a la regla» para borrar la decisión.",
      ),
      vencimiento: null, fuerte: false,
    };
  }
  // vigente
  if (!p.hasta) {
    return { texto: alGuardar(`Rige desde el ${formatoFecha(p.desde)}, sin vencimiento.`), vencimiento: null, fuerte: false };
  }
  const siguiente = formatoFecha(sumarDias(p.hasta, 1));
  const rige = p.desde ? `Rige desde el ${formatoFecha(p.desde)} hasta el ${formatoFecha(p.hasta)} incluido.`
    : `Rige hoy y hasta el ${formatoFecha(p.hasta)} incluido.`;
  const v = vencimientoDe(decision, precioRegla);
  return {
    texto: alGuardar(`${rige} El ${siguiente} vuelve a la regla.`),
    vencimiento: v?.texto ?? null,
    fuerte: v?.fuerte ?? false,
  };
}

// ------------------------------------------------------------------- orden

/**
 * Para ordenar la columna «Vigencia» por fecha de término con los vacíos SIEMPRE al final.
 *
 * AG Grid invierte el resultado del comparador cuando el orden es descendente, así que un
 * comparador "normal" mandaría los vacíos (los miles de productos sin periodo) al principio de
 * un orden descendente y la columna parecería vacía. `descendente` compensa esa inversión.
 */
export function compararVencimiento(a: string | null | undefined, b: string | null | undefined, descendente: boolean): number {
  if (!a && !b) return 0;
  if (!a) return descendente ? -1 : 1;
  if (!b) return descendente ? 1 : -1;
  return a < b ? -1 : a > b ? 1 : 0;
}
