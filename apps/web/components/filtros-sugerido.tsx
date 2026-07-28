"use client";

import { Search, X } from "lucide-react";
import type { SugeridoFiltros } from "@/lib/types";

interface Props {
  filtros: SugeridoFiltros;
  onChange: (f: SugeridoFiltros) => void;
  /** Si hay al menos un filtro activo en las columnas del grid. Cuando llega
   *  true, el boton "Limpiar todo" aparece aunque los filtros server-side
   *  esten en default. */
  hayFiltrosColumna?: boolean;
  /** Callback que el padre usa para limpiar TODO de una sola accion: filtros
   *  server-side + filtros de columna del grid. Si no se pasa, el boton solo
   *  resetea los server-side (comportamiento legacy). */
  onLimpiarTodo?: () => void;
  /** Dispara la busqueda YA, sin esperar el debounce del padre. Lo usa el boton
   *  de la lupa y el Enter en el input. */
  onBuscar?: () => void;
}

export function FiltrosSugerido({
  filtros,
  onChange,
  hayFiltrosColumna,
  onLimpiarTodo,
  onBuscar,
}: Props) {
  const set = (parcial: Partial<SugeridoFiltros>) => onChange({ ...filtros, ...parcial });
  // Cualquier cosa que "Limpiar filtros" vaya a deshacer. Ojo: la vista (pestania)
  // NO cuenta, porque limpiar no cambia de pestania a proposito.
  const hayCambios =
    Boolean(filtros.q) ||
    filtros.solo_pedir === false ||
    filtros.solo_nacionales === true ||
    Boolean(filtros.sucursales?.length) ||
    Boolean(filtros.abc?.length) ||
    Boolean(filtros.filtro1?.length) ||
    Boolean(filtros.tipo_origen?.length) ||
    Boolean(filtros.proveedor) ||
    Boolean(filtros.proveedores?.length) ||
    Boolean(hayFiltrosColumna);

  return (
    <div className="flex flex-wrap items-center gap-3 rounded-sm border border-ink-200 bg-white p-3 shadow-card">
      {/* Buscador global — matchea cualquier columna del sugerido */}
      <form
        className="flex min-w-[260px] flex-1 items-center gap-2"
        onSubmit={(e) => {
          e.preventDefault();
          onBuscar?.();
        }}
      >
        <div className="relative flex-1">
          <Search
            size={15}
            className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-400"
          />
          <input
            aria-label="Buscar"
            placeholder="Buscar en toda la tabla… (producto, sucursal, marca, proveedor, ABC…)"
            className="h-10 w-full rounded-sm border border-ink-200 bg-paper-50 pl-9 pr-8 text-[13.5px] text-ink-900 placeholder:text-ink-400 transition-colors focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent-700/30"
            value={filtros.q ?? ""}
            onChange={(e) => set({ q: e.target.value })}
          />
          {filtros.q && (
            <button
              type="button"
              onClick={() => set({ q: "" })}
              className="absolute right-2 top-1/2 -translate-y-1/2 rounded-sm p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
              aria-label="Borrar búsqueda"
            >
              <X size={13} />
            </button>
          )}
        </div>
        {/* La tabla ya se filtra mientras se escribe; el boton es para quien
            espera apretar algo (y para el Enter, que antes no hacia nada). */}
        <button
          type="submit"
          title="Buscar"
          className="flex h-10 shrink-0 items-center gap-1.5 rounded-sm border border-accent-700 bg-accent-700 px-3.5 text-[13px] font-medium text-white transition-colors hover:bg-accent-800"
        >
          <Search size={15} /> Buscar
        </button>
      </form>

      <Toggle
        label="Solo pedir = Sí"
        active={filtros.solo_pedir ?? true}
        onChange={(v) => set({ solo_pedir: v })}
      />
      <Toggle
        label="Solo nacionales"
        active={filtros.solo_nacionales ?? false}
        onChange={(v) => set({ solo_nacionales: v })}
        title="Excluye los productos importados"
      />

      {/* Siempre visible: antes solo aparecia cuando habia algo filtrado y la gente
          lo buscaba donde no estaba. Deshabilitado dice "aca es, pero no hay nada
          que limpiar" mejor que no mostrar nada. */}
      <button
        type="button"
        disabled={!hayCambios}
        title={hayCambios ? "Vuelve la tabla al estado inicial" : "No hay filtros aplicados"}
        onClick={() => {
          // Reset completo: no sobreescribe campos que el dashboard puede haber
          // seteado por otro lado (sucursales, abc, etc.) — los borramos también
          // porque "Limpiar" es eso, volver al estado inicial. Si el padre nos pasa
          // onLimpiarTodo, se la dejamos para que tambien borre los filtros de
          // columna del grid.
          if (onLimpiarTodo) {
            onLimpiarTodo();
            return;
          }
          onChange({
            q: "",
            solo_pedir: true,
            solo_nacionales: false,
            vista: "todas",
          });
        }}
        className={`flex h-10 items-center gap-1 rounded-sm px-2.5 text-[12px] transition-colors ${
          hayCambios
            ? "text-ink-500 hover:bg-ink-100 hover:text-ink-800"
            : "cursor-not-allowed text-ink-300"
        }`}
      >
        <X size={13} /> Limpiar filtros
      </button>
    </div>
  );
}

function Toggle({
  label,
  active,
  onChange,
  title,
}: {
  label: string;
  active: boolean;
  onChange: (v: boolean) => void;
  title?: string;
}) {
  return (
    <button
      type="button"
      title={title}
      onClick={() => onChange(!active)}
      className={`group flex h-10 items-center gap-2 rounded-sm border px-3 text-[13px] font-medium transition-colors ${
        active
          ? "border-accent-700 bg-accent-50 text-accent-700"
          : "border-ink-200 bg-white text-ink-600 hover:border-ink-300 hover:text-ink-900"
      }`}
    >
      <span
        className={`relative inline-flex h-4 w-7 items-center rounded-full transition-colors ${
          active ? "bg-accent-700" : "bg-ink-300 group-hover:bg-ink-400"
        }`}
      >
        <span
          className={`inline-block h-3 w-3 rounded-full bg-white shadow transition-transform ${
            active ? "translate-x-3.5" : "translate-x-0.5"
          }`}
        />
      </span>
      {label}
    </button>
  );
}
