"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { AlertCircle, Loader2, Plus, Trash2 } from "lucide-react";
import { api } from "@/lib/api-client";
import { getSoloLectura } from "@/lib/auth";
import type { RepuestoInstock } from "@/lib/types";

/**
 * La lista InStock: los repuestos que no pueden faltar en las sucursales con taller.
 *
 * Dos origenes conviven en la misma tabla. Los de la **pauta** los trae el archivo
 * del fabricante y se recargan solos en cada corrida del motor; los **manuales**
 * los agrega alguien desde aca y sobreviven a esa recarga.
 *
 * Por eso los de la pauta no se pueden borrar: la proxima carga los repondria y el
 * boton estaria mintiendo. Solo se muestra el basurero en los manuales.
 */
const SUCURSALES = "Linderos, Rancagua, Curicó y Chillán";

export default function InstockPage() {
  const [filas, setFilas] = useState<RepuestoInstock[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  const [soloManuales, setSoloManuales] = useState(false);
  const [abierto, setAbierto] = useState(false);
  // Se lee en el efecto y no al montar: sale de localStorage y en el render del
  // servidor no existe. Es el mismo patron del detalle de catalogo.
  const [soloLectura, setSoloLectura] = useState(true);

  useEffect(() => {
    setSoloLectura(getSoloLectura());
  }, []);

  const cargar = useCallback(async () => {
    try {
      setFilas(await api.instockLista());
      setError(null);
    } catch {
      setError("No se pudo cargar la lista.");
    }
  }, []);

  useEffect(() => {
    void cargar();
  }, [cargar]);

  const visibles = useMemo(() => {
    if (!filas) return [];
    const q = busqueda.trim().toLowerCase();
    return filas.filter((f) => {
      if (soloManuales && f.origen !== "manual") return false;
      if (!q) return true;
      return [f.producto, f.modelos, f.marca, f.operacion, f.motivo]
        .some((v) => (v ?? "").toLowerCase().includes(q));
    });
  }, [filas, busqueda, soloManuales]);

  const manuales = filas?.filter((f) => f.origen === "manual").length ?? 0;

  async function quitar(producto: string) {
    if (!confirm(`¿Sacar ${producto} de la lista InStock?`)) return;
    try {
      await api.quitarInstock(producto);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo quitar.");
    }
  }

  return (
    <div className="space-y-5 p-6">
      <header className="space-y-1">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
          Abastecimiento
        </p>
        <h1 className="text-2xl font-semibold text-ink-900">Repuestos InStock</h1>
        <p className="max-w-3xl text-sm text-ink-500">
          Estos repuestos nunca pueden faltar en {SUCURSALES}, que son las sucursales
          con taller. Si el stock, el tránsito y el sugerido no llegan al mínimo, el
          sugerido se completa solo. En el resto de las sucursales la regla no aplica.
        </p>
      </header>

      <div className="flex flex-wrap items-center gap-3">
        <input
          value={busqueda}
          onChange={(e) => setBusqueda(e.target.value)}
          placeholder="Buscar por código, modelo o motivo…"
          className="h-9 w-72 rounded-md border border-ink-200 px-3 text-sm outline-none focus:border-brand"
        />
        <label className="flex items-center gap-2 text-sm text-ink-600">
          <input
            type="checkbox"
            checked={soloManuales}
            onChange={(e) => setSoloManuales(e.target.checked)}
          />
          Solo los agregados a mano ({manuales})
        </label>
        {!soloLectura && (
          <button
            onClick={() => setAbierto(true)}
            className="ml-auto inline-flex h-9 items-center gap-1.5 rounded-md bg-brand px-3 text-sm font-semibold text-white hover:bg-brand-600"
          >
            <Plus className="h-4 w-4" />
            Agregar repuesto
          </button>
        )}
      </div>

      {error && (
        <p className="flex items-center gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
          <AlertCircle className="h-4 w-4 shrink-0" />
          {error}
        </p>
      )}

      {filas === null ? (
        <p className="flex items-center gap-2 text-sm text-ink-500">
          <Loader2 className="h-4 w-4 animate-spin" /> Cargando…
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-ink-100">
          <table className="w-full text-sm">
            <thead className="bg-ink-50 text-left text-[11px] uppercase tracking-wide text-ink-500">
              <tr>
                <th className="px-3 py-2">Producto</th>
                <th className="px-3 py-2">Origen</th>
                <th className="px-3 py-2 text-right">Mínimo</th>
                <th className="px-3 py-2">Modelos / motivo</th>
                <th className="px-3 py-2">Agregado por</th>
                <th className="px-3 py-2" />
              </tr>
            </thead>
            <tbody>
              {visibles.map((f) => (
                <tr key={f.producto} className="border-t border-ink-100">
                  <td className="px-3 py-2">
                    <Link
                      href={`/catalogo/${encodeURIComponent(f.producto)}`}
                      className="font-mono text-[12px] text-ink-700 hover:text-brand"
                    >
                      {f.producto}
                    </Link>
                  </td>
                  <td className="px-3 py-2">
                    {f.origen === "manual" ? (
                      <span className="rounded bg-sky-50 px-1.5 py-px text-[10px] font-semibold text-sky-700">
                        A MANO
                      </span>
                    ) : (
                      <span className="rounded bg-ink-100 px-1.5 py-px text-[10px] font-semibold text-ink-500">
                        PAUTA
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-right tabular-nums">{f.minimo}</td>
                  <td className="px-3 py-2 text-ink-600">
                    {f.origen === "manual" ? f.motivo ?? "—" : f.modelos ?? "—"}
                  </td>
                  <td className="px-3 py-2 text-[12px] text-ink-500">
                    {f.creado_por ?? "—"}
                    {f.creado_en ? ` · ${f.creado_en.slice(0, 10)}` : ""}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {/* Los de la pauta no se pueden quitar: la proxima carga los
                        repondria. Se oculta el boton en vez de mostrarlo y fallar. */}
                    {f.origen === "manual" && !soloLectura && (
                      <button
                        onClick={() => void quitar(f.producto)}
                        title="Quitar de la lista"
                        className="text-ink-400 hover:text-rose-600"
                      >
                        <Trash2 className="h-4 w-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
              {visibles.length === 0 && (
                <tr>
                  <td colSpan={6} className="px-3 py-8 text-center text-sm text-ink-500">
                    {busqueda || soloManuales
                      ? "Nada calza con el filtro."
                      : "La lista está vacía."}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      )}

      {abierto && (
        <ModalAgregar
          onCerrar={() => setAbierto(false)}
          onGuardado={async () => {
            setAbierto(false);
            await cargar();
          }}
        />
      )}
    </div>
  );
}

function ModalAgregar({
  onCerrar,
  onGuardado,
}: {
  onCerrar: () => void;
  onGuardado: () => void | Promise<void>;
}) {
  const [producto, setProducto] = useState("");
  const [minimo, setMinimo] = useState(2);
  const [motivo, setMotivo] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  async function guardar() {
    setGuardando(true);
    setError(null);
    try {
      await api.agregarInstock({ producto: producto.trim(), minimo, motivo });
      await onGuardado();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo agregar.");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/30 p-4">
      <div className="w-full max-w-md space-y-4 rounded-xl bg-white p-5 shadow-xl">
        <div className="space-y-1">
          <h2 className="text-lg font-semibold text-ink-900">Agregar a InStock</h2>
          <p className="text-[13px] text-ink-500">
            El repuesto va a tener un mínimo garantizado en {SUCURSALES}.
          </p>
        </div>

        <label className="block space-y-1">
          <span className="text-[12px] font-medium text-ink-600">Código del producto</span>
          <input
            value={producto}
            onChange={(e) => setProducto(e.target.value)}
            placeholder="19 MB3Z19N619A"
            className="h-9 w-full rounded-md border border-ink-200 px-3 font-mono text-sm outline-none focus:border-brand"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-[12px] font-medium text-ink-600">
            Mínimo por sucursal
          </span>
          <input
            type="number"
            min={1}
            value={minimo}
            onChange={(e) => setMinimo(Math.max(1, Number(e.target.value) || 1))}
            className="h-9 w-24 rounded-md border border-ink-200 px-3 text-sm tabular-nums outline-none focus:border-brand"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-[12px] font-medium text-ink-600">
            Motivo <span className="font-normal text-ink-400">(para saber después por qué está)</span>
          </span>
          <textarea
            value={motivo}
            onChange={(e) => setMotivo(e.target.value)}
            rows={2}
            placeholder="Se quiebra seguido y el taller queda parado"
            className="w-full rounded-md border border-ink-200 px-3 py-2 text-sm outline-none focus:border-brand"
          />
        </label>

        {error && (
          <p className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-[13px] text-rose-800">
            {error}
          </p>
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={onCerrar}
            className="h-9 rounded-md px-3 text-sm text-ink-600 hover:bg-ink-50"
          >
            Cancelar
          </button>
          <button
            onClick={() => void guardar()}
            disabled={!producto.trim() || guardando}
            className="inline-flex h-9 items-center gap-1.5 rounded-md bg-brand px-3 text-sm font-semibold text-white hover:bg-brand-600 disabled:opacity-50"
          >
            {guardando && <Loader2 className="h-4 w-4 animate-spin" />}
            Agregar
          </button>
        </div>
      </div>
    </div>
  );
}
