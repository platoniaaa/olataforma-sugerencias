/**
 * Lo que dice el modal de sugerencia manual antes de guardar: cuánto se compra.
 *
 * Las tres frases del modal (opción A, aprobada el 08-10-2026):
 *   - "una":  Quiero N unidades más, una sola vez.
 *   - "min":  Quiero que nunca haya menos de N unidades.     (regla diaria)
 *   - "dias": Quiero que siempre alcance para N días de venta. (regla diaria)
 *
 * Las cuentas son las del servidor (`sugerido_service._faltante_para_objetivo` y
 * `_objetivo_dias`): lo que ya hay es stock + en camino + lo que el sistema ya
 * pide, y una regla pide solo la diferencia. Si estas cuentas se separan de las
 * del servidor, la pantalla promete un número y se guarda otro.
 */
import { formatoNumero } from "@/lib/formato";
import type { ContextoSugerencia } from "@/lib/types";

export type Frase = "una" | "min" | "dias";

export interface Resultado {
  /** Lo que se compra hoy en total: lo del sistema más lo de esta sugerencia. */
  total: number;
  /** Lo que agrega esta sugerencia. */
  tuyas: number;
  /** Con lo que queda la sucursal: stock + en camino + lo que se compra. */
  quedas: number;
  /** Para cuántos días de venta alcanza `quedas`; null sin venta registrada. */
  diasVenta: number | null;
  /** Una regla que hoy no necesita pedir nada. */
  nadaQuePedir: boolean;
  /** "días de venta" sin venta registrada: no se puede pasar a unidades. */
  sinDemanda: boolean;
}

export function cubierto(ctx: ContextoSugerencia): number {
  return (ctx.stock || 0) + (ctx.transito || 0) + (ctx.sugerido_sistema || 0);
}

/** null si el número no sirve (vacío, cero o negativo). */
export function calcular(frase: Frase, ctx: ContextoSugerencia, n: number): Resultado | null {
  if (!Number.isFinite(n) || n <= 0) return null;
  const sistema = ctx.sugerido_sistema || 0;
  const hay = cubierto(ctx);
  const demanda = ctx.demanda_diaria && ctx.demanda_diaria > 0 ? ctx.demanda_diaria : null;
  const dias = (q: number) => (demanda ? q / demanda : null);

  if (frase === "una") {
    const quedas = hay + n;
    return { total: sistema + n, tuyas: n, quedas, diasVenta: dias(quedas), nadaQuePedir: false, sinDemanda: false };
  }
  if (frase === "dias" && !demanda) {
    return { total: sistema, tuyas: 0, quedas: hay, diasVenta: null, nadaQuePedir: false, sinDemanda: true };
  }
  const nivel = frase === "min" ? n : Math.max(1, Math.ceil((demanda as number) * n));
  const tuyas = Math.max(0, Math.ceil(nivel - hay));
  const quedas = hay + tuyas;
  return { total: sistema + tuyas, tuyas, quedas, diasVenta: dias(quedas), nadaQuePedir: tuyas === 0, sinDemanda: false };
}

/** El título y la línea de detalle del recuadro de resultado. */
export function textoResultado(
  frase: Frase,
  ctx: ContextoSugerencia,
  n: number,
): { titulo: string; detalle: string } | null {
  const r = calcular(frase, ctx, n);
  if (!r) return null;
  const f = (x: number) => formatoNumero(Math.round(x));
  const sistema = ctx.sugerido_sistema || 0;
  const alcance = r.diasVenta !== null ? `, unos ${f(r.diasVenta)} días de venta` : "";

  if (r.sinDemanda) {
    return {
      titulo: "No se puede calcular",
      detalle: "Este producto no tiene venta registrada en esta sucursal. Usa “nunca haya menos de”.",
    };
  }
  if (r.nadaQuePedir) {
    return {
      titulo: "Hoy no hace falta pedir",
      detalle: `Entre stock, lo que viene y lo que pide el sistema ya hay ${f(cubierto(ctx))}${alcance}. Pedirá cuando baje.`,
    };
  }
  const partes =
    frase === "una"
      ? `${f(r.tuyas)} tuyas`
      : frase === "min"
        ? `${f(r.tuyas)} para no bajar de ${f(n)}`
        : `${f(r.tuyas)} para cubrir ${f(n)} días`;
  const desglose = sistema > 0 ? `${f(sistema)} que pide el sistema + ${partes}` : `${partes[0].toUpperCase()}${partes.slice(1)}; el sistema no pide nada hoy`;
  return {
    titulo: `Hoy se compran ${f(r.total)} en total`,
    detalle: `${desglose}. Quedas con ${f(r.quedas)}${alcance}.`,
  };
}

/** Fecha YYYY-MM-DD dentro de `dias` días, en hora local (no UTC: de noche en
 *  Chile, UTC ya es mañana). */
export function fechaEnDias(dias: number, desde: Date = new Date()): string {
  const d = new Date(desde);
  d.setDate(d.getDate() + dias);
  d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
  return d.toISOString().slice(0, 10);
}
