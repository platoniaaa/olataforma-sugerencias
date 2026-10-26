"use client";

// Los 27 clusters Frecuencia-Piezas-Valor como tres tablas de 3x3 (una por letra de Frecuencia).
import { formatoCLPCorto, formatoNumero } from "@/lib/formato";
import { NOMBRE_MODO, type ClusterResumen, type ModoPolitica } from "@/lib/canal-digital";

const LETRAS = ["A", "B", "C"] as const;
const NOMBRE_FRECUENCIA: Record<string, string> = {
  A: "Frecuencia A · vende 8 a 12 meses",
  B: "Frecuencia B · vende 5 a 7 meses",
  C: "Frecuencia C · vende 1 a 4 meses",
};

const COLOR_MODO: Record<ModoPolitica, string> = {
  formula: "bg-sky-50 text-sky-800",
  contra_pedido: "bg-slate-100 text-slate-600",
  minimo_fijo: "bg-amber-50 text-amber-800",
};

interface Props {
  clusters: ClusterResumen[];
  seleccionado?: string | null;
  onElegir: (cluster: string) => void;
}

function Celda({ c, activa, onElegir }: { c: ClusterResumen; activa: boolean; onElegir: (c: string) => void }) {
  const vacio = c.productos === 0;
  return (
    <button
      type="button"
      onClick={() => onElegir(c.cluster)}
      disabled={vacio}
      aria-label={`Cluster ${c.cluster}: ${c.productos} productos`}
      aria-pressed={activa}
      className={[
        "flex min-h-[88px] w-full flex-col gap-1 rounded-lg border p-2 text-left transition-colors",
        vacio
          ? "cursor-default border-dashed border-slate-200 bg-slate-50/60 text-slate-400"
          : "border-slate-200 bg-white hover:border-brand hover:bg-brand/5",
        activa ? "border-brand ring-2 ring-brand/30" : "",
      ].join(" ")}
    >
      <span className="flex items-center justify-between">
        <span className="font-mono text-[13px] font-semibold tracking-wider">{c.cluster}</span>
        <span className={`rounded px-1.5 py-0.5 text-[10px] font-medium ${COLOR_MODO[c.modo]}`}>
          {NOMBRE_MODO[c.modo]}
        </span>
      </span>
      <span className="text-[12px] tabular-nums">
        {vacio ? "Sin productos" : `${formatoNumero(c.productos)} prod. · ${formatoNumero(c.pct_unidades * 100, 1)} % u.`}
      </span>
      {!vacio && (
        <span className="text-[11px] tabular-nums text-slate-500">
          {c.productos_que_piden > 0
            ? `Piden ${formatoNumero(c.productos_que_piden)} · ${formatoNumero(c.unidades_sugeridas)} u. · ${formatoCLPCorto(c.sugerido_pesos)}`
            : "Ninguno pide hoy"}
        </span>
      )}
    </button>
  );
}

export function ResumenClusters({ clusters, seleccionado, onElegir }: Props) {
  const por = new Map(clusters.map((c) => [c.cluster, c]));
  return (
    <div className="space-y-5">
      {LETRAS.map((f) => (
        <section key={f} aria-label={NOMBRE_FRECUENCIA[f]}>
          <h3 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
            {NOMBRE_FRECUENCIA[f]}
          </h3>
          <div className="grid grid-cols-[auto_repeat(3,minmax(0,1fr))] gap-2">
            <span />
            {LETRAS.map((v) => (
              <span key={v} className="text-center text-[11px] font-medium text-slate-500">
                Valor {v}
              </span>
            ))}
            {LETRAS.map((p) => (
              <FilaPiezas key={p} f={f} p={p} por={por} seleccionado={seleccionado} onElegir={onElegir} />
            ))}
          </div>
        </section>
      ))}
    </div>
  );
}

function FilaPiezas({
  f,
  p,
  por,
  seleccionado,
  onElegir,
}: {
  f: string;
  p: string;
  por: Map<string, ClusterResumen>;
  seleccionado?: string | null;
  onElegir: (c: string) => void;
}) {
  return (
    <>
      <span className="flex items-center pr-1 text-[11px] font-medium text-slate-500">Piezas {p}</span>
      {LETRAS.map((v) => {
        const c = por.get(`${f}${p}${v}`);
        return c ? (
          <Celda key={v} c={c} activa={seleccionado === c.cluster} onElegir={onElegir} />
        ) : (
          <span key={v} />
        );
      })}
    </>
  );
}
