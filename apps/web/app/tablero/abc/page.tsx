"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { AlertTriangle, ArrowLeft, Loader2, Search } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoNumero } from "@/lib/formato";
import type { AbcStockFila, AbcStockResumen } from "@/lib/types";

/**
 * ABC por sucursal de lo que hay en stock.
 *
 * Responde una pregunta que el sugerido no responde: **de lo que tengo guardado,
 * qué se mueve y qué no**. El sugerido mira al revés —qué hay que comprar— y solo
 * existe para producto × sucursal con venta en los últimos 12 meses.
 *
 * Dos cosas que la pantalla dice en voz alta porque callarlas induce a error:
 *
 * 1. **De dónde sale cada clase.** La mayoría de las líneas son D porque no
 *    vendieron nada, no porque el modelo las haya evaluado y clasificado bajo. No
 *    es lo mismo un repuesto que vendió 2 de 12 meses que uno que no vendió nunca.
 * 2. **Las unidades no se suman.** Un puñado de códigos de granel viene cargado en
 *    mililitros y se lleva casi todo el total. Por eso el número grande de arriba
 *    es la cantidad de códigos, no de unidades.
 */
const CLASES = ["A", "B", "C", "D"] as const;

const COLOR_CLASE: Record<string, string> = {
  A: "bg-emerald-100 text-emerald-800 border-emerald-200",
  B: "bg-sky-100 text-sky-800 border-sky-200",
  C: "bg-amber-100 text-amber-800 border-amber-200",
  D: "bg-slate-100 text-slate-600 border-slate-200",
};

const LIMITE = 300;

