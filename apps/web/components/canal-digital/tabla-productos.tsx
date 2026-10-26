"use client";

// Productos de la bodega con su cluster, stock, posicion y sugerido. Al elegir uno se explica paso a paso.
import { useCallback, useEffect, useState } from "react";
import { Download, Search } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import {
  canalDigitalApi,
  NOMBRE_MODO,
  type PasoCanalDigital,
  type ProductoCanalDigital,
  type ProductosCanalDigital,
} from "@/lib/canal-digital";

interface Props {
  bodega: string;
  /** "sugerido": solo lo que hoy pide, de mayor a menor valor; "todos": cualquier producto con sus filtros. */
  modo?: "sugerido" | "todos";
  clusterInicial?: string | null;
  onLimpiarCluster?: () => void;
}

const ESTADOS = ["", "CLASIFICADO", "NUEVO", "SIN MOVIMIENTO"];
const NOMBRE_AVISO: Record<string, string> = {
  HISTORIA_CORTA: "Historia corta: tiene menos de 52 semanas de venta",
  MUESTRA_INSUFICIENTE: "Muestra insuficiente para estimar la variación",
  MINIMO_POR_DEFECTO: "Mínimo de compra sin dato: se usa 1",
  MULTIPLO_POR_DEFECTO: "Múltiplo sin dato: se usa 1",
  COMPROMETIDO_SIN_DATO: "El ERP no informa reservas: comprometido 0",
};

