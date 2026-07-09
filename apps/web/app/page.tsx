"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { BarChart3, ChevronDown, Columns3, Download, Plus, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { KpiCards } from "@/components/kpi-cards";
import { GraficosDashboard } from "@/components/graficos-dashboard";
import { FiltrosSugerido } from "@/components/filtros-sugerido";
import { TablaSugerido, type TablaSugeridoHandle } from "@/components/tabla-sugerido";
import { ConfigurarColumnas } from "@/components/configurar-columnas";
import { ModalSugerenciaManual } from "@/components/modal-sugerencia-manual";
import { api } from "@/lib/api-client";
import { getEsAdmin, getSoloLectura } from "@/lib/auth";
import { columnasPorDefectoVista } from "@/lib/columnas";
import { formatoFechaHora, formatoNumero } from "@/lib/formato";
import { STORAGE_KEYS, guardar, leer } from "@/lib/persistencia-dashboard";
import type { ColumnaFiltro, Sucursal, SugeridoFiltros, SugeridoKpis, SugeridoRow } from "@/lib/types";

type Vista = NonNullable<SugeridoFiltros["vista"]>;
const VISTAS: { id: Vista; label: string; hint: string }[] = [
  { id: "todas", label: "Todas", hint: "Todo el sugerido sin distinguir el proceso" },
  { id: "sucursales", label: "Compra sucursal", hint: "Lo que cada local pide directo al proveedor" },
  { id: "cd", label: "Compra CD", hint: "Lo que el CD le pide al proveedor para tener en stock central" },
  { id: "distribucion", label: "Distribución CD → Sucursales", hint: "Lo que el CD reparte a las sucursales (traslado interno)" },
];

const LS_COLUMNAS = "sugerido_columnas_visibles";

const FILTROS_DEFAULT: SugeridoFiltros = { solo_pedir: true, vista: "todas" };

// Las columnas se recuerdan por vista: cada pestania del proceso de compras tiene
// su propio set (clave `sugerido_columnas_visibles::<vista>`). Asi "Distribución"
// arranca con el set operativo sin pisar lo que el usuario configuro en "Todas".
function leerColumnasVista(vista: string): string[] {
  if (typeof window === "undefined") return columnasPorDefectoVista(vista);
  try {
    const saved = localStorage.getItem(`${LS_COLUMNAS}::${vista}`);
    if (saved) {
      const arr = JSON.parse(saved);
      if (Array.isArray(arr) && arr.length) return arr;
    }
  } catch {
    /* noop */
  }
  return columnasPorDefectoVista(vista);
}