export default function AbcStockPage() {
  const [resumen, setResumen] = useState<AbcStockResumen | null>(null);
  const [filas, setFilas] = useState<AbcStockFila[]>([]);
  const [totalFilas, setTotalFilas] = useState(0);
  const [sucursal, setSucursal] = useState<string | null>(null);
  const [clase, setClase] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [q, setQ] = useState("");
  const [cargando, setCargando] = useState(true);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .abcStock()
      .then(setResumen)
      .catch(() => setError("No se pudo cargar el ABC por sucursal."))
      .finally(() => setCargando(false));
  }, []);

  const cargarDetalle = useCallback(async () => {
    setCargandoDetalle(true);
    try {
      const r = await api.abcStockDetalle({
        sucursal: sucursal ? [sucursal] : [],
        clase: clase ? [clase] : [],
        q: q || null,
        limit: LIMITE,
      });
      setFilas(r.items);
      setTotalFilas(r.total);
    } catch {
      setError("No se pudo cargar el detalle.");
    } finally {
      setCargandoDetalle(false);
    }
  }, [sucursal, clase, q]);

  useEffect(() => {
    if (sucursal || clase || q) void cargarDetalle();
    else {
      setFilas([]);
      setTotalFilas(0);
    }
  }, [sucursal, clase, q, cargarDetalle]);

  if (cargando) {
    return (
      <div className="flex items-center gap-2 p-8 text-sm text-slate-500">
        <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
      </div>
    );
  }

  if (error || !resumen) {
    return <div className="p-8 text-sm text-red-600">{error ?? "Sin datos."}</div>;
  }

  const t = resumen.total;
  const pctSinVenta = Math.round(
    (resumen.cobertura.sin_venta_12m / Math.max(t.skus, 1)) * 100,
  );

  return (
    <div className="space-y-6 p-4 sm:p-6">
      <div>
        <Link
          href="/tablero"
          className="inline-flex items-center gap-1 text-sm text-slate-500 hover:text-slate-800"
        >
          <ArrowLeft className="h-3.5 w-3.5" /> Tablero mensual
        </Link>
        <h1 className="mt-2 text-2xl font-semibold text-slate-900">
          ABC por sucursal de lo que hay en stock
        </h1>
        <p className="mt-1 max-w-3xl text-sm text-slate-600">
          De lo que está guardado, qué se mueve y qué no. La clase es la misma que usa el
          sugerido para calcular la compra: cuenta en cuántos meses distintos hubo venta de
          ese repuesto en esa sucursal.
        </p>
      </div>

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <Kpi titulo="Códigos con stock" valor={formatoNumero(t.productos, 0)} />
        <Kpi
          titulo="Líneas sucursal × producto"
          valor={formatoNumero(t.skus, 0)}
          pie={`${resumen.sucursales.length} sucursales`}
        />
        <Kpi
          titulo="Clase A + B"
          valor={formatoNumero(t.a + t.b, 0)}
          pie="lo que se mueve todos los meses"
          acento="text-emerald-700"
        />
        <Kpi
          titulo="Sin venta en 12 meses"
          valor={formatoNumero(resumen.cobertura.sin_venta_12m, 0)}
          pie={`${pctSinVenta}% de las líneas`}
          acento="text-amber-700"
        />
      </div>

      <section className="rounded-lg border border-slate-200 bg-white">
        <header className="flex flex-wrap items-baseline justify-between gap-2 border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">
            Códigos con stock por sucursal y clase
          </h2>
          <span className="text-xs text-slate-500">
            Haz clic en un número para ver el detalle
          </span>
        </header>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[720px] text-sm">
            <thead>
              <tr className="border-b border-slate-200 text-xs uppercase tracking-wide text-slate-500">
                <th className="px-4 py-2 text-left font-medium">Sucursal</th>
                {CLASES.map((c) => (
                  <th key={c} className="px-3 py-2 text-right font-medium">
                    {c}
                  </th>
                ))}
                <th className="px-3 py-2 text-right font-medium">Total</th>
                <th className="px-4 py-2 text-right font-medium">Unidades</th>
              </tr>
            </thead>
            <tbody>
              {resumen.sucursales.map((s) => (
                <tr
                  key={s.sucursal}
                  className={`border-b border-slate-100 last:border-0 ${
                    sucursal === s.sucursal ? "bg-slate-50" : ""
                  }`}
                >
                  <td className="px-4 py-2">
                    <button
                      type="button"
                      onClick={() =>
                        setSucursal(sucursal === s.sucursal ? null : s.sucursal)
                      }
                      className="text-left font-medium text-slate-800 hover:text-sky-700 hover:underline"
                    >
                      {s.sucursal}
                    </button>
                    {!s.evaluada && (
                      <span
                        className="ml-2 rounded border border-slate-200 bg-slate-50 px-1.5 py-0.5 text-[11px] text-slate-500"
                        title="Bodega de proceso: el modelo no calcula clase acá, todo sale D"
                      >
                        no evaluada
                      </span>
                    )}
                  </td>
                  {CLASES.map((c) => {
                    const n = s[c.toLowerCase() as "a" | "b" | "c" | "d"];
                    return (
                      <td key={c} className="px-3 py-2 text-right tabular-nums">
                        {n === 0 ? (
                          <span className="text-slate-300">—</span>
                        ) : (
                          <button
                            type="button"
                            onClick={() => {
                              setSucursal(s.sucursal);
                              setClase(c);
                            }}
                            className="hover:text-sky-700 hover:underline"
                          >
                            {formatoNumero(n, 0)}
                          </button>
                        )}
                      </td>
                    );
                  })}
                  <td className="px-3 py-2 text-right font-medium tabular-nums">
                    {formatoNumero(s.skus, 0)}
                  </td>
                  <td className="px-4 py-2 text-right tabular-nums text-slate-500">
                    {formatoNumero(s.unidades, 0)}
                  </td>
                </tr>
              ))}
              <tr className="bg-slate-50 font-semibold">
                <td className="px-4 py-2">Total</td>
                {CLASES.map((c) => (
                  <td key={c} className="px-3 py-2 text-right tabular-nums">
                    {formatoNumero(t[c.toLowerCase() as "a" | "b" | "c" | "d"], 0)}
                  </td>
                ))}
                <td className="px-3 py-2 text-right tabular-nums">
                  {formatoNumero(t.skus, 0)}
                </td>
                <td className="px-4 py-2 text-right tabular-nums">
                  {formatoNumero(t.unidades, 0)}
                </td>
              </tr>
            </tbody>
          </table>
        </div>
      </section>

      <Avisos resumen={resumen} pctSinVenta={pctSinVenta} />

      <section className="rounded-lg border border-slate-200 bg-white">
        <header className="flex flex-wrap items-center gap-3 border-b border-slate-200 px-4 py-3">
          <h2 className="text-sm font-semibold text-slate-800">Detalle</h2>
          <div className="relative">
            <Search className="absolute left-2 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-slate-400" />
            <input
              value={busqueda}
              onChange={(e) => setBusqueda(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && setQ(busqueda.trim())}
              onBlur={() => setQ(busqueda.trim())}
              placeholder="Código o descripción"
              className="w-56 rounded border border-slate-300 py-1 pl-7 pr-2 text-sm"
            />
          </div>
          {(sucursal || clase || q) && (
            <div className="flex flex-wrap items-center gap-2 text-xs">
              {sucursal && <Chip onQuitar={() => setSucursal(null)}>{sucursal}</Chip>}
              {clase && <Chip onQuitar={() => setClase(null)}>Clase {clase}</Chip>}
              {q && <Chip onQuitar={() => { setQ(""); setBusqueda(""); }}>“{q}”</Chip>}
              <span className="text-slate-500">
                {formatoNumero(totalFilas, 0)} líneas
                {totalFilas > LIMITE && ` · se muestran las primeras ${LIMITE}`}
              </span>
            </div>
          )}
        </header>

        {!sucursal && !clase && !q ? (
          <p className="px-4 py-8 text-center text-sm text-slate-500">
            Elige una sucursal o una clase en la tabla de arriba, o busca un código.
          </p>
        ) : cargandoDetalle ? (
          <div className="flex items-center gap-2 px-4 py-8 text-sm text-slate-500">
            <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
          </div>
        ) : filas.length === 0 ? (
          <p className="px-4 py-8 text-center text-sm text-slate-500">
            No hay líneas con esos filtros.
          </p>
        ) : (
          <div className="max-h-[32rem] overflow-auto">
            <table className="w-full min-w-[900px] text-sm">
              <thead className="sticky top-0 bg-white shadow-[0_1px_0_0_#e2e8f0]">
                <tr className="text-xs uppercase tracking-wide text-slate-500">
                  <th className="px-4 py-2 text-left font-medium">Producto</th>
                  <th className="px-3 py-2 text-left font-medium">Descripción</th>
                  <th className="px-3 py-2 text-left font-medium">Sucursal</th>
                  <th className="px-3 py-2 text-center font-medium">Clase</th>
                  <th className="px-3 py-2 text-left font-medium">Base</th>
                  <th className="px-3 py-2 text-right font-medium">6m</th>
                  <th className="px-3 py-2 text-right font-medium">12m</th>
                  <th className="px-4 py-2 text-right font-medium">Unidades</th>
                </tr>
              </thead>
              <tbody>
                {filas.map((f) => (
                  <tr
                    key={`${f.sucursal}|${f.producto}`}
                    className="border-t border-slate-100"
                    title={f.aviso || undefined}
                  >
                    <td className="whitespace-nowrap px-4 py-1.5 font-medium text-slate-800">
                      {f.producto}
                    </td>
                    <td className="max-w-[22rem] truncate px-3 py-1.5 text-slate-600">
                      {f.descripcion || (
                        <span className="text-slate-400">sin descripción</span>
                      )}
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-slate-600">
                      {f.sucursal}
                    </td>
                    <td className="px-3 py-1.5 text-center">
                      <span
                        className={`inline-block w-6 rounded border px-1 text-xs font-semibold ${COLOR_CLASE[f.clase]}`}
                      >
                        {f.clase}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-3 py-1.5 text-xs text-slate-500">
                      {f.base_clase === "Modelo" ? "venta 12m" : "sin venta 12m"}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">
                      {f.meses_con_venta_6m}
                    </td>
                    <td className="px-3 py-1.5 text-right tabular-nums text-slate-600">
                      {f.meses_con_venta_12m}
                    </td>
                    <td className="px-4 py-1.5 text-right tabular-nums">
                      {formatoNumero(f.unidades, 0)}
                      {f.aviso.includes("atipica") && (
                        <AlertTriangle className="ml-1 inline h-3 w-3 text-amber-500" />
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </div>
  );
}

function Avisos({
  resumen,
  pctSinVenta,
}: {
  resumen: AbcStockResumen;
  pctSinVenta: number;
}) {
  const pctUnidades = Math.round(
    (resumen.atipicos.unidades / Math.max(resumen.total.unidades, 1)) * 100,
  );
  return (
    <section className="rounded-lg border border-amber-200 bg-amber-50/60 px-4 py-3">
      <h2 className="text-sm font-semibold text-amber-900">Cómo leer estos números</h2>
      <ul className="mt-2 space-y-1.5 text-sm text-amber-900/90">
        <li>
          <strong>{pctSinVenta}% de las líneas son D porque no vendieron nada</strong> en esa
          sucursal en 12 meses, no porque el modelo las haya evaluado y clasificado bajo. La
          columna «Base» separa una cosa de la otra.
        </li>
        <li>
          <strong>Las unidades no se pueden sumar sin mirar:</strong>{" "}
          {resumen.atipicos.codigos} códigos concentran el {pctUnidades}% del total. Son
          aceites y lubricantes a granel cargados en mililitros, más un par de cantidades que
          no cuadran con el producto. Van marcados con ⚠ en el detalle.
        </li>
        <li>
          Entra <strong>todo el stock, sin filtrar ninguna bodega</strong>. Las bodegas de
          proceso (dañados, devolución, tránsito, PE por regularizar) aparecen como una
          sucursal más y van marcadas «no evaluada»: ahí el modelo no calcula clase.
        </li>
        {resumen.sin_descripcion > 0 && (
          <li>
            {formatoNumero(resumen.sin_descripcion, 0)} códigos con stock no tienen
            descripción en el maestro del ERP.
          </li>
        )}
      </ul>
    </section>
  );
}

function Kpi({
  titulo,
  valor,
  pie,
  acento,
}: {
  titulo: string;
  valor: string;
  pie?: string;
  acento?: string;
}) {
  return (
    <div className="rounded-lg border border-slate-200 bg-white px-4 py-3">
      <p className="text-xs uppercase tracking-wide text-slate-500">{titulo}</p>
      <p className={`mt-1 text-2xl font-semibold tabular-nums ${acento ?? "text-slate-900"}`}>
        {valor}
      </p>
      {pie && <p className="mt-0.5 text-xs text-slate-500">{pie}</p>}
    </div>
  );
}

function Chip({
  children,
  onQuitar,
}: {
  children: React.ReactNode;
  onQuitar: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onQuitar}
      className="rounded-full border border-slate-300 bg-slate-50 px-2 py-0.5 text-slate-700 hover:bg-slate-100"
      title="Quitar filtro"
    >
      {children} ✕
    </button>
  );
}
