"use client";

// Canal Digital: reposicion semanal de la bodega 430 (clusters Frecuencia-Piezas-Valor).
import { useCallback, useEffect, useState } from "react";
import { CheckCircle2, CircleAlert, Layers, TriangleAlert } from "lucide-react";
import { EditorPolitica } from "@/components/canal-digital/editor-politica";
import { ResumenClusters } from "@/components/canal-digital/resumen-clusters";
import { TablaProductos } from "@/components/canal-digital/tabla-productos";
import { getSoloLectura } from "@/lib/auth";
import { canalDigitalApi, type ResumenCanalDigital } from "@/lib/canal-digital";
import { formatoCLPCorto, formatoNumero } from "@/lib/formato";

const BODEGA = "430";
type Pestana = "resumen" | "productos" | "politica";
const PESTANAS: { id: Pestana; texto: string }[] = [
  { id: "resumen", texto: "Resumen por cluster" },
  { id: "productos", texto: "Productos" },
  { id: "politica", texto: "Política" },
];

/** "202609" -> "09-2026". */
const periodoLegible = (p: string | null | undefined) => (p && p.length === 6 ? `${p.slice(4)}-${p.slice(0, 4)}` : "—");
/** "2026-10-19" -> "19-10-2026". */
const fechaLegible = (f: string) => f.split("-").reverse().join("-");

export default function CanalDigitalPage() {
  const [pestana, setPestana] = useState<Pestana>("resumen");
  const [resumen, setResumen] = useState<ResumenCanalDigital | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cluster, setCluster] = useState<string | null>(null);
  const [puedeEditar, setPuedeEditar] = useState(false);

  const cargar = useCallback(() => {
    setError(null);
    canalDigitalApi
      .resumen(BODEGA)
      .then(setResumen)
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudo calcular"));
  }, []);

  useEffect(() => {
    setPuedeEditar(!getSoloLectura());
    cargar();
  }, [cargar]);

  const sinVentas = resumen !== null && resumen.totales.productos === 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
          <Layers size={20} /> Canal Digital · bodega {BODEGA}
        </h1>
        <p className="text-[13px] text-slate-500">
          {resumen && !sinVentas
            ? `Venta de ${periodoLegible(resumen.aviso.periodos[0])} a ${periodoLegible(resumen.aviso.periodos[1])} · última semana completa desde el ${fechaLegible(resumen.aviso.semanas[1])} · reposición semanal`
            : "Clusters y reposición semanal del canal digital."}
        </p>
      </div>

      {error && <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>}

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
        <details className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900" open>
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

      <div role="tablist" aria-label="Secciones" className="flex gap-1 border-b border-slate-200">
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

      {pestana === "resumen" && resumen && !sinVentas && (
        <div className="space-y-5">
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <Kpi titulo="Productos" valor={formatoNumero(resumen.totales.productos)} detalle={detalleEstados(resumen)} />
            <Kpi titulo="Piden reposición hoy" valor={formatoNumero(resumen.totales.productos_que_piden)} />
            <Kpi titulo="Unidades a pedir" valor={formatoNumero(resumen.totales.unidades_sugeridas)} />
            <Kpi titulo="Valor al costo" valor={formatoCLPCorto(resumen.totales.sugerido_pesos)} />
          </div>

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
        <TablaProductos bodega={BODEGA} clusterInicial={cluster} onLimpiarCluster={() => setCluster(null)} />
      )}

      {pestana === "politica" && <EditorPolitica bodega={BODEGA} puedeEditar={puedeEditar} onGuardada={cargar} />}
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
