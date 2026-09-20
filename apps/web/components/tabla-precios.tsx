"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AgGridReact } from "ag-grid-react";
import type { CellContextMenuEvent, ColDef, GridReadyEvent, RowClickedEvent } from "ag-grid-community";
import { ExternalLink, Trash2 } from "lucide-react";
import { COLUMNAS_PRECIOS, claseEstado, type DefColPrecio } from "@/lib/columnas-precios";
import { formatoCLP, formatoFecha, formatoNumero } from "@/lib/formato";
import type { PrecioRow } from "@/lib/types";
import { FiltroMultiSelect } from "@/components/filtro-multiselect";

interface Props {
  rows: PrecioRow[];
  columnasVisibles: string[];
  onFila: (fila: PrecioRow) => void;
  /** Con clic derecho sobre una fila. Si no viene, el usuario no puede editar y
   *  el menu solo ofrece abrir la ficha. */
  onEliminar?: (fila: PrecioRow) => void;
}

interface MenuContextual {
  x: number;
  y: number;
  fila: PrecioRow;
}

function formateador(def: DefColPrecio) {
  return (p: { value: unknown }) => {
    const v = p.value as number | string | boolean | null;
    if (v === null || v === undefined || v === "") return "—";
    switch (def.tipo) {
      case "clp":
        return formatoCLP(v as number);
      case "numero":
        return formatoNumero(v as number, 0);
      case "decimal":
        return formatoNumero(v as number, 2);
      case "pct":
        return `${formatoNumero(v as number, 1)} %`;
      case "fecha":
        return formatoFecha(String(v));
      case "bool":
        return v ? "Si" : "";
      default:
        return String(v);
    }
  };
}

function colDef(def: DefColPrecio): ColDef {
  const numerica = ["clp", "numero", "decimal", "pct"].includes(def.tipo);
  const base: ColDef = {
    field: def.key as string,
    headerName: def.label,
    headerTooltip: def.ayuda,
    pinned: def.pin,
    sortable: true,
    resizable: true,
    minWidth: def.tipo === "texto" ? 130 : 110,
    flex: def.key === "glosa" ? 2 : undefined,
    valueFormatter: formateador(def),
  };
  if (numerica) {
    base.cellClass = "tabular text-right";
    if (def.key === "precio_final") base.cellClass = "tabular text-right font-semibold";
  }
  // ag-grid trata un string devuelto por el renderer como TEXTO (se veia el
  // HTML crudo en la celda): hay que devolver un elemento React.
  if (def.tipo === "estado") {
    base.cellRenderer = EstadoCell;
  }
  if (def.key === "cambios_pendientes") {
    base.cellRenderer = CambiosCell;
    base.cellClass = "text-center";
  }
  return base;
}

function EstadoCell(p: { value: string | null }) {
  if (!p.value) return <span>—</span>;
  return (
    <span className={`inline-flex rounded-sm px-1.5 py-0.5 text-[10px] font-semibold uppercase tracking-wider ${claseEstado(p.value)}`}>
      {p.value}
    </span>
  );
}

function CambiosCell(p: { value: number | null }) {
  if (!p.value) return null;
  return (
    <span className="inline-flex min-w-[1.5rem] justify-center rounded-full bg-amber-100 px-1.5 text-[11px] font-semibold text-amber-800">
      {p.value}
    </span>
  );
}

