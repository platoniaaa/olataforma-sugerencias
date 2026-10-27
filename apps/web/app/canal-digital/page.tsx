"use client";

// Sugerido Canal Digital: reposicion semanal de las bodegas del canal (clusters Frecuencia-Piezas-Valor).
import { useCallback, useEffect, useRef, useState } from "react";
import { CheckCircle2, CircleAlert, Layers, TriangleAlert } from "lucide-react";
import { EditorPolitica } from "@/components/canal-digital/editor-politica";
import { PestanaBodegas } from "@/components/canal-digital/pestana-bodegas";
import { PestanaDatos } from "@/components/canal-digital/pestana-datos";
import { ResumenClusters } from "@/components/canal-digital/resumen-clusters";
import { TablaProductos } from "@/components/canal-digital/tabla-productos";
import { getEsAdmin, getSoloLectura } from "@/lib/auth";
import {
  canalDigitalApi,
  periodoLegible,
  type BodegaCD,
  type BodegasCanalDigital,
  type ResumenCanalDigital,
} from "@/lib/canal-digital";
import { formatoCLPCorto, formatoNumero } from "@/lib/formato";

const BODEGA_DEFECTO = "430";
type Pestana = "sugerido" | "clusters" | "productos" | "datos" | "bodegas" | "politica";
const PESTANAS: { id: Pestana; texto: string }[] = [
  { id: "sugerido", texto: "Sugerido" },
  { id: "clusters", texto: "Clusters" },
  { id: "productos", texto: "Productos" },
  { id: "datos", texto: "Datos" },
  { id: "bodegas", texto: "Bodegas" },
  { id: "politica", texto: "Política" },
];

/** "2026-10-19" -> "19-10-2026". */
const fechaLegible = (f: string) => f.split("-").reverse().join("-");

/** La 430 primero y el resto por codigo, igual que las manda el servidor. */
const ordenarBodegas = (l: BodegaCD[]) =>
  [...l].sort(
    (a, b) => Number(b.bodega === BODEGA_DEFECTO) - Number(a.bodega === BODEGA_DEFECTO) || a.bodega.localeCompare(b.bodega)
  );

