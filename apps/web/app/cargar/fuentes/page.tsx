"use client";

// Fuentes de datos: de donde lee el motor cada archivo, que encontro en la ultima
// corrida y si esta al dia. Solo admin, sin item en el menu: se entra desde la
// tarjeta de /cargar. El semaforo y los textos los calcula el servidor.
//
// Nada de lo que se guarda aca se aplica al tiro: el motor lo toma en su corrida
// siguiente. En prueba el motor sigue usando la configuracion escrita en el PC y
// solo compara.
import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, BookOpen, FolderSearch, RefreshCw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { getEsAdmin } from "@/lib/auth";
import {
  ErrorFuentes,
  fuentesApi,
  type ConfigVigente,
  type FuenteDetalle,
  type Guardado,
  type Panel,
} from "@/lib/fuentes-datos";
import { AvanzadoFuentes } from "@/components/fuentes/avanzado-fuentes";
import { Cargando, MensajeError, MensajeOk } from "@/components/fuentes/comun";
import { DetalleFuente } from "@/components/fuentes/detalle-fuente";
import { EditorFuente } from "@/components/fuentes/editor-fuente";
import { PanelFuentes } from "@/components/fuentes/panel-fuentes";

export default function FuentesDatosPage() {
  const router = useRouter();
  const [panel, setPanel] = useState<Panel | null>(null);
  const [config, setConfig] = useState<ConfigVigente | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const [abierta, setAbierta] = useState<string | null>(null);
  const [editando, setEditando] = useState<FuenteDetalle | null>(null);
  const [recarga, setRecarga] = useState(0);
  const [actualizando, setActualizando] = useState(false);

  const cargar = useCallback(async () => {
    setActualizando(true);
    try {
      const [p, c] = await Promise.all([
        fuentesApi.panel(),
        // La configuracion solo arma los selectores y "Avanzado": sin ella el panel sirve igual.
        fuentesApi.config().catch(() => null),
      ]);
      setPanel(p);
      setConfig(c);
      setError(null);
    } catch (e) {
      // El backend es el gate real: un no admin recibe 403. El menu no muestra
      // /cargar, pero se puede llegar escribiendo la URL.
      setError(
        e instanceof ErrorFuentes && e.status === 403
          ? "No tienes permiso para ver Fuentes de datos. Pídeselo a un administrador."
          : e instanceof Error
            ? e.message
            : "No se pudo cargar el panel de fuentes."
      );
    } finally {
      setActualizando(false);
    }
  }, []);

  useEffect(() => {
    if (!getEsAdmin()) {
      router.replace("/");
      return;
    }
    void cargar();
  }, [router, cargar]);

  const alGuardar = async (g: Guardado, texto?: string) => {
    setEditando(null);
    setMensaje(texto ?? `Guardado como versión ${g.version}. Rige desde la próxima corrida del motor.`);
    setAvisos(g.avisos ?? []);
    await cargar();
    setRecarga((r) => r + 1);
  };

  const recargarTodo = () => {
    setEditando(null);
    setMensaje(null);
    setAvisos([]);
    void cargar();
    setRecarga((r) => r + 1);
  };

  return (
    <div className="space-y-6 p-6">
      <header className="space-y-1">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
          <Link href="/cargar" className="inline-flex items-center gap-1 hover:text-brand">
            <ArrowLeft className="h-3 w-3" aria-hidden="true" /> Cargar datos
          </Link>
        </p>
        <div className="flex flex-wrap items-center justify-between gap-2">
          <h1 className="flex items-center gap-2 text-2xl font-semibold text-ink-900">
            <FolderSearch className="h-5 w-5 text-brand" aria-hidden="true" /> Fuentes de datos
          </h1>
          <div className="flex flex-wrap gap-2">
            <Link
              href="/cargar/fuentes/guia"
              className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-ink-200 bg-white px-3 text-[13px] font-medium text-ink-700 hover:bg-paper-100"
            >
              <BookOpen className="h-3.5 w-3.5" aria-hidden="true" /> Guía para el día a día
            </Link>
            <Button size="sm" variant="outline" onClick={() => void cargar()} disabled={actualizando}>
              <RefreshCw className={`h-3.5 w-3.5 ${actualizando ? "animate-spin" : ""}`} aria-hidden="true" /> Actualizar
            </Button>
          </div>
        </div>
        <p className="max-w-3xl text-sm text-ink-500">
          De dónde lee el motor cada archivo, qué encontró en la última corrida y si está al día. Solo la ven los
          administradores. Lo que cambies acá rige desde la próxima corrida del motor.
        </p>
      </header>

      {mensaje && <MensajeOk>{mensaje}</MensajeOk>}
      {avisos.length > 0 && (
        <ul className="space-y-1 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-sm text-amber-900">
          {avisos.map((a) => (
            <li key={a}>{a}</li>
          ))}
        </ul>
      )}
      {error && <MensajeError>{error}</MensajeError>}

      {!panel && !error && <Cargando />}

      {panel && (
        <>
          <PanelFuentes panel={panel} onAbrirFuente={setAbierta} onGuardado={alGuardar} />
          <AvanzadoFuentes panel={panel} config={config} onGuardado={alGuardar} />

          <DetalleFuente
            clave={abierta}
            ahora={panel.ahora}
            version={panel.version ?? 0}
            carpetas={config?.carpetas ?? []}
            recarga={recarga}
            onClose={() => setAbierta(null)}
            onEditar={setEditando}
            onGuardado={alGuardar}
          />
          <EditorFuente
            detalle={editando}
            carpetas={config?.carpetas ?? []}
            version={panel.version ?? 0}
            onClose={() => setEditando(null)}
            onGuardado={alGuardar}
            onRecargar={recargarTodo}
          />
        </>
      )}
    </div>
  );
}