export function TablaPrecios({ rows, columnasVisibles, onFila, onEliminar }: Props) {
  const gridRef = useRef<AgGridReact<PrecioRow>>(null);
  // AG Grid Community no trae menu contextual (es de la version paga), asi que
  // se dibuja uno propio sobre el clic derecho de la fila.
  const [menu, setMenu] = useState<MenuContextual | null>(null);

  useEffect(() => {
    if (!menu) return;
    const cerrar = () => setMenu(null);
    const tecla = (e: KeyboardEvent) => { if (e.key === "Escape") cerrar(); };
    // Cualquier clic afuera, scroll o Escape lo cierra: un menu que queda
    // colgado sobre otra fila es la forma mas facil de borrar el producto equivocado.
    window.addEventListener("click", cerrar);
    window.addEventListener("scroll", cerrar, true);
    window.addEventListener("keydown", tecla);
    return () => {
      window.removeEventListener("click", cerrar);
      window.removeEventListener("scroll", cerrar, true);
      window.removeEventListener("keydown", tecla);
    };
  }, [menu]);

  const onCellContextMenu = (e: CellContextMenuEvent<PrecioRow>) => {
    const ev = e.event as MouseEvent | null;
    if (!ev || !e.data) return;
    ev.preventDefault();
    // Pegado al borde, el menu se abre hacia adentro para no salirse de la pantalla.
    const x = Math.min(ev.clientX, window.innerWidth - 240);
    const y = Math.min(ev.clientY, window.innerHeight - 120);
    setMenu({ x, y, fila: e.data });
  };

  const columnDefs = useMemo<ColDef[]>(
    () => COLUMNAS_PRECIOS.filter((c) => columnasVisibles.includes(c.key as string)).map(colDef),
    [columnasVisibles]
  );

  const defaultColDef = useMemo<ColDef>(
    () => ({
      sortable: true,
      resizable: true,
      suppressHeaderMenuButton: false,
      filter: FiltroMultiSelect,
      menuTabs: ["filterMenuTab"],
    }),
    []
  );

  const popupParent = useMemo<HTMLElement | undefined>(
    () => (typeof document !== "undefined" ? document.body : undefined),
    []
  );

  const onGridReady = (e: GridReadyEvent) => {
    e.api.sizeColumnsToFit();
  };

  return (
    <div className="ag-theme-quartz" style={{ width: "100%", height: "calc(100vh - 330px)", minHeight: 380 }}>
      <AgGridReact<PrecioRow>
        ref={gridRef}
        rowData={rows}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        popupParent={popupParent}
        onGridReady={onGridReady}
        onRowClicked={(e: RowClickedEvent<PrecioRow>) => {
          if (e.data) onFila(e.data);
        }}
        onCellContextMenu={onCellContextMenu}
        preventDefaultOnContextMenu
        rowClass="cursor-pointer"
        pagination
        paginationPageSize={100}
        paginationPageSizeSelector={[50, 100, 200, 500]}
        animateRows
        suppressCellFocus
        overlayNoRowsTemplate="<span class='text-slate-400'>Sin productos para los filtros aplicados</span>"
        localeText={{
          page: "Pagina", to: "a", of: "de", next: "Siguiente",
          previous: "Anterior", first: "Primera", last: "Ultima",
          noRowsToShow: "Sin datos",
        }}
      />

      {menu && (
        <div
          role="menu"
          aria-label={`Acciones para ${menu.fila.producto}`}
          className="fixed z-50 min-w-[220px] rounded-md border border-slate-200 bg-white py-1 text-[13px] shadow-lg"
          style={{ left: menu.x, top: menu.y }}
          onClick={(e) => e.stopPropagation()}
        >
          <div className="truncate px-3 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-slate-400">
            {menu.fila.producto}
          </div>
          <button
            type="button"
            role="menuitem"
            className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-slate-700 hover:bg-slate-50"
            onClick={() => { const f = menu.fila; setMenu(null); onFila(f); }}
          >
            <ExternalLink size={14} className="text-slate-400" /> Abrir ficha
          </button>
          {onEliminar && (
            <button
              type="button"
              role="menuitem"
              className="flex w-full items-center gap-2 px-3 py-1.5 text-left text-rose-700 hover:bg-rose-50"
              onClick={() => { const f = menu.fila; setMenu(null); onEliminar(f); }}
            >
              <Trash2 size={14} /> Sacar de la lista…
            </button>
          )}
        </div>
      )}
    </div>
  );
}
