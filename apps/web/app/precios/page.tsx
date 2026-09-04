"use client";

// La lista de precios que se sube al ERP. Es la version viva del Excel: la
// tabla se recalcula sola con el stock, el costo y las compras que la
// plataforma ya recibe; lo que decide una persona (precio fijo, congelar,
// tipo o procedencia a mano) vive aparte y ningun recalculo lo pisa.
import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import {
  AlertCircle, Bell, Columns3, Download, Loader2, Plus, RefreshCw, Search, Sigma, Tag,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Card } from "@/components/ui/card";
import { Dialog } from "@/components/ui/dialog";
import { Input } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multiselect";
import { TablaPrecios } from "@/components/tabla-precios";
import { ConfigurarColumnasPrecios } from "@/components/configurar-columnas-precios";
import { api } from "@/lib/api-client";
import { getPuedePrecios } from "@/lib/auth";
import { KEYS_PRECIOS_DEFAULT, claseEstado } from "@/lib/columnas-precios";
import { formatoCLP, formatoFecha, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type {
  PrecioDetalle, PrecioFiltros, PrecioOpciones, PrecioResumen, PrecioRow,
} from "@/lib/types";

const LS_COLUMNAS = "precios_columnas_visibles";
const LIMITE = 2000;
const PROCEDENCIAS = ["Nacional", "Importado"];

export default function PreciosPage() {
  const [filtros, setFiltros] = useState<PrecioFiltros>({});
  const [rows, setRows] = useState<PrecioRow[]>([]);
  const [total, setTotal] = useState(0);
  const [opciones, setOpciones] = useState<PrecioOpciones>({ rubros: [], tipos: [], procedencias: [], estados: [] });
  const [resumen, setResumen] = useState<PrecioResumen | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [puedeEditar, setPuedeEditar] = useState(false);
  const [ocupado, setOcupado] = useState<string | null>(null);

  const [colsVisibles, setColsVisibles] = useState<string[]>(KEYS_PRECIOS_DEFAULT);
  const [modalCols, setModalCols] = useState(false);
  const [seleccion, setSeleccion] = useState<PrecioRow | null>(null);
  const [modalNuevo, setModalNuevo] = useState(false);

  useEffect(() => {
    setPuedeEditar(getPuedePrecios());
    const saved = localStorage.getItem(LS_COLUMNAS);
    if (saved) {
      try {
        const arr = JSON.parse(saved);
        if (Array.isArray(arr) && arr.length) setColsVisibles(arr);
      } catch {
        /* noop */
      }
    }
  }, []);

  useEffect(() => {
    localStorage.setItem(LS_COLUMNAS, JSON.stringify(colsVisibles));
  }, [colsVisibles]);

  const cargarAuxiliares = useCallback(async () => {
    const [o, r] = await Promise.all([api.preciosFiltros().catch(() => null), api.preciosResumen().catch(() => null)]);
    if (o) setOpciones(o);
    if (r) setResumen(r);
  }, []);

  useEffect(() => {
    void cargarAuxiliares();
  }, [cargarAuxiliares]);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const r = await api.precios(filtros, { limit: LIMITE, sort: "producto" });
      setRows(r.items);
      setTotal(r.total);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setCargando(false);
    }
  }, [filtros]);

  useEffect(() => {
    const t = setTimeout(cargar, 300);
    return () => clearTimeout(t);
  }, [cargar]);

  const set = (parcial: Partial<PrecioFiltros>) => setFiltros({ ...filtros, ...parcial });

  async function accion(nombre: string, fn: () => Promise<string>) {
    setOcupado(nombre);
    setError(null);
    setAviso(null);
    try {
      setAviso(await fn());
      await Promise.all([cargar(), cargarAuxiliares()]);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo completar la accion.");
    } finally {
      setOcupado(null);
    }
  }

  const hayFiltros = useMemo(
    () => Boolean(filtros.q || filtros.rubro?.length || filtros.tipo?.length || filtros.procedencia?.length
      || filtros.estado?.length || filtros.con_cambios || filtros.con_stock),
    [filtros]
  );

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
            <Tag size={20} className="text-brand" /> Lista de precios
          </h1>
          <p className="text-[13px] text-slate-500">
            Lo que se sube al ERP.{" "}
            {cargando ? "Cargando…" : (
              <>
                <b>{formatoNumero(total)}</b> productos
                {total > rows.length && ` (mostrando ${formatoNumero(rows.length)}; afina el filtro para ver el resto)`}
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Link href="/precios/politicas">
            <Button variant="outline" size="sm"><Sigma size={15} /> Política</Button>
          </Link>
          <Button variant="outline" size="sm" onClick={() => setModalCols(true)}>
            <Columns3 size={15} /> Columnas
          </Button>
          <Button
            variant="outline" size="sm" disabled={ocupado !== null}
            onClick={() => void accion("exportar", async () => {
              const n = await api.exportarPrecios({ soloDiferencias: false, formato: "erp" });
              return `Lista completa exportada: ${formatoNumero(n)} productos. Quedo registrado como envio.`;
            })}
          >
            <Download size={15} /> Exportar completa
          </Button>
          <Button
            size="sm" disabled={ocupado !== null}
            onClick={() => void accion("exportar", async () => {
              const n = await api.exportarPrecios({ soloDiferencias: true, formato: "erp" });
              return n
                ? `Exportadas ${formatoNumero(n)} diferencias. Quedo registrado como envio.`
                : "No hay diferencias desde el ultimo envio: no se genero archivo con filas.";
            })}
          >
            <Download size={15} /> Solo diferencias
            {resumen && resumen.pendientes_envio > 0 && (
              <span className="ml-1 rounded-full bg-white/20 px-1.5 text-[11px]">{formatoNumero(resumen.pendientes_envio)}</span>
            )}
          </Button>
        </div>
      </div>

      {resumen && (
        <div className="grid grid-cols-2 gap-2 md:grid-cols-5">
          <Kpi etiqueta="Productos" valor={formatoNumero(resumen.productos)} />
          <Kpi etiqueta="Con cambios sin revisar" valor={formatoNumero(resumen.con_cambios)}
               destacar={resumen.con_cambios > 0}
               onClick={() => set({ con_cambios: !filtros.con_cambios })} activo={Boolean(filtros.con_cambios)} />
          <Kpi etiqueta="Pendientes de envío" valor={formatoNumero(resumen.pendientes_envio)} />
          <Kpi etiqueta="Sin revisión" valor={formatoNumero(resumen.por_estado["SIN REVISION"] ?? 0)}
               destacar={(resumen.por_estado["SIN REVISION"] ?? 0) > 0}
               onClick={() => set({ estado: filtros.estado?.includes("SIN REVISION") ? [] : ["SIN REVISION"] })}
               activo={Boolean(filtros.estado?.includes("SIN REVISION"))} />
          <Kpi etiqueta="Último recálculo" valor={resumen.ultimo_recalculo ? formatoFechaHora(resumen.ultimo_recalculo) : "—"}
               nota={resumen.ultimo_envio ? `Último envío ${formatoFechaHora(resumen.ultimo_envio)}` : "Sin envíos aún"} />
        </div>
      )}

      <Card>
        <div className="flex flex-wrap items-center gap-2 p-3">
          <div className="relative min-w-[240px] flex-1">
            <Search size={15} className="absolute left-2.5 top-2.5 text-slate-400" />
            <Input placeholder="Buscar código o glosa…" className="pl-8" value={filtros.q ?? ""}
                   onChange={(e) => set({ q: e.target.value })} />
          </div>
          <MultiSelect label="Rubro" className="w-[130px]"
            opciones={opciones.rubros.map((s) => ({ value: s, label: s }))}
            seleccionados={filtros.rubro ?? []} onChange={(v) => set({ rubro: v })} />
          <MultiSelect label="Tipo" className="w-[150px]"
            opciones={opciones.tipos.map((s) => ({ value: s, label: s }))}
            seleccionados={filtros.tipo ?? []} onChange={(v) => set({ tipo: v })} />
          <MultiSelect label="Procedencia" className="w-[150px]"
            opciones={opciones.procedencias.map((s) => ({ value: s, label: s }))}
            seleccionados={filtros.procedencia ?? []} onChange={(v) => set({ procedencia: v })} />
          <MultiSelect label="Estado" className="w-[150px]"
            opciones={opciones.estados.map((s) => ({ value: s, label: s }))}
            seleccionados={filtros.estado ?? []} onChange={(v) => set({ estado: v })} />
          <label className="flex items-center gap-1.5 text-[13px] text-slate-600">
            <input type="checkbox" className="accent-brand" checked={Boolean(filtros.con_stock)}
                   onChange={(e) => set({ con_stock: e.target.checked })} />
            Con stock
          </label>
          <label className="flex items-center gap-1.5 text-[13px] text-slate-600">
            <input type="checkbox" className="accent-brand" checked={filtros.origen === "manual"}
                   onChange={(e) => set({ origen: e.target.checked ? "manual" : undefined })} />
            Creados aquí
          </label>
          {hayFiltros && (
            <Button variant="ghost" size="sm" onClick={() => setFiltros({})}>Limpiar</Button>
          )}
          <div className="ml-auto flex items-center gap-2">
            {puedeEditar && (
              <>
                <Button variant="outline" size="sm" disabled={ocupado !== null}
                  onClick={() => void accion("recalcular", async () => {
                    const r = await api.recalcularPrecios();
                    return `Recalculados ${formatoNumero(r.productos)} productos: ${formatoNumero(r.cambios)} cambios en ${formatoNumero(r.productos_con_cambios)}.`;
                  })}>
                  {ocupado === "recalcular" ? <Loader2 size={15} className="animate-spin" /> : <RefreshCw size={15} />} Recalcular
                </Button>
                {resumen && resumen.con_cambios > 0 && (
                  <Button variant="outline" size="sm" disabled={ocupado !== null}
                    onClick={() => void accion("vistos", async () => {
                      const r = await api.marcarPreciosVistos(filtros.con_cambios || hayFiltros ? rows.map((x) => x.producto) : null);
                      return `${formatoNumero(r.vistos)} cambios marcados como revisados.`;
                    })}>
                    <Bell size={15} /> Marcar revisados{hayFiltros ? " (los filtrados)" : ""}
                  </Button>
                )}
                <Button size="sm" onClick={() => setModalNuevo(true)}><Plus size={15} /> Nuevo producto</Button>
              </>
            )}
          </div>
        </div>
      </Card>

      {error && (
        <p className="flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          <AlertCircle className="h-4 w-4 shrink-0" /> {error}
        </p>
      )}
      {aviso && (
        <p className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">{aviso}</p>
      )}

      <TablaPrecios rows={rows} columnasVisibles={colsVisibles} onFila={setSeleccion} />

      <ConfigurarColumnasPrecios open={modalCols} onClose={() => setModalCols(false)}
                                 visibles={colsVisibles} onChange={setColsVisibles} />

      {seleccion && (
        <ModalProducto
          producto={seleccion.producto}
          puedeEditar={puedeEditar}
          tipos={Array.from(new Set([...opciones.tipos, "Sugerido"])).sort()}
          onCerrar={() => setSeleccion(null)}
          onGuardado={async () => {
            await Promise.all([cargar(), cargarAuxiliares()]);
          }}
        />
      )}

      {modalNuevo && (
        <ModalNuevo
          tipos={opciones.tipos}
          onCerrar={() => setModalNuevo(false)}
          onGuardado={async () => {
            setModalNuevo(false);
            await Promise.all([cargar(), cargarAuxiliares()]);
          }}
        />
      )}
    </div>
  );
}

