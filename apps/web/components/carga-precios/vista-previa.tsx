"use client";

// "Qué cambia": la vista previa de una carga de precios por Excel, antes de guardar. Se saco
// de carga-precios-excel.tsx sin cambiar nada de lo que hace. Aqui solo se dibuja la lectura
// que ya hizo el servidor: el estado (archivo, fase, casillas de confirmacion) y los efectos
// de foco siguen en el dialogo, que se entera por los callbacks.
import { Loader2, Upload } from "lucide-react";
import type { Ref } from "react";
import { Button } from "@/components/ui/button";
import { formatoNumero } from "@/lib/formato";
import type { CargaPreciosError, CargaPreciosVistaPrevia } from "@/lib/types";

/** Como se llama cada decision que una carga puede quitar. */
const DECISION: Record<string, string> = {
  tipo: "tipo a mano",
  procedencia: "procedencia a mano",
  factor: "factor propio",
  precio_fijo: "precio fijo",
  obs: "observación",
  congelar: "congelado",
  no_producto: "«no es producto»",
};

/** Las decisiones que una carga puede PONER en bloque, en singular y plural. */
const FIJAN: Record<string, [string, string]> = {
  precio_fijo: ["precio fijo", "precios fijos"],
  factor: ["factor propio", "factores propios"],
};

const pesos = (n: number | null) => (n == null ? "sin precio" : `$${formatoNumero(n)}`);

/** "1 producto", "2 productos". */
export const cantidad = (n: number, uno: string, varios: string) => `${formatoNumero(n)} ${n === 1 ? uno : varios}`;

function textoFijan(clave: string, n: number): string {
  const [uno, varios] = FIJAN[clave] ?? [clave, clave];
  return cantidad(n, uno, varios);
}

/** "1 sube, 0 bajan, ...": el verbo concuerda con la cantidad. */
function efectoTexto(e: CargaPreciosVistaPrevia["efecto"]): string {
  const v = (n: number, uno: string, varios: string) => (n === 1 ? uno : varios);
  return (
    `Precios: ${formatoNumero(e.suben)} ${v(e.suben, "sube", "suben")}, ` +
    `${formatoNumero(e.bajan)} ${v(e.bajan, "baja", "bajan")}, ` +
    `${formatoNumero(e.con_precio_nuevo)} ${v(e.con_precio_nuevo, "pasa", "pasan")} de sin precio a tener uno y ` +
    `${formatoNumero(e.sin_cambio_de_precio)} no ${v(e.sin_cambio_de_precio, "cambia", "cambian")} de precio.`
  );
}

function ListaErrores({ items, total, tono }: { items: CargaPreciosError[]; total: number; tono: "rojo" | "ambar" }) {
  const clase = tono === "rojo" ? "text-rose-800" : "text-amber-800";
  return (
    <ul className={`mt-1 max-h-40 space-y-0.5 overflow-y-auto text-[12px] ${clase}`}>
      {items.map((e, i) => (
        <li key={`${e.fila}-${i}`}>
          <span className="font-medium">Fila {e.fila}</span> · <span className="font-mono">{e.producto}</span>: {e.mensaje}
        </li>
      ))}
      {total > items.length && <li>… y {formatoNumero(total - items.length)} más.</li>}
    </ul>
  );
}

function ListaCodigos({ codigos, total }: { codigos: string[]; total: number }) {
  return (
    <p className="mt-1 max-h-24 overflow-y-auto font-mono text-[12px]">
      {codigos.join(", ")}
      {total > codigos.length && ` … y ${formatoNumero(total - codigos.length)} más.`}
    </p>
  );
}

/**
 * Lo que se deduce de la lectura para decidir que se avisa y si se puede cargar. Lo usan
 * la vista previa (que avisos mostrar) y el dialogo (cuando se habilita "Cargar"): estando
 * en un solo lugar, la casilla de confirmacion y el boton no pueden quedar en desacuerdo.
 */
export function derivadosDePrevia(previa: CargaPreciosVistaPrevia | null) {
  const hayErrores = (previa?.errores_total ?? 0) > 0;
  const quitan = previa?.quitan_total ?? 0;
  const pideConfirmar = previa !== null && quitan >= previa.umbral_quitas;
  const fijan = previa?.fijan_total ?? 0;
  const pideConfirmarMasiva = previa !== null && fijan > previa.umbral_masiva;
  const omitidos = previa
    ? previa.conflictos_total + previa.desconocidos_total + previa.sin_referencia_total
    : 0;
  return { hayErrores, quitan, pideConfirmar, fijan, pideConfirmarMasiva, omitidos };
}