export function TablaProductos({ bodega, modo = "todos", clusterInicial, onLimpiarCluster }: Props) {
  const sugerido = modo === "sugerido";
  const [q, setQ] = useState("");
  const [estado, setEstado] = useState("");
  const [soloPideManual, setSoloPide] = useState(false);
  const soloPide = sugerido || soloPideManual;
  const [data, setData] = useState<ProductosCanalDigital | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [elegido, setElegido] = useState<ProductoCanalDigital | null>(null);

  const filtros = useCallback(
    () => ({
      cluster: clusterInicial ?? undefined,
      estado: estado || undefined,
      q: q.trim() || undefined,
      solo_pide: soloPide,
      orden: sugerido ? ("sugerido" as const) : undefined,
    }),
    [clusterInicial, estado, q, soloPide, sugerido]
  );

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      setData(await canalDigitalApi.productos(bodega, filtros()));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al consultar");
    } finally {
      setCargando(false);
    }
  }, [bodega, filtros]);

  useEffect(() => {
    cargar();
    // Se vuelve a consultar al cambiar estado, "solo pide" o el cluster; el texto, al apretar Buscar o Enter.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [bodega, clusterInicial, estado, soloPide, sugerido]);

  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-end gap-3">
        <label className="block">
          <span className="mb-1 block text-[12px] font-medium text-slate-600">Producto o descripción</span>
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            onKeyDown={(e) => e.key === "Enter" && cargar()}
            placeholder="Código o parte del nombre"
            className="w-64 rounded-md border border-slate-300 px-3 py-1.5 text-[13px]"
          />
        </label>
        {!sugerido && (
          <>
            <label className="block">
              <span className="mb-1 block text-[12px] font-medium text-slate-600">Estado</span>
              <select
                value={estado}
                onChange={(e) => setEstado(e.target.value)}
                className="rounded-md border border-slate-300 px-2 py-1.5 text-[13px]"
              >
                {ESTADOS.map((s) => (
                  <option key={s} value={s}>
                    {s || "Todos"}
                  </option>
                ))}
              </select>
            </label>
            <label className="flex min-h-[34px] items-center gap-2 text-[13px] text-slate-700">
              <input type="checkbox" checked={soloPideManual} onChange={(e) => setSoloPide(e.target.checked)} />
              Solo los que piden hoy
            </label>
          </>
        )}
        {clusterInicial && (
          <button
            type="button"
            onClick={onLimpiarCluster}
            className="rounded-full bg-brand/10 px-3 py-1 text-[12px] font-medium text-brand hover:bg-brand/20"
          >
            Cluster {clusterInicial} ✕
          </button>
        )}
        <button
          type="button"
          onClick={cargar}
          disabled={cargando}
          className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700 disabled:opacity-50"
        >
          <Search size={14} /> {cargando ? "Buscando…" : "Buscar"}
        </button>
        <button
          type="button"
          onClick={() => canalDigitalApi.exportarCSV(bodega, filtros()).catch((e) => setError(String(e.message ?? e)))}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-[13px] text-slate-700 hover:bg-slate-50"
        >
          <Download size={14} /> Descargar CSV
        </button>
      </div>

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>}

      {data && (
        <p className="text-[12px] text-slate-500">
          {formatoNumero(data.total)} {sugerido ? "productos para pedir, de mayor a menor valor" : "productos"}
          {!sugerido && data.total > data.items.length
            ? ` · se muestran los ${formatoNumero(data.items.length)} de mayor venta`
            : ""}
        </p>
      )}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full min-w-[960px] text-[12.5px]">
          <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Producto</th>
              <th className="px-2 py-2">Cluster</th>
              <th className="px-2 py-2 text-right">Venta 12m</th>
              <th className="px-2 py-2 text-right">Demanda / sem.</th>
              <th className="px-2 py-2 text-right">Plazo (días)</th>
              <th className="px-2 py-2 text-right">Stock 430</th>
              <th className="px-2 py-2 text-right">ML-FULL</th>
              <th className="px-2 py-2 text-right">Posición</th>
              <th className="px-2 py-2 text-right">Sugerido</th>
              <th className="px-3 py-2 text-right">Valor</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {(data?.items ?? []).map((p) => (
              <tr
                key={p.producto}
                onClick={() => setElegido(p)}
                onKeyDown={(e) => e.key === "Enter" && setElegido(p)}
                tabIndex={0}
                className="cursor-pointer hover:bg-slate-50 focus:bg-slate-50 focus:outline-none"
              >
                <td className="px-3 py-2">
                  <div className="font-mono text-[12px] font-medium text-slate-900">{p.producto}</div>
                  <div className="max-w-[260px] truncate text-[11.5px] text-slate-500">{p.descripcion}</div>
                </td>
                <td className="px-2 py-2">
                  {p.cluster ? (
                    <span className="font-mono font-semibold">{p.cluster}</span>
                  ) : (
                    <span className="rounded bg-slate-100 px-1.5 py-0.5 text-[10.5px] text-slate-600">{p.estado}</span>
                  )}
                </td>
                <td className="px-2 py-2 text-right tabular-nums">{formatoNumero(p.unidades_12m)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{formatoNumero(p.demanda_semanal, 1)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{formatoNumero(p.plazo_dias, 1)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{formatoNumero(p.stock_disponible)}</td>
                <td className="px-2 py-2 text-right tabular-nums text-slate-500">{formatoNumero(p.stock_aparte)}</td>
                <td className="px-2 py-2 text-right tabular-nums">{formatoNumero(p.posicion)}</td>
                <td
                  className={`px-2 py-2 text-right font-semibold tabular-nums ${p.sugerido > 0 ? "text-brand" : "text-slate-400"}`}
                >
                  {formatoNumero(p.sugerido)}
                </td>
                <td className="px-3 py-2 text-right tabular-nums">{p.sugerido > 0 ? formatoCLP(p.sugerido_pesos) : "—"}</td>
              </tr>
            ))}
            {data && data.items.length === 0 && (
              <tr>
                <td colSpan={10} className="px-3 py-8 text-center text-slate-500">
                  No hay productos con esos filtros.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {elegido && <DetalleProducto bodega={bodega} producto={elegido} onClose={() => setElegido(null)} />}
    </div>
  );
}

function DetalleProducto({
  bodega,
  producto: p,
  onClose,
}: {
  bodega: string;
  producto: ProductoCanalDigital;
  onClose: () => void;
}) {
  const [pasos, setPasos] = useState<PasoCanalDigital[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let vivo = true;
    canalDigitalApi
      .pasoAPaso(p.producto, bodega)
      .then((r) => vivo && setPasos(r))
      .catch((e) => vivo && setError(e instanceof Error ? e.message : "Error"));
    return () => {
      vivo = false;
    };
  }, [bodega, p.producto]);

  return (
    <Dialog open onClose={onClose} title={p.producto} description={p.descripcion ?? undefined} className="max-w-3xl">
      <div className="space-y-4 text-[13px]">
        <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <Dato titulo="Cluster" valor={p.cluster ?? p.estado} />
          <Dato titulo="Política" valor={p.modo ? NOMBRE_MODO[p.modo] : "—"} />
          <Dato titulo="Sugerido" valor={`${formatoNumero(p.sugerido)} u.`} fuerte />
          <Dato titulo="Valor" valor={p.sugerido > 0 ? formatoCLP(p.sugerido_pesos) : "—"} />
          <Dato titulo="Stock 430" valor={formatoNumero(p.stock_disponible)} />
          <Dato titulo="ML-FULL (aparte)" valor={formatoNumero(p.stock_aparte)} />
          <Dato titulo="Tránsito a la 430" valor={formatoNumero(p.transito)} />
          <Dato titulo="Posición" valor={formatoNumero(p.posicion)} />
        </div>
        <p className="text-[12px] text-slate-600">
          Plazo: {formatoNumero(p.plazo_dias, 1)} días — {p.plazo_origen}. Costo: {p.costo_respaldo}. Vendido bajo:{" "}
          {p.codigos_vendidos}.
        </p>
        {p.avisos.length > 0 && (
          <ul className="space-y-1 rounded-md bg-amber-50 px-3 py-2 text-[12px] text-amber-900">
            {p.avisos.map((a) => (
              <li key={a}>{NOMBRE_AVISO[a] ?? a}</li>
            ))}
          </ul>
        )}
        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-red-700">{error}</p>}
        {!pasos && !error && <p className="text-slate-500">Armando el paso a paso…</p>}
        {pasos && (
          <ol className="space-y-3">
            {pasos.map((s) => (
              <li key={s.numero} className="rounded-lg border border-slate-200 p-3">
                <div className="text-[12.5px] font-semibold text-slate-900">
                  {s.numero}. {s.titulo}
                </div>
                <div className="mt-1 text-[12px] text-slate-500">{s.formula}</div>
                <div className="mt-1 text-[12.5px] text-slate-800">{s.numeros}</div>
                <div className="mt-1 text-[12.5px] font-medium text-brand">{s.resultado}</div>
              </li>
            ))}
          </ol>
        )}
      </div>
    </Dialog>
  );
}

function Dato({ titulo, valor, fuerte }: { titulo: string; valor: string; fuerte?: boolean }) {
  return (
    <div className="rounded-lg bg-slate-50 px-3 py-2">
      <div className="text-[11px] text-slate-500">{titulo}</div>
      <div className={`tabular-nums ${fuerte ? "text-[15px] font-semibold text-brand" : "text-[13px] text-slate-900"}`}>
        {valor}
      </div>
    </div>
  );
}
