"use client";

import { forwardRef, useEffect, useImperativeHandle, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useRouter } from "next/navigation";
import { AgGridReact } from "ag-grid-react";
import type {
  CellContextMenuEvent,
  ColDef,
  ColumnState,
  FirstDataRenderedEvent,
  GridReadyEvent,
  IHeaderParams,
  IRowNode,
  RowClickedEvent,
  SortDirection,
} from "ag-grid-community";
import { Check, Copy, Info } from "lucide-react";
import { COLUMNAS, type DefColumna } from "@/lib/columnas";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import { STORAGE_KEYS, guardar, leer } from "@/lib/persistencia-dashboard";
import type { ColumnaFiltro, SugeridoFiltros, SugeridoKpis, SugeridoRow } from "@/lib/types";
import { FiltroMultiSelect } from "@/components/filtro-multiselect";

type Vista = NonNullable<SugeridoFiltros["vista"]>;

interface Props {
  rows: SugeridoRow[];
  columnasVisibles: string[];
  /**
   * Vista activa (todas/sucursales/cd/distribucion). El filter model se guarda
   * por vista porque sus columnas/valores no son iguales entre tabs.
   */
  vista: Vista;
  onRowClick: (row: SugeridoRow) => void;
  /**
   * Se dispara cada vez que cambia el conjunto de filas visibles (filtros de
   * columna, sort, rowData). El padre lo usa para refrescar los KPIs sobre las
   * filas realmente visibles, no sobre el universo server-side.
   */
  onKpisVisiblesChange?: (kpis: SugeridoKpis, totalVisibles: number) => void;
  /** Notifica al padre los filtros de columna activos, traducidos del multi-select,
   *  para mandarlos al backend (KPIs, conteo y Excel exactos sobre el total). */
  onFiltrosColumnaChange?: (filtros: ColumnaFiltro[]) => void;
}

export interface TablaSugeridoHandle {
  /** IDs de las filas visibles tras filtros y orden del AG Grid. Solo del BI (id > 0). */
  obtenerIdsVisibles(): number[];
  /** Borra el filterModel del grid y persiste el cambio. */
  limpiarFiltrosColumnas(): void;
}

function ProductoCelda(p: { value: unknown; data?: SugeridoRow }) {
  const v = (p.value as string | null) ?? "";
  const origen = p.data?.origen;
  if (origen !== "catalogo" && origen !== "manual") return <>{v}</>;
  const cls =
    origen === "manual"
      ? "rounded bg-emerald-50 px-1.5 py-px text-[10px] font-semibold text-emerald-700"
      : "rounded bg-slate-100 px-1.5 py-px text-[10px] font-semibold text-slate-500";
  return (
    <span className="inline-flex items-center gap-1.5">
      <span>{v}</span>
      <span className={cls}>{origen === "manual" ? "MANUAL" : "CATÁLOGO"}</span>
    </span>
  );
}

/**
 * Encabezado custom de AG Grid: réplica del header por defecto (click para ordenar,
 * indicador de orden, botón de filtro) MÁS un icono de info que muestra el detalle
 * de la columna al pasar el mouse. El tooltip se renderiza en un portal a <body>
 * (posición fija sobre el icono) para que no lo recorte el overflow del header.
 * Se usa header component completo porque `innerHeaderComponent` no se aplica en
 * esta versión de AG Grid React.
 */
