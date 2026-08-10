"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { Boxes, ClipboardPaste, Layers, Package, Repeat, TriangleAlert } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multiselect";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api-client";
import { formatoNumero } from "@/lib/formato";
import type {
  CargaPegadaResultado,
  PreviewDias,
  PreviewObjetivo,
  Producto,
  Sucursal,
  SugeridoFiltros,
} from "@/lib/types";

type Modo = "individual" | "grupo" | "todos" | "pegar";
// Solo "unidades" suma sobre el sugerido. "objetivo" fija un nivel de stock y
// "dias" fija una cobertura en dias: los dos piden solo la brecha que falta,
// descontando stock, transito y lo que el sistema ya sugiere.
type TipoCantidad = "dias" | "unidades" | "objetivo";

interface Props {
  open: boolean;
  onClose: () => void;
  onGuardado: () => void;
  sucursales: Sucursal[];
  /** Lista de proveedores distintos (modo grupo). */
  proveedores?: string[];
  productoInicial?: string;
  sucursalInicial?: string;
  /** Si es true, solo permite el modo individual (ej. desde la vista detalle). */
  soloIndividual?: boolean;
}

const ABC = [
  { value: "A", label: "A" },
  { value: "B", label: "B" },
  { value: "C", label: "C" },
];

export function ModalSugerenciaManual({
  open,
  onClose,
  onGuardado,
  sucursales,
  proveedores = [],
  productoInicial,
  sucursalInicial,
  soloIndividual = false,
}: Props) {
  const [modo, setModo] = useState<Modo>("individual");

  // Comunes
  const [tipoCantidad, setTipoCantidad] = useState<TipoCantidad>("dias");
  const [cantidad, setCantidad] = useState("");
  const [fechaLimite, setFechaLimite] = useState("");
  const [motivo, setMotivo] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Confirmación de "esto no vence nunca" antes de guardar sin fecha límite.
  const [confirmarSinFecha, setConfirmarSinFecha] = useState(false);
  const refFechaLimite = useRef<HTMLInputElement>(null);

  // Individual
  const [producto, setProducto] = useState("");
  const [sucursal, setSucursal] = useState("");
  const [sugerencias, setSugerencias] = useState<Producto[]>([]);
  // El codigo escrito no aparece en ningun catalogo. Avisar mientras se escribe:
  // guardarlo termina en una fila sin descripcion, proveedor ni costo (el backend
  // lo rechaza, pero es mejor decirlo antes que al apretar Guardar).
  const [codigoDesconocido, setCodigoDesconocido] = useState(false);

  // Grupo
  const [gSucursales, setGSucursales] = useState<string[]>([]);
  const [gProveedores, setGProveedores] = useState<string[]>([]);
  const [gAbc, setGAbc] = useState<string[]>([]);

  // Grupo/Todos
  const [soloPedir, setSoloPedir] = useState(true);
  const [conteo, setConteo] = useState<number | null>(null);
  const [contando, setContando] = useState(false);

  // Vista previa de los modos que descuentan lo ya cubierto — "mantener stock" y
  // "días" (solo individual: necesita el par exacto).
  const [preview, setPreview] = useState<PreviewObjetivo | PreviewDias | null>(null);

  // Pegar lista: cada línea trae su propia cantidad, así que no hay un número
  // único que validar. La previa la calcula el servidor (necesita demanda y
  // stock por par) y es lo que se mira antes de guardar.
  const [textoPegado, setTextoPegado] = useState("");
  const [previaPegada, setPreviaPegada] = useState<CargaPegadaResultado | null>(null);
  const [leyendo, setLeyendo] = useState(false);

  // Recurrencia
  const [recurrente, setRecurrente] = useState(false);
  const [cadaDias, setCadaDias] = useState("7");
  const [fechaFin, setFechaFin] = useState("");

  const nombresSucursales = useMemo(
    () => sucursales.map((s) => s.nombre ?? s.sucursal_id),
    [sucursales]
  );

  // Mínimo del calendario: hoy en hora LOCAL (no se puede elegir una fecha límite
  // en el pasado). Con toISOString() directo (UTC), de noche en Chile el datepicker
  // bloqueaba elegir "hoy" porque en UTC ya era mañana.
  const hoyISO = useMemo(() => {
    const d = new Date();
    d.setMinutes(d.getMinutes() - d.getTimezoneOffset());
    return d.toISOString().slice(0, 10);
  }, []);

  useEffect(() => {
    if (open) {
      setModo("individual");
      setTipoCantidad("dias");
      setCantidad("");
      setFechaLimite("");
      setMotivo("");
      setError(null);
      setConfirmarSinFecha(false);
      setProducto(productoInicial ?? "");
      setSucursal(sucursalInicial ?? "");
      setCodigoDesconocido(false);
      setGSucursales([]);
      setGProveedores([]);
      setGAbc([]);
      setSoloPedir(true);
      setConteo(null);
      setRecurrente(false);
      setCadaDias("7");
      setFechaFin("");
      setTextoPegado("");
      setPreviaPegada(null);
    }
  }, [open, productoInicial, sucursalInicial]);

  // Autocomplete producto (modo individual)
  useEffect(() => {
    if (modo !== "individual" || !producto || producto === productoInicial) {
      setSugerencias([]);
      setCodigoDesconocido(false);
      return;
    }
    const t = setTimeout(async () => {
      try {
        const r = await api.productos(producto);
        setSugerencias(r.items.slice(0, 6));
        // Ni una coincidencia parcial. Mientras se escribe un codigo valido siempre
        // hay alguna, asi que cero resultados es señal de codigo inexistente y no
        // ruido de tipeo.
        setCodigoDesconocido(r.items.length === 0);
      } catch {
        // Sin respuesta del servidor no se puede afirmar que el codigo no existe.
        setSugerencias([]);
        setCodigoDesconocido(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [producto, productoInicial, modo]);

  // Vista previa: explica de dónde sale el número antes de guardar. Se recalcula
  // al cambiar producto, sucursal o nivel.
  useEffect(() => {
    const n = parseInt(cantidad, 10);
    const descuenta = tipoCantidad === "objetivo" || tipoCantidad === "dias";
    if (!descuenta || modo !== "individual" || !producto || !sucursal || !n) {
      setPreview(null);
      return;
    }
    const t = setTimeout(async () => {
      try {
        setPreview(
          tipoCantidad === "dias"
            ? await api.previsualizarDias(producto, sucursal, n)
            : await api.previsualizarObjetivo(producto, sucursal, n)
        );
      } catch {
        setPreview(null);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [tipoCantidad, modo, producto, sucursal, cantidad]);

  // La preview de días trae la demanda y los días ya cubiertos; la de objetivo no.
  const previewDias =
    preview && "dias_cubiertos" in preview ? (preview as PreviewDias) : null;

  // Filtros equivalentes al modo grupo/todos.
  const filtrosModo: SugeridoFiltros = useMemo(() => {
    if (modo === "todos") return { solo_pedir: soloPedir };
    if (modo === "grupo")
      return {
        sucursales: gSucursales,
        proveedores: gProveedores,
        abc: gAbc,
        solo_pedir: soloPedir,
      };
    return {};
  }, [modo, soloPedir, gSucursales, gProveedores, gAbc]);

  // Conteo en vivo de productos afectados.
  useEffect(() => {
    if (!open || modo === "individual" || modo === "pegar") return;
    setContando(true);
    const t = setTimeout(async () => {
      try {
        setConteo(await api.contar(filtrosModo));
      } catch {
        setConteo(null);
      } finally {
        setContando(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [open, modo, filtrosModo]);

  /** Primer problema del formulario, o null si está listo para guardar. */
  const validar = (): string | null => {
    // Pegar lista no tiene un número único: cada línea trae el suyo y el
    // servidor ya dijo cuáles sirven.
    if (modo === "pegar") {
      if (!textoPegado.trim()) return "Pega la lista de productos.";
      if (!previaPegada) return "Aprieta “Revisar la lista” antes de guardar.";
      if (!previaPegada.lineas.some((l) => l.unidades_resultantes !== null))
        return "Ninguna línea de la lista se puede cargar. Revisa los errores.";
      return null;
    }
    const n = parseInt(cantidad, 10);
    if (!n || n <= 0)
      return tipoCantidad === "dias"
        ? "Ingresa los días de inventario (entero positivo)."
        : tipoCantidad === "objetivo"
          ? "Ingresa el nivel de stock a mantener (entero positivo)."
          : "Ingresa una cantidad de unidades (entero positivo).";
    const cada = parseInt(cadaDias, 10);
    if (recurrente && (!cada || cada <= 0))
      return "Para repetir, indica cada cuántos días (entero positivo).";
    if (modo === "individual" && (!producto || !sucursal))
      return "Completa producto y sucursal.";
    if (modo !== "individual" && (!conteo || conteo === 0))
      return "Ningun producto cumple ese criterio. Ajusta el grupo.";
    return null;
  };

  /** Manda la lista al servidor para ver qué se crearía, sin escribir nada. */
  const revisarLista = async () => {
    setError(null);
    setLeyendo(true);
    try {
      setPreviaPegada(
        await api.crearSugerenciasPegadas(textoPegado, { previsualizar: true })
      );
    } catch (e) {
      setPreviaPegada(null);
      setError(e instanceof Error ? e.message : "No se pudo leer la lista");
    } finally {
      setLeyendo(false);
    }
  };

  const ejecutarGuardado = async () => {
    setConfirmarSinFecha(false);
    setError(null);

    if (modo === "pegar") {
      const expiraLista = fechaLimite || undefined;
      setGuardando(true);
      try {
        const r = await api.crearSugerenciasPegadas(textoPegado, {
          motivo: motivo || undefined,
          expiraEn: expiraLista,
        });
        onGuardado();
        onClose();
        return r;
      } catch (e) {
        setError(e instanceof Error ? e.message : "No se pudo guardar");
        return;
      } finally {
        setGuardando(false);
      }
    }

    const n = parseInt(cantidad, 10);
    const cantidadPayload =
      tipoCantidad === "dias"
        ? { dias_inventario: n }
        : tipoCantidad === "objetivo"
          ? { stock_objetivo: n }
          : { unidades: n };
    // Fecha límite de vigencia. Solo aplica a sugerencias no recurrentes: las
    // recurrencias controlan su fin con "Hasta (fecha)".
    const expiraEn = !recurrente && fechaLimite ? fechaLimite : undefined;
    const dias = parseInt(cadaDias, 10);
    setGuardando(true);
    try {
      if (recurrente) {
        // Regla recurrente (se aplica de inmediato y se repite cada N días).
        await api.crearRecurrente(
          modo === "individual"
            ? {
                modo: "individual",
                producto,
                sucursal_id: sucursal,
                ...cantidadPayload,
                motivo: motivo || undefined,
                cada_dias: dias,
                fecha_fin: fechaFin || undefined,
              }
            : {
                modo: "grupo",
                filtros: filtrosModo,
                ...cantidadPayload,
                motivo: motivo || undefined,
                cada_dias: dias,
                fecha_fin: fechaFin || undefined,
              }
        );
      } else if (modo === "individual") {
        await api.crearSugerenciaManual({
          producto,
          sucursal_id: sucursal,
          ...cantidadPayload,
          expira_en: expiraEn,
          motivo: motivo || undefined,
        });
      } else {
        const r = await api.crearSugerenciaMasiva(
          filtrosModo, cantidadPayload, motivo || undefined, expiraEn
        );
        if (r.omitidas > 0) {
          // Avisa pero igual cerramos: las creadas ya se aplicaron.
          alert(
            `Se aplicaron ${r.creadas} sugerencias. ` +
              (tipoCantidad === "objetivo"
                ? `${r.omitidas} producto/sucursal ya estaban en el nivel pedido.`
                : `${r.omitidas} producto/sucursal se omitieron: sin demanda diaria o ya tenían esos días cubiertos.`)
          );
        }
      }
      onGuardado();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al guardar");
    } finally {
      setGuardando(false);
    }
  };

  const guardar = () => {
    const problema = validar();
    if (problema) {
      setError(problema);
      return;
    }
    setError(null);
    // Sin fecha límite la sugerencia no vence: sigue sumando las mismas unidades a la
    // compra todos los días hasta que alguien la borre a mano, y no se apaga cuando
    // llega la mercadería. Es el default más caro, así que hay que confirmarlo.
    if (!recurrente && !fechaLimite) {
      setConfirmarSinFecha(true);
      return;
    }
    void ejecutarGuardado();
  };

  const tabs: { id: Modo; icon: React.ReactNode; label: string; sub: string }[] = [
    { id: "individual", icon: <Package size={16} />, label: "Individual", sub: "Un producto" },
    { id: "grupo", icon: <Layers size={16} />, label: "Por grupo", sub: "Por sucursal / proveedor / ABC" },
    { id: "todos", icon: <Boxes size={16} />, label: "Todos", sub: "Todos los productos" },
    // Los tres de arriba aplican UN criterio a lo que caiga en un filtro. Este es
    // el caso contrario: una lista armada a mano donde cada linea trae lo suyo.
    { id: "pegar", icon: <ClipboardPaste size={16} />, label: "Pegar lista", sub: "Una cantidad por línea" },
  ];

  // Cuántas líneas de la lista pegada van a crear algo (las omitidas no cuentan).
  const lineasQueEntran =
    previaPegada?.lineas.filter((l) => l.unidades_resultantes !== null).length ?? 0;

  const etiquetaBoton =
    modo === "individual"
      ? guardando
        ? "Guardando…"
        : "Guardar"
      : modo === "pegar"
        ? guardando
          ? "Cargando…"
          : lineasQueEntran
            ? `Cargar ${formatoNumero(lineasQueEntran)} línea${lineasQueEntran === 1 ? "" : "s"}`
            : "Cargar la lista"
        : guardando
          ? "Aplicando…"
          : conteo
            ? `Aplicar a ${formatoNumero(conteo)} producto${conteo === 1 ? "" : "s"}`
            : "Aplicar";

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Agregar sugerencia manual"
      description={
        tipoCantidad === "objetivo"
          ? "Mantiene un nivel de stock: pide solo lo que falta para llegar a él."
          : tipoCantidad === "dias"
            ? "Completa la cobertura hasta esos días: si el stock ya alcanza, no pide nada."
            : "Suma unidades por sobre lo que sugiere el sistema."
      }
    >
      <div className="space-y-4">
        {/* Selector de modo */}
        {!soloIndividual && (
          <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
            {tabs.map((t) => (
              <button
                key={t.id}
                type="button"
                onClick={() => setModo(t.id)}
                className={cn(
                  "flex flex-col items-start gap-0.5 rounded-lg border p-2.5 text-left transition-colors",
                  modo === t.id
                    ? "border-brand bg-brand-50 text-brand"
                    : "border-slate-200 text-slate-600 hover:bg-slate-50"
                )}
              >
                <span className="flex items-center gap-1.5 text-[13px] font-medium">
                  {t.icon}
                  {t.label}
                </span>
                <span className="text-[11px] text-slate-400">{t.sub}</span>
              </button>
            ))}
          </div>
        )}

        {/* --- Modo individual --- */}
        {modo === "individual" && (
          <>
            <div className="relative">
              <Label htmlFor="prod">Producto</Label>
              <Input
                id="prod"
                value={producto}
                onChange={(e) => setProducto(e.target.value)}
                placeholder="Codigo del producto"
                autoComplete="off"
              />
              {sugerencias.length > 0 && (
                <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg">
                  {sugerencias.map((p) => (
                    <button
                      key={p.producto}
                      type="button"
                      onClick={() => {
                        setProducto(p.producto);
                        setSugerencias([]);
                      }}
                      className="block w-full px-3 py-1.5 text-left text-[13px] hover:bg-slate-50"
                    >
                      <span className="font-medium">{p.producto}</span>{" "}
                      <span className="text-slate-500">{p.descripcion}</span>
                    </button>
                  ))}
                </div>
              )}
              {codigoDesconocido && (
                <p className="mt-1 flex items-start gap-1.5 text-[11.5px] text-amber-700">
                  <TriangleAlert size={13} className="mt-px shrink-0" />
                  <span>
                    Ese código no existe en el catálogo. Revísalo: si lo guardas así, la
                    fila queda sin descripción, proveedor ni costo.
                  </span>
                </p>
              )}
            </div>
            <div>
              <Label htmlFor="suc">Sucursal</Label>
              <select
                id="suc"
                value={sucursal}
                onChange={(e) => setSucursal(e.target.value)}
                className="h-9 w-full rounded-md border border-slate-300 bg-white px-3 text-sm text-slate-900 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-brand"
              >
                <option value="">Selecciona…</option>
                {sucursales.map((s) => (
                  <option key={s.sucursal_id} value={s.sucursal_id}>
                    {s.nombre ?? s.sucursal_id}
                  </option>
                ))}
              </select>
            </div>
          </>
        )}

        {/* --- Modo grupo --- */}
        {modo === "grupo" && (
          <div className="space-y-3 rounded-lg border border-slate-100 bg-slate-50/60 p-3">
            <p className="text-[12px] text-slate-500">
              Elige uno o varios criterios. Se aplicara a los productos que cumplan
              <b> todos</b> los criterios seleccionados.
            </p>
            <div className="grid grid-cols-3 gap-2">
              <div>
                <Label>Sucursal</Label>
                <MultiSelect
                  label="Todas"
                  opciones={nombresSucursales.map((s) => ({ value: s, label: s }))}
                  seleccionados={gSucursales}
                  onChange={setGSucursales}
                />
              </div>
              <div>
                <Label>Proveedor</Label>
                <MultiSelect
                  label="Todos"
                  opciones={proveedores.map((p) => ({ value: p, label: p }))}
                  seleccionados={gProveedores}
                  onChange={setGProveedores}
                />
              </div>
              <div>
                <Label>ABC</Label>
                <MultiSelect
                  label="Todas"
                  opciones={ABC}
                  seleccionados={gAbc}
                  onChange={setGAbc}
                />
              </div>
            </div>
          </div>
        )}

        {/* Toggle solo pedir (grupo y todos) */}
        {modo !== "individual" && (
          <label className="flex cursor-pointer select-none items-center gap-2 text-[13px] text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand"
              checked={soloPedir}
              onChange={(e) => setSoloPedir(e.target.checked)}
            />
            Solo productos con pedir = Si (recomendado)
          </label>
        )}

        {/* Conteo en vivo */}
        {modo !== "individual" && (
          <div
            className={cn(
              "flex items-center gap-2 rounded-md px-3 py-2 text-[13px]",
              conteo && conteo > 1000
                ? "bg-amber-50 text-amber-800"
                : "bg-brand-50 text-brand"
            )}
          >
            {conteo && conteo > 1000 && <TriangleAlert size={15} />}
            {contando ? (
              "Calculando productos afectados…"
            ) : conteo === null ? (
              "—"
            ) : (
              <span>
                Se aplicara a <b>{formatoNumero(conteo)}</b> producto
                {conteo === 1 ? "" : "s"} (producto × sucursal).
                {conteo > 1000 && " Es una carga grande, revisa antes de aplicar."}
              </span>
            )}
          </div>
        )}

        {/* --- Modo pegar lista --- */}
        {modo === "pegar" && (
          <div className="space-y-3">
            <div>
              <Label htmlFor="pegado">Pega la lista</Label>
              <Textarea
                id="pegado"
                rows={7}
                value={textoPegado}
                onChange={(e) => {
                  setTextoPegado(e.target.value);
                  setPreviaPegada(null);
                }}
                placeholder={
                  "producto\tsucursal\tunidades\tdías\tmantener\n" +
                  "25 DG9Z8100A\tLINDEROS\t5\n" +
                  "20 BXO5W30BA\tCURICO\t\t30\n" +
                  "13 C5TS7600B3\tTALCA\t\t\t12"
                }
                className="font-mono text-[12px]"
              />
              <p className="mt-1 text-[11.5px] text-slate-500">
                Copia el rango desde Excel y pégalo. La primera fila puede ser el
                encabezado (da igual el orden de las columnas). Si una línea trae
                más de una cantidad, manda <b>mantener</b>, después <b>días</b> y
                al final <b>unidades</b>.
              </p>
            </div>

            <Button
              type="button"
              variant="secondary"
              onClick={revisarLista}
              disabled={!textoPegado.trim() || leyendo}
            >
              {leyendo ? "Leyendo…" : "Revisar la lista"}
            </Button>

            {previaPegada && (
              <div className="space-y-2">
                <div className="flex flex-wrap gap-3 text-[12.5px]">
                  <span className="text-emerald-700">
                    <b>{formatoNumero(previaPegada.lineas.filter((l) => l.unidades_resultantes !== null).length)}</b>{" "}
                    líneas se van a cargar
                  </span>
                  {previaPegada.omitidas > 0 && (
                    <span className="text-slate-500">
                      <b>{formatoNumero(previaPegada.omitidas)}</b> omitidas
                    </span>
                  )}
                  {previaPegada.errores.length > 0 && (
                    <span className="text-red-600">
                      <b>{previaPegada.errores.length}</b> con error
                    </span>
                  )}
                </div>

                <div className="max-h-52 overflow-auto rounded-md border border-slate-200">
                  <table className="w-full text-[12px]">
                    <thead className="sticky top-0 bg-slate-50 text-slate-500">
                      <tr>
                        <th className="px-2 py-1 text-left font-normal">Producto</th>
                        <th className="px-2 py-1 text-left font-normal">Sucursal</th>
                        <th className="px-2 py-1 text-left font-normal">Criterio</th>
                        <th className="px-2 py-1 text-right font-normal">Pide</th>
                      </tr>
                    </thead>
                    <tbody>
                      {previaPegada.lineas.map((l, i) => (
                        <tr
                          key={`${l.producto}-${l.sucursal}-${i}`}
                          className={cn(
                            "border-t border-slate-100",
                            l.unidades_resultantes === null && "text-slate-400"
                          )}
                        >
                          <td className="px-2 py-1 font-mono">{l.producto}</td>
                          <td className="px-2 py-1">{l.sucursal}</td>
                          <td className="px-2 py-1">
                            {l.criterio === "mantener"
                              ? `completar a ${formatoNumero(l.mantener ?? 0)} u`
                              : l.criterio === "dias"
                                ? `cubrir ${l.dias} días`
                                : `suma ${formatoNumero(l.unidades ?? 0)} u fijas`}
                          </td>
                          <td className="px-2 py-1 text-right tabular">
                            {l.unidades_resultantes !== null ? (
                              <b>{formatoNumero(l.unidades_resultantes)}</b>
                            ) : (
                              <span title={l.omitida_porque ?? undefined}>no pide</span>
                            )}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {previaPegada.errores.length > 0 && (
                  <ul className="space-y-0.5 rounded-md border border-red-200 bg-red-50 px-3 py-2 text-[12px] text-red-800">
                    {previaPegada.errores.slice(0, 6).map((e) => (
                      <li key={e.linea}>
                        <b>Línea {e.linea}:</b> {e.error}
                      </li>
                    ))}
                    {previaPegada.errores.length > 6 && (
                      <li className="text-red-600">
                        y {previaPegada.errores.length - 6} más…
                      </li>
                    )}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}

        {/* Cantidad (dias o unidades) + motivo (comunes). En "pegar" no hay un
            número único: cada línea trae el suyo. */}
        {modo !== "pegar" && (
        <div>
          <div className="mb-1.5 flex items-center justify-between gap-2">
            <Label htmlFor="uni" className="!mb-0">
              {tipoCantidad === "dias"
                ? modo === "individual"
                  ? "Días de inventario a cubrir"
                  : "Días de inventario a cubrir en cada producto"
                : tipoCantidad === "objetivo"
                  ? modo === "individual"
                    ? "Stock a mantener (unidades)"
                    : "Stock a mantener en cada producto"
                  : modo === "individual"
                    ? "Unidades adicionales"
                    : "Unidades para cada producto"}
            </Label>
            <div className="inline-flex shrink-0 rounded-md border border-slate-200 bg-white p-0.5 text-[11px] font-medium">
              {(
                [
                  { id: "dias", label: "Días" },
                  { id: "unidades", label: "Unidades" },
                  { id: "objetivo", label: "Mantener stock" },
                ] as const
              ).map((t) => (
                <button
                  key={t.id}
                  type="button"
                  onClick={() => {
                    setTipoCantidad(t.id);
                    // "Mantener stock" es una regla, no una compra puntual: sin
                    // repeticion el nivel se cubre una vez y nunca mas. Se puede
                    // desmarcar si solo se quiere el relleno de hoy.
                    if (t.id === "objetivo") setRecurrente(true);
                  }}
                  className={cn(
                    "rounded px-2 py-0.5 transition-colors",
                    tipoCantidad === t.id
                      ? "bg-brand text-white"
                      : "text-slate-500 hover:text-slate-800"
                  )}
                >
                  {t.label}
                </button>
              ))}
            </div>
          </div>
          <Input
            id="uni"
            type="number"
            min={1}
            value={cantidad}
            onChange={(e) => setCantidad(e.target.value)}
            placeholder="0"
          />
          {tipoCantidad === "dias" && (
            <p className="mt-1 text-[11px] text-slate-500">
              Cobertura que quieres tener. Se convierte a unidades segun la demanda diaria
              de cada producto/sucursal (redondeo hacia arriba) y se pide{" "}
              <b>solo lo que falta</b>: descuenta el stock actual, lo que viene en tránsito y
              lo que el sistema ya está sugiriendo. Si el stock ya cubre esos días no se pide
              nada. Los productos sin demanda registrada se omiten.
            </p>
          )}
          {tipoCantidad === "objetivo" && (
            <p className="mt-1 text-[11px] text-slate-500">
              Nivel que quieres tener en bodega. Se pide <b>solo lo que falta</b> para llegar
              a ese nivel: descuenta el stock actual, lo que viene en tránsito y lo que el
              sistema ya está sugiriendo. Lo que ya está en nivel se omite. Sirve también
              para productos que el sistema no sugiere: ahí se mira el stock de bodega.
              {!recurrente && (
                <>
                  {" "}
                  Marca <b>Repetir periódicamente</b> para que el nivel se mantenga solo.
                </>
              )}
            </p>
          )}

          {/* Sin demanda diaria no hay forma de convertir días a unidades. */}
          {previewDias?.sin_demanda && (
            <div className="mt-2 rounded-md bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
              Este producto no tiene demanda diaria registrada en esta sucursal, así que
              los días no se pueden convertir a unidades. Usa <b>Unidades</b> o{" "}
              <b>Mantener stock</b>.
            </div>
          )}

          {/* De dónde sale el número, antes de guardar. */}
          {preview && !previewDias?.sin_demanda && (
            <div
              className={cn(
                "mt-2 rounded-md px-3 py-2 text-[12px]",
                preview.faltante > 0
                  ? "bg-brand-50 text-brand"
                  : "bg-amber-50 text-amber-800"
              )}
            >
              <p className="font-medium">
                {preview.faltante > 0 ? (
                  <>Se pedirán {formatoNumero(preview.faltante)} unidades.</>
                ) : previewDias ? (
                  <>
                    Ya tienes cobertura para {formatoNumero(Math.floor(previewDias.dias_cubiertos))}{" "}
                    días: no se pide nada.
                  </>
                ) : recurrente ? (
                  <>
                    El nivel ya está cubierto hoy: no se pide nada ahora, y la regla
                    repone sola cuando baje.
                  </>
                ) : (
                  <>
                    El nivel ya está cubierto hoy. Marca <b>Repetir periódicamente</b> para
                    dejarlo como regla y que se reponga cuando baje.
                  </>
                )}
              </p>
              <ul className="mt-1 space-y-0.5 text-[11.5px] opacity-90">
                <li>
                  Stock hoy en la sucursal: <b>{formatoNumero(preview.stock)}</b>
                  {preview.bodegas.length > 0 && (
                    <span className="opacity-80">
                      {" — "}
                      {preview.bodegas
                        .map((b) => `${b.bodega}: ${formatoNumero(b.stock)}`)
                        .join(", ")}
                    </span>
                  )}
                </li>
                {preview.transito > 0 && (
                  <li>
                    En tránsito: <b>{formatoNumero(preview.transito)}</b>
                  </li>
                )}
                {preview.sugerido_sistema > 0 && (
                  <li>
                    Ya sugerido por el sistema: <b>{formatoNumero(preview.sugerido_sistema)}</b>
                  </li>
                )}
                <li className="border-t border-current/15 pt-0.5">
                  Cubierto: <b>{formatoNumero(preview.cubierto)}</b> de{" "}
                  {formatoNumero(preview.objetivo)}
                  {previewDias && (
                    <span className="opacity-80">
                      {" "}
                      u que cubren {previewDias.dias} días (demanda{" "}
                      {previewDias.demanda_diaria.toFixed(1)} u/día)
                    </span>
                  )}
                </li>
              </ul>
              {!preview.en_sugerido && (
                <p className="mt-1 text-[11px] opacity-80">
                  El sistema no sugiere este producto en esta sucursal.
                </p>
              )}
            </div>
          )}
        </div>
        )}

        {/* Fecha límite: hasta cuándo la sugerencia sigue vigente (no aplica a recurrentes). */}
        {!recurrente && (
          <div>
            <Label htmlFor="fechalim">Fecha límite (recomendada)</Label>
            <Input
              id="fechalim"
              ref={refFechaLimite}
              type="date"
              min={hoyISO}
              value={fechaLimite}
              onChange={(e) => setFechaLimite(e.target.value)}
            />
            {fechaLimite ? (
              <p className="mt-1 text-[11px] text-slate-500">
                Hasta esa fecha (incluida) la sugerencia suma a la compra; al día
                siguiente se archiva sola.
              </p>
            ) : (
              <p className="mt-1 flex items-start gap-1.5 text-[11.5px] text-amber-700">
                <TriangleAlert size={13} className="mt-px shrink-0" />
                <span>
                  Sin fecha no vence: sigue pidiendo las mismas unidades{" "}
                  <b>todos los días</b> hasta que la borres a mano, aunque ya hayas
                  comprado.
                </span>
              </p>
            )}
          </div>
        )}

        <div>
          <Label htmlFor="mot">Motivo (opcional)</Label>
          <Textarea
            id="mot"
            rows={2}
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            placeholder="Ej: promo, quiebre puntual, pedido especial de la jefa…"
          />
        </div>

        {/* Recurrencia */}
        <div className="rounded-lg border border-slate-200 p-3">
          <label className="flex cursor-pointer select-none items-center gap-2 text-[13px] font-medium text-slate-800">
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand"
              checked={recurrente}
              onChange={(e) => setRecurrente(e.target.checked)}
            />
            <Repeat size={15} className="text-brand" />
            Repetir periódicamente
          </label>
          {recurrente && (
            <div className="mt-3 grid grid-cols-2 gap-3">
              <div>
                <Label htmlFor="dias">Cada cuántos días</Label>
                <Input
                  id="dias"
                  type="number"
                  min={1}
                  value={cadaDias}
                  onChange={(e) => setCadaDias(e.target.value)}
                  placeholder="7"
                />
              </div>
              <div>
                <Label htmlFor="fin">Hasta (opcional)</Label>
                <Input
                  id="fin"
                  type="date"
                  value={fechaFin}
                  onChange={(e) => setFechaFin(e.target.value)}
                />
              </div>
              <p className="col-span-2 text-[12px] text-slate-500">
                {tipoCantidad === "objetivo" ? (
                  <>
                    Cada {parseInt(cadaDias, 10) || "—"} días se revisa el stock y se repone
                    <b> solo lo que falte</b> para volver a {cantidad || "—"} unidades
                    {fechaFin ? `, hasta el ${fechaFin}` : ", hasta que elimines la regla"}. Si
                    el nivel ya está cubierto, esa vez no pide nada.
                  </>
                ) : tipoCantidad === "dias" ? (
                  <>
                    Cada {parseInt(cadaDias, 10) || "—"} días se revisa la demanda y el stock y
                    se pide <b>solo lo que falte</b> para cubrir {cantidad || "—"} días
                    {fechaFin ? `, hasta el ${fechaFin}` : ", hasta que elimines la regla"}. Si
                    la cobertura ya está, esa vez no pide nada.
                  </>
                ) : (
                  <>
                    Se aplica ahora y se vuelve a aplicar cada {parseInt(cadaDias, 10) || "—"} días
                    {fechaFin ? ` hasta el ${fechaFin}` : " hasta que la elimines"}. Cada repetición
                    reemplaza la anterior (no se acumulan).
                  </>
                )}
              </p>
            </div>
          )}
        </div>

        {error && (
          <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
        )}

        <div className="flex justify-end gap-2 border-t border-slate-100 pt-3">
          <Button variant="outline" onClick={onClose}>
            Cancelar
          </Button>
          <Button onClick={guardar} disabled={guardando}>
            {etiquetaBoton}
          </Button>
        </div>

        {/* Última barrera antes de crear algo que no se apaga solo. Va dentro del panel
            del modal para que cerrarlo (Escape o backdrop) no descarte el formulario. */}
        <Dialog
          open={confirmarSinFecha}
          onClose={() => setConfirmarSinFecha(false)}
          title="Esto no va a vencer nunca"
          description="Le falta la fecha límite."
          className="max-w-md"
        >
          <div className="space-y-3">
            <div className="flex items-start gap-2 rounded-md bg-amber-50 px-3 py-2.5 text-[12.5px] text-amber-800">
              <TriangleAlert size={16} className="mt-px shrink-0" />
              <div className="space-y-1.5">
                <p>
                  {modo === "individual"
                    ? "Esta sugerencia va a sumarse"
                    : `Las ${formatoNumero(conteo ?? 0)} sugerencias van a sumarse`}{" "}
                  a la compra <b>todos los días</b>, siempre con las mismas unidades,
                  hasta que alguien las elimine a mano.
                </p>
                <p>
                  Tampoco se apagan cuando llegue la mercadería: el número queda
                  congelado y se sigue pidiendo encima de lo que sugiere el sistema.
                </p>
              </div>
            </div>
            <p className="text-[12.5px] text-slate-600">
              Si es una compra puntual, pon el último día en que la quieras comprar: se
              archiva sola al día siguiente y no queda pidiéndose para siempre.
            </p>
            <div className="flex flex-col-reverse gap-2 border-t border-slate-100 pt-3 sm:flex-row sm:justify-end">
              <Button
                variant="outline"
                onClick={() => void ejecutarGuardado()}
                disabled={guardando}
              >
                {guardando ? "Guardando…" : "Guardar sin fecha límite"}
              </Button>
              <Button
                onClick={() => {
                  setConfirmarSinFecha(false);
                  // El input sigue montado detrás; el foco espera al re-render.
                  setTimeout(() => refFechaLimite.current?.focus(), 0);
                }}
              >
                Volver y poner fecha
              </Button>
            </div>
          </div>
        </Dialog>
      </div>
    </Dialog>
  );
}