export default function DashboardPage() {
  const router = useRouter();

  // Lazy init: leemos localStorage (namespaced por email) ANTES del primer render
  // para que el efecto de fetch arranque ya con los filtros buenos. Si guardáramos
  // dentro de un useEffect haríamos 2 fetches (uno con defaults, otro con
  // restaurados).
  const [filtros, setFiltrosRaw] = useState<SugeridoFiltros>(() =>
    leer<SugeridoFiltros>(STORAGE_KEYS.filtros, FILTROS_DEFAULT)
  );

  // Wrapper de setFiltros que persiste sincrónicamente. Si el usuario filtra y
  // navega al detalle en <300ms (más rápido que el debounce de fetch), igual
  // se guarda. Cubre setter como objeto o como función.
  const setFiltros: React.Dispatch<React.SetStateAction<SugeridoFiltros>> = useCallback(
    (updater) => {
      setFiltrosRaw((prev) => {
        const nuevo =
          typeof updater === "function"
            ? (updater as (p: SugeridoFiltros) => SugeridoFiltros)(prev)
            : updater;
        guardar(STORAGE_KEYS.filtros, nuevo);
        return nuevo;
      });
    },
    []
  );

  const [esAdmin, setEsAdmin] = useState(false);
  const [soloLectura, setSoloLectura] = useState(false);

  // Las tabs de vista solo se muestran a admin. El botón de sugerencia manual se
  // oculta a los usuarios de solo lectura. Detectamos al montar (localStorage).
  useEffect(() => {
    setEsAdmin(getEsAdmin());
    setSoloLectura(getSoloLectura());
  }, []);
  const [rows, setRows] = useState<SugeridoRow[]>([]);
  // KPIs exactos del backend (agregan sobre TODO el set filtrado, incluidos los
  // filtros de columna del grid). No se calculan en el grid.
  const [kpis, setKpis] = useState<SugeridoKpis | null>(null);
  const [total, setTotal] = useState(0);
  // Fecha/hora de la última carga de datos desde Power BI (para todos los usuarios).
  const [ultimaSync, setUltimaSync] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [sucursales, setSucursales] = useState<Sucursal[]>([]);
  const [proveedores, setProveedores] = useState<string[]>([]);

  const vista = filtros.vista ?? "todas";
  const [colsVisibles, setColsVisibles] = useState<string[]>(() =>
    leerColumnasVista(leer<SugeridoFiltros>(STORAGE_KEYS.filtros, FILTROS_DEFAULT).vista ?? "todas")
  );
  const [modalCols, setModalCols] = useState(false);
  const [modalManual, setModalManual] = useState(false);

  // Ref al grid (para limpiar sus filtros de columna desde "Limpiar filtros").
  const tablaRef = useRef<TablaSugeridoHandle>(null);
  const [exportando, setExportando] = useState(false);
  const [mostrarGraficos, setMostrarGraficos] = useState(false);
  // Filtros de columna del grid (traducidos del multi-select). Se mandan al backend
  // para que KPIs, conteo y Excel sean EXACTOS sobre el total (no solo las 5.000
  // filas cargadas). El listado de filas NO los usa: el grid filtra del lado cliente
  // para conservar todas las opciones del multi-select.
  const [filtrosColumna, setFiltrosColumna] = useState<ColumnaFiltro[]>([]);
  const hayFiltrosColumna = filtrosColumna.length > 0;

  const limpiarFiltrosTodo = useCallback(() => {
    // Filtros server-side -> default.
    setFiltros((f) => ({
      q: "",
      solo_pedir: true,
      solo_nacionales: false,
      // Mantener la vista que el usuario tiene seleccionada: limpiar filtros
      // no implica cambiar de pestania.
      vista: f.vista ?? "todas",
    }));
    // Filtros de columna del grid (el grid tambien notifica [] al limpiarse, pero
    // lo reseteamos ya para que el fetch de KPIs no use el valor viejo).
    setFiltrosColumna([]);
    tablaRef.current?.limpiarFiltrosColumnas();
  }, [setFiltros]);

  // Al cambiar de vista, cargar las columnas de esa pestania (guardadas o su
  // set por defecto). No persiste: cargar defaults no debe pisar lo guardado.
  useEffect(() => {
    setColsVisibles(leerColumnasVista(vista));
  }, [vista]);

  // Cambios explicitos del usuario (modal de columnas): persisten en la vista actual.
  const cambiarColumnas = useCallback(
    (cols: string[]) => {
      setColsVisibles(cols);
      try {
        localStorage.setItem(`${LS_COLUMNAS}::${vista}`, JSON.stringify(cols));
      } catch {
        /* noop */
      }
    },
    [vista]
  );

  // Fecha/hora de la última sincronización de datos desde Power BI.
  useEffect(() => {
    api
      .ultimaSincronizacion()
      .then((r) => setUltimaSync(r.creado_en))
      .catch(() => {
        /* el backend puede no estar arriba todavia */
      });
  }, []);

  // Cargar catalogos una vez (sucursales + proveedores).
  useEffect(() => {
    (async () => {
      try {
        const sucs = await api.sucursales();
        setSucursales(sucs);
        // Proveedores: distinct de un fetch amplio sin filtro.
        const todo = await api.sugerido({ solo_pedir: false }, { limit: 5000 });
        const set = new Set<string>();
        todo.items.forEach((r) => r.proveedor && set.add(r.proveedor));
        setProveedores([...set].sort());
      } catch {
        /* el backend puede no estar arriba todavia */
      }
    })();
  }, []);

  // Filas: dependen SOLO de los filtros server-side. Los de columna NO recargan las
  // filas (el grid filtra del lado cliente): así conservamos las opciones del
  // multi-select y no se reinicia el scroll al filtrar por columna.
  const cargarFilas = useCallback(async () => {
    setCargando(true);
    setError(null);
    try {
      const page = await api.sugerido(filtros, { limit: 5000, sort: "-total_sugerido_suc" });
      setRows(page.items);
      setTotal(page.total);
    } catch (e) {
      setError(
        e instanceof Error
          ? `${e.message}. ¿Esta corriendo el backend en localhost:8000?`
          : "Error al cargar"
      );
    } finally {
      setCargando(false);
    }
  }, [filtros]);

  // KPIs + conteo EXACTOS: backend con TODOS los filtros (server-side + columna).
  const cargarKpis = useCallback(async () => {
    try {
      const k = await api.kpis({ ...filtros, filtros_columna: filtrosColumna });
      setKpis(k);
    } catch {
      /* el backend puede no estar arriba todavia */
    }
  }, [filtros, filtrosColumna]);

  // Refresco manual (botón Actualizar / tras guardar una sugerencia): filas + KPIs.
  const cargar = useCallback(async () => {
    await Promise.all([cargarFilas(), cargarKpis()]);
  }, [cargarFilas, cargarKpis]);

  // Filas al cambiar filtros server-side; KPIs al cambiar cualquiera (con debounce).
  useEffect(() => {
    const t = setTimeout(cargarFilas, 300);
    return () => clearTimeout(t);
  }, [cargarFilas]);
  useEffect(() => {
    const t = setTimeout(cargarKpis, 300);
    return () => clearTimeout(t);
  }, [cargarKpis]);

  const nombresSucursales = useMemo(
    () => sucursales.map((s) => s.nombre ?? s.sucursal_id),
    [sucursales]
  );

  // Conteo a mostrar: con filtro de columna, el conteo EXACTO del backend (n_filas);
  // si no, el total del set server-side.
  const nFiltradas = hayFiltrosColumna ? kpis?.n_filas ?? 0 : total;
  const detalleFilas = cargando
    ? ""
    : hayFiltrosColumna
      ? " tras el filtro de columna · KPIs y Excel exactos"
      : total > rows.length
        ? ` (mostrando ${formatoNumero(rows.length)} — los KPIs y el Excel cubren el total)`
        : "";

  const exportar = async () => {
    setExportando(true);
    try {
      // Los filtros de columna viajan dentro de `filtros`: el backend exporta el
      // set filtrado COMPLETO (no solo las ~5.000 filas cargadas en la grilla).
      await api.exportExcel(
        { ...filtros, filtros_columna: filtrosColumna },
        colsVisibles,
        "-total_sugerido_suc"
      );
    } catch (e) {
      alert(e instanceof Error ? e.message : "No se pudo exportar");
    } finally {
      setExportando(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <p className="kicker mb-1">Reposición</p>
          <h1 className="editorial-rule font-display text-[28px] font-medium leading-none tracking-tight text-ink-900">
            Sugerido de compras
          </h1>
          <p className="mt-3 text-[13px] text-ink-500">
            {cargando ? "Cargando…" : `${formatoNumero(nFiltradas)} filas`}
            {detalleFilas}
          </p>
          {ultimaSync && (
            <p className="mt-1 text-[12px] text-ink-400">
              Datos actualizados el {formatoFechaHora(ultimaSync)}
            </p>
          )}
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="outline" size="sm" onClick={cargar}>
            <RefreshCw size={15} /> Actualizar
          </Button>
          <Button variant="outline" size="sm" onClick={() => setModalCols(true)}>
            <Columns3 size={15} /> Columnas
          </Button>
          <Button variant="outline" size="sm" onClick={exportar} disabled={exportando}>
            <Download size={15} /> {exportando ? "Generando…" : "Exportar Excel"}
          </Button>
          {!soloLectura && (
            <Button size="sm" onClick={() => setModalManual(true)}>
              <Plus size={15} /> Sugerencia manual
            </Button>
          )}
        </div>
      </div>

      {esAdmin && (
        <div className="flex flex-wrap gap-1 border-b border-ink-200">
          {VISTAS.map((v) => {
            const activa = (filtros.vista ?? "todas") === v.id;
            return (
              <button
                key={v.id}
                onClick={() => setFiltros((f) => ({ ...f, vista: v.id }))}
                title={v.hint}
                className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${
                  activa
                    ? "border-accent-700 text-ink-900"
                    : "border-transparent text-ink-500 hover:text-ink-900"
                }`}
              >
                {v.label}
              </button>
            );
          })}
        </div>
      )}

      <KpiCards kpis={kpis} cargando={cargando} />

      <div>
        <button
          onClick={() => setMostrarGraficos((v) => !v)}
          className="flex items-center gap-1.5 text-[13px] font-medium text-slate-600 hover:text-slate-900"
        >
          <BarChart3 size={15} />
          {mostrarGraficos ? "Ocultar gráficos" : "Ver gráficos"}
          <ChevronDown
            size={15}
            className={mostrarGraficos ? "rotate-180 transition-transform" : "transition-transform"}
          />
        </button>
        {mostrarGraficos && (
          <div className="mt-3">
            <GraficosDashboard filtros={{ ...filtros, filtros_columna: filtrosColumna }} />
          </div>
        )}
      </div>

      <FiltrosSugerido
        filtros={filtros}
        onChange={setFiltros}
        hayFiltrosColumna={hayFiltrosColumna}
        onLimpiarTodo={limpiarFiltrosTodo}
      />

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          {error}
        </div>
      )}

      <TablaSugerido
        ref={tablaRef}
        rows={rows}
        columnasVisibles={colsVisibles}
        vista={filtros.vista ?? "todas"}
        onFiltrosColumnaChange={(fc) =>
          setFiltrosColumna((prev) =>
            JSON.stringify(prev) === JSON.stringify(fc) ? prev : fc
          )
        }
        onRowClick={(r) =>
          router.push(
            `/producto/${encodeURIComponent(r.producto)}?sucursal=${encodeURIComponent(
              r.sucursal_id
            )}`
          )
        }
      />

      <ConfigurarColumnas
        open={modalCols}
        onClose={() => setModalCols(false)}
        visibles={colsVisibles}
        onChange={cambiarColumnas}
      />
      <ModalSugerenciaManual
        open={modalManual}
        onClose={() => setModalManual(false)}
        onGuardado={cargar}
        sucursales={sucursales}
        proveedores={proveedores}
      />
    </div>
  );
}
