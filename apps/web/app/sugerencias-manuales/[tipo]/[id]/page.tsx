"use client";

/**
 * Detalle de una sugerencia manual: qué productos toca y cuánto aporta cada uno.
 *
 * La lista de sugerencias mostraba el titular ("mantener 2 u", "65 repuestos") y
 * nada más. Con reglas que abarcan decenas de productos eso deja al comprador sin
 * poder responder la única pregunta que importa: **¿esto está sirviendo o es peso
 * muerto?**
 *
 * Por eso la pantalla se organiza alrededor de esa pregunta y no alrededor de la
 * lista: arriba va cuánto está aportando de verdad, y cada línea que no aporta
 * dice por qué. Al activar InStock en producción, 97 de sus 262 líneas no agregan
 * una sola unidad porque el stock, el tránsito o el modelo ya cubren el mínimo —
 * y hasta ahora se veían idénticas a las 165 que sí aportan.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  Download,
  Loader2,
  Lock,
  Pause,
  Play,
  Search,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { ComoSeCalcula } from "@/components/como-se-calcula";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { DetalleSugerencia, LineaDetalleSugerencia } from "@/lib/types";

type Filtro = "todas" | "aportan" | "sin_efecto";

export default function DetalleSugerenciaPage() {
  const params = useParams<{ tipo: string; id: string }>();
  const router = useRouter();
  const tipo = params?.tipo ?? "";
  const id = decodeURIComponent(params?.id ?? "");

  const [d, setD] = useState<DetalleSugerencia | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [ocupado, setOcupado] = useState(false);

  // Filtros de la lista.
  const [q, setQ] = useState("");
  const [sucursal, setSucursal] = useState("");
  const [proveedor, setProveedor] = useState("");
  const [abc, setAbc] = useState("");
  const [filtro, setFiltro] = useState<Filtro>("todas");
  // La explicación del cálculo va colapsada: se lee una vez y después estorba.
  const [infoAbierta, setInfoAbierta] = useState(false);

  const cargar = async () => {
    try {
      setD(await api.detalleSugerencia(tipo, id));
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar");
    }
  };

  useEffect(() => {
    if (tipo && id) cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [tipo, id]);

  const lineas = d?.lineas ?? [];

  const opciones = useMemo(() => {
    const uniq = (xs: (string | null)[]) =>
      Array.from(new Set(xs.filter((x): x is string => !!x))).sort();
    return {
      sucursales: uniq(lineas.map((l) => l.nombre_sucursal ?? l.sucursal_id)),
      proveedores: uniq(lineas.map((l) => l.proveedor)),
      abc: uniq(lineas.map((l) => l.clasificacion_abc)),
    };
  }, [lineas]);

  const visibles = useMemo(() => {
    const texto = q.trim().toLowerCase();
    return lineas.filter((l) => {
      if (filtro === "aportan" && l.estado !== "aporta") return false;
      if (filtro === "sin_efecto" && l.estado === "aporta") return false;
      if (sucursal && (l.nombre_sucursal ?? l.sucursal_id) !== sucursal) return false;
      if (proveedor && l.proveedor !== proveedor) return false;
      if (abc && l.clasificacion_abc !== abc) return false;
      if (texto) {
        const heno = `${l.producto} ${l.descripcion ?? ""} ${l.modelos ?? ""} ${
          l.operacion ?? ""
        }`.toLowerCase();
        if (!heno.includes(texto)) return false;
      }
      return true;
    });
  }, [lineas, q, sucursal, proveedor, abc, filtro]);

  const totalVisible = useMemo(
    () => ({
      unidades: visibles.reduce((s, l) => s + (l.estado === "aporta" ? l.aporta : 0), 0),
      valor: visibles.reduce(
        (s, l) => s + (l.estado === "aporta" ? l.valor_aporte_clp ?? 0 : 0),
        0
      ),
    }),
    [visibles]
  );

  /** Dos líneas reales para explicar el cálculo: una que aporta y otra que no.
   *
   *  Lo ideal es que sean el MISMO producto en dos sucursales distintas — misma
   *  regla, mismo mínimo, resultado opuesto. Puesto uno al lado del otro se
   *  entiende de una; por separado no. Si no hay un producto que cumpla las dos
   *  condiciones, se toma la mejor pareja disponible. */
  const ejemplos = useMemo(() => {
    const conAporte = lineas.filter((l) => l.estado === "aporta");
    const sinAporte = lineas.filter((l) => l.estado !== "aporta");
    const mismoProducto = conAporte.find((a) =>
      sinAporte.some((s) => s.producto === a.producto)
    );
    if (mismoProducto) {
      return {
        aporta: mismoProducto,
        noAporta: sinAporte.find((s) => s.producto === mismoProducto.producto) ?? null,
      };
    }
    return { aporta: conAporte[0] ?? null, noAporta: sinAporte[0] ?? null };
  }, [lineas]);

  const hayFiltro = !!(q || sucursal || proveedor || abc || filtro !== "todas");
  const limpiar = () => {
    setQ("");
    setSucursal("");
    setProveedor("");
    setAbc("");
    setFiltro("todas");
  };

  const pausar = async (activa: boolean) => {
    if (
      !activa &&
      !confirm(
        "¿Pausar esta regla? Deja de dispararse y sus ajustes vigentes se archivan, así que la compra baja."
      )
    )
      return;
    setOcupado(true);
    try {
      await api.pausarRecurrente(id, activa);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cambiar el estado");
    } finally {
      setOcupado(false);
    }
  };

  const borrarLinea = async (linea: LineaDetalleSugerencia) => {
    if (!confirm(`¿Sacar ${linea.producto} de esta sugerencia?`)) return;
    setOcupado(true);
    try {
      await api.eliminarSugerenciaManual(linea.id);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar");
    } finally {
      setOcupado(false);
    }
  };

  if (error && !d) {
    return (
      <div className="mx-auto max-w-5xl space-y-3">
        <Link
          href="/sugerencias-manuales"
          className="inline-flex items-center gap-1 text-[13px] text-slate-500 hover:text-brand"
        >
          <ArrowLeft size={14} /> Sugerencias manuales
        </Link>
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
          {error}
        </div>
      </div>
    );
  }
  if (!d) {
    return (
      <div className="flex items-center gap-2 px-4 py-10 text-[13.5px] text-slate-400">
        <Loader2 size={15} className="animate-spin" /> Cargando…
      </div>
    );
  }

  const t = d.totales;
  const esInstock = d.tipo === "instock";
  const esRecurrente = d.tipo === "recurrente";
  const puedeBorrarLineas = d.tipo === "lote" || d.tipo === "unica";

  return (
    <div className="mx-auto max-w-6xl space-y-4">
      <div>
        <Link
          href="/sugerencias-manuales"
          className="inline-flex items-center gap-1 text-[13px] text-slate-500 hover:text-brand"
        >
          <ArrowLeft size={14} /> Sugerencias manuales
        </Link>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">{d.titulo}</h1>
          {esInstock && (
            <span className="inline-flex items-center gap-1 rounded bg-slate-100 px-2 py-0.5 text-[11px] text-slate-600">
              <Lock size={11} /> regla del sistema
            </span>
          )}
          {esRecurrente && !d.activa && (
            <span className="rounded bg-amber-100 px-2 py-0.5 text-[11px] font-medium text-amber-800">
              pausada
            </span>
          )}
        </div>
        <p className="text-[13px] text-slate-500">{d.subtitulo}</p>
        <p className="mt-1 text-[12px] text-slate-400">
          {d.creado_por && <>{d.creado_por} · </>}
          {d.creado_en && formatoFechaHora(d.creado_en)}
          {esRecurrente && d.ultima_ejecucion && <> · última corrida {d.ultima_ejecucion}</>}
          {esRecurrente && d.proxima_ejecucion && d.activa && (
            <> · próxima {d.proxima_ejecucion}</>
          )}
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
          {error}
        </div>
      )}

      {/* Lo primero: cuánto está aportando de verdad. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Tarjeta titulo="Aporta a la compra" valor={`${formatoNumero(t.unidades)} u`} />
        <Tarjeta titulo="Valorizado" valor={formatoCLP(t.valor_clp)} />
        <Tarjeta
          titulo="Líneas que aportan"
          valor={`${formatoNumero(t.n_aportan)} de ${formatoNumero(t.n_lineas)}`}
        />
        <Tarjeta
          titulo="Sin efecto hoy"
          valor={formatoNumero(t.n_sin_efecto)}
          alerta={t.n_sin_efecto > 0}
        />
      </div>

      {t.n_sin_efecto > 0 && (
        <div className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-900">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>
            <b>{formatoNumero(t.n_sin_efecto)}</b>{" "}
            {t.n_sin_efecto === 1 ? "línea no está agregando" : "líneas no están agregando"}{" "}
            nada a la compra: el stock, el tránsito o lo que el modelo ya pide alcanzan
            para cubrirlas. No es un error —{" "}
            {esInstock
              ? "es la regla trabajando bien"
              : "puede que la sugerencia ya no haga falta"}
            . Filtra por «sin efecto» para verlas.
          </span>
        </div>
      )}

      <ComoSeCalcula
        abierta={infoAbierta}
        onToggle={() => setInfoAbierta((v) => !v)}
        esInstock={esInstock}
        ejemplos={ejemplos}
      />

      {/* Acciones */}
      <div className="flex flex-wrap items-center gap-2">
        <Button variant="outline" size="sm" onClick={() => api.detalleSugerenciaExcel(tipo, id)}>
          <Download size={14} /> Bajar a Excel
        </Button>
        {esRecurrente && (
          <Button
            variant="outline"
            size="sm"
            onClick={() => pausar(!d.activa)}
            disabled={ocupado}
          >
            {d.activa ? <Pause size={14} /> : <Play size={14} />}
            {d.activa ? "Pausar la regla" : "Reactivar"}
          </Button>
        )}
      </div>

      {/* Filtros */}
      <div className="flex flex-wrap items-center gap-2 rounded-md border border-slate-200 bg-white p-3">
        <div className="relative">
          <Search
            size={14}
            className="pointer-events-none absolute left-2.5 top-1/2 -translate-y-1/2 text-slate-400"
          />
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Buscar código o descripción…"
            className="h-8 w-[240px] rounded-md border border-slate-200 bg-slate-50 pl-7 pr-2 text-[13px] focus-visible:border-brand focus-visible:bg-white focus-visible:outline-none"
          />
        </div>
        {opciones.sucursales.length > 1 && (
          <Select value={sucursal} onChange={setSucursal} vacio="Todas las sucursales"
                  opciones={opciones.sucursales} />
        )}
        {opciones.proveedores.length > 1 && (
          <Select value={proveedor} onChange={setProveedor} vacio="Todos los proveedores"
                  opciones={opciones.proveedores} />
        )}
        {opciones.abc.length > 1 && (
          <Select value={abc} onChange={setAbc} vacio="Todas las clases" opciones={opciones.abc} />
        )}
        <div className="flex items-center gap-1 rounded-md border border-slate-200 p-0.5">
          {(
            [
              ["todas", "Todas"],
              ["aportan", "Aportan"],
              ["sin_efecto", "Sin efecto"],
            ] as [Filtro, string][]
          ).map(([v, txt]) => (
            <button
              key={v}
              onClick={() => setFiltro(v)}
              className={`rounded px-2 py-1 text-[12.5px] transition-colors ${
                filtro === v ? "bg-slate-900 font-medium text-white" : "text-slate-600 hover:bg-slate-100"
              }`}
            >
              {txt}
            </button>
          ))}
        </div>
        {hayFiltro && (
          <button
            onClick={limpiar}
            className="inline-flex items-center gap-1 text-[12.5px] text-slate-500 hover:text-brand"
          >
            <X size={13} /> Limpiar filtros
          </button>
        )}
        <span className="ml-auto text-[12.5px] text-slate-500">
          {formatoNumero(visibles.length)} de {formatoNumero(lineas.length)} ·{" "}
          <b className="text-slate-900">{formatoNumero(totalVisible.unidades)} u</b> ·{" "}
          <b className="text-slate-900">{formatoCLP(totalVisible.valor)}</b>
        </span>
      </div>

      {/* La lista */}
      <div className="overflow-x-auto rounded-md border border-slate-200 bg-white">
        <table className="w-full min-w-[980px] text-[13px]">
          <thead>
            <tr className="border-b border-slate-200 bg-slate-50 text-left text-[11.5px] uppercase tracking-wide text-slate-500">
              <th className="px-3 py-2">Producto</th>
              <th className="px-3 py-2">Sucursal</th>
              {esInstock && <th className="px-3 py-2">Pauta</th>}
              <th className="px-3 py-2">ABC</th>
              <th className="px-3 py-2 text-right">Stock</th>
              <th className="px-3 py-2 text-right">Tránsito</th>
              <th
                className="px-3 py-2 text-right"
                title="Lo que el modelo del BI pide por su cuenta, sin esta sugerencia."
              >
                Pide el modelo
              </th>
              <th
                className="px-3 py-2 text-right"
                title="Unidades que esta sugerencia agrega a la compra. Ver «+ info» arriba."
              >
                Aporta esto
              </th>
              <th className="px-3 py-2 text-right">Valorizado</th>
              {puedeBorrarLineas && <th className="w-10 px-3 py-2"></th>}
            </tr>
          </thead>
          <tbody>
            {visibles.map((l) => (
              <tr
                key={l.id}
                className={`border-b border-slate-100 ${
                  l.estado !== "aporta" ? "bg-slate-50/60 text-slate-500" : ""
                }`}
              >
                <td className="px-3 py-2">
                  <span className="font-medium text-slate-900">{l.producto}</span>
                  <span className="block max-w-[280px] truncate text-[12px] text-slate-500">
                    {l.descripcion ?? "—"}
                  </span>
                  {l.estado !== "aporta" && l.motivo_sin_efecto && (
                    <span className="mt-0.5 block text-[11.5px] text-amber-700">
                      {l.motivo_sin_efecto}
                    </span>
                  )}
                  {l.redundante && l.estado === "aporta" && (
                    <span className="mt-0.5 block text-[11.5px] text-amber-700">
                      el modelo ya pide {formatoNumero(l.sugerido_modelo ?? 0)} por su cuenta
                    </span>
                  )}
                </td>
                <td className="px-3 py-2">{l.nombre_sucursal ?? l.sucursal_id}</td>
                {esInstock && (
                  <td className="max-w-[180px] px-3 py-2 text-[12px] text-slate-500">
                    {l.marca} {l.modelos && <span className="block">{l.modelos}</span>}
                  </td>
                )}
                <td className="px-3 py-2">{l.clasificacion_abc ?? "—"}</td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatoNumero(l.stock_actual ?? 0)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatoNumero(l.stock_transito ?? 0)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums text-slate-500">
                  {l.sugerido_modelo === null ? "—" : formatoNumero(l.sugerido_modelo)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {l.estado === "aporta" ? (
                    <span className="font-semibold text-emerald-700">
                      +{formatoNumero(l.aporta)}
                    </span>
                  ) : (
                    <span className="text-slate-400">0</span>
                  )}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">
                  {l.estado === "aporta" ? formatoCLP(l.valor_aporte_clp ?? 0) : "—"}
                </td>
                {puedeBorrarLineas && (
                  <td className="px-3 py-2">
                    <button
                      onClick={() => borrarLinea(l)}
                      disabled={ocupado}
                      className="text-slate-300 transition-colors hover:text-red-600"
                      aria-label={`Sacar ${l.producto}`}
                    >
                      <Trash2 size={15} />
                    </button>
                  </td>
                )}
              </tr>
            ))}
            {visibles.length === 0 && (
              <tr>
                <td colSpan={10} className="px-3 py-10 text-center text-slate-400">
                  Ninguna línea calza con esos filtros.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {/* InStock: los part numbers de la pauta que no existen en el maestro. */}
      {esInstock && (d.pautas_sin_codigo?.length ?? 0) > 0 && (
        <div className="rounded-md border border-amber-200 bg-amber-50/50 p-4">
          <p className="text-[13px] font-semibold text-slate-900">
            {formatoNumero(d.pautas_sin_codigo!.length)} repuestos de la pauta no existen en
            el maestro de Curifor
          </p>
          <p className="mt-0.5 text-[12.5px] text-slate-600">
            No se marcan, así que la regla no los cubre. Pueden ser códigos que se dejaron
            de usar o que están bajo otro rubro; hay que revisarlos con Repuestos.
          </p>
          <div className="mt-2 overflow-x-auto">
            <table className="w-full min-w-[520px] text-[12.5px]">
              <thead>
                <tr className="text-left text-[11px] uppercase tracking-wide text-slate-500">
                  <th className="py-1 pr-3">Marca</th>
                  <th className="py-1 pr-3">Part number</th>
                  <th className="py-1 pr-3">Operación</th>
                  <th className="py-1">Modelos</th>
                </tr>
              </thead>
              <tbody>
                {d.pautas_sin_codigo!.map((p) => (
                  <tr key={p.part_number} className="border-t border-amber-100">
                    <td className="py-1 pr-3">{p.marca ?? "—"}</td>
                    <td className="py-1 pr-3 font-mono">{p.part_number}</td>
                    <td className="py-1 pr-3">{p.operacion ?? "—"}</td>
                    <td className="py-1">{p.modelos ?? "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* Historial */}
      {d.historial.length > 0 && (
        <div className="rounded-md border border-slate-200 bg-white p-4">
          <p className="text-[13px] font-semibold text-slate-900">Historial</p>
          <p className="mt-0.5 text-[12.5px] text-slate-500">
            Sirve para saber si esto se sigue ejecutando o quedó detenido.
          </p>
          <ul className="mt-2 space-y-1.5">
            {d.historial.map((h, i) => (
              <li key={i} className="flex items-start gap-2 text-[12.5px]">
                <Check size={13} className="mt-0.5 shrink-0 text-slate-300" />
                <span className="text-slate-500">
                  <span className="text-slate-700">{formatoFechaHora(h.creado_en)}</span> ·{" "}
                  {h.accion.replace(/_/g, " ")}
                  {h.usuario_email && <> · {h.usuario_email}</>}
                  {h.detalle && <> · {h.detalle}</>}
                </span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}

function Tarjeta({
  titulo,
  valor,
  alerta,
}: {
  titulo: string;
  valor: string;
  alerta?: boolean;
}) {
  return (
    <div
      className={`rounded-md border p-3 ${
        alerta ? "border-amber-200 bg-amber-50/50" : "border-slate-200 bg-white"
      }`}
    >
      <p className="text-[11.5px] uppercase tracking-wide text-slate-500">{titulo}</p>
      <p
        className={`mt-0.5 text-[19px] font-semibold ${
          alerta ? "text-amber-800" : "text-slate-900"
        }`}
      >
        {valor}
      </p>
    </div>
  );
}

function Select({
  value,
  onChange,
  vacio,
  opciones,
}: {
  value: string;
  onChange: (v: string) => void;
  vacio: string;
  opciones: string[];
}) {
  return (
    <select
      value={value}
      onChange={(e) => onChange(e.target.value)}
      className="h-8 rounded-md border border-slate-200 bg-slate-50 px-2 text-[13px]"
    >
      <option value="">{vacio}</option>
      {opciones.map((o) => (
        <option key={o} value={o}>
          {o}
        </option>
      ))}
    </select>
  );
}
