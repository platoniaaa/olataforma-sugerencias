"use client";

/**
 * "+ info": de dónde sale la columna «Aporta esto».
 *
 * Va colapsado a propósito. Es una explicación que se lee una vez y después
 * estorba, pero sin ella la columna deja una duda razonable: por qué una
 * sugerencia que está activa aporta cero.
 *
 * Dos decisiones de presentación, las dos por haberlo hecho mal antes:
 *
 * 1. **Tabla, no texto alineado con espacios.** La primera versión era un bloque
 *    monoespaciado con las columnas cuadradas a mano; con las tildes de "mínimo"
 *    y "tránsito" se descuadraba y quedaba ilegible.
 * 2. **Nunca se muestra la resta cruda.** "aporta = 2 − 5 → 0" parece matemática
 *    rota, porque el `max(0, ...)` queda invisible. Cuando lo cubierto supera el
 *    mínimo se dice en palabras, no con una resta que da negativo.
 *
 * Y el ejemplo son DOS líneas reales de la misma sugerencia —una que aporta y
 * otra que no, ojalá del mismo producto en dos sucursales—. Puestas al lado se
 * entiende de una: misma regla, mismo mínimo, resultado opuesto.
 */

import { ChevronDown, ChevronRight } from "lucide-react";
import { formatoNumero } from "@/lib/formato";
import type { LineaDetalleSugerencia } from "@/lib/types";

interface Props {
  abierta: boolean;
  onToggle: () => void;
  esInstock: boolean;
  ejemplos: {
    aporta: LineaDetalleSugerencia | null;
    noAporta: LineaDetalleSugerencia | null;
  };
}

export function ComoSeCalcula({ abierta, onToggle, esInstock, ejemplos }: Props) {
  return (
    <div className="rounded-md border border-slate-200 bg-white">
      <button
        onClick={onToggle}
        className="flex w-full items-center gap-1.5 px-4 py-2.5 text-left text-[13px] font-medium text-slate-600 transition-colors hover:text-brand"
      >
        {abierta ? <ChevronDown size={15} /> : <ChevronRight size={15} />}
        {abierta ? "Ocultar" : "+ info"} · cómo se calcula la columna «Aporta esto»
      </button>

      {abierta && (
        <div className="space-y-4 border-t border-slate-100 px-4 py-4 text-[13px] leading-relaxed text-slate-600">
          {esInstock ? <ExplicacionMinimo ejemplos={ejemplos} /> : <ExplicacionAditiva ejemplos={ejemplos} />}
          <NotaStockSeguridad esInstock={esInstock} />
        </div>
      )}
    </div>
  );
}

// --------------------------------------------------------------------------- //
// InStock y los objetivos: completan hasta un nivel, así que pueden aportar 0.
// --------------------------------------------------------------------------- //
function ExplicacionMinimo({ ejemplos }: { ejemplos: Props["ejemplos"] }) {
  const { aporta, noAporta } = ejemplos;
  return (
    <>
      <p>
        Esta regla no suma unidades sueltas: <b>completa hasta un mínimo</b>. Primero
        suma todo lo que ya está cubierto —lo que hay en bodega, lo que viene en
        tránsito y lo que el modelo ya está pidiendo por su cuenta— y solo pide la
        diferencia que falte. Si no descontara lo último, se compraría dos veces para
        el mismo nivel.
      </p>

      {(aporta || noAporta) && (
        <div className="grid gap-3 sm:grid-cols-2">
          {noAporta && <CasoMinimo linea={noAporta} />}
          {aporta && <CasoMinimo linea={aporta} />}
        </div>
      )}

      <p>
        Por eso una línea puede estar activa y aportar cero:{" "}
        <b>no es que la regla falle, es que ese repuesto ya está cubierto</b>. Si mañana
        se vende ese stock, la misma línea vuelve a pedir sola.
      </p>
    </>
  );
}

/** Una línea explicada: qué hay, cuánto falta y qué decidió la regla. */
function CasoMinimo({ linea }: { linea: LineaDetalleSugerencia }) {
  const minimo = linea.minimo ?? 0;
  const stock = linea.stock_actual ?? 0;
  const transito = linea.stock_transito ?? 0;
  const modelo = linea.sugerido_modelo ?? 0;
  const cubierto = stock + transito + modelo;
  const pide = linea.aporta > 0;

  return (
    <div
      className={`rounded-md border p-3 ${
        pide ? "border-emerald-200 bg-emerald-50/40" : "border-slate-200 bg-slate-50/60"
      }`}
    >
      <p className="text-[12.5px] font-semibold text-slate-900">
        {linea.producto}
        <span className="font-normal text-slate-500">
          {" "}
          · {linea.nombre_sucursal ?? linea.sucursal_id}
        </span>
      </p>

      <table className="mt-2 w-full text-[12.5px]">
        <tbody>
          <Fila etiqueta="Nunca puede bajar de" valor={minimo} destacado />
          <tr>
            <td colSpan={2} className="pt-1.5">
              <span className="text-[11.5px] uppercase tracking-wide text-slate-400">
                Lo que ya está cubierto
              </span>
            </td>
          </tr>
          <Fila etiqueta="En bodega" valor={stock} />
          <Fila etiqueta="En tránsito" valor={transito} />
          <Fila etiqueta="Ya lo pide el modelo" valor={modelo} />
          <Fila etiqueta="Total cubierto" valor={cubierto} borde />
        </tbody>
      </table>

      <p
        className={`mt-2 border-t pt-2 text-[12.5px] ${
          pide ? "border-emerald-200 text-emerald-800" : "border-slate-200 text-slate-600"
        }`}
      >
        {pide ? (
          <>
            Cubierto <b>{formatoNumero(cubierto)}</b>, y el mínimo es{" "}
            <b>{formatoNumero(minimo)}</b>. {linea.aporta === 1 ? "Falta" : "Faltan"}{" "}
            <b>{formatoNumero(linea.aporta)}</b>, así que{" "}
            <b>pide {formatoNumero(linea.aporta)}</b>.
          </>
        ) : (
          <>
            Cubierto <b>{formatoNumero(cubierto)}</b>, que ya alcanza el mínimo de{" "}
            <b>{formatoNumero(minimo)}</b>. <b>No pide nada.</b>
          </>
        )}
      </p>
    </div>
  );
}