export default function CanalDigitalPage() {
  const [bodega, setBodega] = useState(BODEGA_DEFECTO);
  const [bodegas, setBodegas] = useState<BodegasCanalDigital | null>(null);
  const [errorBodegas, setErrorBodegas] = useState<string | null>(null);
  const [pestana, setPestana] = useState<Pestana>("sugerido");
  const [resumen, setResumen] = useState<ResumenCanalDigital | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cluster, setCluster] = useState<string | null>(null);
  const [puedeEditar, setPuedeEditar] = useState(false);
  const [esAdmin, setEsAdmin] = useState(false);
  const pedido = useRef(0);

  const cargar = useCallback(() => {
    const mio = ++pedido.current;
    setError(null);
    canalDigitalApi
      .resumen(bodega)
      .then((r) => {
        if (mio === pedido.current) setResumen(r);
      })
      .catch((e) => {
        if (mio === pedido.current) setError(e instanceof Error ? e.message : "No se pudo calcular");
      });
  }, [bodega]);

  const cargarBodegas = useCallback(() => {
    setErrorBodegas(null);
    canalDigitalApi
      .bodegas()
      .then(setBodegas)
      .catch((e) => setErrorBodegas(e instanceof Error ? e.message : "No se pudieron cargar las bodegas"));
  }, []);

  useEffect(() => {
    setPuedeEditar(!getSoloLectura());
    setEsAdmin(getEsAdmin());
    cargarBodegas();
  }, [cargarBodegas]);

  // Al cambiar de bodega se recarga todo: lo de la anterior sale de la vista y una respuesta tardia se descarta.
  useEffect(() => {
    setResumen(null);
    cargar();
    return () => {
      pedido.current++;
    };
  }, [cargar]);

  function elegirBodega(b: string) {
    setBodega(b);
    setCluster(null);
  }

  const lista = bodegas?.bodegas ?? [];
  const actual = lista.find((b) => b.bodega === bodega) ?? null;

  function guardada(b: BodegaCD) {
    setBodegas((d) => (d ? { ...d, bodegas: d.bodegas.map((x) => (x.bodega === b.bodega ? b : x)) } : d));
    cargar(); // los parametros cambian lo que se calcula: se actualizan los totales de arriba
  }

  function creada(b: BodegaCD) {
    setBodegas((d) =>
      d ? { ...d, bodegas: ordenarBodegas([...d.bodegas.filter((x) => x.bodega !== b.bodega), b]) } : d
    );
    elegirBodega(b.bodega);
  }

  const sinVentas = resumen !== null && resumen.totales.productos === 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
            <Layers size={20} /> Sugerido Canal Digital · bodega {bodega}
          </h1>
          <p className="text-[13px] text-slate-500">
            {resumen && !sinVentas
              ? `Venta de ${periodoLegible(resumen.aviso.periodos[0])} a ${periodoLegible(resumen.aviso.periodos[1])} · última semana completa desde el ${fechaLegible(resumen.aviso.semanas[1])} · reposición semanal`
              : "Clusters y reposición semanal del canal digital."}
          </p>
        </div>
        {lista.length > 1 && (
          <label className="flex items-center gap-2 text-[13px] text-slate-600">
            Bodega
            <select
              aria-label="Bodega"
              value={bodega}
              onChange={(e) => elegirBodega(e.target.value)}
              className="rounded-md border border-slate-300 bg-white px-2 py-1.5 text-[13px] text-slate-900"
            >
              {lista.map((b) => (
                <option key={b.bodega} value={b.bodega}>
                  {b.bodega} · {b.nombre}
                  {b.activa ? "" : " (desactivada)"}
                </option>
              ))}
            </select>
          </label>
        )}
      </div>

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>}

      {actual && !actual.activa && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-[13px] text-amber-900">
          Esta bodega está desactivada. Se puede seguir consultando; si vuelve a usarse, se activa en la pestaña Bodegas.
        </p>
      )}

      {sinVentas && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-[13px] text-amber-900">
          Todavía no hay venta del canal cargada para esta bodega. Se publica desde el motor con la carga de ventas semanales.
        </p>
      )}

      {resumen && !sinVentas && (resumen.aviso.meses_sin_cargar ?? 0) > 0 && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-[13px] text-amber-900">
          La venta está cargada hasta {periodoLegible(resumen.aviso.ultimo_periodo_cargado)} y faltan{" "}
          {resumen.aviso.meses_sin_cargar} {resumen.aviso.meses_sin_cargar === 1 ? "mes cerrado" : "meses cerrados"}. La demanda
          y las clases se calculan hasta ese mes; el stock es el de hoy.
        </p>
      )}

      {resumen && resumen.provisorio.length > 0 && (
        <details className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
          <summary className="flex cursor-pointer items-center gap-1.5 font-medium">
            <TriangleAlert size={14} /> Versión provisoria: qué todavía no está confirmado
          </summary>
          <ul className="mt-2 list-disc space-y-1 pl-5">
            {resumen.provisorio.map((t) => (
              <li key={t}>{t}</li>
            ))}
          </ul>
        </details>
      )}

      {resumen && !sinVentas && (
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
          <Kpi titulo="Productos" valor={formatoNumero(resumen.totales.productos)} detalle={detalleEstados(resumen)} />
          <Kpi titulo="Piden reposición hoy" valor={formatoNumero(resumen.totales.productos_que_piden)} />
          <Kpi titulo="Unidades a pedir" valor={formatoNumero(resumen.totales.unidades_sugeridas)} />
          <Kpi titulo="Valor al costo" valor={formatoCLPCorto(resumen.totales.sugerido_pesos)} />
        </div>
      )}

      <div role="tablist" aria-label="Secciones" className="flex flex-wrap gap-1 border-b border-slate-200">
        {PESTANAS.map((p) => (
          <button
            key={p.id}
            role="tab"
            aria-selected={pestana === p.id}
            onClick={() => setPestana(p.id)}
            className={`-mb-px border-b-2 px-3 py-2 text-[13px] font-medium ${
              pestana === p.id ? "border-brand text-brand" : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {p.texto}
          </button>
        ))}
      </div>

      {/* Cada pestana lleva la bodega en su key: al cambiar de bodega se vuelve a montar y recarga sus datos. */}
      {pestana === "sugerido" && <TablaProductos key={bodega} bodega={bodega} modo="sugerido" />}

      {pestana === "clusters" && resumen && !sinVentas && (
        <div key={bodega} className="space-y-5">
          <ResumenClusters
            clusters={resumen.clusters}
            seleccionado={cluster}
            onElegir={(c) => {
              setCluster(c);
              setPestana("productos");
            }}
          />

          <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
            <h2 className="mb-2 text-[13px] font-semibold text-slate-900">Validaciones</h2>
            <ul className="space-y-1.5">
              {resumen.validaciones.map((v) => (
                <li key={v.nombre} className="flex items-start gap-2 text-[12.5px]">
                  {v.ok ? (
                    <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600" aria-label="Pasa" />
                  ) : (
                    <CircleAlert size={15} className="mt-0.5 shrink-0 text-red-600" aria-label="Falla" />
                  )}
                  <span>
                    <span className="font-medium text-slate-800">{v.nombre}.</span>{" "}
                    <span className="text-slate-500">{v.detalle}</span>
                  </span>
                </li>
              ))}
            </ul>
            <p className="mt-3 text-[12px] text-slate-500">
              {formatoNumero(resumen.aviso.sin_proveedor)} productos sin proveedor usan el plazo de respaldo de 3 días.
              {resumen.aviso.codigos_en_dos_grupos > 0 &&
                ` ${resumen.aviso.codigos_en_dos_grupos} códigos figuran en dos grupos de reemplazo.`}
            </p>
          </section>
        </div>
      )}

      {pestana === "productos" && (
        <TablaProductos
          key={bodega}
          bodega={bodega}
          modo="todos"
          clusterInicial={cluster}
          onLimpiarCluster={() => setCluster(null)}
        />
      )}

      {pestana === "datos" && <PestanaDatos key={bodega} bodega={bodega} />}

      {pestana === "bodegas" && (
        <PestanaBodegas
          bodega={bodega}
          datos={bodegas}
          error={errorBodegas}
          puedeEditar={puedeEditar}
          esAdmin={esAdmin}
          onReintentar={cargarBodegas}
          onGuardada={guardada}
          onCreada={creada}
        />
      )}

      {pestana === "politica" && (
        <EditorPolitica key={bodega} bodega={bodega} puedeEditar={puedeEditar} onGuardada={cargar} />
      )}
    </div>
  );
}

function detalleEstados(r: ResumenCanalDigital): string {
  const e = r.estados;
  return `${formatoNumero(e.CLASIFICADO)} clasificados · ${formatoNumero(e.NUEVO)} nuevos · ${formatoNumero(e["SIN MOVIMIENTO"])} sin movimiento`;
}

function Kpi({ titulo, valor, detalle }: { titulo: string; valor: string; detalle?: string }) {
  return (
    <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="text-[12px] text-slate-500">{titulo}</div>
      <div className="mt-1 text-2xl font-semibold tabular-nums text-slate-900">{valor}</div>
      {detalle && <div className="mt-1 text-[11.5px] text-slate-500">{detalle}</div>}
    </div>
  );
}
