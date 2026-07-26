"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { CheckCircle2, FileSpreadsheet, Upload } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { getEsAdmin } from "@/lib/auth";
import { formatoNumero } from "@/lib/formato";
import { SincronizacionManual } from "@/components/sincronizacion-manual";
import { PanelMotorSombra } from "@/components/panel-motor-sombra";
import type { CargaResultado } from "@/lib/types";

export default function CargarPage() {
  const router = useRouter();
  // Si alguien sin permisos cae aca por URL, lo mandamos al dashboard.
  useEffect(() => {
    if (!getEsAdmin()) router.replace("/");
  }, [router]);
  const [file, setFile] = useState<File | null>(null);
  const [cargando, setCargando] = useState(false);
  const [resultado, setResultado] = useState<CargaResultado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [drag, setDrag] = useState(false);

  // La subida de archivo a mano queda SOLO en modo local (desarrollo). En produccion
  // el sugerido entra por el motor: subir un Excel cualquiera podria pisar los datos
  // buenos, y para forzar una actualizacion ya esta el boton de arriba.
  const apiEsLocal = (process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000").includes(
    "localhost"
  );

  const subir = async () => {
    if (!file) return;
    setCargando(true);
    setError(null);
    setResultado(null);
    try {
      setResultado(await api.cargarSugerido(file));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setCargando(false);
    }
  };

  return (
    <div className="mx-auto max-w-2xl space-y-5">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">Cargar datos</h1>
        <p className="text-[13px] text-slate-500">
          El sugerido lo calcula el motor con los Excel de <b>Bases de datos</b> y se
          publica solo todos los días. Acá puedes ver cuándo fue la última vez y
          forzarlo si hace falta.
        </p>
      </div>

      {/* Como se actualiza hoy: la tarea corre el motor, sin Power BI. */}
      <Card className="border-brand-200 bg-brand-50/60">
        <CardContent className="text-[13px] text-ink-700">
          <p className="font-display text-[15px] font-medium text-ink-900">
            Actualización automática diaria
          </p>
          <p className="mt-2">
            Todos los días a las <b>10:00 AM</b>, una tarea programada en el PC del
            administrador ejecuta el motor: lee los Excel de{" "}
            <code className="rounded-sm bg-white px-1 py-px font-mono text-[12px] text-accent-700">
              Bases de datos
            </code>
            , calcula el sugerido y lo publica para todo el equipo.{" "}
            <b>Ya no depende del Power BI.</b>
          </p>
          <p className="mt-3">
            <span className="kicker">Lo único que hay que mantener</span>
            <br />
            Los archivos de esa carpeta al día (stock y seguimiento a diario; ventas al
            cerrar el mes). Si alguno está vencido, el motor <b>no publica</b> y lo avisa,
            en vez de dejar datos viejos como buenos.
          </p>
          <SincronizacionManual />
          <p className="mt-3 text-[11.5px] text-ink-500">
            Log de cada corrida en{" "}
            <code className="font-mono">logs/motor_&lt;fecha&gt;.log</code> del PC del admin.
          </p>
        </CardContent>
      </Card>

      {/* Subida manual: SOLO en modo local. En la nube se oculta para evitar que un
          Excel de la tabla base (sin medidas) pise los datos buenos por accidente. */}
      {apiEsLocal && (
      <div className="flex items-center gap-3 text-[12px] text-slate-400">
        <span className="h-px flex-1 bg-slate-200" />o sube un archivo manualmente
        <span className="h-px flex-1 bg-slate-200" />
      </div>
      )}

      {apiEsLocal && (
      <Card>
        <CardContent className="space-y-4">
          <label
            onDragOver={(e) => {
              e.preventDefault();
              setDrag(true);
            }}
            onDragLeave={() => setDrag(false)}
            onDrop={(e) => {
              e.preventDefault();
              setDrag(false);
              const f = e.dataTransfer.files?.[0];
              if (f) setFile(f);
            }}
            className={`flex cursor-pointer flex-col items-center justify-center gap-2 rounded-xl border-2 border-dashed px-6 py-10 text-center transition-colors ${
              drag ? "border-brand bg-brand-50" : "border-slate-300 bg-slate-50 hover:bg-slate-100"
            }`}
          >
            <input
              type="file"
              accept=".xlsx,.xlsm,.csv"
              className="hidden"
              onChange={(e) => setFile(e.target.files?.[0] ?? null)}
            />
            {file ? (
              <>
                <FileSpreadsheet size={32} className="text-brand" />
                <span className="text-sm font-medium text-slate-900">{file.name}</span>
                <span className="text-[12px] text-slate-500">
                  {(file.size / 1024).toFixed(0)} KB · click para cambiar
                </span>
              </>
            ) : (
              <>
                <Upload size={32} className="text-slate-400" />
                <span className="text-sm font-medium text-slate-700">
                  Arrastra el archivo aqui o haz click
                </span>
                <span className="text-[12px] text-slate-500">.xlsx, .xlsm o .csv</span>
              </>
            )}
          </label>

          <Button onClick={subir} disabled={!file || cargando} className="w-full">
            {cargando ? "Cargando…" : "Cargar a la plataforma"}
          </Button>

          {error && (
            <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
          )}
        </CardContent>
      </Card>
      )}

      {/* Aparece solo si ya se corrio alguna comparacion del motor propio. */}
      <PanelMotorSombra />

      {resultado && (
        <Card className="border-emerald-200">
          <CardHeader>
            <CardTitle className="flex items-center gap-2 text-emerald-700">
              <CheckCircle2 size={18} /> Carga exitosa
            </CardTitle>
          </CardHeader>
          <CardContent className="space-y-3 text-[13px] text-slate-700">
            <div className="grid grid-cols-3 gap-3">
              <div className="rounded-lg bg-slate-50 p-3 text-center">
                <p className="tabular text-lg font-semibold text-slate-900">
                  {formatoNumero(resultado.filas_cargadas)}
                </p>
                <p className="text-[12px] text-slate-500">filas</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-center">
                <p className="tabular text-lg font-semibold text-slate-900">
                  {formatoNumero(resultado.productos)}
                </p>
                <p className="text-[12px] text-slate-500">productos</p>
              </div>
              <div className="rounded-lg bg-slate-50 p-3 text-center">
                <p className="tabular text-lg font-semibold text-slate-900">
                  {formatoNumero(resultado.sucursales)}
                </p>
                <p className="text-[12px] text-slate-500">sucursales</p>
              </div>
            </div>

            {resultado.advertencias.length > 0 && (
              <div className="rounded-md bg-amber-50 px-3 py-2 text-amber-800">
                {resultado.advertencias.map((a, i) => (
                  <p key={i}>⚠ {a}</p>
                ))}
              </div>
            )}

            <details className="text-[12px] text-slate-500">
              <summary className="cursor-pointer">
                Ver columnas detectadas ({resultado.columnas_detectadas.length})
              </summary>
              <ul className="mt-1 space-y-0.5">
                {resultado.columnas_detectadas.map((c) => (
                  <li key={c} className="tabular">{c}</li>
                ))}
              </ul>
            </details>

            <Link href="/">
              <Button className="w-full">Ir al dashboard</Button>
            </Link>
          </CardContent>
        </Card>
      )}
    </div>
  );
}
