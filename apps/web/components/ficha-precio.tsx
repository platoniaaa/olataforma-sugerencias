"use client";

// La ficha de un producto de la lista de precios: como se llego al precio, la
// decision de una persona sobre el y su historia. Vivia dentro de
// app/precios/page.tsx; esta aparte porque Next no admite exports extra en una
// page.tsx y porque asi se puede probar sin montar la lista entera.
import { useCallback, useEffect, useState } from "react";
import { Loader2, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { api } from "@/lib/api-client";
import { claseEstado, explicacionPrecio } from "@/lib/columnas-precios";
import { factorDesdeMargen } from "@/lib/margen";
import { formatoCLP, formatoFecha, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { PrecioDetalle } from "@/lib/types";

export const PROCEDENCIAS = ["Nacional", "Importado"];

/** Ficha del producto: como se llego al precio, la decision humana, y su historia. */
export function ModalProducto({ producto, puedeEditar, tipos, onCerrar, onGuardado }: {
  producto: string; puedeEditar: boolean; tipos: string[];
  onCerrar: () => void; onGuardado: () => Promise<void>;
}) {
  const [d, setD] = useState<PrecioDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [precioFijo, setPrecioFijo] = useState<string>("");
  const [margenFijo, setMargenFijo] = useState<string>("");
  const [congelar, setCongelar] = useState(false);
  const [tipoManual, setTipoManual] = useState("");
  const [procManual, setProcManual] = useState("");
  const [noProducto, setNoProducto] = useState(false);
  const [obs, setObs] = useState("");

  const cargar = useCallback(async () => {
    try {
      const det = await api.precioDetalle(producto);
      setD(det);
      setPrecioFijo(det.precio_fijo === null ? "" : String(det.precio_fijo));
      setMargenFijo(det.margen_fijo === null ? "" : String(det.margen_fijo));
      setCongelar(det.congelar);
      setTipoManual(det.tipo_manual ?? "");
      setProcManual(det.procedencia_manual ?? "");
      setNoProducto(det.no_producto);
      setObs(det.obs ?? "");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar el producto.");
    }
  }, [producto]);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  async function guardar() {
    if (!d) return;
    setGuardando(true);
    setError(null);
    try {
      await api.guardarPrecioOverride(producto, {
        precio_fijo: precioFijo.trim() === "" ? null : Number(precioFijo.replace(",", ".")),
        margen_fijo: margenFijo.trim() === "" ? null : Number(margenFijo.replace(",", ".")),
        congelar,
        tipo_manual: tipoManual || null,
        procedencia_manual: procManual || null,
        no_producto: noProducto,
        obs: obs || null,
      });
      await cargar();
      await onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setGuardando(false);
    }
  }

  async function sacarDeLaLista() {
    // Se avisa lo que NO hace: nadie espera que "eliminar" deje el producto
    // intacto en el ERP, y esa es justo la parte que confunde.
    if (!confirm(
      `¿Sacar ${producto} de la lista de precios?

Deja de tener precio calculado y no va a salir en el envío al ERP. NO lo da de baja en el ERP.

Si tiene precio fijo o congelado, esa decisión se conserva por si el producto vuelve.`
    )) return;
    setGuardando(true);
    setError(null);
    try {
      await api.eliminarPrecioProducto(producto);
      await onGuardado();
      onCerrar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo sacar de la lista.");
      setGuardando(false);
    }
  }

  async function volverALaRegla() {
    if (!confirm(`¿Quitar toda decisión manual de ${producto} y volver a la regla?`)) return;
    setGuardando(true);
    setError(null);
    try {
      await api.quitarPrecioOverride(producto);
      await cargar();
      await onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo volver a la regla.");
    } finally {
      setGuardando(false);
    }
  }

  const tieneOverride = d && (d.precio_fijo !== null || d.margen_fijo !== null || d.congelar || d.tipo_manual || d.procedencia_manual || d.no_producto || d.obs);
  const campo = "h-9 w-full rounded-md border border-ink-200 px-2 text-sm outline-none focus:border-brand disabled:bg-ink-50";

  return (
    <Dialog open onClose={onCerrar} title={producto} description={d?.glosa ?? undefined} className="max-w-3xl">
      {!d ? (
        <p className="flex items-center gap-2 text-sm text-ink-500"><Loader2 className="h-4 w-4 animate-spin" /> Cargando…</p>
      ) : (
        <div className="space-y-4">
          {/* El resultado primero. Antes el precio final era una fila más entre
              once, del mismo tamaño que "Rubro", y la diferencia contra el ERP
              -que es lo que hace que alguien abra esta ficha- había que
              calcularla mentalmente restando dos filas separadas. */}
          <div className="flex flex-wrap items-end justify-between gap-4 rounded-lg border border-ink-100 bg-ink-50/60 px-4 py-3"
               data-tour="ficha-precio">
            <div>
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">Precio final</p>
              <p className="flex items-baseline gap-2">
                <span className="font-mono text-3xl font-semibold tabular-nums tracking-tight text-ink-900">
                  {formatoCLP(d.precio_final)}
                </span>
                <span className={`rounded px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${claseEstado(d.estado)}`}>
                  {d.estado}
                </span>
              </p>
              <p className="mt-0.5 font-mono text-[12px] text-ink-500">{explicacionPrecio(d)}</p>
            </div>
            <div className="text-right">
              <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">Precio en el ERP hoy</p>
              <p className="font-mono text-xl tabular-nums text-ink-700">{formatoCLP(d.precio_erp)}</p>
              {d.desviacion_pct !== null && d.desviacion_pct !== undefined && (
                <p className={`text-[12px] font-semibold ${Math.abs(d.desviacion_pct) >= 20 ? "text-accent-700" : "text-ink-500"}`}>
                  {d.desviacion_pct > 0 ? "+" : ""}{formatoNumero(d.desviacion_pct, 1)}% vs. el nuevo
                </p>
              )}
            </div>
          </div>

          <div className="grid gap-5 md:grid-cols-2">
            <section className="space-y-2 text-sm" data-tour="ficha-origen">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">De dónde sale</h3>
              {/* El origen va como etiqueta y no entre paréntesis: dice de un
                  vistazo qué está decidido a mano y qué lo pone la regla. */}
              <FilaOrigen k="Tipo" v={d.tipo ?? "—"} origen={d.tipo_origen} />
              <FilaOrigen k="Procedencia" v={d.procedencia_final ?? "—"} origen={d.procedencia_origen} />
              <Fila k="Rubro" v={d.rubro ?? "—"} />
              <FilaOrigen k="Factor" v={d.factor ? formatoNumero(d.factor, 2) : "—"}
                          origen={d.margen_fijo !== null ? `margen ${formatoNumero(d.margen_fijo, 1)} %` : null} />
              <Fila k="Costo" v={formatoCLP(d.costo)} />
              {d.precio_sugerido !== null && <Fila k="Precio proveedor" v={formatoCLP(d.precio_sugerido)} />}

              <div className="!mt-4 space-y-2 border-t border-ink-100 pt-3">
                <Fila k="Stock / en tránsito" v={`${formatoNumero(d.stock ?? 0)} / ${formatoNumero(d.stock_transito ?? 0)}`} />
                {(d.ult_recep_importado || d.ult_pe_nacional) && (
                  <Fila k="Última compra"
                        v={`imp. ${formatoFecha(d.ult_recep_importado)} · nac. ${formatoFecha(d.ult_pe_nacional)}`} />
                )}
                <Fila k="Última venta" v={d.ultima_venta ? formatoFecha(d.ultima_venta) : "sin venta registrada"} />
              </div>

              {(d.envios ?? []).length > 0 && (
                <p className="!mt-3 text-[12px] text-ink-500">
                  Último envío al ERP: {formatoCLP((d.envios ?? [])[0].precio)} el {formatoFecha((d.envios ?? [])[0].enviado_en)}
                  {(d.envios ?? [])[0].enviado_por ? ` por ${(d.envios ?? [])[0].enviado_por}` : ""}
                </p>
              )}
            </section>

            <section className="space-y-4" data-tour="ficha-decision">
              <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">Decisión sobre este precio</h3>
              {!puedeEditar && (
                <p className="rounded-md bg-ink-50 px-3 py-2 text-[12px] text-ink-500">
                  Tu usuario puede ver la lista pero no editarla.
                </p>
              )}

              {/* Tres grupos, no seis controles sueltos: fijar el precio,
                  corregir la clasificación, sacarlo del cálculo. */}
              <div className="space-y-2">
                <p className="text-[12px] font-semibold text-ink-700">Fijar el precio</p>
                <label className="block text-sm">
                  <input className={campo} type="number" min="0" step="1" disabled={!puedeEditar}
                         value={precioFijo} onChange={(e) => setPrecioFijo(e.target.value)}
                         placeholder="Precio fijo — vacío sigue la regla" />
                  <span className="text-[11px] text-ink-400">Gana a todo, incluso sin stock.</span>
                </label>
                {/* Margen fijo: a diferencia del precio fijo, sigue al costo. Se
                    escribe como lo mira contabilidad (% sobre la venta) y se ve
                    al tiro a qué factor y precio equivale con el costo de hoy. */}
                <label className="block text-sm">
                  <input className={campo} type="number" min="0" max="99.9" step="0.1" disabled={!puedeEditar}
                         value={margenFijo} onChange={(e) => setMargenFijo(e.target.value)}
                         placeholder="Margen fijo en % sobre la venta — vacío sigue la regla" />
                  <span className="text-[11px] text-ink-400">{explicacionMargen(margenFijo, d.costo)}</span>
                </label>
                <label className="flex items-start gap-2 text-sm text-ink-700">
                  <input type="checkbox" className="mt-0.5 accent-brand" disabled={!puedeEditar}
                         checked={congelar} onChange={(e) => setCongelar(e.target.checked)} />
                  <span>
                    Congelar el precio actual
                    {d.congelar && d.congelado_precio !== null && (
                      <span className="block text-[11px] text-ink-400">
                        Congelado en {formatoCLP(d.congelado_precio)}{d.editado_en ? `, ${formatoFecha(d.editado_en)}` : ""}
                      </span>
                    )}
                  </span>
                </label>
              </div>

              <div className="space-y-2 border-t border-ink-100 pt-3">
                <p className="text-[12px] font-semibold text-ink-700">Corregir la clasificación</p>
                <div className="grid grid-cols-2 gap-2">
                  <label className="block text-sm">
                    <span className="text-[12px] text-ink-500">Tipo</span>
                    <select className={campo} disabled={!puedeEditar} value={tipoManual} onChange={(e) => setTipoManual(e.target.value)}>
                      <option value="">(según regla)</option>
                      {tipos.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </label>
                  <label className="block text-sm">
                    <span className="text-[12px] text-ink-500">Procedencia</span>
                    <select className={campo} disabled={!puedeEditar} value={procManual} onChange={(e) => setProcManual(e.target.value)}>
                      <option value="">(según regla)</option>
                      {PROCEDENCIAS.map((p) => <option key={p} value={p}>{p}</option>)}
                    </select>
                  </label>
                </div>
                <p className="text-[11px] text-ink-400">
                  Con «(según regla)» la procedencia sigue a la última compra sola.
                </p>
              </div>

              <div className="space-y-2 border-t border-ink-100 pt-3">
                <label className="flex items-start gap-2 text-sm text-ink-700">
                  <input type="checkbox" className="mt-0.5 accent-brand" disabled={!puedeEditar}
                         checked={noProducto} onChange={(e) => setNoProducto(e.target.checked)} />
                  <span>
                    No es un producto
                    <span className="block text-[11px] text-ink-400">Servicio, cargo o mano de obra: queda sin precio.</span>
                  </span>
                </label>
                <label className="block text-sm">
                  <span className="text-[12px] text-ink-500">Observación</span>
                  <textarea className={`${campo} h-14 py-1`} disabled={!puedeEditar} maxLength={500}
                            value={obs} onChange={(e) => setObs(e.target.value)}
                            placeholder="Por qué este precio no sigue la regla" />
                </label>
              </div>

              {d.editado_por && (
                <p className="text-[11px] text-ink-400">
                  Última edición: {d.editado_por}{d.editado_en ? ` · ${formatoFechaHora(d.editado_en)}` : ""}
                </p>
              )}
              {error && <p className="text-sm text-rose-700">{error}</p>}
            </section>
          </div>

          {/* El historial es consulta, no la razón por la que se abre la ficha:
              va plegado y con el número afuera, para que no compita con el
              precio. */}
          {(d.cambios ?? []).length > 0 && (
            <details className="rounded-lg border border-ink-100 px-3 py-2">
              <summary className="cursor-pointer text-[12px] font-semibold text-ink-600">
                Cambios detectados ({(d.cambios ?? []).length})
                {(d.cambios ?? []).some((c) => !c.visto) && (
                  <span className="ml-2 rounded bg-amber-100 px-1.5 text-[10px] font-semibold text-amber-800">sin revisar</span>
                )}
              </summary>
              <ul className="mt-2 max-h-40 space-y-1 overflow-auto text-[12px]">
                {(d.cambios ?? []).map((c, i) => (
                  <li key={i} className={c.visto ? "text-ink-400" : "text-ink-700"}>
                    {formatoFecha(c.detectado_en)} · <b>{c.campo}</b>: {c.antes ?? "—"} → {c.despues ?? "—"}
                  </li>
                ))}
              </ul>
            </details>
          )}

          {puedeEditar && (
            <div className="flex flex-wrap items-center justify-between gap-2 border-t border-ink-100 pt-3">
              <div className="flex gap-2">
                {tieneOverride && (
                  <Button variant="ghost" size="sm" disabled={guardando} onClick={() => void volverALaRegla()}>
                    Volver a la regla
                  </Button>
                )}
                {/* Sacar de la lista es distinto de "volver a la regla": el
                    producto deja de existir acá y de salir en el envío al ERP.
                    Por eso pide confirmación y dice que NO lo da de baja en el
                    ERP, que es lo primero que alguien va a suponer. */}
                <Button variant="ghost" size="sm" disabled={guardando}
                        className="text-rose-700 hover:bg-rose-50"
                        onClick={() => void sacarDeLaLista()}>
                  <Trash2 size={14} /> Sacar de la lista
                </Button>
              </div>
              <div className="flex gap-2">
                <Button variant="outline" size="sm" onClick={onCerrar}>Cerrar</Button>
                <Button size="sm" disabled={guardando} onClick={() => void guardar()}>
                  {guardando && <Loader2 size={14} className="animate-spin" />} Guardar
                </Button>
              </div>
            </div>
          )}
        </div>
      )}
    </Dialog>
  );
}

/** Lo que se ve bajo el campo de margen mientras se escribe. */
export function explicacionMargen(texto: string, costo: number | null): string {
  if (texto.trim() === "") return "Sobre la venta. El precio sigue al costo; sin stock queda en $0.";
  const factor = factorDesdeMargen(Number(texto.replace(",", ".")));
  if (factor === null) return "El margen tiene que estar entre 0 y 100.";
  const precio = costo && costo > 0 ? ` → ${formatoCLP(Math.floor(costo * factor + 0.5))} con el costo de hoy` : "";
  return `Factor ${formatoNumero(factor, 2)}${precio}. Sin stock queda en $0.`;
}

/** Una fila con el valor y, al lado, de dónde salió. */
export function FilaOrigen({ k, v, origen }: { k: string; v: string; origen?: string | null }) {
  // "manual" y "margen" son lo único que conviene que salte a la vista: significa
  // que alguien decidió y que la regla no lo va a tocar.
  const esManual = origen === "manual" || (origen ?? "").startsWith("margen");
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-ink-500">{k}</span>
      <span className="flex items-baseline gap-1.5 text-right">
        <span className="text-ink-800">{v}</span>
        {origen && (
          <span className={`rounded px-1 py-px text-[10px] font-medium ${
            esManual ? "bg-brand-50 text-brand" : "bg-ink-100 text-ink-500"}`}>
            {origen}
          </span>
        )}
      </span>
    </div>
  );
}

export function Fila({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-ink-500">{k}</span>
      <span className="text-right tabular-nums text-ink-800">{v}</span>
    </div>
  );
}