interface Props {
  previa: CargaPreciosVistaPrevia;
  /** El dialogo le pasa el foco a este panel cuando termina de leer el archivo. */
  panelRef: Ref<HTMLElement>;
  /** Mientras se guarda, nada se puede tocar. */
  cargando: boolean;
  puedeCargar: boolean;
  confirmaQuitas: boolean;
  confirmaMasiva: boolean;
  onConfirmaQuitas: (marcada: boolean) => void;
  onConfirmaMasiva: (marcada: boolean) => void;
  /** Vuelve a "Elegir archivo" y lleva el foco ahi (lo hace el dialogo). */
  onDescartar: () => void;
  onCargar: () => void;
}

export function VistaPrevia({
  previa, panelRef, cargando, puedeCargar, confirmaQuitas, confirmaMasiva,
  onConfirmaQuitas, onConfirmaMasiva, onDescartar, onCargar,
}: Props) {
  const { hayErrores, quitan, pideConfirmar, fijan, pideConfirmarMasiva, omitidos } = derivadosDePrevia(previa);
  return (
    <section ref={panelRef} tabIndex={-1} className="space-y-3 outline-none" aria-label="Qué cambia">
      <h3 className="text-[13px] font-semibold text-slate-900">Qué cambia</h3>
      <div className="flex flex-wrap gap-2 text-[12px]">
        <span className="rounded-md bg-slate-100 px-2 py-1">{cantidad(previa.filas, "fila leída", "filas leídas")}</span>
        <span className="rounded-md bg-slate-100 px-2 py-1">{formatoNumero(previa.sin_cambios)} sin cambios</span>
        {hayErrores ? (
          <span className="rounded-md bg-slate-100 px-2 py-1">
            {cantidad(previa.a_cambiar, "producto con cambios válido", "productos con cambios válidos")}
          </span>
        ) : (
          <span className="rounded-md bg-brand-50 px-2 py-1 font-medium text-brand">
            {previa.a_cambiar === 1 ? "1 producto se cargará" : `${formatoNumero(previa.a_cambiar)} productos se cargarán`}
          </span>
        )}
        {omitidos > 0 && (
          <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-800">
            {omitidos === 1 ? "1 se omite" : `${formatoNumero(omitidos)} se omiten`}
          </span>
        )}
      </div>

      {hayErrores && (
        <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-rose-800">
          <p className="font-medium">
            {previa.errores_total === 1
              ? "El archivo tiene 1 error. No se carga nada hasta corregirlo: arréglalo en Excel y vuelve a subirlo."
              : `El archivo tiene ${formatoNumero(previa.errores_total)} errores. No se carga nada hasta corregirlos: arréglalos en Excel y vuelve a subirlo.`}
          </p>
          <ListaErrores items={previa.errores} total={previa.errores_total} tono="rojo" />
        </div>
      )}

      {quitan > 0 && !hayErrores && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
          <p className="font-medium">
            Esta carga quita {cantidad(quitan, "decisión", "decisiones")}:{" "}
            {Object.entries(previa.quitan).map(([k, n]) => `${formatoNumero(n)} ${DECISION[k] ?? k}`).join(", ")}.
          </p>
          {previa.quitan_ejemplos.length > 0 && (
            <p className="mt-0.5 text-[12px]">
              Por ejemplo:{" "}
              {previa.quitan_ejemplos.slice(0, 5).map((e) => `${e.producto} (${e.campo.toLowerCase()})`).join(", ")}
              {quitan > Math.min(5, previa.quitan_ejemplos.length) && "…"}
            </p>
          )}
          <p className="mt-0.5 text-[12px]">
            Una celda vacía quita la decisión del producto. Si no dejaste esas celdas vacías a propósito, puede
            que el Excel tenga celdas con error (#N/D, #REF!), que se leen como vacías.
          </p>
          {pideConfirmar && (
            <label className="mt-2 flex items-start gap-2 text-[13px]">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={confirmaQuitas}
                disabled={cargando}
                onChange={(e) => onConfirmaQuitas(e.target.checked)}
              />
              <span>Entiendo que se quitan {formatoNumero(quitan)} decisiones y quiero cargarlas.</span>
            </label>
          )}
        </div>
      )}

      {pideConfirmarMasiva && !hayErrores && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
          <p className="font-medium">
            Esta carga deja {formatoNumero(fijan)} precios fijos o factores propios nuevos:{" "}
            {Object.entries(previa.fijan).map(([k, n]) => textoFijan(k, n)).join(", ")}.
          </p>
          <p className="mt-0.5 text-[12px]">
            Son muchos para una edición a mano. Si ordenaste una sola columna del Excel (por ejemplo Precio final
            o Factor), cada valor quedó en la fila de otro producto: descarga el archivo de nuevo y edítalo sin
            ordenar columnas sueltas.
          </p>
          <label className="mt-2 flex items-start gap-2 text-[13px]">
            <input
              type="checkbox"
              className="mt-0.5"
              checked={confirmaMasiva}
              disabled={cargando}
              onChange={(e) => onConfirmaMasiva(e.target.checked)}
            />
            <span>Entiendo que se fijan {formatoNumero(fijan)} valores y quiero cargarlos.</span>
          </label>
        </div>
      )}

      {previa.factor_redondeado_total > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
          <p className="font-medium">
            {previa.factor_redondeado_total === 1
              ? "1 producto trae el Factor redondeado (por ejemplo 1,14 en vez de 1,1429) y se toma como sin cambios."
              : `${formatoNumero(previa.factor_redondeado_total)} productos traen el Factor redondeado (por ejemplo 1,14 en vez de 1,1429) y se toman como sin cambios.`}
          </p>
          <ListaCodigos codigos={previa.factor_redondeado} total={previa.factor_redondeado_total} />
          <p className="mt-1 text-[12px]">
            Excel lo hace al mostrar menos decimales. Si querías justo ese valor, no se cargará: cámbialo en la ficha del producto.
          </p>
        </div>
      )}

      {previa.conflictos_total > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
          <p className="font-medium">
            {previa.conflictos_total === 1
              ? "1 producto no se cargará: cambió en la plataforma"
              : `${formatoNumero(previa.conflictos_total)} productos no se cargarán: cambiaron en la plataforma`}{" "}
            después de que bajaste el archivo.
          </p>
          <ListaErrores items={previa.conflictos} total={previa.conflictos_total} tono="ambar" />
          <p className="mt-1 text-[12px]">Descarga el archivo de nuevo y repite el cambio en esos productos.</p>
        </div>
      )}

      {previa.desconocidos_total > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
          <p className="font-medium">
            {previa.desconocidos_total === 1
              ? "1 código no está en la lista y se ignora."
              : `${formatoNumero(previa.desconocidos_total)} códigos no están en la lista y se ignoran.`}
          </p>
          <ListaCodigos codigos={previa.desconocidos} total={previa.desconocidos_total} />
        </div>
      )}

      {previa.sin_referencia_total > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
          <p className="font-medium">
            {previa.sin_referencia_total === 1
              ? "1 fila no trae Referencia y se ignora (¿fila agregada a mano?)."
              : `${formatoNumero(previa.sin_referencia_total)} filas no traen Referencia y se ignoran (¿filas agregadas a mano?).`}
          </p>
          <ListaCodigos codigos={previa.sin_referencia} total={previa.sin_referencia_total} />
        </div>
      )}

      {previa.a_cambiar > 0 && !hayErrores && (
        <>
          <p className="text-slate-700">{efectoTexto(previa.efecto)}</p>
          <div className="max-h-72 overflow-auto rounded-md border border-slate-200">
            <table className="w-full text-[12px]">
              <thead className="sticky top-0 bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
                <tr>
                  <th className="px-3 py-1.5">Producto</th>
                  <th className="px-3 py-1.5">Qué cambia</th>
                  <th className="px-3 py-1.5 text-right">Precio</th>
                </tr>
              </thead>
              <tbody>
                {previa.cambios.map((c) => (
                  <tr key={c.producto} className="border-t border-slate-100 align-top">
                    <td className="px-3 py-1.5">
                      <span className="font-mono">{c.producto}</span>
                      {c.glosa && <span className="block text-slate-500">{c.glosa}</span>}
                    </td>
                    <td className="px-3 py-1.5">
                      {c.campos.map((f) => (
                        <span key={f.campo} className="block">
                          <span className="font-medium">{f.campo}:</span> {f.antes} → {f.despues}
                        </span>
                      ))}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">
                      {c.precio_antes === c.precio_despues ? "no cambia" : `${pesos(c.precio_antes)} → ${pesos(c.precio_despues)}`}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
            {previa.cambios_total > previa.cambios.length && (
              <p className="border-t border-slate-100 px-3 py-1.5 text-[12px] text-slate-500">
                … y {cantidad(previa.cambios_total - previa.cambios.length, "producto más", "productos más")} con cambios.
              </p>
            )}
          </div>
        </>
      )}

      {previa.a_cambiar === 0 && !hayErrores && (
        <p className="text-slate-600">
          {omitidos > 0
            ? "No hay nada que cargar: los cambios del archivo se omiten (detalle arriba)."
            : "El archivo no trae ningún cambio que cargar."}
        </p>
      )}

      <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onDescartar()}
          disabled={cargando}
        >
          Descartar
        </Button>
        <Button size="sm" onClick={() => onCargar()} disabled={!puedeCargar}>
          {cargando ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
          {cargando ? "Cargando…" : `Cargar ${cantidad(previa.a_cambiar, "producto", "productos")}`}
        </Button>
      </div>
      {cargando && (
        <p role="status" className="text-right text-[12px] text-slate-500">
          Guardando y recalculando solo los productos editados. No cierres esta ventana.
        </p>
      )}
    </section>
  );
}
