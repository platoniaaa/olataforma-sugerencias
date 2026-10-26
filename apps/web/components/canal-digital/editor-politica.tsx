"use client";

// La politica de reposicion: una fila por cluster. Se edita en pantalla y se guarda completa o no se guarda.
import { useEffect, useMemo, useState } from "react";
import { RotateCcw, Save } from "lucide-react";
import {
  canalDigitalApi,
  NOMBRE_MODO,
  type FilaPoliticaCD,
  type ModoPolitica,
  type PoliticaCanalDigital,
} from "@/lib/canal-digital";

/** z para un nivel de servicio (0,5 a 0,999): aproximacion de Abramowitz-Stegun 26.2.23, error < 0,0005. */
export function zParaNivel(nivel: number): number {
  const p = Math.min(Math.max(nivel, 0.5), 0.999);
  const t = Math.sqrt(-2 * Math.log(1 - p));
  const z = t - (2.515517 + 0.802853 * t + 0.010328 * t * t) / (1 + 1.432788 * t + 0.189269 * t * t + 0.001308 * t ** 3);
  return Math.round(z * 100) / 100;
}

interface Props {
  bodega: string;
  puedeEditar: boolean;
  onGuardada: () => void;
}

const clonar = (f: FilaPoliticaCD[]) => f.map((x) => ({ ...x }));
const numero = (v: string): number | null => {
  const n = Number(v.replace(",", "."));
  return v.trim() === "" || Number.isNaN(n) ? null : n;
};

export function EditorPolitica({ bodega, puedeEditar, onGuardada }: Props) {
  const [original, setOriginal] = useState<PoliticaCanalDigital | null>(null);
  const [filas, setFilas] = useState<FilaPoliticaCD[]>([]);
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [ok, setOk] = useState(false);

  useEffect(() => {
    canalDigitalApi
      .politica(bodega)
      .then((p) => {
        setOriginal(p);
        setFilas(clonar(p.filas));
      })
      .catch((e) => setError(e instanceof Error ? e.message : "Error"));
  }, [bodega]);

  const cambios = useMemo(
    () => (original ? JSON.stringify(original.filas) !== JSON.stringify(filas) : false),
    [original, filas]
  );

  function editar(cluster: string, cambio: Partial<FilaPoliticaCD>) {
    setOk(false);
    setFilas((fs) =>
      fs.map((f) => {
        if (f.cluster !== cluster) return f;
        const n = { ...f, ...cambio };
        if (cambio.modo === "contra_pedido") return { ...n, nivel_servicio: null, z: null, minimo_fijo: null };
        if (cambio.modo === "minimo_fijo") return { ...n, nivel_servicio: null, z: null, minimo_fijo: n.minimo_fijo ?? 1 };
        if (cambio.modo === "formula") {
          const nivel = n.nivel_servicio ?? 0.95;
          return { ...n, nivel_servicio: nivel, z: n.z ?? zParaNivel(nivel), minimo_fijo: null };
        }
        return n;
      })
    );
  }

  async function guardar() {
    setGuardando(true);
    setError(null);
    try {
      const p = await canalDigitalApi.guardarPolitica(bodega, filas);
      setOriginal(p);
      setFilas(clonar(p.filas));
      setOk(true);
      onGuardada();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  const campo = "w-20 rounded border border-slate-300 px-2 py-1 text-right text-[12.5px] tabular-nums disabled:bg-slate-50";

  return (
    <div className="space-y-3">
      <p className="rounded-md bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
        Provisoria: son los valores del brief y todavía no están confirmados. Al guardar, el resumen y los sugeridos se
        recalculan al tiro.
      </p>
      {error && <pre className="whitespace-pre-wrap rounded-md bg-red-50 px-3 py-2 text-[12.5px] text-red-700">{error}</pre>}
      {ok && <p className="rounded-md bg-emerald-50 px-3 py-2 text-[12.5px] text-emerald-800">Política guardada.</p>}

      <div className="overflow-x-auto rounded-xl border border-slate-200 bg-white shadow-sm">
        <table className="w-full min-w-[640px] text-[12.5px]">
          <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
            <tr>
              <th className="px-3 py-2">Cluster</th>
              <th className="px-2 py-2">Cómo se repone</th>
              <th className="px-2 py-2 text-right">Nivel de servicio (%)</th>
              <th className="px-2 py-2 text-right">z</th>
              <th className="px-3 py-2 text-right">Mínimo fijo (u.)</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100">
            {filas.map((f) => (
              <tr key={f.cluster}>
                <td className="px-3 py-1.5 font-mono font-semibold">{f.cluster}</td>
                <td className="px-2 py-1.5">
                  <select
                    aria-label={`Modo del cluster ${f.cluster}`}
                    value={f.modo}
                    disabled={!puedeEditar}
                    onChange={(e) => editar(f.cluster, { modo: e.target.value as ModoPolitica })}
                    className="rounded border border-slate-300 px-2 py-1 text-[12.5px] disabled:bg-slate-50"
                  >
                    {(original?.modos ?? []).map((m) => (
                      <option key={m} value={m}>
                        {NOMBRE_MODO[m]}
                      </option>
                    ))}
                  </select>
                </td>
                <td className="px-2 py-1.5 text-right">
                  <input
                    aria-label={`Nivel de servicio del cluster ${f.cluster}`}
                    className={campo}
                    disabled={!puedeEditar || f.modo !== "formula"}
                    value={f.nivel_servicio === null ? "" : String(Math.round(f.nivel_servicio * 1000) / 10)}
                    onChange={(e) => {
                      const v = numero(e.target.value);
                      const nivel = v === null ? null : v / 100;
                      editar(f.cluster, { nivel_servicio: nivel, z: nivel === null ? null : zParaNivel(nivel) });
                    }}
                  />
                </td>
                <td className="px-2 py-1.5 text-right">
                  <input
                    aria-label={`z del cluster ${f.cluster}`}
                    className={campo}
                    disabled={!puedeEditar || f.modo !== "formula"}
                    value={f.z === null ? "" : String(f.z)}
                    onChange={(e) => editar(f.cluster, { z: numero(e.target.value) })}
                  />
                </td>
                <td className="px-3 py-1.5 text-right">
                  <input
                    aria-label={`Mínimo fijo del cluster ${f.cluster}`}
                    className={campo}
                    disabled={!puedeEditar || f.modo !== "minimo_fijo"}
                    value={f.minimo_fijo === null ? "" : String(f.minimo_fijo)}
                    onChange={(e) => editar(f.cluster, { minimo_fijo: numero(e.target.value) })}
                  />
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {puedeEditar ? (
        <div className="flex gap-2">
          <button
            type="button"
            onClick={guardar}
            disabled={!cambios || guardando}
            className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700 disabled:opacity-50"
          >
            <Save size={14} /> {guardando ? "Guardando…" : "Guardar política"}
          </button>
          <button
            type="button"
            onClick={() => original && setFilas(clonar(original.filas))}
            disabled={!cambios}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-[13px] text-slate-700 hover:bg-slate-50 disabled:opacity-50"
          >
            <RotateCcw size={14} /> Descartar cambios
          </button>
        </div>
      ) : (
        <p className="text-[12px] text-slate-500">Tu usuario es de solo lectura: puedes ver la política pero no cambiarla.</p>
      )}
    </div>
  );
}
