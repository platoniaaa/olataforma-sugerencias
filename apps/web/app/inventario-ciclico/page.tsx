"use client";

// Inventario ciclico. Jefatura (admin) carga los lunes y sigue avance y diferencias;
// bodega cuenta en el celular. El rol lo decide el backend (/api/inventario-ciclico/yo).
import { useCallback, useEffect, useState } from "react";
import { ClipboardCheck, RefreshCw } from "lucide-react";
import { Carga } from "@/components/inventario-ciclico/carga";
import { Conteo } from "@/components/inventario-ciclico/conteo";
import { Detalle } from "@/components/inventario-ciclico/detalle";
import { Resumen } from "@/components/inventario-ciclico/resumen";
import {
  etiquetaSemana,
  inventarioApi,
  type ItemInventario,
  type ResumenSucursal,
  type RolInventario,
} from "@/lib/inventario-ciclico";

type Pestana = "resumen" | "carga";

export default function InventarioCiclicoPage() {
  const [rol, setRol] = useState<RolInventario | undefined>(undefined);
  const [semanas, setSemanas] = useState<string[]>([]);
  const [semana, setSemana] = useState<string>("");
  const [pestana, setPestana] = useState<Pestana>("resumen");
  const [resumen, setResumen] = useState<ResumenSucursal[]>([]);
  const [sucursal, setSucursal] = useState<string | null>(null);
  const [items, setItems] = useState<ItemInventario[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const esAdmin = rol === "admin";

  const cargarSemanas = useCallback(async (preferida?: string) => {
    const lista = await inventarioApi.semanas();
    setSemanas(lista);
    setSemana((actual) => preferida ?? (actual && lista.includes(actual) ? actual : lista[0] ?? ""));
  }, []);

  useEffect(() => {
    (async () => {
      try {
        const yo = await inventarioApi.yo();
        setRol(yo.rol);
        if (yo.rol) await cargarSemanas();
      } catch (e) {
        setError(e instanceof Error ? e.message : "Error al cargar");
      } finally {
        setCargando(false);
      }
    })();
  }, [cargarSemanas]);

  const cargarDatos = useCallback(async () => {
    if (!rol || !semana) return;
    setCargando(true);
    setError(null);
    try {
      if (rol === "admin") {
        const r = await inventarioApi.resumen(semana);
        setResumen(r);
        const suc = sucursal && r.some((f) => f.sucursal_id === sucursal) ? sucursal : r[0]?.sucursal_id ?? null;
        setSucursal(suc);
        setItems(suc ? await inventarioApi.items(semana, suc) : []);
      } else {
        setItems(await inventarioApi.items(semana));
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setCargando(false);
    }
    // `sucursal` se lee pero no dispara recarga: cambiarla usa elegirSucursal.
  }, [rol, semana]);

  useEffect(() => {
    cargarDatos();
  }, [cargarDatos]);

  const elegirSucursal = async (s: string) => {
    setSucursal(s);
    try {
      setItems(await inventarioApi.items(semana, s));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    }
  };

  const actualizarItem = (nuevo: ItemInventario) => {
    setItems((prev) => prev.map((i) => (i.id === nuevo.id ? nuevo : i)));
    if (esAdmin) inventarioApi.resumen(semana).then(setResumen).catch(() => undefined);
  };

  if (rol === undefined) {
    return <p className="text-[13px] text-ink-500">{error ?? "Cargando…"}</p>;
  }
  if (rol === null) {
    return (
      <div className="rounded-sm border border-dashed border-ink-200 bg-white px-4 py-10 text-center">
        <ClipboardCheck className="mx-auto mb-2 text-ink-300" size={28} />
        <p className="text-[13px] text-ink-500">No tienes acceso al inventario cíclico. Pídelo a tu jefatura.</p>
      </div>
    );
  }

  const pestanaClase = (p: Pestana) =>
    `border-b-2 px-3 py-2 text-[13.5px] font-medium transition-colors ${
      pestana === p ? "border-accent-500 text-ink-900" : "border-transparent text-ink-500 hover:text-ink-800"
    }`;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-ink-900">Inventario cíclico</h1>
          <p className="text-[13px] text-ink-500">
            {esAdmin ? "Avance y diferencias de la toma de inventario por bodega" : "Productos a contar esta semana"}
          </p>
        </div>
        {semanas.length > 0 && (
          <div className="flex items-center gap-2">
            <select
              value={semana}
              onChange={(e) => setSemana(e.target.value)}
              className="h-9 rounded-sm border border-ink-200 bg-white px-2 text-[13px]"
              aria-label="Semana"
            >
              {semanas.map((s) => (
                <option key={s} value={s}>
                  {etiquetaSemana(s)}
                </option>
              ))}
            </select>
            <button
              type="button"
              onClick={cargarDatos}
              className="inline-flex h-9 items-center gap-1.5 rounded-sm border border-ink-200 bg-white px-3 text-[13px] hover:bg-paper-100"
            >
              <RefreshCw size={14} className={cargando ? "animate-spin" : ""} /> Actualizar
            </button>
          </div>
        )}
      </div>

      {esAdmin && (
        <div className="flex gap-1 border-b border-ink-200">
          <button type="button" className={pestanaClase("resumen")} onClick={() => setPestana("resumen")}>
            Avance y diferencias
          </button>
          <button type="button" className={pestanaClase("carga")} onClick={() => setPestana("carga")}>
            Carga semanal
          </button>
        </div>
      )}

      {error && <p className="rounded-sm bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>}

      {esAdmin && pestana === "carga" && (
        <Carga
          onCargado={async (s) => {
            await cargarSemanas(s);
            // Misma semana ya seleccionada: el cambio de estado no dispara la recarga.
            if (s === semana) await cargarDatos();
          }}
        />
      )}

      {esAdmin && pestana === "resumen" && (
        <div className="space-y-4">
          <Resumen filas={resumen} seleccionada={sucursal} onSeleccionar={elegirSucursal} />
          {sucursal && (
            <div className="space-y-2">
              <h2 className="font-display text-[16px] font-medium text-ink-900">{sucursal}</h2>
              <Detalle items={items} onCambio={actualizarItem} />
            </div>
          )}
        </div>
      )}

      {!esAdmin &&
        (semanas.length === 0 && !cargando ? (
          <p className="rounded-sm border border-dashed border-ink-200 bg-white px-4 py-8 text-center text-[13px] text-ink-500">
            Todavía no hay productos asignados.
          </p>
        ) : (
          <Conteo items={items} esAdmin={false} onCambio={actualizarItem} />
        ))}
    </div>
  );
}
