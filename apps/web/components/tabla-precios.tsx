"use client";

import { useMemo, useRef } from "react";
import { AgGridReact } from "ag-grid-react";
import type { ColDef, GridReadyEvent, RowClickedEvent } from "ag-grid-community";
import { COLUMNAS_PRECIOS, claseEstado, type DefColPrecio } from "@/lib/columnas-precios";
import { formatoCLP, formatoFecha, formatoNumero } from "@/lib/formato";
import type { PrecioRow } from "@/lib/types";
import { FiltroMultiSelect } from "@/components/filtro-multiselect";

interface Props {
  rows: PrecioRow[];
  columnasVisibles: string[];
  onFila: (fila: PrecioRow) => void;
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

export function TablaPrecios({ rows, columnasVisibles, onFila }: Props) {
  const gridRef = useRef<AgGridReact<PrecioRow>>(null);

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
    </div>
  );
}
