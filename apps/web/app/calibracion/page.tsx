"use client";

// Calibracion del modelo, por modulos: cada seccion cubre un aspecto del modelo
// (lead time, stock de seguridad, demanda) con sus perillas. Edita, mira el
// impacto y aplica; el motor usa los valores en su proxima corrida. Solo admin.
import { useEffect, useState } from "react";
import {
  SlidersHorizontal, Play, Save, RotateCcw, Truck, Shield, TrendingUp, History, Search, Tags,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type {
  ConfigModelo, ConfigModeloPlano, LeadTimeResponse, SimulacionResultado,
} from "@/lib/types";

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

/** Avisos de configuraciones que "compilan" pero casi seguro son un error.
 *  No bloquean: puede haber una razon de negocio, pero conviene verlo antes. */
function avisosCoherencia(e: ConfigModeloPlano): string[] {
  const a: string[] = [];
  if (!(e.z_a >= e.z_b && e.z_b >= e.z_c && e.z_c >= e.z_d)) {
    a.push(
      "El nivel de servicio deberia bajar de A a D (A ≥ B ≥ C ≥ D). Asi como esta, una clase menos importante lleva mas colchon que una mas importante."
    );
  }
  if (e.z_imp_cd_a > e.z_a || e.z_imp_cd_b > e.z_b) {
    a.push(
      "El importado por CD usa un nivel de servicio MAYOR que el normal. Suele ser al reves: el CD consolida la variabilidad de varias sucursales y necesita menos colchon."
    );
  }
  if (!(e.abc_umbral_a_m6 > e.abc_umbral_b_m6 && e.abc_umbral_b_m6 > e.abc_umbral_c_m6)) {
    a.push(
      "Los umbrales ABC deberian ir de mayor a menor (A > B > C). Con estos valores hay clases que nunca se van a asignar."
    );
  }
  if (e.transito_importado_dias < e.transito_nacional_dias) {
    a.push(
      "La ventana de transito del importado es menor que la del nacional. El importado suele tardar mas, no menos."
    );
  }
  if (e.lt_cd_rm_dias > e.lt_cd_resto_dias) {
    a.push("El envio del CD a la Region Metropolitana tarda mas que al resto del pais.");
  }
  return a;
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
    lt_cd_rm_dias: c.lt_cd_rm_dias,
    lt_cd_resto_dias: c.lt_cd_resto_dias,
    lt_tope_dias: c.lt_tope_dias,
    transito_nacional_dias: c.transito_nacional_dias,
    transito_importado_dias: c.transito_importado_dias,
    dias_habiles_mes: c.dias_habiles_mes,
    abc_umbral_a_m6: c.abc_umbral_a_m6,
    abc_umbral_b_m6: c.abc_umbral_b_m6,
    abc_umbral_c_m6: c.abc_umbral_c_m6,
    abc_umbral_c_m3: c.abc_umbral_c_m3,
    abc_umbral_c_m12: c.abc_umbral_c_m12,
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

  const avisos = avisosCoherencia(ed);
  const delta = impacto?.resumen.delta_clp ?? 0;

  return (
    <div className="space-y-5">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
          <SlidersHorizontal size={20} /> Calibración del modelo
        </h1>
        <p className="text-[13px] text-slate-500">
          Ajusta los parámetros del sugerido, por módulo. Los cambios se aplican en la próxima
          corrida del motor.
        </p>
      </div>

      <div className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-[12px] text-slate-600">
        {vigente.es_default
          ? "Vigente: valores por defecto (nunca se ha editado)."
          : `Vigente: editada por ${vigente.creado_por ?? "—"}${
              vigente.creado_en ? " el " + new Date(vigente.creado_en).toLocaleString("es-CL") : ""
            }${vigente.nota ? ` · “${vigente.nota}”` : ""}.`}
      </div>

      {/* MÓDULO · Stock de seguridad */}
      <Modulo icon={Shield} titulo="Stock de seguridad" subtitulo="El colchón para no quebrar mientras llega la reposición.">
        <Grupo titulo="Ciclo de orden (días de cobertura extra)">
          <Campo label="Compra directa" min={1} max={60} value={ed.ciclo_orden_dias}
            onChange={(v) => set("ciclo_orden_dias", v)} />
          <Campo label="Abastecido del CD" min={1} max={60} value={ed.ciclo_orden_dias_cd}
            onChange={(v) => set("ciclo_orden_dias_cd", v)} />
        </Grupo>
        <Grupo titulo="Nivel de servicio (Z) por clase" cols={4}>
          <Campo label="Clase A" min={0} max={3.5} step={0.001} value={ed.z_a}
            onChange={(v) => set("z_a", v)} hint={nivelServicio(ed.z_a)} />
          <Campo label="Clase B" min={0} max={3.5} step={0.001} value={ed.z_b}
            onChange={(v) => set("z_b", v)} hint={nivelServicio(ed.z_b)} />
          <Campo label="Clase C" min={0} max={3.5} step={0.001} value={ed.z_c}
            onChange={(v) => set("z_c", v)} hint={nivelServicio(ed.z_c)} />
          <Campo label="Clase D" min={0} max={3.5} step={0.001} value={ed.z_d}
            onChange={(v) => set("z_d", v)} hint={nivelServicio(ed.z_d)} />
        </Grupo>
        <Grupo titulo="Nivel de servicio para importado por CD">
          <Campo label="Clase A" min={0} max={3.5} step={0.001} value={ed.z_imp_cd_a}
            onChange={(v) => set("z_imp_cd_a", v)} hint={nivelServicio(ed.z_imp_cd_a)} />
          <Campo label="Clase B" min={0} max={3.5} step={0.001} value={ed.z_imp_cd_b}
            onChange={(v) => set("z_imp_cd_b", v)} hint={nivelServicio(ed.z_imp_cd_b)} />
        </Grupo>
      </Modulo>

      {/* MÓDULO · Lead time */}
      <Modulo icon={Truck} titulo="Lead time y tránsito" subtitulo="Cuánto tarda la reposición y qué OC cuentan como en camino.">
        <Grupo titulo="Del CD a la sucursal (días)">
          <Campo label="Región Metropolitana" min={0} max={30} value={ed.lt_cd_rm_dias}
            onChange={(v) => set("lt_cd_rm_dias", v)} />
          <Campo label="Resto de regiones" min={0} max={30} value={ed.lt_cd_resto_dias}
            onChange={(v) => set("lt_cd_resto_dias", v)} />
        </Grupo>
        <Grupo titulo="Lead time del proveedor">
          <Campo label="Por defecto (sin historial de OC)" min={1} max={90} value={ed.lead_time_fallback_dias}
            onChange={(v) => set("lead_time_fallback_dias", v)}
            hint="Cuando no hay proveedor ni OCs para calcularlo." />
          <Campo label="Tope de días (descarta outliers)" min={1} max={365} value={ed.lt_tope_dias}
            onChange={(v) => set("lt_tope_dias", v)}
            hint="Las OC con LT sobre esto no cuentan al promediar." />
        </Grupo>
        <Grupo titulo="Ventana de tránsito (una OC pendiente cuenta como en camino si es más nueva que…)">
          <Campo label="Nacional (días)" min={1} max={365} value={ed.transito_nacional_dias}
            onChange={(v) => set("transito_nacional_dias", v)} />
          <Campo label="Importado (días)" min={1} max={730} value={ed.transito_importado_dias}
            onChange={(v) => set("transito_importado_dias", v)} />
        </Grupo>
        <DetalleLeadTime />
      </Modulo>

      {/* MÓDULO · Demanda */}
      <Modulo icon={TrendingUp} titulo="Demanda" subtitulo="Cómo se estima la venta esperada.">
        <Grupo titulo="Parámetros">
          <Campo label="Winsor k (recorte de picos)" min={0.5} max={6} step={0.1} value={ed.winsor_k}
            onChange={(v) => set("winsor_k", v)} hint="Más alto = recorta menos los meses pico." />
          <Campo label="Días hábiles por mes" min={15} max={31} value={ed.dias_habiles_mes}
            onChange={(v) => set("dias_habiles_mes", v)} hint="Divisor para pasar de demanda mensual a diaria." />
        </Grupo>
        <p className="text-[11px] text-slate-400">
          Estos dos afectan la demanda/clasificación, que solo se recalcula cuando corre el motor: el
          previsualizador de impacto no los refleja.
        </p>
      </Modulo>

      {/* MÓDULO · Clasificación ABC */}
      <Modulo icon={Tags} titulo="Clasificación ABC"
        subtitulo="En cuántos meses tiene que haber venta para que un producto sea A, B, C o D.">
        <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-[12px] text-amber-800">
          Es la perilla más potente del modelo: mover un umbral cambia de clase a muchos productos y
          con eso su ventana de demanda, su nivel de servicio y si se compra o no. El efecto solo se
          ve al correr el motor (el previsualizador de impacto no lo refleja).
        </div>
        <Grupo titulo="Meses con venta en los últimos 6 meses">
          <Campo label="Clase A — desde (≥)" min={1} max={6} value={ed.abc_umbral_a_m6}
            onChange={(v) => set("abc_umbral_a_m6", v)} hint={`Vende en ${ed.abc_umbral_a_m6} meses o más de 6.`} />
          <Campo label="Clase B — exactamente" min={0} max={6} value={ed.abc_umbral_b_m6}
            onChange={(v) => set("abc_umbral_b_m6", v)} hint={`Vende en exactamente ${ed.abc_umbral_b_m6} de 6.`} />
        </Grupo>
        <Grupo titulo="Clase C (la cola que el CD consolida)" cols={4}>
          <Campo label="Meses en 6m (=)" min={0} max={6} value={ed.abc_umbral_c_m6}
            onChange={(v) => set("abc_umbral_c_m6", v)} />
          <Campo label="y meses en 3m (≥)" min={0} max={3} value={ed.abc_umbral_c_m3}
            onChange={(v) => set("abc_umbral_c_m3", v)} />
          <Campo label="o meses en 12m (>)" min={0} max={12} value={ed.abc_umbral_c_m12}
            onChange={(v) => set("abc_umbral_c_m12", v)} />
        </Grupo>
        <p className="text-[11.5px] text-slate-500">
          Regla actual: <strong>A</strong> si vende en {ed.abc_umbral_a_m6}+ de los últimos 6 meses ·{" "}
          <strong>B</strong> si vende en {ed.abc_umbral_b_m6} · <strong>C</strong> si vende en{" "}
          {ed.abc_umbral_c_m6} y al menos {ed.abc_umbral_c_m3} de los últimos 3 (o más de{" "}
          {ed.abc_umbral_c_m12} de los últimos 12) · <strong>D</strong> el resto.
        </p>
      </Modulo>

      {/* Acciones */}
      <section className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
        <label className="block">
          <span className="mb-1 block text-[12px] font-medium text-slate-600">Nota (por qué del cambio)</span>
          <input type="text" value={nota} maxLength={500} onChange={(e) => setNota(e.target.value)}
            placeholder="Opcional — queda en el historial"
            className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px]" />
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
        {avisos.length > 0 && (
          <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2">
            <p className="mb-1 text-[12px] font-medium text-amber-900">Revisa antes de aplicar:</p>
            <ul className="list-disc space-y-1 pl-4 text-[12px] text-amber-800">
              {avisos.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          </div>
        )}
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
        El impacto es una estimación sobre los datos vigentes (misma base que el Simulador) y refleja
        el ciclo de orden y los niveles de servicio. El resto de los parámetros se aplica al correr el motor.
      </p>

      <Historial recargar={cargar} />
    </div>
  );
}

/** Lead time que calculo el motor: el "por que" detras del numero. */
function DetalleLeadTime() {
  const [datos, setDatos] = useState<LeadTimeResponse | null>(null);
  const [buscar, setBuscar] = useState("");
  const [abierto, setAbierto] = useState(false);

  useEffect(() => {
    if (!abierto) return;
    const t = setTimeout(() => {
      api.leadTimeProveedor({ buscar: buscar || undefined }).then(setDatos).catch(() => setDatos(null));
    }, 250);
    return () => clearTimeout(t);
  }, [abierto, buscar]);

  return (
    <div className="rounded-md border border-slate-200 bg-slate-50/60 p-3">
      <button onClick={() => setAbierto(!abierto)}
        className="text-[12px] font-medium text-slate-700 hover:text-slate-900">
        {abierto ? "▾" : "▸"} Lead time calculado por el motor (detalle por proveedor y sucursal)
      </button>
      {abierto && (
        <div className="mt-3 space-y-2">
          <div className="flex items-center gap-2">
            <span className="relative flex-1">
              <Search size={13} className="absolute left-2.5 top-2 text-slate-400" />
              <input value={buscar} onChange={(e) => setBuscar(e.target.value)}
                placeholder="Buscar proveedor o sucursal…"
                className="w-full rounded-md border border-slate-300 py-1.5 pl-8 pr-3 text-[13px]" />
            </span>
            {datos?.actualizado_en && (
              <span className="text-[11px] text-slate-400">
                Calculado el {new Date(datos.actualizado_en).toLocaleString("es-CL")}
              </span>
            )}
          </div>
          {!datos ? (
            <p className="text-[12px] text-slate-400">Cargando…</p>
          ) : datos.total === 0 ? (
            <p className="text-[12px] text-slate-500">
              Todavía no hay datos: el motor lo publica en su próxima corrida oficial.
            </p>
          ) : (
            <>
              <div className="max-h-80 overflow-auto rounded-md border border-slate-200 bg-white">
                <table className="w-full text-[13px]">
                  <thead className="sticky top-0 bg-slate-50 text-left text-[11px] uppercase text-slate-500">
                    <tr>
                      <th className="px-3 py-1.5">Proveedor</th>
                      <th className="px-3 py-1.5">Sucursal</th>
                      <th className="px-3 py-1.5 text-right">Días</th>
                      <th className="px-3 py-1.5 text-right">Muestras</th>
                    </tr>
                  </thead>
                  <tbody>
                    {datos.items.map((f, i) => (
                      <tr key={i} className="border-t border-slate-100">
                        <td className="px-3 py-1.5">{f.proveedor}</td>
                        <td className="px-3 py-1.5 text-slate-500">
                          {f.sucursal_id ?? <em className="text-slate-400">todas (global)</em>}
                        </td>
                        <td className="px-3 py-1.5 text-right tabular">{f.lead_time_dias.toFixed(1)}</td>
                        <td className={`px-3 py-1.5 text-right tabular ${
                          f.n_muestras !== null && f.n_muestras < 5 ? "text-amber-700" : "text-slate-500"
                        }`}>
                          {f.n_muestras ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <p className="text-[11px] text-slate-400">
                Mostrando {datos.items.length} de {formatoNumero(datos.total)}. Pocas muestras (menos
                de 5, en ámbar) = promedio poco confiable. Es resultado del cálculo, no configurable.
              </p>
            </>
          )}
        </div>
      )}
    </div>
  );
}

/** Historial de versiones de la configuracion, con reversa. */
function Historial({ recargar }: { recargar: () => Promise<void> }) {
  const [versiones, setVersiones] = useState<ConfigModelo[] | null>(null);
  const [abierto, setAbierto] = useState(false);
  const [ocupado, setOcupado] = useState(false);

  const cargarHistorial = async () => {
    try {
      setVersiones(await api.configModeloHistorial());
    } catch {
      setVersiones([]);
    }
  };

  useEffect(() => {
    if (abierto) cargarHistorial();
  }, [abierto]);

  const revertir = async (v: ConfigModelo) => {
    const cuando = v.creado_en ? new Date(v.creado_en).toLocaleString("es-CL") : "—";
    if (!window.confirm(`¿Volver a la configuración del ${cuando}?\n\nSe aplica en la próxima corrida del motor.`)) {
      return;
    }
    setOcupado(true);
    try {
      await api.revertirConfigModelo(v.id!);
      await Promise.all([recargar(), cargarHistorial()]);
    } finally {
      setOcupado(false);
    }
  };

  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <button onClick={() => setAbierto(!abierto)}
        className="flex items-center gap-1.5 text-[13px] font-medium text-slate-700 hover:text-slate-900">
        <History size={14} /> {abierto ? "▾" : "▸"} Historial de cambios
      </button>
      {abierto && (
        <div className="mt-3">
          {!versiones ? (
            <p className="text-[12px] text-slate-400">Cargando…</p>
          ) : versiones.length === 0 ? (
            <p className="text-[12px] text-slate-500">Todavía no se ha editado la configuración.</p>
          ) : (
            <ul className="divide-y divide-slate-100">
              {versiones.map((v, i) => (
                <li key={v.id} className="flex items-center justify-between gap-3 py-2">
                  <div className="min-w-0">
                    <p className="text-[13px] text-slate-800">
                      {v.creado_en ? new Date(v.creado_en).toLocaleString("es-CL") : "—"}
                      {i === 0 && (
                        <span className="ml-2 rounded bg-emerald-50 px-1.5 py-0.5 text-[10px] font-medium text-emerald-700">
                          vigente
                        </span>
                      )}
                    </p>
                    <p className="truncate text-[11.5px] text-slate-500">
                      {v.creado_por ?? "—"}
                      {v.nota ? ` · “${v.nota}”` : ""}
                      {` · ciclo ${v.ciclo_orden_dias}/${v.ciclo_orden_dias_cd} · Z(A) ${v.z_por_clase.A}`}
                    </p>
                  </div>
                  {i > 0 && (
                    <button onClick={() => revertir(v)} disabled={ocupado}
                      className="shrink-0 rounded-md border border-slate-200 px-2.5 py-1 text-[12px] hover:bg-slate-50 disabled:opacity-40">
                      Volver a esta
                    </button>
                  )}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}

function Modulo({
  icon: Icon, titulo, subtitulo, children,
}: {
  icon: typeof Truck;
  titulo: string;
  subtitulo: string;
  children: React.ReactNode;
}) {
  return (
    <section className="space-y-4 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <div className="flex items-center gap-2">
        <span className="flex h-7 w-7 items-center justify-center rounded-md bg-slate-100 text-slate-600">
          <Icon size={15} />
        </span>
        <div>
          <h2 className="text-[14px] font-semibold text-slate-900">{titulo}</h2>
          <p className="text-[11.5px] text-slate-500">{subtitulo}</p>
        </div>
      </div>
      {children}
    </section>
  );
}

function Grupo({ titulo, cols = 2, children }: { titulo: string; cols?: number; children: React.ReactNode }) {
  const grid = cols === 4 ? "sm:grid-cols-4" : "sm:grid-cols-2";
  return (
    <div>
      <p className="mb-2 text-[12px] font-medium text-slate-600">{titulo}</p>
      <div className={`grid gap-4 ${grid}`}>{children}</div>
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
      <input type="number" min={min} max={max} step={step} value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px]" />
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