function HeaderConInfo(props: IHeaderParams & { info?: string }) {
  const { displayName, enableSorting, enableFilterButton, progressSort, showFilter, column, info } = props;
  const [sort, setSort] = useState<SortDirection>(() => column.getSort() ?? null);
  const [filtroActivo, setFiltroActivo] = useState<boolean>(() => column.isFilterActive());
  const filterRef = useRef<HTMLSpanElement>(null);
  const iconRef = useRef<HTMLSpanElement>(null);
  const [tip, setTip] = useState<{ x: number; y: number } | null>(null);

  useEffect(() => {
    const onSort = () => setSort(column.getSort() ?? null);
    const onFilter = () => setFiltroActivo(column.isFilterActive());
    column.addEventListener("sortChanged", onSort);
    column.addEventListener("filterChanged", onFilter);
    return () => {
      column.removeEventListener("sortChanged", onSort);
      column.removeEventListener("filterChanged", onFilter);
    };
  }, [column]);

  const mostrarTip = () => {
    const r = iconRef.current?.getBoundingClientRect();
    if (r) setTip({ x: r.left + r.width / 2, y: r.bottom + 6 });
  };

  return (
    <div className="flex h-full w-full items-center gap-1">
      <span
        className={enableSorting ? "cursor-pointer select-none" : "select-none"}
        onClick={(e) => enableSorting && progressSort(e.shiftKey)}
      >
        {displayName}
      </span>
      {sort === "asc" && <span className="ag-icon ag-icon-asc shrink-0" role="presentation" />}
      {sort === "desc" && <span className="ag-icon ag-icon-desc shrink-0" role="presentation" />}
      {info && (
        <span
          ref={iconRef}
          onMouseEnter={mostrarTip}
          onMouseLeave={() => setTip(null)}
          onClick={(e) => e.stopPropagation()}
          className="inline-flex shrink-0 cursor-help text-ink-400 transition-colors hover:text-accent-600"
          aria-label={info}
        >
          <Info size={13} />
        </span>
      )}
      <span className="flex-1" />
      {enableFilterButton && (
        <span
          ref={filterRef}
          role="button"
          aria-label="Filtrar"
          onClick={(e) => {
            e.stopPropagation();
            if (filterRef.current) showFilter(filterRef.current);
          }}
          className={`ag-icon ag-icon-filter shrink-0 cursor-pointer ${
            filtroActivo ? "text-accent-600" : "text-ink-400 hover:text-ink-600"
          }`}
        />
      )}
      {tip &&
        info &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            className="pointer-events-none fixed z-[200] max-w-[280px] -translate-x-1/2 rounded-md border border-ink-200 bg-white px-3 py-2 text-[12px] font-normal normal-case leading-snug tracking-normal text-ink-700 shadow-lift"
            style={{ left: tip.x, top: tip.y }}
          >
            {info}
          </div>,
          document.body
        )}
    </div>
  );
}

function formateador(def: DefColumna) {
  return (p: { value: unknown }) => {
    const v = p.value as number | string | null;
    if (v === null || v === undefined || v === "") return "—";
    switch (def.tipo) {
      case "clp":
        return formatoCLP(v as number);
      case "numero":
        return formatoNumero(v as number, 0);
      case "decimal":
        return formatoNumero(v as number, 2);
      default:
        return String(v);
    }
  };
}

function colDef(def: DefColumna): ColDef {
  const numerica = def.tipo !== "texto" && def.tipo !== "abc";
  // Todas las columnas comparten ancho por defecto (flex viene del defaultColDef
  // del grid). Solo seteamos minWidth para que columnas con valores largos no
  // se hagan ilegibles al achicar mucho. El usuario puede redimensionar a gusto
  // (resizable: true en defaultColDef).
  const base: ColDef = {
    field: def.key as string,
    headerName: def.label,
    pinned: def.pin,
    minWidth: def.tipo === "texto" ? 120 : 100,
  };

  if (def.key === "producto") {
    base.cellRenderer = ProductoCelda;
  }

  // Header custom con icono de info (detalle de la columna al hover) + sort/filtro.
  base.headerComponent = HeaderConInfo;
  base.headerComponentParams = { info: def.info };

  if (def.tipo === "abc") {
    base.cellClass = "font-semibold";
    base.cellStyle = (p) => {
      const map: Record<string, { color: string }> = {
        A: { color: "#047857" },
        B: { color: "#b45309" },
        C: { color: "#64748b" },
      };
      return map[String(p.value)] ?? null;
    };
  } else if (numerica) {
    // Solo alineamos la CELDA a la derecha (numeros), no el header. El built-in
    // type='rightAligned' tambien aplica ag-right-aligned-header, que invierte
    // el orden del header a [icono-filtro][texto] y deja el icono inconsistente
    // entre columnas de texto y numericas.
    base.cellClass = "tabular ag-right-aligned-cell";
    base.valueFormatter = formateador(def);
    if (def.key === "total_sugerido_suc") {
      base.cellClass = "tabular ag-right-aligned-cell font-semibold";
    }
  }
  return base;
}

type FilterModelByVista = Record<string, Record<string, unknown>>;
type FilterModel = Record<string, unknown>;

/** Traduce el filter model del grid (multi-select) a la forma del backend: por
 *  columna, {contiene} (busqueda) o {valores} (lista exacta; "(en blanco)" = nulo). */
function traducirFilterModel(model: Record<string, unknown>): ColumnaFiltro[] {
  const out: ColumnaFiltro[] = [];
  for (const [campo, raw] of Object.entries(model ?? {})) {
    const m = raw as { contains?: string; values?: string[] } | null;
    if (!m) continue;
    if (typeof m.contains === "string" && m.contains !== "") {
      out.push({ campo, contiene: m.contains });
    } else if (Array.isArray(m.values)) {
      out.push({ campo, valores: m.values });
    }
  }
  return out;
}

