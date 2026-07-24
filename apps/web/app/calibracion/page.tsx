"use client";

// Calibracion del modelo: edita los parametros del sugerido (ciclo de orden,
// niveles de servicio, etc.) y APLICALOS. A diferencia del simulador (que solo
// muestra el impacto), esto guarda una version nueva que el motor usa en su
// proxima corrida. Solo admin.
import { useEffect, useState } from "react";
import { SlidersHorizontal, Play, Save, RotateCcw } from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type { ConfigModelo, ConfigModeloPlano, SimulacionResultado } from "@/lib/types";

// Nivel de servicio (una cola de la normal) a partir de Z, para mostrar "≈ 95%".
function erf(x: number): number {
  const t = 1 / (1 + 0.3275911 * Math.abs(x));
  const y =
    1 -
    ((((1.061405429 * t - 1.453152027) * t + 1.421413741) * t - 0.284496736) * t +
      0.254829592) *
      t *
      Math.exp(-x * x);
  return x >= 0 ? y : -y;
}
function nivelServicio(z: number): string {
  if (z <= 0) return "sin colchón";
  return `≈ ${Math.round(50 * (1 + erf(z / Math.SQRT2)))} %`;
}

function aPlano(c: ConfigModelo): ConfigModeloPlano {
  return {
    ciclo_orden_dias: c.ciclo_orden_dias,
    ciclo_orden_dias_cd: c.ciclo_orden_dias_cd,
    z_a: c.z_por_clase.A,
    z_b: c.z_por_clase.B,
    z_c: c.z_por_clase.C,
    z_d: c.z_por_clase.D,
    z_imp_cd_a: c.z_importado_cd.A,
    z_imp_cd_b: c.z_importado_cd.B,
    lead_time_fallback_dias: c.lead_time_fallback_dias,
    winsor_k: c.winsor_k,
  };
}

