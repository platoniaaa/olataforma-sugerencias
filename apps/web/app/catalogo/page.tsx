"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BookOpen, Columns3, Download, RefreshCw, Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { MultiSelect } from "@/components/ui/multiselect";
import { Card } from "@/components/ui/card";
import { TablaCatalogo } from "@/components/tabla-catalogo";
import { ConfigurarColumnasCatalogo } from "@/components/configurar-columnas-catalogo";
import { api } from "@/lib/api-client";
import { KEYS_CAT_DEFAULT } from "@/lib/columnas-catalogo";
import { formatoNumero } from "@/lib/formato";
import type { CatalogoFiltros, CatalogoOpciones, CatalogoRow } from "@/lib/types";

const LS_COLUMNAS = "catalogo_columnas_visibles";

export default function CatalogoPage() {
  const [filtros, setFiltros] = useState<CatalogoFiltros>({ con_stock: false });
  const [rows, setRows] = useState<CatalogoRow[]>([]);
  const [total, setTotal] = useState(0);
  const [opciones, setOpciones] = useState<CatalogoOpciones>({
    familias: [],
    procedencias: [],
    categorias: [],
  });
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [colsVisibles, setColsVisibles] = useState<string[]>(KEYS_CAT_DEFAULT);
  const [modalCols, setModalCols] = useState(false);

  // Restaurar columnas
  useEffect(() => {
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

  // Cargar opciones de filtros una vez
  useEffect(() => {
    api.catalogoFiltros().then(setOpciones).catch(() => {});
  }, []);

  const cargar = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const r = await api.catalogo(filtros, { limit: 5000, sort: "producto" });
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

  const set = (parcial: Partial<CatalogoFiltros>) =>
    setFiltros({ ...filtros, ...parcial });

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
            <BookOpen size={20} className="text-brand" /> Catálogo de productos
          </h1>
          <p className="text-[13px] text-slate-500">
            Listado maestro completo del ERP.{" "}
            {cargando ? "Cargando…" : (
              <>
                <b>{formatoNumero(total)}</b> productos
                {total > rows.length && ` (mostrando ${formatoNumero(rows.length)})`}
              </>
            )}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={cargar}>
            <RefreshCw size={15} /> Actualizar
          </Button>
          <Button variant="outline" size="sm" onClick={() => setModalCols(true)}>
            <Columns3 size={15} /> Columnas
          </Button>
        </div>
      </div>

      {/* Filtros */}
      <Card>
        <div className="flex flex-wrap items-center gap-2 p-3">
          <div className="relative min-w-[260px] flex-1">
            <Search size={15} className="absolute left-2.5 top-2.5 text-slate-400" />
            <Input
              placeholder="Buscar código o descripción…"
              className="pl-8"
              value={filtros.q ?? ""}
              onChange={(e) => set({ q: e.target.value })}
            />
          </div>
          <MultiSelect
            label="Familia"
            className="w-[160px]"
            opciones={opciones.familias.map((s) => ({ value: s, label: s }))}
            seleccionados={filtros.familia ?? []}
            onChange={(v) => set({ familia: v })}
          />
          <MultiSelect
            label="Procedencia"
            className="w-[160px]"
            opciones={opciones.procedencias.map((s) => ({ value: s, label: s }))}
            seleccionados={filtros.procedencia ?? []}
            onChange={(v) => set({ procedencia: v })}
          />
          <MultiSelect
            label="Categoría"
            className="w-[160px]"
            opciones={opciones.categorias.map((s) => ({ value: s, label: s }))}
            seleccionados={filtros.categoria ?? []}
            onChange={(v) => set({ categoria: v })}
          />
          <label className="flex h-9 cursor-pointer items-center gap-2 rounded-md border border-slate-300 bg-white px-3 text-[13px] text-slate-700">
            <input
              type="checkbox"
              className="h-4 w-4 accent-brand"
              checked={filtros.con_stock ?? false}
              onChange={(e) => set({ con_stock: e.target.checked })}
            />
            Solo con stock
          </label>
        </div>
      </Card>

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          {error}
        </div>
      )}

      <TablaCatalogo rows={rows} columnasVisibles={colsVisibles} />

      <ConfigurarColumnasCatalogo
        open={modalCols}
        onClose={() => setModalCols(false)}
        visibles={colsVisibles}
        onChange={setColsVisibles}
      />
    </div>
  );
}
