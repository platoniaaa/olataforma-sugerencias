"use client";

/**
 * Requerimiento de sucursal: pegar la lista, decidir, bajar el archivo del portal.
 *
 * Reemplaza el Excel que el comprador usaba antes de la plataforma. La idea es
 * poka-yoke: que el error no pueda ocurrir, no avisarlo después.
 *
 * - Se pega como venga (tabulación, coma, punto y coma, espacios, con encabezado
 *   o sin él). No hay formato que aprenderse.
 * - La sucursal se elige UNA vez, arriba, no por línea.
 * - Lo que no existe no se puede seleccionar.
 * - El archivo sale ya en el formato de cada portal, con los códigos convertidos
 *   y separado por proveedor: no se puede mezclar Ford con Gildemeister.
 */

import { useEffect, useMemo, useState } from "react";
import {
  AlertTriangle,
  ArrowLeft,
  Copy,
  Download,
  Loader2,
  Search,
  Trash2,
} from "lucide-react";
import Link from "next/link";
import { Button } from "@/components/ui/button";
import { FrecuenciaVenta } from "@/components/frecuencia-venta";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import type { LineaRequerimiento, RequerimientoResponse, Sucursal } from "@/lib/types";

const EJEMPLO = `19 SZ6Z3B437B	4
70 2723982	2
25 DG9Z8100A	3`;

/** Color y texto del estado de cada línea. */
function Estado({ linea }: { linea: LineaRequerimiento }) {
  if (linea.estado === "no_existe") {
    return (
      <span className="inline-flex items-center gap-1 rounded-sm bg-red-50 px-1.5 py-0.5 text-[11px] font-medium text-red-700">
        <AlertTriangle size={11} /> no existe
      </span>
    );
  }
  if (linea.estado === "sin_venta_local") {
    const otra = linea.frecuencia_otra_sucursal;
    return (
      <span className="inline-flex items-center gap-1 rounded-sm bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-800">
        nunca vendido acá
        {otra && (
          <span className="font-normal">
            · {otra.nombre_sucursal} {otra.meses_con_venta_12m}/12
          </span>
        )}
      </span>
    );
  }
  return null;
}

/** Cada cuanto se mueve. Ver `components/frecuencia-venta.tsx`. */
function Frecuencia({ linea }: { linea: LineaRequerimiento }) {
  return (
    <FrecuenciaVenta
      meses3={linea.meses_con_venta_3m}
      meses6={linea.meses_con_venta_6m}
      meses12={linea.meses_con_venta_12m}
    />
  );
}