export default function CalibracionPage() {
  const [vigente, setVigente] = useState<ConfigModelo | null>(null);
  const [ed, setEd] = useState<ConfigModeloPlano | null>(null);
  const [nota, setNota] = useState("");
  const [impacto, setImpacto] = useState<SimulacionResultado | null>(null);
  const [cargando, setCargando] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = async () => {
    try {
      const c = await api.configModelo();
      setVigente(c);
      setEd(aPlano(c));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la configuración");
    }
  };

  useEffect(() => {
    cargar();
  }, []);

  if (!ed || !vigente) {
    return <p className="text-slate-500">{error ?? "Cargando…"}</p>;
  }

  const set = (k: keyof ConfigModeloPlano, v: number) => {
    setEd({ ...ed, [k]: v });
    setImpacto(null);
    setMsg(null);
  };

  // Solo los campos que cambiaron respecto de la vigente.
  const cambios = (): Partial<ConfigModeloPlano> => {
    const base = aPlano(vigente);
    const out: Partial<ConfigModeloPlano> = {};
    (Object.keys(ed) as (keyof ConfigModeloPlano)[]).forEach((k) => {
      if (ed[k] !== base[k]) out[k] = ed[k];
    });
    return out;
  };
  const hayCambios = Object.keys(cambios()).length > 0;

  const verImpacto = async () => {
    setCargando(true);
    setError(null);
    try {
      setImpacto(
        await api.simular({
          ciclo_orden_dias: ed.ciclo_orden_dias,
          ciclo_orden_dias_cd: ed.ciclo_orden_dias_cd,
          z_por_clase: { A: ed.z_a, B: ed.z_b, C: ed.z_c, D: ed.z_d },
          factor_lead_time: 1,
        })
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo calcular el impacto");
    } finally {
      setCargando(false);
    }
  };

  const guardar = async () => {
    const c = cambios();
    const resumen = Object.entries(c)
      .map(([k, v]) => `${k}: ${v}`)
      .join("\n");
    if (
      !window.confirm(
        `Esto cambia el modelo para todo el equipo (se aplica en la próxima corrida del motor):\n\n${resumen}\n\n¿Guardar y aplicar?`
      )
    ) {
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      const nueva = await api.guardarConfigModelo({ ...c, nota: nota || undefined });
      setVigente(nueva);
      setEd(aPlano(nueva));
      setNota("");
      setImpacto(null);
      setMsg("Guardado. El motor usará estos valores en su próxima corrida.");
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  };

  const delta = impacto?.resumen.delta_clp ?? 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
          <SlidersHorizontal size={20} /> Calibración del modelo
        </h1>
        <p className="text-[13px] text-slate-500">
          Ajusta los parámetros del sugerido. Los cambios se aplican en la próxima corrida del motor.
        </p>
      </div>

      <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-[12px] text-slate-600">
        {vigente.es_default
          ? "Vigente: valores por defecto (nunca se ha editado)."
          : `Vigente: editada por ${vigente.creado_por ?? "—"}${
              vigente.creado_en ? " el " + new Date(vigente.creado_en).toLocaleString("es-CL") : ""
            }${vigente.nota ? ` · “${vigente.nota}”` : ""}.`}
      </div>

      <section className="space-y-5 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <div>
          <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
            Ciclo de orden (días)
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo label="Compra directa" min={1} max={60} value={ed.ciclo_orden_dias}
              onChange={(v) => set("ciclo_orden_dias", v)} />
            <Campo label="Abastecido del CD" min={1} max={60} value={ed.ciclo_orden_dias_cd}
              onChange={(v) => set("ciclo_orden_dias_cd", v)} />
          </div>
        </div>

        <div>
          <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
            Nivel de servicio (Z) por clase
          </p>
          <div className="grid gap-4 sm:grid-cols-4">
            <Campo label="Clase A" min={0} max={3.5} step={0.001} value={ed.z_a}
              onChange={(v) => set("z_a", v)} hint={nivelServicio(ed.z_a)} />
            <Campo label="Clase B" min={0} max={3.5} step={0.001} value={ed.z_b}
              onChange={(v) => set("z_b", v)} hint={nivelServicio(ed.z_b)} />
            <Campo label="Clase C" min={0} max={3.5} step={0.001} value={ed.z_c}
              onChange={(v) => set("z_c", v)} hint={nivelServicio(ed.z_c)} />
            <Campo label="Clase D" min={0} max={3.5} step={0.001} value={ed.z_d}
              onChange={(v) => set("z_d", v)} hint={nivelServicio(ed.z_d)} />
          </div>
          <div className="mt-3 grid gap-4 sm:grid-cols-2">
            <Campo label="Importado por CD — Clase A" min={0} max={3.5} step={0.001} value={ed.z_imp_cd_a}
              onChange={(v) => set("z_imp_cd_a", v)} hint={nivelServicio(ed.z_imp_cd_a)} />
            <Campo label="Importado por CD — Clase B" min={0} max={3.5} step={0.001} value={ed.z_imp_cd_b}
              onChange={(v) => set("z_imp_cd_b", v)} hint={nivelServicio(ed.z_imp_cd_b)} />
          </div>
        </div>

        <div>
          <p className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
            Otros
          </p>
          <div className="grid gap-4 sm:grid-cols-2">
            <Campo label="Lead time por defecto (días)" min={1} max={90} value={ed.lead_time_fallback_dias}
              onChange={(v) => set("lead_time_fallback_dias", v)}
              hint="Cuando no hay proveedor ni historial de OC." />
            <Campo label="Winsor k (recorte de picos)" min={0.5} max={6} step={0.1} value={ed.winsor_k}
              onChange={(v) => set("winsor_k", v)} hint="Más alto = recorta menos los meses pico." />
          </div>
        </div>

        <label className="block">
          <span className="mb-1 block text-[12px] font-medium text-slate-600">Nota (por qué del cambio)</span>
          <input
            type="text"
            value={nota}
            maxLength={500}
            onChange={(e) => setNota(e.target.value)}
            placeholder="Opcional — queda en el historial"
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px]"
          />
        </label>

        <div className="flex flex-wrap items-center gap-2">
          <button onClick={verImpacto} disabled={cargando}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-[13px] hover:bg-slate-50 disabled:opacity-50">
            <Play size={14} /> {cargando ? "Calculando…" : "Ver impacto"}
          </button>
          <button onClick={guardar} disabled={!hayCambios || guardando}
            className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700 disabled:opacity-50">
            <Save size={14} /> {guardando ? "Guardando…" : "Guardar y aplicar"}
          </button>
          <button onClick={() => { setEd(aPlano(vigente)); setImpacto(null); setMsg(null); }}
            disabled={!hayCambios}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 px-3 py-1.5 text-[13px] hover:bg-slate-50 disabled:opacity-40">
            <RotateCcw size={14} /> Descartar
          </button>
          {!hayCambios && <span className="text-[12px] text-slate-400">Sin cambios pendientes.</span>}
        </div>
        {msg && <p className="rounded-md bg-emerald-50 px-3 py-2 text-[13px] text-emerald-700">{msg}</p>}
        {error && <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>}
      </section>

      {impacto && (
        <section className="grid grid-cols-2 gap-px bg-ink-200 lg:grid-cols-4">
          <Tile label="Compra actual" valor={formatoCLPCorto(impacto.resumen.actual_clp)}
            nota={`${formatoNumero(impacto.resumen.actual_unidades)} u`} />
          <Tile label="Con estos parámetros" valor={formatoCLPCorto(impacto.resumen.simulado_clp)}
            nota={`${formatoNumero(impacto.resumen.simulado_unidades)} u`} />
          <Tile label="Diferencia" acento
            valor={`${delta >= 0 ? "+" : ""}${formatoCLPCorto(delta)}`}
            nota={`${impacto.resumen.delta_unidades >= 0 ? "+" : ""}${formatoNumero(impacto.resumen.delta_unidades)} u`} />
          <Tile label="Líneas que cambian" valor={formatoNumero(impacto.resumen.lineas_que_cambian)}
            nota={`de ${formatoNumero(impacto.resumen.n_filas)}`} />
        </section>
      )}

      <p className="text-[11px] text-slate-400">
        El impacto es una estimación sobre los datos vigentes (misma base que el Simulador): mueve el
        ciclo de orden y los niveles de servicio. El winsor y el lead time por defecto afectan la
        demanda/clasificación, que solo se recalculan cuando corre el motor.
      </p>
    </div>
  );
}

function Campo({
  label, value, onChange, min, max, step = 1, hint,
}: {
  label: string;
  value: number;
  onChange: (v: number) => void;
  min: number;
  max: number;
  step?: number;
  hint?: string;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-[12px] font-medium text-slate-600">{label}</span>
      <input
        type="number"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px]"
      />
      {hint && <span className="mt-1 block text-[11px] text-slate-400">{hint}</span>}
    </label>
  );
}

function Tile({ label, valor, nota, acento }: { label: string; valor: string; nota?: string; acento?: boolean }) {
  return (
    <div className="border border-ink-200 bg-white p-5">
      <p className="kicker">{label}</p>
      <p className={`figure mt-2 text-[26px] leading-none ${acento ? "text-accent-700" : "text-ink-900"}`}>{valor}</p>
      {nota && <p className="mt-1.5 text-[11px] text-ink-500">{nota}</p>}
    </div>
  );
}
