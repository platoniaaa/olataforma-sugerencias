"use client";

/**
 * Consumo mes a mes de un repuesto. UNA serie, no dos.
 *
 * La venta de la sucursal es un subconjunto de la nacional, asi que graficarlas
 * juntas en el mismo eje deja las barras de la sucursal invisibles cuando la
 * nacional la multiplica (que es lo normal). En vez de inventar un segundo eje
 * -que hace parecer correlaciones que no existen- se grafica UNA serie y la otra
 * queda como cifra al lado.
 *
 * Cual: la de la sucursal, que es con la que se decide. Si la sucursal no vendio
 * NADA en 12 meses -el caso mas comun en un requerimiento- doce barras en cero no
 * dicen nada, asi que ahi el grafico pasa a la venta nacional y el subtitulo lo
 * dice. "No se vende aca pero si en la empresa" es informacion; doce ceros no.
 */

import { useState } from "react";
import { formatoNumero } from "@/lib/formato";

/** "202601" -> "ene 26". */
export function mesCorto(periodo: string): string {
  const MESES = ["ene", "feb", "mar", "abr", "may", "jun",
                 "jul", "ago", "sep", "oct", "nov", "dic"];
  const m = Number(periodo.slice(4, 6));
  return `${MESES[m - 1] ?? "?"} ${periodo.slice(2, 4)}`;
}

// Azul Curifor un paso mas claro que el de marca: el de marca (#1e40af) queda
// fuera de la banda de luminosidad para una barra de datos. Validado en claro y
// oscuro contra la superficie.
const SERIE = "#2563eb";

/** Barra con la punta redondeada y la base cuadrada contra el eje. */
function barra(x: number, y: number, w: number, h: number): string {
  const r = Math.min(4, h, w / 2);
  return (
    `M${x},${y + h} L${x},${y + r} Q${x},${y} ${x + r},${y} ` +
    `L${x + w - r},${y} Q${x + w},${y} ${x + w},${y + r} ` +
    `L${x + w},${y + h} Z`
  );
}

type Punto = { periodo: string; sucursal: number; nacional: number };

export function ConsumoChart({
  datos,
  nombreSucursal,
}: {
  datos: Punto[];
  nombreSucursal: string;
}) {
  const [verNumeros, setVerNumeros] = useState(false);

  if (datos.length === 0) {
    return (
      <p className="text-[12.5px] text-ink-400">
        No hay histórico de ventas cargado para dibujar el consumo.
      </p>
    );
  }

  const totalSuc = datos.reduce((s, d) => s + d.sucursal, 0);
  // Si la sucursal no movio nada, la serie util es la nacional.
  const usaNacional = totalSuc === 0;
  const valores = datos.map((d) => (usaNacional ? d.nacional : d.sucursal));
  const max = Math.max(...valores, 1);
  const iMax = valores.indexOf(Math.max(...valores));

  // Geometria: banda por mes, barra tope 24px, 2px de aire entre vecinas.
  const ALTO = 96;
  const BANDA = 34;
  const ANCHO_BARRA = Math.min(24, BANDA - 2);
  const ancho = datos.length * BANDA;

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <div>
          <p className="text-[12.5px] font-medium text-ink-700">
            Consumo mensual · {usaNacional ? "toda la empresa" : nombreSucursal}
          </p>
          {usaNacional && (
            <p className="text-[11.5px] text-amber-800">
              En {nombreSucursal} no se vendió ninguna unidad en 12 meses. Se
              muestra la venta nacional.
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={() => setVerNumeros((v) => !v)}
          className="text-[11.5px] text-ink-500 underline underline-offset-2 hover:text-accent-700"
        >
          {verNumeros ? "Ver gráfico" : "Ver números"}
        </button>
      </div>

      {verNumeros ? (
        <div className="mt-2 overflow-x-auto">
          <table className="text-[12px]">
            <tbody>
              <tr className="text-ink-500">
                {datos.map((d) => (
                  <th key={d.periodo} className="px-2 py-1 text-right font-normal">
                    {mesCorto(d.periodo)}
                  </th>
                ))}
              </tr>
              <tr className="tabular">
                {valores.map((v, i) => (
                  <td key={datos[i].periodo} className="px-2 py-1 text-right">
                    {formatoNumero(v)}
                  </td>
                ))}
              </tr>
            </tbody>
          </table>
        </div>
      ) : (
        <div className="mt-2 overflow-x-auto">
          <svg
            width={ancho}
            height={ALTO + 30}
            role="img"
            aria-label={`Consumo mensual de los últimos 12 meses. Máximo ${formatoNumero(
              max
            )} unidades.`}
            className="block"
          >
            <title>Consumo mensual, últimos 12 meses</title>
            {/* Linea base: hairline solida, un paso de la superficie. */}
            <line
              x1={0}
              y1={ALTO}
              x2={ancho}
              y2={ALTO}
              stroke="#e7e5e4"
              strokeWidth={1}
            />
            {valores.map((v, i) => {
              const h = v === 0 ? 0 : Math.max(2, (v / max) * (ALTO - 14));
              const x = i * BANDA + (BANDA - ANCHO_BARRA) / 2;
              return (
                <g key={datos[i].periodo}>
                  {/* Area de hover mas grande que la barra. */}
                  <rect
                    x={i * BANDA}
                    y={0}
                    width={BANDA}
                    height={ALTO}
                    fill="transparent"
                    className="hover:fill-ink-50"
                  >
                    <title>{`${mesCorto(datos[i].periodo)}: ${formatoNumero(v)} u`}</title>
                  </rect>
                  {/* Punta redondeada 4px, cuadrada contra la linea base. */}
                  {h > 0 && (
                    <path
                      d={barra(x, ALTO - h, ANCHO_BARRA, h)}
                      fill={SERIE}
                      pointerEvents="none"
                    />
                  )}
                  {/* Etiqueta directa SOLO en el maximo: el resto lo lleva el hover. */}
                  {i === iMax && v > 0 && (
                    <text
                      x={i * BANDA + BANDA / 2}
                      y={ALTO - h - 4}
                      textAnchor="middle"
                      className="fill-ink-600 tabular"
                      fontSize={10.5}
                    >
                      {formatoNumero(v)}
                    </text>
                  )}
                  <text
                    x={i * BANDA + BANDA / 2}
                    y={ALTO + 14}
                    textAnchor="middle"
                    className="fill-ink-400"
                    fontSize={10}
                  >
                    {mesCorto(datos[i].periodo)}
                  </text>
                </g>
              );
            })}
          </svg>
        </div>
      )}
    </div>
  );
}
