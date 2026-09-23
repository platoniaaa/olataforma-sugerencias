"use client";

// Carga de los lunes: plantilla, subir Excel/CSV, ver errores (no se guarda nada)
// o el resultado con los avisos de las reglas (1 por clase, cantidad sugerida).
import { useRef, useState } from "react";
import { AlertTriangle, CheckCircle2, Download, Loader2, Upload } from "lucide-react";
import { ErrorCarga, etiquetaSemana, inventarioApi, lunesDe, type ResultadoCarga } from "@/lib/inventario-ciclico";

interface Props {
  onCargado: (semana: string) => void;
}

export function Carga({ onCargado }: Props) {
  const [fecha, setFecha] = useState(lunesDe(new Date()));
  const [archivo, setArchivo] = useState<File | null>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [errores, setErrores] = useState<string[]>([]);
  const [resultado, setResultado] = useState<ResultadoCarga | null>(null);
  const input = useRef<HTMLInputElement>(null);

  const semana = fecha ? lunesDe(new Date(`${fecha}T12:00:00`)) : "";

  const subir = async () => {
    if (!archivo || !semana) return;
    setSubiendo(true);
    setErrores([]);
    setResultado(null);
    try {
      const r = await inventarioApi.cargar(semana, archivo);
      setResultado(r);
      setArchivo(null);
      if (input.current) input.current.value = "";
      onCargado(r.semana);
    } catch (e) {
      setErrores(e instanceof ErrorCarga ? e.errores : [e instanceof Error ? e.message : "No se pudo cargar"]);
    } finally {
      setSubiendo(false);
    }
  };

  return (
    <div className="max-w-2xl space-y-3">
      <div className="rounded-sm border border-ink-200 bg-white p-4 shadow-card">
        <ol className="space-y-3 text-[13.5px] text-ink-700">
          <li>
            <p className="font-medium text-ink-900">1. Descarga la plantilla</p>
            <p className="text-[12.5px] text-ink-500">
              Columnas: Producto, Descripcion, Sucursal, Clasif ABC, Cantidad, Costo y, opcional, Requiere evidencia (Si/No).
            </p>
            <button
              type="button"
              onClick={() => inventarioApi.descargarPlantilla()}
              className="mt-1.5 inline-flex items-center gap-1.5 rounded-sm border border-ink-200 px-3 py-1.5 text-[13px] hover:bg-paper-100"
            >
              <Download size={14} /> Plantilla Excel
            </button>
          </li>
          <li>
            <p className="font-medium text-ink-900">2. Elige la semana</p>
            <input
              type="date"
              value={fecha}
              onChange={(e) => setFecha(e.target.value)}
              className="mt-1.5 h-9 rounded-sm border border-ink-200 px-2 text-[13px]"
            />
            {semana && <span className="ml-2 text-[12.5px] text-ink-500">{etiquetaSemana(semana)}</span>}
          </li>
          <li>
            <p className="font-medium text-ink-900">3. Sube el archivo</p>
            <p className="text-[12.5px] text-ink-500">
              Si la semana ya estaba cargada, reemplaza lo no contado de esas sucursales. Lo ya contado no se toca.
            </p>
            <div className="mt-1.5 flex flex-wrap items-center gap-2">
              <input
                ref={input}
                type="file"
                accept=".xlsx,.xlsm,.csv"
                onChange={(e) => setArchivo(e.target.files?.[0] ?? null)}
                className="text-[13px]"
              />
              <button
                type="button"
                onClick={subir}
                disabled={!archivo || !semana || subiendo}
                className="inline-flex items-center gap-1.5 rounded-sm bg-ink-900 px-3 py-1.5 text-[13px] font-medium text-paper hover:bg-accent-700 disabled:opacity-40"
              >
                {subiendo ? <Loader2 size={14} className="animate-spin" /> : <Upload size={14} />}
                Cargar
              </button>
            </div>
          </li>
        </ol>
      </div>

      {errores.length > 0 && (
        <div className="rounded-sm border border-red-200 bg-red-50 p-3 text-[13px] text-red-800">
          <p className="font-medium">No se guardó nada. Corrige el archivo y vuelve a subirlo:</p>
          <ul className="mt-1.5 max-h-72 list-disc space-y-0.5 overflow-y-auto pl-5">
            {errores.map((e) => (
              <li key={e}>{e}</li>
            ))}
          </ul>
        </div>
      )}

      {resultado && (
        <div className="rounded-sm border border-emerald-200 bg-emerald-50 p-3 text-[13px] text-emerald-900">
          <p className="flex items-center gap-1.5 font-medium">
            <CheckCircle2 size={15} /> {etiquetaSemana(resultado.semana)} cargada: {resultado.sucursales.join(", ")}
          </p>
          <p className="mt-1">
            {resultado.insertados} nuevos · {resultado.actualizados} actualizados · {resultado.conservados} ya contados
            (sin cambios) · {resultado.eliminados} quitados
          </p>
          {resultado.avisos.length > 0 && (
            <ul className="mt-2 space-y-0.5 text-amber-900">
              {resultado.avisos.map((a) => (
                <li key={a} className="flex items-start gap-1.5">
                  <AlertTriangle size={13} className="mt-0.5 shrink-0" /> {a}
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