function Kpi({ etiqueta, valor, nota, destacar, onClick, activo }: {
  etiqueta: string; valor: string; nota?: string; destacar?: boolean; onClick?: () => void; activo?: boolean;
}) {
  const base = "rounded-lg border px-3 py-2 text-left";
  const cls = activo
    ? `${base} border-brand bg-brand/5`
    : destacar ? `${base} border-amber-200 bg-amber-50` : `${base} border-slate-200 bg-white`;
  const inner = (
    <>
      <p className="text-[11px] font-semibold uppercase tracking-wide text-slate-500">{etiqueta}</p>
      <p className="text-lg font-semibold tabular-nums text-slate-900">{valor}</p>
      {nota && <p className="text-[11px] text-slate-400">{nota}</p>}
    </>
  );
  return onClick
    ? <button className={`${cls} w-full hover:border-brand`} onClick={onClick}>{inner}</button>
    : <div className={cls}>{inner}</div>;
}

/** Ficha del producto: como se llego al precio, la decision humana, y su historia. */
function ModalProducto({ producto, puedeEditar, tipos, onCerrar, onGuardado }: {
  producto: string; puedeEditar: boolean; tipos: string[];
  onCerrar: () => void; onGuardado: () => Promise<void>;
}) {
  const [d, setD] = useState<PrecioDetalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [precioFijo, setPrecioFijo] = useState<string>("");
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

  const tieneOverride = d && (d.precio_fijo !== null || d.congelar || d.tipo_manual || d.procedencia_manual || d.no_producto || d.obs);
  const campo = "h-9 w-full rounded-md border border-ink-200 px-2 text-sm outline-none focus:border-brand disabled:bg-ink-50";

  return (
    <Dialog open onClose={onCerrar} title={producto} description={d?.glosa ?? undefined} className="max-w-3xl">
      {!d ? (
        <p className="flex items-center gap-2 text-sm text-ink-500"><Loader2 className="h-4 w-4 animate-spin" /> Cargando…</p>
      ) : (
        <div className="grid gap-5 md:grid-cols-2">
          <section className="space-y-2 text-sm">
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">Cómo se llega al precio</h3>
            <Fila k="Rubro" v={d.rubro ?? "—"} />
            <Fila k="Tipo" v={`${d.tipo ?? "—"}${d.tipo_origen ? ` (${d.tipo_origen})` : ""}`} />
            <Fila k="Procedencia" v={`${d.procedencia_final ?? "—"}${d.procedencia_origen ? ` (${d.procedencia_origen})` : ""}`} />
            {(d.ult_recep_importado || d.ult_pe_nacional) && (
              <Fila k="Últimas compras" v={`imp. ${formatoFecha(d.ult_recep_importado)} · nac. ${formatoFecha(d.ult_pe_nacional)}`} />
            )}
            <Fila k="Factor" v={d.factor ? formatoNumero(d.factor, 2) : "—"} />
            <Fila k="Costo" v={formatoCLP(d.costo)} />
            <Fila k="Stock / en tránsito" v={`${formatoNumero(d.stock ?? 0)} / ${formatoNumero(d.stock_transito ?? 0)}`} />
            {d.precio_sugerido !== null && <Fila k="Precio proveedor" v={formatoCLP(d.precio_sugerido)} />}
            <Fila k="Precio calculado" v={formatoCLP(d.precio_calculado)} />
            <Fila k="Precio ERP hoy" v={formatoCLP(d.precio_erp)} />
            <div className="flex items-center justify-between border-t border-ink-100 pt-2">
              <span className="font-semibold text-ink-800">Precio final</span>
              <span className="flex items-center gap-2">
                <span className={`rounded-sm px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${claseEstado(d.estado)}`}>{d.estado}</span>
                <b className="tabular-nums">{formatoCLP(d.precio_final)}</b>
              </span>
            </div>
            <Fila k="Última venta" v={d.ultima_venta ? formatoFecha(d.ultima_venta) : "sin venta registrada"} />

            {(d.cambios ?? []).length > 0 && (
              <div className="pt-2">
                <h3 className="mb-1 text-[11px] font-semibold uppercase tracking-wide text-ink-400">Cambios detectados</h3>
                <ul className="max-h-40 space-y-1 overflow-auto text-[12px]">
                  {(d.cambios ?? []).map((c, i) => (
                    <li key={i} className={c.visto ? "text-ink-400" : "text-ink-700"}>
                      {formatoFecha(c.detectado_en)} · <b>{c.campo}</b>: {c.antes ?? "—"} → {c.despues ?? "—"}
                      {!c.visto && <span className="ml-1 rounded bg-amber-100 px-1 text-[10px] text-amber-800">nuevo</span>}
                    </li>
                  ))}
                </ul>
              </div>
            )}
            {(d.envios ?? []).length > 0 && (
              <p className="text-[12px] text-ink-500">
                Último envío al ERP: {formatoCLP((d.envios ?? [])[0].precio)} el {formatoFecha((d.envios ?? [])[0].enviado_en)}
                {(d.envios ?? [])[0].enviado_por ? ` por ${(d.envios ?? [])[0].enviado_por}` : ""}
              </p>
            )}
          </section>

          <section className="space-y-3">
            <h3 className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">Decisión sobre este precio</h3>
            {!puedeEditar && (
              <p className="text-[12px] text-ink-500">Tu usuario puede ver la lista pero no editarla.</p>
            )}
            <label className="block text-sm">
              <span className="text-ink-600">Precio fijo</span>
              <input className={campo} type="number" min="0" step="1" disabled={!puedeEditar}
                     value={precioFijo} onChange={(e) => setPrecioFijo(e.target.value)} placeholder="vacío = sigue la regla" />
              <span className="text-[11px] text-ink-400">Gana a todo, incluso sin stock.</span>
            </label>
            <label className="flex items-center gap-2 text-sm text-ink-700">
              <input type="checkbox" className="accent-brand" disabled={!puedeEditar}
                     checked={congelar} onChange={(e) => setCongelar(e.target.checked)} />
              Congelar el precio actual
              {d.congelar && d.congelado_precio !== null && (
                <span className="text-[11px] text-ink-400">(congelado en {formatoCLP(d.congelado_precio)}{d.editado_en ? `, ${formatoFecha(d.editado_en)}` : ""})</span>
              )}
            </label>
            <div className="grid grid-cols-2 gap-2">
              <label className="block text-sm">
                <span className="text-ink-600">Tipo a mano</span>
                <select className={campo} disabled={!puedeEditar} value={tipoManual} onChange={(e) => setTipoManual(e.target.value)}>
                  <option value="">(según regla)</option>
                  {tipos.map((t) => <option key={t} value={t}>{t}</option>)}
                </select>
              </label>
              <label className="block text-sm">
                <span className="text-ink-600">Procedencia a mano</span>
                <select className={campo} disabled={!puedeEditar} value={procManual} onChange={(e) => setProcManual(e.target.value)}>
                  <option value="">(según regla)</option>
                  {PROCEDENCIAS.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
            </div>
            <label className="flex items-center gap-2 text-sm text-ink-700">
              <input type="checkbox" className="accent-brand" disabled={!puedeEditar}
                     checked={noProducto} onChange={(e) => setNoProducto(e.target.checked)} />
              No es un producto (servicio, cargo, mano de obra): sin precio
            </label>
            <label className="block text-sm">
              <span className="text-ink-600">Observación</span>
              <textarea className={`${campo} h-16 py-1`} disabled={!puedeEditar} maxLength={500}
                        value={obs} onChange={(e) => setObs(e.target.value)} placeholder="Por qué este precio no sigue la regla" />
            </label>
            {d.editado_por && (
              <p className="text-[11px] text-ink-400">Última edición: {d.editado_por}{d.editado_en ? ` · ${formatoFechaHora(d.editado_en)}` : ""}</p>
            )}
            {error && <p className="text-sm text-rose-700">{error}</p>}
            {puedeEditar && (
              <div className="flex items-center justify-between gap-2 border-t border-ink-100 pt-3">
                {tieneOverride ? (
                  <Button variant="ghost" size="sm" disabled={guardando} onClick={() => void volverALaRegla()}>Volver a la regla</Button>
                ) : <span />}
                <div className="flex gap-2">
                  <Button variant="outline" size="sm" onClick={onCerrar}>Cerrar</Button>
                  <Button size="sm" disabled={guardando} onClick={() => void guardar()}>
                    {guardando && <Loader2 size={14} className="animate-spin" />} Guardar
                  </Button>
                </div>
              </div>
            )}
          </section>
        </div>
      )}
    </Dialog>
  );
}

function Fila({ k, v }: { k: string; v: string }) {
  return (
    <div className="flex items-baseline justify-between gap-3">
      <span className="text-ink-500">{k}</span>
      <span className="text-right tabular-nums text-ink-800">{v}</span>
    </div>
  );
}

function ModalNuevo({ tipos, onCerrar, onGuardado }: {
  tipos: string[]; onCerrar: () => void; onGuardado: () => Promise<void>;
}) {
  const [producto, setProducto] = useState("");
  const [glosa, setGlosa] = useState("");
  const [tipo, setTipo] = useState("");
  const [procedencia, setProcedencia] = useState("");
  const [costo, setCosto] = useState("");
  const [stock, setStock] = useState("");
  const [precioFijo, setPrecioFijo] = useState("");
  const [obs, setObs] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const campo = "h-9 w-full rounded-md border border-ink-200 px-2 text-sm outline-none focus:border-brand";

  async function guardar() {
    setGuardando(true);
    setError(null);
    try {
      await api.crearPrecioProducto({
        producto: producto.trim(), glosa: glosa.trim() || undefined,
        tipo: tipo || undefined, procedencia: procedencia || undefined,
        costo: costo ? Number(costo.replace(",", ".")) : undefined,
        stock: stock ? Number(stock.replace(",", ".")) : undefined,
        precio_fijo: precioFijo ? Number(precioFijo.replace(",", ".")) : undefined,
        obs: obs.trim() || undefined,
      });
      await onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo crear.");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialog open onClose={onCerrar} title="Nuevo producto"
            description="Se crea en la lista de precios y sale en el próximo envío al ERP. El código lleva el rubro adelante, como en el ERP (ej. 71 2720142).">
      <div className="grid gap-3 md:grid-cols-2">
        <label className="block text-sm md:col-span-2">
          <span className="text-ink-600">Código *</span>
          <input className={`${campo} font-mono`} value={producto} onChange={(e) => setProducto(e.target.value)} placeholder="71 2720142" />
        </label>
        <label className="block text-sm md:col-span-2">
          <span className="text-ink-600">Glosa</span>
          <input className={campo} value={glosa} onChange={(e) => setGlosa(e.target.value)} />
        </label>
        <label className="block text-sm">
          <span className="text-ink-600">Tipo</span>
          <select className={campo} value={tipo} onChange={(e) => setTipo(e.target.value)}>
            <option value="">(según el rubro)</option>
            {tipos.map((t) => <option key={t} value={t}>{t}</option>)}
          </select>
        </label>
        <label className="block text-sm">
          <span className="text-ink-600">Procedencia</span>
          <select className={campo} value={procedencia} onChange={(e) => setProcedencia(e.target.value)}>
            <option value="">(según compras)</option>
            {PROCEDENCIAS.map((p) => <option key={p} value={p}>{p}</option>)}
          </select>
        </label>
        <label className="block text-sm">
          <span className="text-ink-600">Costo</span>
          <input className={campo} type="number" min="0" value={costo} onChange={(e) => setCosto(e.target.value)} />
        </label>
        <label className="block text-sm">
          <span className="text-ink-600">Stock</span>
          <input className={campo} type="number" min="0" value={stock} onChange={(e) => setStock(e.target.value)} />
        </label>
        <label className="block text-sm">
          <span className="text-ink-600">Precio fijo</span>
          <input className={campo} type="number" min="0" value={precioFijo} onChange={(e) => setPrecioFijo(e.target.value)} placeholder="vacío = costo × factor" />
        </label>
        <label className="block text-sm">
          <span className="text-ink-600">Observación</span>
          <input className={campo} value={obs} onChange={(e) => setObs(e.target.value)} />
        </label>
      </div>
      {error && <p className="mt-2 text-sm text-rose-700">{error}</p>}
      <div className="mt-4 flex justify-end gap-2 border-t border-ink-100 pt-3">
        <Button variant="outline" size="sm" onClick={onCerrar}>Cancelar</Button>
        <Button size="sm" disabled={guardando || !producto.trim()} onClick={() => void guardar()}>
          {guardando && <Loader2 size={14} className="animate-spin" />} Crear
        </Button>
      </div>
    </Dialog>
  );
}