export default function RequerimientoPage() {
  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [sucursal, setSucursal] = useState("");
  const [texto, setTexto] = useState("");
  const [datos, setDatos] = useState<RequerimientoResponse | null>(null);
  const [cargando, setCargando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [descartados, setDescartados] = useState<string | null>(null);
  // Líneas que el comprador decidió NO comprar (por índice).
  const [excluidas, setExcluidas] = useState<Set<number>>(new Set());
  // Cantidades editadas en pantalla.
  const [cantidades, setCantidades] = useState<Record<number, number | null>>({});

  useEffect(() => {
    api.sucursales().then(setSucursales).catch(() => {});
  }, []);

  const analizar = async () => {
    if (!sucursal || !texto.trim()) return;
    setCargando(true);
    setError(null);
    setDescartados(null);
    try {
      const r = await api.analizarRequerimiento(sucursal, texto);
      setDatos(r);
      setExcluidas(new Set());
      setCantidades({});
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo analizar la lista");
    } finally {
      setCargando(false);
    }
  };

  const lineas = datos?.lineas ?? [];
  const cantidadDe = (i: number) =>
    cantidades[i] !== undefined ? cantidades[i] : lineas[i]?.cantidad ?? null;

  /** Lo que de verdad se va a pedir: sin excluidas, sin inexistentes, con cantidad. */
  const aPedir = useMemo(
    () =>
      lineas
        .map((l, i) => ({ linea: l, i }))
        .filter(
          ({ linea, i }) =>
            !excluidas.has(i) && linea.estado !== "no_existe" && (cantidadDe(i) ?? 0) > 0
        )
        .map(({ linea, i }) => ({ producto: linea.producto, cantidad: cantidadDe(i) })),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lineas, excluidas, cantidades]
  );

  const valorTotal = useMemo(
    () =>
      lineas.reduce((suma, l, i) => {
        if (excluidas.has(i) || l.estado === "no_existe") return suma;
        return suma + (l.costo_unitario ?? 0) * (cantidadDe(i) ?? 0);
      }, 0),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [lineas, excluidas, cantidades]
  );

  const descargar = async (proveedor: "FORD" | "GILDEMEISTER") => {
    if (!aPedir.length) return;
    setError(null);
    try {
      const fuera = await api.archivoPortal(proveedor, sucursal, aPedir);
      setDescartados(
        fuera > 0
          ? `${fuera} línea(s) quedaron fuera del archivo de ${proveedor}: no tienen código de ese portal o no tienen cantidad.`
          : null
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo generar el archivo");
    }
  };

  const r = datos?.resumen;

  return (
    <div className="space-y-5">
      <div>
        <Link
          href="/"
          className="inline-flex items-center gap-1 text-[13px] text-accent-700 hover:underline"
        >
          <ArrowLeft size={14} /> Volver al sugerido
        </Link>
        <p className="kicker mt-3">Compras</p>
        <h1 className="display text-[30px] leading-tight">Requerimiento de sucursal</h1>
        <p className="mt-1 text-[13.5px] text-ink-500">
          Pega la lista que te mandó el vendedor y decide con la frecuencia de venta y
          el stock a la vista. Al final se descarga el archivo listo para el portal.
        </p>
      </div>

      {/* Paso 1 y 2: sucursal + pegar */}
      <div className="rounded-sm border border-ink-200 bg-white p-4 shadow-card">
        <div className="flex flex-wrap items-end gap-4">
          <label className="block">
            <span className="mb-1 block text-[12px] font-medium text-ink-600">
              1 · ¿De qué sucursal es el requerimiento?
            </span>
            <select
              value={sucursal}
              onChange={(e) => setSucursal(e.target.value)}
              className="h-10 min-w-[220px] rounded-sm border border-ink-200 bg-paper-50 px-3 text-[13.5px]"
            >
              <option value="">Elige una sucursal…</option>
              {sucursales.map((s) => (
                <option key={s.sucursal_id} value={s.sucursal_id}>
                  {s.nombre ?? s.sucursal_id}
                </option>
              ))}
            </select>
          </label>
          <p className="pb-2 text-[12px] text-ink-400">
            El stock y la frecuencia son <strong>de esa sucursal</strong>.
          </p>
        </div>

        <label className="mt-4 block">
          <span className="mb-1 block text-[12px] font-medium text-ink-600">
            2 · Pega los códigos y las cantidades
          </span>
          <textarea
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            rows={6}
            spellCheck={false}
            placeholder={`Pega como venga. Ejemplo:\n${EJEMPLO}`}
            className="w-full rounded-sm border border-ink-200 bg-paper-50 p-3 font-mono text-[13px] leading-relaxed text-ink-900 placeholder:text-ink-300 focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none"
          />
        </label>
        <p className="mt-1 text-[12px] text-ink-400">
          Da igual el separador (tabulación, coma, punto y coma o espacios) y si trae
          encabezado. Si una línea no tiene cantidad, la pones acá abajo.
        </p>

        <div className="mt-3 flex flex-wrap items-center gap-2">
          <Button onClick={analizar} disabled={!sucursal || !texto.trim() || cargando}>
            {cargando ? <Loader2 size={15} className="animate-spin" /> : <Search size={15} />}
            {cargando ? "Analizando…" : "Analizar la lista"}
          </Button>
          {texto && (
            <Button variant="outline" size="sm" onClick={() => { setTexto(""); setDatos(null); }}>
              <Trash2 size={14} /> Limpiar
            </Button>
          )}
          {!texto && (
            <Button variant="outline" size="sm" onClick={() => setTexto(EJEMPLO)}>
              <Copy size={14} /> Probar con un ejemplo
            </Button>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-sm border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
          {error}
        </div>
      )}

      {r && (
        <>
          {/* Resumen: lo primero que quiere saber es cuánto de la lista es problema */}
          <div className="flex flex-wrap items-center gap-3 rounded-sm border border-ink-200 bg-white px-4 py-3 text-[13px] shadow-card">
            <span className="font-medium">{r.total} líneas</span>
            <span className="text-ink-400">·</span>
            <span className="text-emerald-700">{r.en_sugerido} con historial acá</span>
            {r.sin_venta_local > 0 && (
              <>
                <span className="text-ink-400">·</span>
                <span className="text-amber-700">
                  {r.sin_venta_local} nunca vendidas acá
                </span>
              </>
            )}
            {r.no_existe > 0 && (
              <>
                <span className="text-ink-400">·</span>
                <span className="text-red-700">{r.no_existe} no existen</span>
              </>
            )}
            {r.duplicados > 0 && (
              <>
                <span className="text-ink-400">·</span>
                <span className="text-amber-700">{r.duplicados} repetidas</span>
              </>
            )}
            <span className="ml-auto text-ink-500">
              A pedir: <strong className="text-ink-900">{aPedir.length}</strong> líneas ·{" "}
              <strong className="text-ink-900">{formatoCLP(valorTotal)}</strong>
            </span>
          </div>

          {/* La tabla de decisión */}
          <div className="overflow-x-auto rounded-sm border border-ink-200 bg-white shadow-card">
            <table className="w-full min-w-[1000px] text-[13px]">
              <thead>
                <tr className="border-b border-ink-200 bg-paper-50 text-left text-[11.5px] uppercase tracking-wide text-ink-500">
                  <th className="w-10 px-3 py-2"></th>
                  <th className="px-3 py-2">Producto</th>
                  <th className="px-3 py-2">Descripción</th>
                  <th className="px-3 py-2 text-right">Cantidad</th>
                  <th
                    className="px-3 py-2"
                    title="De los últimos 12 meses, en cuántos se vendió este repuesto en esa sucursal"
                  >
                    Meses con venta
                  </th>
                  <th className="px-3 py-2">ABC</th>
                  <th className="px-3 py-2 text-right">Stock acá</th>
                  <th className="px-3 py-2 text-right">Stock CD</th>
                  <th className="px-3 py-2 text-right">Nacional</th>
                  <th className="px-3 py-2">Proveedor</th>
                  <th className="px-3 py-2 text-right">Costo</th>
                </tr>
              </thead>
              <tbody>
                {lineas.map((l, i) => {
                  const fuera = excluidas.has(i) || l.estado === "no_existe";
                  return (
                    <tr
                      key={`${l.producto}-${i}`}
                      className={`border-b border-ink-100 last:border-0 ${
                        fuera ? "bg-ink-50/60 text-ink-400" : "hover:bg-paper-50"
                      }`}
                    >
                      <td className="px-3 py-2">
                        <input
                          type="checkbox"
                          checked={!fuera}
                          disabled={l.estado === "no_existe"}
                          title={
                            l.estado === "no_existe"
                              ? "Este código no existe: no se puede pedir"
                              : "Incluir en el pedido"
                          }
                          onChange={(e) => {
                            const s = new Set(excluidas);
                            if (e.target.checked) s.delete(i);
                            else s.add(i);
                            setExcluidas(s);
                          }}
                          className="h-4 w-4 accent-accent-700 disabled:opacity-40"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-mono text-[12.5px]">{l.producto}</div>
                        <div className="mt-0.5 flex flex-wrap gap-1">
                          <Estado linea={l} />
                          {l.duplicado && (
                            <span className="rounded-sm bg-amber-50 px-1.5 py-0.5 text-[11px] font-medium text-amber-800">
                              repetido
                            </span>
                          )}
                          {l.reemplazos && (
                            <span
                              className="rounded-sm bg-sky-50 px-1.5 py-0.5 text-[11px] text-sky-800"
                              title={`Grupo de reemplazo: ${l.reemplazos}`}
                            >
                              tiene reemplazo
                            </span>
                          )}
                        </div>
                      </td>
                      <td className="max-w-[260px] truncate px-3 py-2" title={l.descripcion ?? ""}>
                        {l.descripcion ?? <span className="text-ink-300">—</span>}
                      </td>
                      <td className="px-3 py-2 text-right">
                        <input
                          type="number"
                          min={0}
                          value={cantidadDe(i) ?? ""}
                          disabled={l.estado === "no_existe"}
                          onChange={(e) =>
                            setCantidades({
                              ...cantidades,
                              [i]: e.target.value === "" ? null : Number(e.target.value),
                            })
                          }
                          className="tabular h-8 w-20 rounded-sm border border-ink-200 bg-white px-2 text-right disabled:bg-ink-50"
                        />
                      </td>
                      <td className="px-3 py-2">
                        <Frecuencia linea={l} />
                      </td>
                      <td className="px-3 py-2">{l.clasificacion_abc ?? "—"}</td>
                      <td className="tabular px-3 py-2 text-right">
                        {formatoNumero(l.stock_sucursal ?? 0)}
                      </td>
                      <td className="tabular px-3 py-2 text-right">
                        {l.stock_cd === null ? "—" : formatoNumero(l.stock_cd)}
                      </td>
                      <td className="tabular px-3 py-2 text-right">
                        {formatoNumero(l.stock_nacional ?? 0)}
                      </td>
                      <td className="max-w-[180px] truncate px-3 py-2" title={l.proveedor ?? ""}>
                        {l.proveedor ?? <span className="text-ink-300">—</span>}
                      </td>
                      <td className="tabular px-3 py-2 text-right">
                        {l.costo_unitario ? formatoCLP(l.costo_unitario) : "—"}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>

          {/* Paso 3: el archivo del portal */}
          <div className="rounded-sm border border-ink-200 bg-white p-4 shadow-card">
            <p className="text-[12px] font-medium text-ink-600">
              3 · Descarga el archivo para el portal
            </p>
            <p className="mt-1 text-[12px] text-ink-400">
              Sale con los códigos ya convertidos al formato de cada portal. Un archivo
              por proveedor: no se pueden mezclar.
            </p>
            <div className="mt-3 flex flex-wrap gap-2">
              <Button onClick={() => descargar("FORD")} disabled={!aPedir.length}>
                <Download size={15} /> Archivo para Ford
              </Button>
              <Button
                variant="outline"
                onClick={() => descargar("GILDEMEISTER")}
                disabled={!aPedir.length}
              >
                <Download size={15} /> Archivo para Gildemeister
              </Button>
            </div>
            {descartados && (
              <p className="mt-3 rounded-sm border border-amber-300 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-800">
                {descartados}
              </p>
            )}
          </div>
        </>
      )}
    </div>
  );
}
