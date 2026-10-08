"use client";

/**
 * Agregar una sugerencia manual: lo que el modelo no ve (un pedido de taller, una
 * promoción, un mínimo que se quiere tener).
 *
 * Opción A, aprobada el 08-10-2026. Antes había que combinar "Días / Unidades /
 * Mantener stock" con una casilla de "Repetir cada N días" y una fecha límite, y
 * casi nadie sabía qué resultaba. Ahora se completa una de tres frases y, antes de
 * guardar, se ve cuánto se compra hoy:
 *   - "N unidades más, una sola vez": se borra sola al marcarla como pedida, o a los
 *     7 días si nadie la compra (nunca queda pidiéndose para siempre por omisión).
 *   - "nunca menos de N unidades": regla que cada día pide solo lo que falte.
 *   - "que alcance para N días de venta": lo mismo, con la venta del momento.
 * Las cuentas del recuadro están en `lib/pedido-especial.ts` y son las del servidor.
 */

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { TriangleAlert } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multiselect";
import { cn } from "@/lib/utils";
import { api } from "@/lib/api-client";
import { formatoFecha, formatoNumero } from "@/lib/formato";
import { calcular, fechaEnDias, textoResultado, type Frase } from "@/lib/pedido-especial";
import type {
  CargaPegadaResultado,
  ContextoSugerencia,
  Producto,
  Sucursal,
  SugeridoFiltros,
} from "@/lib/types";

type Alcance = "uno" | "varios" | "lista";
/** Si nadie compra la sugerencia de una sola vez, a los cuántos días se borra. */
type Plazo = "7" | "14" | "30" | "nunca";

interface Props {
  open: boolean;
  onClose: () => void;
  onGuardado: () => void;
  sucursales: Sucursal[];
  /** Lista de proveedores distintos (pestaña Varios productos). */
  proveedores?: string[];
  productoInicial?: string;
  sucursalInicial?: string;
  /** Si es true, solo permite un producto (ej. desde la vista detalle). */
  soloIndividual?: boolean;
}

const ABC = [
  { value: "A", label: "A" },
  { value: "B", label: "B" },
  { value: "C", label: "C" },
];

const PESTANAS: { id: Alcance; label: string; sub: string }[] = [
  { id: "uno", label: "Un producto", sub: "El caso normal" },
  { id: "varios", label: "Varios productos", sub: "Por sucursal, proveedor o ABC" },
  { id: "lista", label: "Pegar lista", sub: "Desde Excel" },
];

const PLAZOS: { value: Plazo; label: string }[] = [
  { value: "7", label: "7 días" },
  { value: "14", label: "14 días" },
  { value: "30", label: "30 días" },
  { value: "nunca", label: "Nunca" },
];

const SIN_NUMEROS: Record<Frase, string> = { una: "", min: "", dias: "" };

const CLASE_SELECT =
  "h-9 rounded-sm border border-ink-200 bg-white px-2.5 text-[13.5px] text-ink-900 transition-colors focus-visible:border-accent-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-700/30";

/** "LINDEROS" → "Linderos" para leerlo dentro de una frase; lo demás, tal cual. */
function nombreEnFrase(nombre: string): string {
  if (nombre !== nombre.toUpperCase()) return nombre;
  return nombre
    .toLowerCase()
    .split(" ")
    .map((p) => (p ? p[0].toUpperCase() + p.slice(1) : p))
    .join(" ");
}

/** "5 en stock · 2 en camino · el sistema ya pide 3 · se venden 0,8 al día" */
function lineaContexto(c: ContextoSugerencia): string {
  const sistema = c.sugerido_sistema || 0;
  return [
    `${formatoNumero(c.stock)} en stock`,
    `${formatoNumero(c.transito)} en camino`,
    !c.en_sugerido
      ? "el sistema no lo sugiere aquí"
      : sistema > 0
        ? `el sistema ya pide ${formatoNumero(sistema)}`
        : "el sistema hoy no pide",
    c.demanda_diaria
      ? `se venden ${formatoNumero(c.demanda_diaria, 1)} al día`
      : "sin venta registrada",
  ].join(" · ");
}

function describirRegla(r: ContextoSugerencia["reglas"][number]): string {
  if (r.stock_objetivo) return `nunca menos de ${formatoNumero(r.stock_objetivo)} unidades`;
  if (r.dias_inventario)
    return `que alcance para ${formatoNumero(r.dias_inventario)} días de venta`;
  return `${formatoNumero(r.unidades ?? 0)} unidades cada vez`;
}