export const TablaSugerido = forwardRef<TablaSugeridoHandle, Props>(function TablaSugerido(
  { rows, columnasVisibles, vista, onRowClick, onKpisVisiblesChange, onFiltrosColumnaChange },
  ref
) {
  const gridRef = useRef<AgGridReact<SugeridoRow>>(null);
  const router = useRouter();

  // Persistencia:
  // - `restoredRef`: pasa a true tras la primera restauración. Antes de eso,
  //   ignoramos los eventos del grid (algunos disparan durante setup interno).
  // - `aplicandoRef`: true mientras NOSOTROS llamamos setFilterModel/applyColumnState
  //   para que no se persistan los cambios derivados de esa restauración.
  // - `vistaRef`: vista activa al momento del último evento (refleja la prop
  //   sin requerir cierre fresco en los handlers).
  const restoredRef = useRef(false);
  const aplicandoRef = useRef(false);
  const vistaRef = useRef<Vista>(vista);
  const resizeTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Ref a la callback de KPIs para que `notificarKpis` lea siempre la version
  // mas reciente sin recrear el handler cada render.
  const onKpisRef = useRef(onKpisVisiblesChange);
  useEffect(() => {
    onKpisRef.current = onKpisVisiblesChange;
  }, [onKpisVisiblesChange]);

  // Ref equivalente para la callback de "hay filtros de columna".
  const onFiltrosColRef = useRef(onFiltrosColumnaChange);
  useEffect(() => {
    onFiltrosColRef.current = onFiltrosColumnaChange;
  }, [onFiltrosColumnaChange]);

  // Ref a las filas para que el handler imperativo (obtenerIdsVisibles) y los
  // KPIs vean siempre el array actualizado sin recrearse en cada render.
  const rowsRef = useRef(rows);
  useEffect(() => {
    rowsRef.current = rows;
    // Cuando llegan filas nuevas (recarga del backend, cambio de vista),
    // recalculamos KPIs. Si AG Grid aun no esta listo, onFirstDataRendered los
    // calculara despues; mientras tanto, el primer pintado ya tiene un total
    // correcto.
    if (restoredRef.current) notificarKpis();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [rows]);

  /**
   * Suma KPIs sobre las filas visibles tras filtros de columna + sort del grid.
   * Espeja la misma lógica que `kpis()` del backend: sum totales, distinct de
   * producto y proveedor. Asi cuando el comprador filtra ABC=A en la columna,
   * las tarjetas de arriba muestran exactamente lo que ve en la tabla.
   */
  const notificarKpis = () => {
    const api = gridRef.current?.api;
    if (!api) return;
    const filterModel = api.getFilterModel() ?? {};
    // Notificar SIEMPRE los filtros de columna (traducidos) al padre, para que los
    // mande al backend y KPIs/conteo/Excel salgan EXACTOS sobre el total. Va antes
    // del calculo local para que funcione aunque el padre no compute KPIs en el grid.
    onFiltrosColRef.current?.(traducirFilterModel(filterModel));

    const cb = onKpisRef.current;
    if (!cb) return; // el padre calcula los KPIs en el backend; no los computamos aca
    const hayFiltros = Object.keys(filterModel).length > 0;

    let totalSugerido = 0;
    let valorTotal = 0;
    const productos = new Set<string>();
    const proveedores = new Set<string>();
    let n = 0;

    const acumular = (d: SugeridoRow | null | undefined) => {
      if (!d) return;
      n += 1;
      if (typeof d.total_sugerido_suc === "number") totalSugerido += d.total_sugerido_suc;
      if (typeof d.total_valor_sugerido_clp === "number") valorTotal += d.total_valor_sugerido_clp;
      if (d.producto) productos.add(d.producto);
      if (d.proveedor) proveedores.add(d.proveedor);
    };

    if (!hayFiltros) {
      for (const r of rowsRef.current) acumular(r);
    } else {
      // Con filtros de columna activos, dejamos al grid aplicar el filtro y
      // recolectamos las filas que lo pasan.
      api.forEachNodeAfterFilter((node: IRowNode<SugeridoRow>) => acumular(node.data));
    }

    cb(
      {
        total_sugerido: totalSugerido,
        valor_total_clp: valorTotal,
        n_productos: productos.size,
        n_proveedores: proveedores.size,
      },
      n
    );
  };

  // Context menu custom (AG Grid Community no incluye context menu nativo).
  // Posicion absoluta en pixeles del viewport. valor = lo que ve el usuario
  // (post valueFormatter), no el numerico crudo: al pegar en una nota queda
  // legible; para pegar en Excel hay que limpiar puntos a mano.
  const [menu, setMenu] = useState<{ x: number; y: number; valor: string } | null>(null);
  const [toast, setToast] = useState<{ x: number; y: number } | null>(null);
  const toastTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useImperativeHandle(
    ref,
    () => ({
      obtenerIdsVisibles: () => {
        const api = gridRef.current?.api;
        if (!api) return [];
        // Misma idea que notificarKpis: si no hay filtros de columna activos,
        // devolvemos los IDs directamente desde el state, sin depender del
        // grid (que con paginacion + cambios recientes de columnas puede ser
        // inconsistente). Con filtros activos, delegamos al grid.
        const filterModel = api.getFilterModel() ?? {};
        const hayFiltros = Object.keys(filterModel).length > 0;
        const ids: number[] = [];
        if (!hayFiltros) {
          for (const r of rowsRef.current) {
            if (typeof r.id === "number" && r.id > 0) ids.push(r.id);
          }
          return ids;
        }
        api.forEachNodeAfterFilter((node: IRowNode<SugeridoRow>) => {
          const id = node.data?.id;
          if (typeof id === "number" && id > 0) ids.push(id);
        });
        return ids;
      },
      limpiarFiltrosColumnas: () => {
        const api = gridRef.current?.api;
        if (!api) return;
        // setFilterModel(null) borra todos los filtros del grid. onFilterChanged
        // se dispara como consecuencia y persiste {} en localStorage.
        api.setFilterModel(null);
      },
    }),
    []
  );

  const columnDefs = useMemo<ColDef[]>(() => {
    return COLUMNAS.filter((c) => columnasVisibles.includes(c.key as string)).map(colDef);
  }, [columnasVisibles]);

  const defaultColDef = useMemo<ColDef>(
    () => ({
      sortable: true,
      resizable: true,
      suppressHeaderMenuButton: false,
      filter: FiltroMultiSelect,
      menuTabs: ["filterMenuTab"],
      // Todas las columnas se reparten el espacio disponible en partes iguales.
      // El usuario puede arrastrar el borde para redimensionar (resizable=true);
      // su cambio se persiste por columnState en localStorage.
      flex: 1,
    }),
    []
  );

  // Al cambiar la vista activa, re-aplicar el filter model guardado para
  // esa vista (puede ser null → AG Grid limpia los filtros).
  useEffect(() => {
    vistaRef.current = vista;
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current) return;
    const all = leer<FilterModelByVista>(STORAGE_KEYS.gridFilter, {});
    const model = all[vista] ?? null;
    aplicandoRef.current = true;
    try {
      api.setFilterModel(model);
    } catch {
      /* setFilterModel puede rechazar valores incompatibles: ignoramos */
    }
    aplicandoRef.current = false;
  }, [vista]);

  const onGridReady = (e: GridReadyEvent) => {
    // Column state (sort + orden + width) no depende de filas — se restaura ahora.
    aplicandoRef.current = true;
    try {
      const cols = leer<ColumnState[] | null>(STORAGE_KEYS.gridCols, null);
      if (cols && Array.isArray(cols) && cols.length > 0) {
        // Descartamos width/flex del state restaurado para que las columnas
        // arranquen uniformes (flex=1 del defaultColDef). Preservamos orden,
        // sort, pinned y visibilidad. Si el usuario redimensiona despues, ese
        // nuevo width queda persistido en el proximo onColumnResized.
        const limpio = cols.map((c) => ({
          ...c,
          width: undefined,
          flex: null,
        }));
        e.api.applyColumnState({ state: limpio, applyOrder: true });
      }
    } catch {
      /* state incompatible (cambio columnas visibles, etc.): ignoramos */
    }
    aplicandoRef.current = false;
    // Las columnas usan flex=1 en defaultColDef, asi que el grid las distribuye
    // automaticamente. No llamamos sizeColumnsToFit (chocaria con el flex).
  };

  const onFirstDataRendered = (e: FirstDataRenderedEvent) => {
    // El filter model del multiselect necesita rowData presente para preseleccionar
    // valores → se restaura recién acá.
    aplicandoRef.current = true;
    try {
      const all = leer<FilterModelByVista>(STORAGE_KEYS.gridFilter, {});
      const model = all[vistaRef.current] ?? null;
      if (model) e.api.setFilterModel(model);
      const page = leer<number>(STORAGE_KEYS.gridPage, 0);
      if (typeof page === "number" && page > 0) {
        e.api.paginationGoToPage(page);
      }
    } catch {
      /* noop */
    }
    aplicandoRef.current = false;
    restoredRef.current = true;
    // Primer cálculo de KPIs visibles (ya hay filas + filtros restaurados).
    notificarKpis();
  };

  // Cada vez que cambia rowData (sync, cambio vista, refresh), AG Grid puede
  // descartar valores del filter multiselect que ya no existan. Re-aplicar el
  // modelo guardado de la vista actual.
  const onRowDataUpdated = () => {
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current) return;
    aplicandoRef.current = true;
    try {
      const all = leer<FilterModelByVista>(STORAGE_KEYS.gridFilter, {});
      const model = all[vistaRef.current] ?? null;
      api.setFilterModel(model);
    } catch {
      /* noop */
    }
    aplicandoRef.current = false;
    // El dataset cambió → recalcular KPIs sobre las filas visibles.
    notificarKpis();
  };

  // Eventos que persisten cambios del usuario:

  const onFilterChanged = () => {
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current) return;
    // El usuario cambió un filtro de columna → recalcular KPIs siempre, no
    // solo cuando persistimos (la restauración también dispara este evento).
    notificarKpis();
    if (aplicandoRef.current) return;
    try {
      const all = leer<FilterModelByVista>(STORAGE_KEYS.gridFilter, {});
      const model = (api.getFilterModel() ?? {}) as FilterModel;
      all[vistaRef.current] = model;
      guardar(STORAGE_KEYS.gridFilter, all);
    } catch {
      /* noop */
    }
  };

  const persistirColumnState = () => {
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current || aplicandoRef.current) return;
    try {
      guardar(STORAGE_KEYS.gridCols, api.getColumnState());
    } catch {
      /* noop */
    }
  };

  const onSortChanged = persistirColumnState;
  const onColumnMoved = persistirColumnState;

  const onColumnResized = () => {
    if (!restoredRef.current || aplicandoRef.current) return;
    if (resizeTimerRef.current) clearTimeout(resizeTimerRef.current);
    resizeTimerRef.current = setTimeout(persistirColumnState, 200);
  };

  const onPaginationChanged = () => {
    const api = gridRef.current?.api;
    if (!api || !restoredRef.current || aplicandoRef.current) return;
    try {
      guardar(STORAGE_KEYS.gridPage, api.paginationGetCurrentPage());
    } catch {
      /* noop */
    }
  };

  // --- Context menu (copiar celda) ---

  const onCellContextMenu = (e: CellContextMenuEvent<SugeridoRow>) => {
    // Sin valor: no abrir menu (evitamos celdas vacias).
    if (e.value === null || e.value === undefined || e.value === "") return;
    // Prevenir el menu nativo del navegador.
    const mouse = e.event as MouseEvent | undefined;
    mouse?.preventDefault?.();
    // Calcular el texto que el usuario ve (aplicando valueFormatter si hay).
    let valor = "";
    try {
      const fmt = e.colDef?.valueFormatter;
      if (typeof fmt === "function") {
        const out = fmt({
          value: e.value,
          data: e.data,
          node: e.node,
          colDef: e.colDef,
          column: e.column,
          api: e.api,
          context: e.context,
        } as Parameters<typeof fmt>[0]);
        valor = out == null ? "" : String(out);
      } else {
        valor = String(e.value);
      }
    } catch {
      valor = String(e.value);
    }
    if (!valor || valor === "—") return;
    const x = mouse?.clientX ?? 0;
    const y = mouse?.clientY ?? 0;
    setMenu({ x, y, valor });
  };

  const copiarValor = async () => {
    if (!menu) return;
    const { x, y, valor } = menu;
    setMenu(null);
    try {
      await navigator.clipboard.writeText(valor);
    } catch {
      // Fallback: textarea + execCommand (navegadores viejos).
      try {
        const ta = document.createElement("textarea");
        ta.value = valor;
        ta.style.position = "fixed";
        ta.style.opacity = "0";
        document.body.appendChild(ta);
        ta.select();
        document.execCommand("copy");
        document.body.removeChild(ta);
      } catch {
        return; // sin copy posible: no mostramos toast
      }
    }
    setToast({ x, y });
    if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    toastTimerRef.current = setTimeout(() => setToast(null), 1200);
  };

  // ESC y click fuera: cerrar menu.
  useEffect(() => {
    if (!menu) return;
    const onKey = (ev: KeyboardEvent) => {
      if (ev.key === "Escape") setMenu(null);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menu]);

  // Limpiar timer del toast al desmontar.
  useEffect(() => {
    return () => {
      if (toastTimerRef.current) clearTimeout(toastTimerRef.current);
    };
  }, []);

  // El popup del menu/filtro se monta en body para poder voltearse hacia arriba
  // cuando no hay espacio abajo (asi el boton ACEPTAR no queda cortado).
  const popupParent = useMemo<HTMLElement | undefined>(
    () => (typeof document !== "undefined" ? document.body : undefined),
    []
  );

  return (
    <div
      className="ag-theme-quartz"
      style={{ width: "100%", height: "calc(100vh - 290px)", minHeight: 380 }}
      // Bloquea el menu nativo del navegador dentro del grid: el preventDefault
      // de AG Grid no siempre alcanza (sobre celdas con cellRenderer custom,
      // padding o cuando el target real es un span hijo). Esto lo cubre todo.
      onContextMenu={(e) => e.preventDefault()}
    >
      <AgGridReact<SugeridoRow>
        ref={gridRef}
        rowData={rows}
        columnDefs={columnDefs}
        defaultColDef={defaultColDef}
        popupParent={popupParent}
        onGridReady={onGridReady}
        onFirstDataRendered={onFirstDataRendered}
        onRowDataUpdated={onRowDataUpdated}
        onFilterChanged={onFilterChanged}
        onSortChanged={onSortChanged}
        onColumnMoved={onColumnMoved}
        onColumnResized={onColumnResized}
        onPaginationChanged={onPaginationChanged}
        onCellContextMenu={onCellContextMenu}
        onRowClicked={(e: RowClickedEvent<SugeridoRow>) => {
          if (!e.data) return;
          if (e.data.origen === "catalogo" || e.data.origen === "manual") {
            router.push(`/catalogo/${encodeURIComponent(e.data.producto)}`);
            return;
          }
          onRowClick(e.data);
        }}
        getRowClass={() => "cursor-pointer"}
        pagination
        paginationPageSize={50}
        paginationPageSizeSelector={[50, 100, 200, 500]}
        animateRows
        suppressCellFocus
        overlayNoRowsTemplate="<span class='text-slate-400'>No hay datos para los filtros aplicados</span>"
        localeText={{
          page: "Pagina",
          to: "a",
          of: "de",
          next: "Siguiente",
          previous: "Anterior",
          first: "Primera",
          last: "Ultima",
          noRowsToShow: "Sin datos",
        }}
      />

      {/* Context menu custom (AG Grid Community no incluye uno nativo) */}
      {menu && (
        <>
          <div
            className="fixed inset-0 z-[100]"
            onClick={() => setMenu(null)}
            onContextMenu={(ev) => {
              ev.preventDefault();
              setMenu(null);
            }}
          />
          <div
            className="fixed z-[101] min-w-[160px] overflow-hidden rounded-sm border border-ink-200 bg-white shadow-lift"
            style={{ left: menu.x, top: menu.y }}
          >
            <button
              type="button"
              onClick={copiarValor}
              className="flex w-full items-center gap-2 px-3 py-2 text-left text-[13px] text-ink-800 hover:bg-paper-100"
            >
              <Copy size={14} className="text-ink-500" /> Copiar
            </button>
          </div>
        </>
      )}

      {/* Toast "Copiado" sobre la celda copiada */}
      {toast && (
        <div
          className="pointer-events-none fixed z-[102] -translate-x-1/2 -translate-y-full rounded-sm bg-ink-900 px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wider text-paper shadow-lift"
          style={{ left: toast.x, top: toast.y - 8, animation: "fadeOut 1.2s ease-out forwards" }}
        >
          <span className="inline-flex items-center gap-1">
            <Check size={12} className="text-accent-500" /> Copiado
          </span>
        </div>
      )}

      <style jsx>{`
        @keyframes fadeOut {
          0% { opacity: 0; transform: translate(-50%, -100%) translateY(4px); }
          15% { opacity: 1; transform: translate(-50%, -100%) translateY(0); }
          70% { opacity: 1; }
          100% { opacity: 0; transform: translate(-50%, -100%) translateY(-6px); }
        }
      `}</style>
    </div>
  );
});
