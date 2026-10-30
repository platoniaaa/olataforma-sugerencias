"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { ChevronRight, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import type { ConsultaProducto } from "@/lib/types";

const LS_BUSQUEDA = "consulta_productos_q";
const POR_PAGINA = 50;

/**
 * Consulta de productos del vendedor: se busca por código o descripción y se toca
 * un producto para ver su detalle (stock en todas las sucursales, reemplazos y
 * ventas). Es la ficha del catálogo sin el costo.
 *
 * La búsqueda se recuerda en la sesión: al volver desde el detalle el vendedor
 * encuentra la misma lista y no tiene que escribirla otra vez.
 */
export default function ConsultaProductosPage() {
  const [q, setQ] = useState("");
  const [conStock, setConStock] = useState(false);
  const [items, setItems] = useState<ConsultaProducto[]>([]);
  const [total, setTotal] = useState(0);
  const [pagina, setPagina] = useState(1);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [listo, setListo] = useState(false);
  // Una respuesta vieja no puede pisar a una más nueva (se escribe más rápido de
  // lo que responde el servidor).
  const pedido = useRef(0);

  // Restaurar la búsqueda de la sesión (solo en el navegador).
  useEffect(() => {
    try {
      const guardada = sessionStorage.getItem(LS_BUSQUEDA);
      if (guardada) setQ(guardada);
    } catch {
      /* sin sessionStorage: se parte vacío */
    }
    setListo(true);
  }, []);

  const cargar = useCallback(
    async (pag: number, reemplazar: boolean) => {
      const mio = ++pedido.current;
      setCargando(true);
      setError(null);
      try {
        const r = await api.consultaProductos(
          { q: q.trim() || undefined, con_stock: conStock },
          { page: pag, limit: POR_PAGINA }
        );
        if (mio !== pedido.current) return;
        setItems((prev) => (reemplazar ? r.items : [...prev, ...r.items]));
        setTotal(r.total);
        setPagina(pag);
      } catch (e) {
        if (mio !== pedido.current) return;
        setError(e instanceof Error ? e.message : "No se pudo cargar la lista");
      } finally {
        if (mio === pedido.current) setCargando(false);
      }
    },
    [q, conStock]
  );

  // Buscar al escribir, con una pausa corta para no pedir en cada letra.
  useEffect(() => {
    if (!listo) return;
    try {
      sessionStorage.setItem(LS_BUSQUEDA, q);
    } catch {
      /* noop */
    }
    const t = setTimeout(() => cargar(1, true), 300);
    return () => clearTimeout(t);
  }, [listo, q, conStock, cargar]);

  const hayMas = items.length < total;
  const buscando = q.trim().length > 0;

  return (
    <div className="space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
          <Search size={20} className="text-brand" aria-hidden="true" /> Productos
        </h1>
        <p className="text-[13px] text-slate-600">
          Busca un producto por código o descripción y tócalo para ver su stock,
          sus reemplazos y sus ventas.
        </p>
      </div>

      <div className="space-y-2 rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
        <label htmlFor="buscar-producto" className="text-[13px] font-medium text-slate-700">
          Buscar producto
        </label>
        <div className="relative">
          <Search
            size={16}
            className="pointer-events-none absolute left-3 top-3 text-slate-400"
            aria-hidden="true"
          />
          <Input
            id="buscar-producto"
            type="search"
            inputMode="search"
            autoComplete="off"
            placeholder="Código o descripción, por ejemplo «filtro de aceite»"
            className="h-11 pl-9"
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <label className="flex min-h-[44px] cursor-pointer items-center gap-2 text-[13px] text-slate-700">
          <input
            type="checkbox"
            className="h-5 w-5 accent-brand"
            checked={conStock}
            onChange={(e) => setConStock(e.target.checked)}
          />
          Solo productos con stock
        </label>
      </div>

      <p className="text-[13px] text-slate-600" aria-live="polite">
        {cargando && items.length === 0 ? (
          "Buscando…"
        ) : error ? null : (
          <>
            <b>{formatoNumero(total)}</b> {total === 1 ? "producto" : "productos"}
            {hayMas && ` (mostrando ${formatoNumero(items.length)})`}
          </>
        )}
      </p>

      {error && (
        <div
          role="alert"
          className="flex flex-wrap items-center justify-between gap-2 rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800"
        >
          <span>{error}</span>
          <Button variant="outline" size="sm" onClick={() => cargar(1, true)}>
            Reintentar
          </Button>
        </div>
      )}

      {!cargando && !error && items.length === 0 && (
        <div className="rounded-xl border border-slate-200 bg-white px-4 py-8 text-center text-sm text-slate-600">
          {buscando
            ? `No encontramos productos con «${q.trim()}». Prueba con otra parte del código o de la descripción.`
            : "No hay productos para mostrar."}
        </div>
      )}

      {items.length > 0 && (
        <ul className="divide-y divide-slate-100 overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {items.map((p) => (
            <li key={p.producto}>
              <FilaProducto p={p} />
            </li>
          ))}
        </ul>
      )}

      {hayMas && (
        <div className="flex justify-center">
          <Button variant="outline" disabled={cargando} onClick={() => cargar(pagina + 1, false)}>
            {cargando ? "Cargando…" : "Ver más productos"}
          </Button>
        </div>
      )}
    </div>
  );
}

function FilaProducto({ p }: { p: ConsultaProducto }) {
  const stock = p.stock_total ?? 0;
  const transito = p.en_transito ?? 0;
  const reemplazos = (p.reemplazo ?? "").split(",").map((s) => s.trim()).filter(Boolean).length;
  return (
    <Link
      href={`/consulta-productos/${encodeURIComponent(p.producto)}`}
      className="flex min-h-[64px] items-center gap-3 px-4 py-3 transition-colors hover:bg-slate-50 focus-visible:bg-slate-50 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-brand"
    >
      <div className="min-w-0 flex-1">
        <p className="font-mono text-[13px] font-semibold text-slate-900">{p.producto}</p>
        <p className="line-clamp-2 text-[13px] text-slate-700">{p.glosa ?? "Sin descripción"}</p>
        {reemplazos > 0 && (
          <p className="mt-0.5 text-[11.5px] text-slate-600">
            Tiene {reemplazos} {reemplazos === 1 ? "reemplazo" : "reemplazos"}
          </p>
        )}
      </div>
      <div className="shrink-0 text-right">
        <p className="text-[13px] font-semibold tabular-nums text-slate-900">
          {p.precio != null ? formatoCLP(p.precio) : "—"}
        </p>
        <p
          className={`text-[11.5px] font-medium tabular-nums ${
            stock > 0 ? "text-emerald-700" : "text-slate-500"
          }`}
        >
          {stock > 0 ? `Stock ${formatoNumero(stock)}` : "Sin stock"}
        </p>
        {transito > 0 && (
          <p className="text-[11.5px] font-medium tabular-nums text-sky-800">
            +{formatoNumero(transito)} en tránsito
          </p>
        )}
      </div>
      <ChevronRight size={18} className="shrink-0 text-slate-400" aria-hidden="true" />
    </Link>
  );
}