/** Una de las tres frases. Toda la tarjeta elige la frase; el detalle solo se ve
 *  en la elegida, para que se lea una cosa a la vez. */
function Tarjeta({
  activa,
  onElegir,
  children,
  pie,
}: {
  activa: boolean;
  onElegir: () => void;
  children: ReactNode;
  pie?: ReactNode;
}) {
  return (
    <div
      onClick={onElegir}
      className={cn(
        "cursor-pointer rounded-lg border bg-white px-3.5 py-2.5 transition-colors",
        activa
          ? "border-brand text-ink-900 ring-1 ring-inset ring-brand/40"
          : "border-ink-200 text-ink-400 hover:border-ink-300 hover:text-ink-600"
      )}
    >
      <p className="text-[14.5px] leading-8">{children}</p>
      {activa && pie}
    </div>
  );
}

function Radio({
  activa,
  onElegir,
  etiqueta,
}: {
  activa: boolean;
  onElegir: () => void;
  etiqueta: string;
}) {
  return (
    <input
      type="radio"
      name="frase-sugerencia-manual"
      checked={activa}
      onChange={onElegir}
      aria-label={etiqueta}
      className="mr-2 h-4 w-4 cursor-pointer align-middle accent-brand"
    />
  );
}

function NumeroEnLinea({
  valor,
  onCambio,
  onElegir,
  etiqueta,
  activa,
}: {
  valor: string;
  onCambio: (v: string) => void;
  onElegir: () => void;
  etiqueta: string;
  activa: boolean;
}) {
  return (
    <input
      type="number"
      inputMode="numeric"
      min={1}
      step={1}
      value={valor}
      onChange={(e) => onCambio(e.target.value)}
      onFocus={onElegir}
      aria-label={etiqueta}
      className={cn(
        // Sin las flechitas del navegador: en un campo angosto tapan el número.
        "mx-1.5 inline-block h-8 w-[4.5rem] rounded-sm border border-ink-200 px-1 text-center align-middle font-mono text-[14px] transition-colors [appearance:textfield] focus-visible:border-accent-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-700/30 [&::-webkit-inner-spin-button]:appearance-none [&::-webkit-outer-spin-button]:appearance-none",
        activa ? "bg-white text-ink-900" : "bg-ink-100 text-ink-400"
      )}
    />
  );
}

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
  const [alcance, setAlcance] = useState<Alcance>("uno");
  const [frase, setFrase] = useState<Frase>("una");
  // Un número por frase: cambiar de frase no borra lo que se escribió en otra.
  const [numeros, setNumeros] = useState<Record<Frase, string>>(SIN_NUMEROS);
  const [motivo, setMotivo] = useState("");
  const [masOpciones, setMasOpciones] = useState(false);
  const [plazo, setPlazo] = useState<Plazo>("7");
  const [hastaFecha, setHastaFecha] = useState(false);
  const [fechaFin, setFechaFin] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Un producto
  const [producto, setProducto] = useState("");
  // El código tal como está en el catálogo, cuando lo escrito coincide con uno.
  // El stock y lo que pide el sistema se buscan solo para un código confirmado:
  // con medio código escrito saldría "0 en stock" y engañaría.
  const [productoConfirmado, setProductoConfirmado] = useState<string | null>(null);
  const elegidoDeLaLista = useRef<string | null>(null);
  const [sucursal, setSucursal] = useState("");
  const [sugerencias, setSugerencias] = useState<Producto[]>([]);
  // El código escrito no aparece en ningún catálogo. Avisar mientras se escribe:
  // guardarlo termina en una fila sin descripción, proveedor ni costo.
  const [codigoDesconocido, setCodigoDesconocido] = useState(false);
  // El código existe, pero FORD lo dio de baja. Se AVISA, no se bloquea: si el
  // vigente no tiene stock en FORD la orden va con otro código del grupo.
  const [vigenteSugerido, setVigenteSugerido] = useState<string | null>(null);
  const [ctx, setCtx] = useState<ContextoSugerencia | null>(null);
  const [cargandoCtx, setCargandoCtx] = useState(false);
  const [ctxFallo, setCtxFallo] = useState(false);
  // Si ya hay algo cargado para el mismo producto y sucursal: reemplazarlo (lo
  // normal) o sumar. Dos sugerencias del mismo par se suman entre sí.
  const [reemplazar, setReemplazar] = useState(true);

  // Varios productos
  const [gSucursales, setGSucursales] = useState<string[]>([]);
  const [gProveedores, setGProveedores] = useState<string[]>([]);
  const [gAbc, setGAbc] = useState<string[]>([]);
  const [soloPedir, setSoloPedir] = useState(true);
  const [conteo, setConteo] = useState<number | null>(null);
  const [contando, setContando] = useState(false);

  // Pegar lista: cada línea trae su propia cantidad. La previa la calcula el
  // servidor (necesita demanda y stock por par) y se mira antes de guardar.
  const [textoPegado, setTextoPegado] = useState("");
  const [previaPegada, setPreviaPegada] = useState<CargaPegadaResultado | null>(null);
  const [leyendo, setLeyendo] = useState(false);

  const nombresSucursales = useMemo(
    () => sucursales.map((s) => s.nombre ?? s.sucursal_id),
    [sucursales]
  );

  // Mínimo del calendario: hoy en hora LOCAL (de noche en Chile, UTC ya es mañana).
  // Sin memo: la página puede quedar abierta de un día para otro.
  const hoyISO = fechaEnDias(0);

  useEffect(() => {
    if (!open) return;
    setAlcance("uno");
    setFrase("una");
    setNumeros(SIN_NUMEROS);
    setMotivo("");
    setMasOpciones(false);
    setPlazo("7");
    setHastaFecha(false);
    setFechaFin("");
    setError(null);
    setProducto(productoInicial ?? "");
    setProductoConfirmado(productoInicial ?? null);
    elegidoDeLaLista.current = null;
    setSucursal(sucursalInicial ?? "");
    setSugerencias([]);
    setCodigoDesconocido(false);
    setVigenteSugerido(null);
    setGSucursales([]);
    setGProveedores([]);
    setGAbc([]);
    setSoloPedir(true);
    setConteo(null);
    setTextoPegado("");
    setPreviaPegada(null);
  }, [open, productoInicial, sucursalInicial]);

  // Autocompletar y confirmar el código (solo "Un producto").
  useEffect(() => {
    const escrito = producto.trim();
    if (alcance !== "uno" || !escrito || producto === productoInicial) {
      setSugerencias([]);
      setCodigoDesconocido(false);
      setVigenteSugerido(null);
      setProductoConfirmado(escrito && producto === productoInicial ? escrito : null);
      return;
    }
    // Recién elegido de la lista: ya está confirmado, no se vuelve a buscar.
    if (producto === elegidoDeLaLista.current) return;
    setProductoConfirmado(null);
    const t = setTimeout(async () => {
      try {
        const r = await api.productos(escrito);
        const exacto = r.items.find(
          (p) => p.producto.toUpperCase() === escrito.toUpperCase()
        );
        // Si lo escrito es exactamente el único resultado, la lista no aporta.
        setSugerencias(exacto && r.items.length === 1 ? [] : r.items.slice(0, 6));
        setProductoConfirmado(exacto?.producto ?? null);
        setVigenteSugerido(exacto?.reemplazado_por ?? null);
        // Ni una coincidencia parcial: mientras se escribe un código válido
        // siempre hay alguna, así que cero es señal de código inexistente.
        setCodigoDesconocido(r.items.length === 0);
      } catch {
        // Sin respuesta del servidor no se puede afirmar que el código no existe.
        setSugerencias([]);
        setCodigoDesconocido(false);
        setVigenteSugerido(null);
        setProductoConfirmado(null);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [producto, productoInicial, alcance]);

  // Stock, en camino, lo que pide el sistema, venta diaria y lo que ya hay
  // cargado: con eso la pantalla calcula cada frase mientras se escribe.
  useEffect(() => {
    setCtx(null);
    setCtxFallo(false);
    setReemplazar(true);
    const codigo = productoConfirmado;
    const listo = open && alcance === "uno" && !!codigo && !!sucursal;
    setCargandoCtx(listo);
    if (!listo || !codigo) return;
    let vigente = true;
    const t = setTimeout(async () => {
      try {
        const c = await api.contextoSugerencia(codigo, sucursal);
        if (vigente) setCtx(c);
      } catch {
        if (vigente) setCtxFallo(true);
      } finally {
        if (vigente) setCargandoCtx(false);
      }
    }, 200);
    return () => {
      vigente = false;
      clearTimeout(t);
    };
  }, [open, alcance, productoConfirmado, sucursal]);

  const filtrosVarios: SugeridoFiltros = useMemo(
    () => ({
      sucursales: gSucursales,
      proveedores: gProveedores,
      abc: gAbc,
      solo_pedir: soloPedir,
    }),
    [gSucursales, gProveedores, gAbc, soloPedir]
  );

  // Conteo en vivo de productos afectados (Varios productos).
  useEffect(() => {
    if (!open || alcance !== "varios") return;
    setContando(true);
    const t = setTimeout(async () => {
      try {
        setConteo(await api.contar(filtrosVarios));
      } catch {
        setConteo(null);
      } finally {
        setContando(false);
      }
    }, 300);
    return () => clearTimeout(t);
  }, [open, alcance, filtrosVarios]);

  const n = parseInt(numeros[frase], 10);
  const numeroValido = Number.isFinite(n) && n > 0;

  const nombreSuc = useMemo(() => {
    const s = sucursales.find((x) => x.sucursal_id === sucursal);
    return s ? nombreEnFrase(s.nombre ?? s.sucursal_id) : "";
  }, [sucursales, sucursal]);
  const enSuc = nombreSuc || "la sucursal";

  const calculo = alcance === "uno" && ctx && numeroValido ? calcular(frase, ctx, n) : null;
  const resultado =
    alcance === "uno" && ctx && numeroValido ? textoResultado(frase, ctx, n) : null;
  const existentes = ctx ? ctx.vigentes.length + ctx.reglas.length : 0;
  const expiraUna = plazo === "nunca" ? undefined : fechaEnDias(Number(plazo));
  const lineasQueEntran =
    previaPegada?.lineas.filter((l) => l.unidades_resultantes !== null).length ?? 0;

  const elegirFrase = (f: Frase) => {
    setFrase(f);
    setError(null);
  };
  const cambiarNumero = (f: Frase, v: string) => {
    setNumeros((prev) => ({ ...prev, [f]: v }));
    elegirFrase(f);
  };

  /** Primer problema del formulario, o null si está listo para guardar. */
  const validar = (): string | null => {
    if (alcance === "lista") {
      if (!textoPegado.trim()) return "Pega la lista de productos.";
      if (!previaPegada) return "Aprieta “Revisar la lista” antes de guardar.";
      if (!lineasQueEntran) return "Ninguna línea de la lista se puede cargar. Revisa los errores.";
      return null;
    }
    if (alcance === "uno" && (!producto.trim() || !sucursal))
      return "Elige el producto y la sucursal.";
    if (!numeroValido) return "Escribe un número mayor que cero.";
    if (alcance === "uno" && frase === "dias" && calculo?.sinDemanda)
      return "Este producto no tiene venta registrada en esta sucursal: los días no se pueden pasar a unidades. Usa “nunca haya menos de”.";
    if (alcance === "varios" && !conteo)
      return "Ningún producto cumple esos filtros. Cambia la selección.";
    if (frase !== "una" && hastaFecha && !fechaFin) return "Elige hasta qué fecha sigue la regla.";
    return null;
  };

  /** Manda la lista al servidor para ver qué se crearía, sin escribir nada. */
  const revisarLista = async () => {
    setError(null);
    setLeyendo(true);
    try {
      setPreviaPegada(await api.crearSugerenciasPegadas(textoPegado, { previsualizar: true }));
    } catch (e) {
      setPreviaPegada(null);
      setError(e instanceof Error ? e.message : "No se pudo leer la lista");
    } finally {
      setLeyendo(false);
    }
  };

  const guardar = async () => {
    const problema = validar();
    if (problema) {
      setError(problema);
      return;
    }
    setError(null);
    setGuardando(true);
    const motivoFinal = motivo.trim() || undefined;
    const fin = hastaFecha && fechaFin ? fechaFin : undefined;
    const cantidadRegla = frase === "min" ? { stock_objetivo: n } : { dias_inventario: n };
    try {
      if (alcance === "lista") {
        await api.crearSugerenciasPegadas(textoPegado, {
          motivo: motivoFinal,
          expiraEn: expiraUna,
        });
      } else if (alcance === "uno") {
        const codigo = productoConfirmado ?? producto.trim();
        const reemplazarLoQueHay = existentes > 0 && reemplazar;
        if (frase === "una") {
          await api.crearSugerenciaManual({
            producto: codigo,
            sucursal_id: sucursal,
            unidades: n,
            expira_en: expiraUna,
            motivo: motivoFinal,
            reemplazar: reemplazarLoQueHay,
          });
        } else {
          await api.crearRecurrente({
            modo: "individual",
            producto: codigo,
            sucursal_id: sucursal,
            ...cantidadRegla,
            cada_dias: 1,
            fecha_fin: fin,
            motivo: motivoFinal,
            reemplazar: reemplazarLoQueHay,
          });
        }
      } else if (frase === "una") {
        await api.crearSugerenciaMasiva(filtrosVarios, { unidades: n }, motivoFinal, expiraUna);
      } else {
        await api.crearRecurrente({
          modo: "grupo",
          filtros: filtrosVarios,
          ...cantidadRegla,
          cada_dias: 1,
          fecha_fin: fin,
          motivo: motivoFinal,
        });
      }
      onGuardado();
      onClose();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  };

  const productos =
    conteo === null ? "los productos" : conteo === 1 ? "1 producto" : `${formatoNumero(conteo)} productos`;
  const etiquetaBoton = guardando
    ? "Guardando…"
    : alcance === "lista"
      ? lineasQueEntran
        ? `Cargar ${formatoNumero(lineasQueEntran)} línea${lineasQueEntran === 1 ? "" : "s"}`
        : "Cargar la lista"
      : alcance === "varios"
        ? frase === "una"
          ? `Agregar a ${productos}`
          : `Guardar regla para ${productos}`
        : frase === "una"
          ? "Agregar a la compra"
          : "Guardar regla";

  // Lo que pasa después de guardar, bajo la frase elegida.
  const varios = alcance === "varios";
  const hasta = hastaFecha && fechaFin ? ` Sigue hasta el ${formatoFecha(fechaFin)}.` : "";
  const notaUna =
    plazo === "nunca"
      ? varios
        ? "Cada una se borra sola cuando la marques como pedida. Sin plazo: si nadie las compra, siguen sumándose hasta que las borres."
        : "Se borra sola cuando la marques como pedida. Sin plazo: si nadie la compra, sigue sumándose hasta que la borres."
      : varios
        ? `Cada una se borra sola cuando la marques como pedida. Si nadie las compra, a los ${plazo} días.`
        : `Se borra sola cuando la marques como pedida. Si nadie la compra, a los ${plazo} días.`;
  const notaMin = `No compra todos los días: cada día revisa el stock y pide solo lo que falte. Lo que ya viene en camino no se vuelve a pedir.${hasta}`;
  const notaDias = `No compra todos los días: cada día revisa el stock con la venta del momento y pide solo lo que falte. Si se vende más, pide más.${varios ? " Los productos sin venta registrada no piden nada." : ""}${hasta}`;

  const pista =
    alcance !== "uno" || resultado
      ? null
      : !producto.trim() || !sucursal
        ? "Elige producto y sucursal para ver cuánto se compra hoy."
        : cargandoCtx
          ? "Calculando…"
          : !productoConfirmado
            ? "Elige el producto de la lista para ver cuánto se compra hoy."
            : ctx && !numeroValido
              ? "Escribe la cantidad para ver cuánto se compra hoy."
              : null;

  const recuadro = resultado ? (
      <div
        aria-live="polite"
        className={cn(
          "mt-2 rounded-md px-3 py-2",
          calculo?.sinDemanda ? "bg-amber-50 text-amber-800" : "bg-brand-50 text-brand-900"
        )}
      >
        <p className="text-[14px] font-semibold">{resultado.titulo}</p>
        <p className="mt-0.5 text-[12.5px]">{resultado.detalle}</p>
      </div>
    ) : pista ? (
      <p className="mt-1 text-[12px] text-ink-500">{pista}</p>
    ) : null;

  const pie = (nota: string) => (
    <>
      {recuadro}
      <p className="mt-1.5 text-[12px] leading-snug text-ink-500">{nota}</p>
    </>
  );

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title="Agregar sugerencia manual"
      description="Lo que el modelo no ve: un pedido de taller, una promoción o un mínimo que quieres tener."
      className="max-w-xl"
    >
      <div className="space-y-4">
        {!soloIndividual && (
          <div className="grid grid-cols-3 gap-2">
            {PESTANAS.map((t) => (
              <button
                key={t.id}
                type="button"
                aria-pressed={alcance === t.id}
                onClick={() => {
                  setAlcance(t.id);
                  setError(null);
                }}
                className={cn(
                  "flex flex-col items-start gap-0.5 rounded-lg border px-2.5 py-2 text-left transition-colors",
                  alcance === t.id
                    ? "border-brand bg-brand-50 text-brand"
                    : "border-slate-200 text-slate-600 hover:bg-slate-50"
                )}
              >
                <span className="text-[13px] font-medium">{t.label}</span>
                <span className="text-[11px] text-slate-400">{t.sub}</span>
              </button>
            ))}
          </div>
        )}

        {/* --- Un producto --- */}
        {alcance === "uno" && (
          <div>
            <div className="grid grid-cols-1 gap-2.5 sm:grid-cols-[minmax(0,1.7fr)_minmax(0,1fr)]">
              <div className="relative">
                <Label htmlFor="sug-producto">Producto</Label>
                <Input
                  id="sug-producto"
                  value={producto}
                  onChange={(e) => {
                    elegidoDeLaLista.current = null;
                    setProducto(e.target.value);
                  }}
                  placeholder="Código del producto"
                  autoComplete="off"
                />
                {sugerencias.length > 0 && (
                  <div className="absolute z-20 mt-1 w-full overflow-hidden rounded-md border border-slate-200 bg-white shadow-lg">
                    {sugerencias.map((p) => (
                      <button
                        key={p.producto}
                        type="button"
                        onClick={() => {
                          elegidoDeLaLista.current = p.producto;
                          setProducto(p.producto);
                          setProductoConfirmado(p.producto);
                          setVigenteSugerido(p.reemplazado_por ?? null);
                          setCodigoDesconocido(false);
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
              </div>
              <div>
                <Label htmlFor="sug-sucursal">Sucursal</Label>
                <select
                  id="sug-sucursal"
                  value={sucursal}
                  onChange={(e) => setSucursal(e.target.value)}
                  className={cn(CLASE_SELECT, "w-full")}
                >
                  <option value="">Elige…</option>
                  {sucursales.map((s) => (
                    <option key={s.sucursal_id} value={s.sucursal_id}>
                      {s.nombre ?? s.sucursal_id}
                    </option>
                  ))}
                </select>
              </div>
            </div>

            {codigoDesconocido && (
              <p className="mt-1.5 flex items-start gap-1.5 text-[11.5px] text-amber-700">
                <TriangleAlert size={13} className="mt-px shrink-0" />
                <span>
                  Ese código no existe en el catálogo. Revísalo: si lo guardas así, la fila
                  queda sin descripción, proveedor ni costo.
                </span>
              </p>
            )}
            {vigenteSugerido && (
              <p className="mt-1.5 flex items-start gap-1.5 text-[11.5px] text-rose-700">
                <TriangleAlert size={13} className="mt-px shrink-0" />
                <span>
                  FORD dio de baja este código. El vigente es{" "}
                  <span className="font-mono font-semibold">{vigenteSugerido}</span>.{" "}
                  <button
                    type="button"
                    onClick={() => {
                      elegidoDeLaLista.current = null;
                      setProducto(vigenteSugerido);
                    }}
                    className="font-medium underline hover:no-underline"
                  >
                    Usar el vigente
                  </button>
                  {" · "}
                  <span className="text-rose-500">
                    Puedes pedir el viejo igual si sabes lo que haces.
                  </span>
                </span>
              </p>
            )}

            {ctx ? (
              <p
                className="mt-2 text-[12px] text-ink-500"
                title={
                  ctx.bodegas.length
                    ? ctx.bodegas
                        .map((b) => `${b.bodega}: ${formatoNumero(b.stock)}`)
                        .join(", ")
                    : undefined
                }
              >
                {lineaContexto(ctx)}
              </p>
            ) : ctxFallo ? (
              <p className="mt-2 text-[12px] text-ink-500">
                No se pudo leer el stock de este producto. Igual puedes guardar.
              </p>
            ) : null}
          </div>
        )}

        {/* --- Varios productos --- */}
        {alcance === "varios" && (
          <div className="space-y-2.5">
            <p className="text-[12px] text-slate-500">
              Elige uno o varios filtros: se aplica a los productos que cumplan{" "}
              <b>todos</b>. Sin filtros, a todos los productos.
            </p>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-3">
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
            <label className="flex cursor-pointer select-none items-center gap-2 text-[13px] text-slate-700">
              <input
                type="checkbox"
                className="h-4 w-4 accent-brand"
                checked={soloPedir}
                onChange={(e) => setSoloPedir(e.target.checked)}
              />
              Solo productos con Pedir = Sí (recomendado)
            </label>
            <div
              className={cn(
                "flex items-center gap-2 rounded-md px-3 py-2 text-[13px]",
                conteo && conteo > 1000 ? "bg-amber-50 text-amber-800" : "bg-brand-50 text-brand"
              )}
            >
              {conteo !== null && conteo > 1000 && <TriangleAlert size={15} />}
              {contando ? (
                "Contando productos…"
              ) : conteo === null ? (
                "—"
              ) : (
                <span>
                  Se aplica a <b>{formatoNumero(conteo)}</b> producto
                  {conteo === 1 ? "" : "s"} (producto × sucursal).
                  {conteo > 1000 && " Es una carga grande, revísala antes de guardar."}
                </span>
              )}
            </div>
          </div>
        )}

        {/* --- Las tres frases (Un producto y Varios productos) --- */}
        {alcance !== "lista" && (
          <div>
            <p className="mb-2 text-[13px] font-medium text-ink-900">¿Qué quieres?</p>
            <div className="space-y-2">
              <Tarjeta
                activa={frase === "una"}
                onElegir={() => elegirFrase("una")}
                pie={pie(notaUna)}
              >
                <Radio
                  activa={frase === "una"}
                  onElegir={() => elegirFrase("una")}
                  etiqueta="Unidades más, una sola vez"
                />
                Quiero
                <NumeroEnLinea
                  valor={numeros.una}
                  onCambio={(v) => cambiarNumero("una", v)}
                  onElegir={() => elegirFrase("una")}
                  etiqueta="Unidades a agregar"
                  activa={frase === "una"}
                />
                {varios ? (
                  <>unidades más de cada producto, una sola vez.</>
                ) : (
                  <>
                    unidades más para <b>{enSuc}</b>, una sola vez.
                  </>
                )}
              </Tarjeta>

              <Tarjeta
                activa={frase === "min"}
                onElegir={() => elegirFrase("min")}
                pie={pie(notaMin)}
              >
                <Radio
                  activa={frase === "min"}
                  onElegir={() => elegirFrase("min")}
                  etiqueta="Nunca menos de cierta cantidad"
                />
                {varios ? (
                  <>Quiero que ningún producto baje de</>
                ) : (
                  <>
                    Quiero que en <b>{enSuc}</b> nunca haya menos de
                  </>
                )}
                <NumeroEnLinea
                  valor={numeros.min}
                  onCambio={(v) => cambiarNumero("min", v)}
                  onElegir={() => elegirFrase("min")}
                  etiqueta="Mínimo en unidades"
                  activa={frase === "min"}
                />
                unidades.
              </Tarjeta>

              <Tarjeta
                activa={frase === "dias"}
                onElegir={() => elegirFrase("dias")}
                pie={pie(notaDias)}
              >
                <Radio
                  activa={frase === "dias"}
                  onElegir={() => elegirFrase("dias")}
                  etiqueta="Que alcance para ciertos días de venta"
                />
                {varios ? (
                  <>Quiero que cada producto tenga siempre para</>
                ) : (
                  <>
                    Quiero que en <b>{enSuc}</b> siempre alcance para
                  </>
                )}
                <NumeroEnLinea
                  valor={numeros.dias}
                  onCambio={(v) => cambiarNumero("dias", v)}
                  onElegir={() => elegirFrase("dias")}
                  etiqueta="Días de venta"
                  activa={frase === "dias"}
                />
                días de venta.
              </Tarjeta>
            </div>
          </div>
        )}

        {/* Ya hay algo cargado para este producto y sucursal. */}
        {alcance === "uno" && ctx && existentes > 0 && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2.5 text-[12.5px] text-amber-800">
            {ctx.vigentes.length === 1 && (
              <p>
                Ya hay una sugerencia de {formatoNumero(ctx.vigentes[0].unidades)} unidades
                para este producto en <b>{enSuc}</b>
                {ctx.vigentes[0].creado_en
                  ? `, del ${formatoFecha(ctx.vigentes[0].creado_en).slice(0, 5)}`
                  : ""}
                .
              </p>
            )}
            {ctx.vigentes.length > 1 && (
              <p>
                Ya hay {ctx.vigentes.length} sugerencias para este producto en{" "}
                <b>{enSuc}</b>:{" "}
                {formatoNumero(ctx.vigentes.reduce((a, v) => a + (v.unidades || 0), 0))}{" "}
                unidades en total.
              </p>
            )}
            {ctx.reglas.map((r) => (
              <p key={r.id}>
                Ya hay una regla para este producto en <b>{enSuc}</b>: {describirRegla(r)}.
              </p>
            ))}
            <div className="mt-2 flex flex-wrap items-center gap-1.5">
              <button
                type="button"
                aria-pressed={reemplazar}
                onClick={() => setReemplazar(true)}
                className={cn(
                  "h-[30px] rounded-sm border px-3 text-[12.5px] font-medium transition-colors",
                  reemplazar ? "border-amber-300 bg-white" : "border-transparent hover:bg-amber-100"
                )}
              >
                {existentes === 1 ? "Reemplazarla" : "Reemplazarlas"}
              </button>
              <button
                type="button"
                aria-pressed={!reemplazar}
                onClick={() => setReemplazar(false)}
                className={cn(
                  "h-[30px] rounded-sm border px-3 text-[12.5px] font-medium transition-colors",
                  !reemplazar ? "border-amber-300 bg-white" : "border-transparent hover:bg-amber-100"
                )}
              >
                {existentes === 1 ? "Sumar las dos" : "Sumar todas"}
              </button>
              <span className="ml-1 text-[12px] text-amber-700">
                {reemplazar ? "Queda solo la nueva." : "Quedan todas y se suman."}
              </span>
            </div>
          </div>
        )}

        {/* --- Pegar lista --- */}
        {alcance === "lista" && (
          <div className="space-y-3">
            <div>
              <Label htmlFor="sug-pegado">Pega la lista</Label>
              <Textarea
                id="sug-pegado"
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
                Copia el rango desde Excel y pégalo. La primera fila puede ser el encabezado
                (da igual el orden de las columnas). Cada línea se carga una sola vez. Si trae
                más de una cantidad, manda <b>mantener</b>, después <b>días</b> y al final{" "}
                <b>unidades</b>.
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
                    <b>{formatoNumero(lineasQueEntran)}</b> líneas se van a cargar
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
                      <li className="text-red-600">y {previaPegada.errores.length - 6} más…</li>
                    )}
                  </ul>
                )}
              </div>
            )}
          </div>
        )}

        {/* --- Más opciones --- */}
        <div>
          <button
            type="button"
            aria-expanded={masOpciones}
            onClick={() => setMasOpciones((v) => !v)}
            className="py-1 text-[12.5px] font-medium text-brand hover:text-brand-700"
          >
            {masOpciones ? "Menos opciones" : "Más opciones"}
          </button>
          {masOpciones && (
            <div className="mt-2 space-y-3 border-t border-ink-100 pt-3">
              <div>
                <Label htmlFor="sug-motivo">Motivo (opcional)</Label>
                <Input
                  id="sug-motivo"
                  value={motivo}
                  onChange={(e) => setMotivo(e.target.value)}
                  placeholder="Pedido especial de taller"
                />
              </div>
              {alcance === "lista" || frase === "una" ? (
                <div>
                  <Label htmlFor="sug-plazo">
                    {alcance === "uno"
                      ? "Si nadie la compra, borrarla a los"
                      : "Si nadie las compra, borrarlas a los"}
                  </Label>
                  <select
                    id="sug-plazo"
                    value={plazo}
                    onChange={(e) => setPlazo(e.target.value as Plazo)}
                    className={cn(CLASE_SELECT, "w-48")}
                  >
                    {PLAZOS.map((p) => (
                      <option key={p.value} value={p.value}>
                        {p.label}
                      </option>
                    ))}
                  </select>
                  {plazo === "nunca" && (
                    <p className="mt-1 flex items-start gap-1.5 text-[11.5px] text-amber-700">
                      <TriangleAlert size={13} className="mt-px shrink-0" />
                      <span>
                        Sin plazo sigue sumándose a la compra todos los días hasta que la
                        marques como pedida o la borres.
                      </span>
                    </p>
                  )}
                </div>
              ) : (
                <div>
                  <Label htmlFor="sug-hasta">¿Hasta cuándo?</Label>
                  <div className="flex flex-wrap items-center gap-2">
                    <select
                      id="sug-hasta"
                      value={hastaFecha ? "fecha" : "siempre"}
                      onChange={(e) => setHastaFecha(e.target.value === "fecha")}
                      className={cn(CLASE_SELECT, "w-48")}
                    >
                      <option value="siempre">Hasta que la borre</option>
                      <option value="fecha">Hasta una fecha…</option>
                    </select>
                    {hastaFecha && (
                      <Input
                        type="date"
                        aria-label="Último día de la regla"
                        min={hoyISO}
                        value={fechaFin}
                        onChange={(e) => setFechaFin(e.target.value)}
                        className="w-44"
                      />
                    )}
                  </div>
                </div>
              )}
            </div>
          )}
        </div>

        {error && (
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">
            {error}
          </p>
        )}

        <div className="flex items-center justify-between gap-2 border-t border-slate-100 pt-3">
          <a
            href="/modelo#manuales"
            target="_blank"
            rel="noopener noreferrer"
            className="text-[12px] text-ink-500 hover:text-ink-800 hover:underline"
          >
            Cómo funciona
          </a>
          <div className="flex gap-2">
            <Button variant="outline" onClick={onClose}>
              Cancelar
            </Button>
            <Button onClick={() => void guardar()} disabled={guardando}>
              {etiquetaBoton}
            </Button>
          </div>
        </div>
      </div>
    </Dialog>
  );
}