// --------------------------------------------------------------------------- //
// Manuales en unidades directas: aditivas, siempre suman.
// --------------------------------------------------------------------------- //
function ExplicacionAditiva({ ejemplos }: { ejemplos: Props["ejemplos"] }) {
  const linea = ejemplos.aporta ?? ejemplos.noAporta;
  return (
    <>
      <p>
        Una sugerencia manual en unidades directas <b>es aditiva</b>: sus unidades se
        suman al sugerido del modelo siempre, sin descontar nada. Por eso acá «aporta»
        es simplemente lo que se pidió.
      </p>
      <p>
        Lo que sí conviene mirar es la columna <b>«Pide el modelo»</b>. Si el modelo ya
        está pidiendo tanto o más por su cuenta, la sugerencia quedó{" "}
        <b>redundante</b>: sigue sumando a la compra, pero probablemente ya no hace
        falta. Esas líneas van marcadas debajo del código.
      </p>

      {linea && (
        <div className="max-w-sm rounded-md border border-slate-200 bg-slate-50/60 p-3">
          <p className="text-[12.5px] font-semibold text-slate-900">
            {linea.producto}
            <span className="font-normal text-slate-500">
              {" "}
              · {linea.nombre_sucursal ?? linea.sucursal_id}
            </span>
          </p>
          <table className="mt-2 w-full text-[12.5px]">
            <tbody>
              <Fila
                etiqueta="El modelo pide por su cuenta"
                valor={linea.sugerido_modelo ?? 0}
              />
              <Fila etiqueta="Esta sugerencia agrega" valor={linea.aporta} destacado />
              <Fila etiqueta="Total a comprar" valor={linea.total_con_sugerencia} borde />
            </tbody>
          </table>
        </div>
      )}

      <p>
        Las que se pidieron como <b>«mantener N unidades en stock»</b> sí descuentan lo
        que hay: esa brecha se calculó al crearlas, contra el stock, el tránsito y lo
        que el modelo pedía en ese momento.
      </p>
    </>
  );
}

function Fila({
  etiqueta,
  valor,
  destacado,
  borde,
}: {
  etiqueta: string;
  valor: number;
  destacado?: boolean;
  borde?: boolean;
}) {
  return (
    <tr className={borde ? "border-t border-slate-200" : ""}>
      <td className={`py-0.5 pr-3 ${destacado ? "font-medium text-slate-900" : "text-slate-600"}`}>
        {etiqueta}
      </td>
      <td
        className={`py-0.5 text-right tabular-nums ${
          destacado || borde ? "font-semibold text-slate-900" : "text-slate-700"
        }`}
      >
        {formatoNumero(valor)}
      </td>
    </tr>
  );
}

/**
 * El stock de seguridad SÍ está en la resta, pero un nivel más abajo. Verificado
 * contra `motor/safety_stock.py` y `motor/sugerido.py`.
 */
function NotaStockSeguridad({ esInstock }: { esInstock: boolean }) {
  return (
    <div className="space-y-2 border-t border-slate-100 pt-3 text-[12.5px] text-slate-500">
      <p>
        <b>¿Y el stock de seguridad?</b> No aparece en la tabla, pero está adentro
        igual: viaja dentro de «lo que el modelo ya pide». El modelo arma su objetivo
        como{" "}
        <span className="font-mono text-[11.5px]">
          demanda diaria × (ciclo + lead time) + stock de seguridad
        </span>{" "}
        y le descuenta el stock y el tránsito. O sea que restar lo que ya tienes no es
        algo de esta regla: es como funciona el modelo entero, en todas sus capas.
      </p>
      <p>
        El stock de seguridad se calcula aparte, con la variabilidad de la venta (
        <span className="font-mono text-[11.5px]">Z × σ × √((lead time + ciclo)/22)</span>
        , con Z según la clase ABC) y responde otra pregunta: cuánto colchón hace falta
        para no quebrar un repuesto <b>que sí se vende</b>.{" "}
        {esInstock ? "La regla InStock" : "Una sugerencia manual"} existe justamente para
        lo otro: lo que el modelo no pediría solo.
      </p>
    </div>
  );
}
