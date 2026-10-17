"use client";

// Alta y edicion de una carpeta de donde lee el motor. Solo dos tipos: OneDrive
// (una ruta dentro del OneDrive de la empresa) y SharePoint (una biblioteca
// sincronizada con un acceso directo). Una ruta local cualquiera va solo en el
// .env del PC, nunca aca.
import { useEffect, useState } from "react";
import { Loader2, Plus, X } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Input, Label, Textarea } from "@/components/ui/input";
import {
  fuentesApi,
  type CambiosCarpeta,
  type CarpetaCfg,
  type Guardado,
} from "@/lib/fuentes-datos";
import { MensajeError } from "./comun";

type Tipo = "onedrive" | "sharepoint";

interface Form {
  clave: string;
  nombre: string;
  tipo: Tipo;
  ruta: string;
  sitio_url: string;
  biblioteca: string;
  nombre_atajo: string;
  rutas: { pc: string; ruta: string }[];
  activa: boolean;
}

function formDe(c: CarpetaCfg | null): Form {
  const p = c?.params ?? {};
  return {
    clave: c?.clave ?? "",
    nombre: c?.nombre ?? "",
    tipo: c?.tipo === "sharepoint" ? "sharepoint" : "onedrive",
    ruta: p.ruta ?? "",
    sitio_url: p.sitio_url ?? "",
    biblioteca: p.biblioteca ?? "",
    nombre_atajo: p.nombre_atajo ?? "",
    rutas: Object.entries(c?.rutas_por_pc ?? {}).map(([pc, ruta]) => ({ pc, ruta })),
    activa: c?.activa ?? true,
  };
}

function paramsDe(f: Form): Record<string, string> {
  return f.tipo === "onedrive"
    ? { ruta: f.ruta.trim() }
    : { sitio_url: f.sitio_url.trim(), biblioteca: f.biblioteca.trim(), ruta: f.ruta.trim(), nombre_atajo: f.nombre_atajo.trim() };
}

function rutasDe(f: Form): Record<string, string> {
  const r: Record<string, string> = {};
  for (const x of f.rutas) if (x.pc.trim() && x.ruta.trim()) r[x.pc.trim()] = x.ruta.trim();
  return r;
}

const igual = (a: unknown, b: unknown) => JSON.stringify(a) === JSON.stringify(b);

/** Lo que cambio de una carpeta existente. Los parametros viajan solo si se tocaron:
 *  la carpeta sembrada no trae el sitio de SharePoint y exigirlo bloquearia todo. */
function cambiosCarpeta(c: CarpetaCfg, f: Form): CambiosCarpeta {
  const cambios: CambiosCarpeta = {};
  if (f.nombre.trim() !== c.nombre) cambios.nombre = f.nombre.trim();
  if (f.tipo !== c.tipo) cambios.tipo = f.tipo;
  const antes = paramsDe(formDe(c));
  const ahora = paramsDe(f);
  if (f.tipo !== c.tipo || !igual(antes, ahora)) cambios.params = ahora;
  if (!igual(rutasDe(f), c.rutas_por_pc ?? {})) cambios.rutas_por_pc = rutasDe(f);
  if (f.activa !== c.activa) cambios.activa = f.activa;
  return cambios;
}

interface Props {
  open: boolean;
  /** null = carpeta nueva. */
  carpeta: CarpetaCfg | null;
  /** PCs que ya reportaron (para las rutas por PC). */
  pcs: string[];
  version: number;
  onClose: () => void;
  onGuardado: (g: Guardado, texto?: string) => void | Promise<void>;
}

export function EditorCarpeta({ open, carpeta, pcs, version, onClose, onGuardado }: Props) {
  const [f, setF] = useState<Form>(() => formDe(carpeta));
  const [nota, setNota] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);

  useEffect(() => {
    if (open) {
      setF(formDe(carpeta));
      setNota("");
      setError(null);
    }
  }, [open, carpeta]);

  const set = <K extends keyof Form>(k: K, v: Form[K]) => {
    setF((x) => ({ ...x, [k]: v }));
    setError(null);
  };

  const guardar = async () => {
    if (!nota.trim()) {
      setError("Escribe una nota: qué cambias y por qué.");
      return;
    }
    setGuardando(true);
    setError(null);
    try {
      let g: Guardado;
      if (carpeta) {
        const cambios = cambiosCarpeta(carpeta, f);
        if (Object.keys(cambios).length === 0) {
          setError("No hay cambios para guardar.");
          return;
        }
        g = await fuentesApi.editarCarpeta(carpeta.clave, cambios, nota.trim(), version);
      } else {
        g = await fuentesApi.crearCarpeta(
          { clave: f.clave.trim(), nombre: f.nombre.trim(), tipo: f.tipo, params: paramsDe(f), rutas_por_pc: rutasDe(f), activa: f.activa },
          nota.trim(),
          version
        );
      }
      await onGuardado(g, `Carpeta ${f.nombre.trim()} guardada. Rige desde la próxima corrida del motor.`);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setGuardando(false);
    }
  };

  const id = (s: string) => `carpeta-${s}`;

  return (
    <Dialog
      open={open}
      onClose={() => !guardando && onClose()}
      title={carpeta ? `Carpeta: ${carpeta.nombre}` : "Agregar carpeta"}
      description="Nada cambia hasta la próxima corrida del motor."
      className="max-w-2xl"
    >
      <div className="space-y-3 text-[13px] text-ink-700">
        <div className="grid gap-3 sm:grid-cols-2">
          {!carpeta && (
            <div>
              <Label htmlFor={id("clave")}>Clave (minúsculas, sin espacios)</Label>
              <Input id={id("clave")} value={f.clave} maxLength={40} placeholder="motor_sp" onChange={(e) => set("clave", e.target.value.toLowerCase())} />
            </div>
          )}
          <div className={carpeta ? "sm:col-span-2" : ""}>
            <Label htmlFor={id("nombre")}>Nombre</Label>
            <Input id={id("nombre")} value={f.nombre} maxLength={100} onChange={(e) => set("nombre", e.target.value)} />
          </div>
        </div>

        <fieldset className="flex flex-wrap gap-4">
          <legend className="mb-1 font-medium text-ink-800">Tipo</legend>
          {(["onedrive", "sharepoint"] as const).map((t) => (
            <label key={t} className="flex items-center gap-1.5">
              <input type="radio" name="tipo-carpeta" className="accent-brand" checked={f.tipo === t} onChange={() => set("tipo", t)} />
              {t === "onedrive" ? "OneDrive de la empresa" : "Biblioteca de SharePoint sincronizada"}
            </label>
          ))}
        </fieldset>

        {f.tipo === "sharepoint" && (
          <div className="grid gap-3 sm:grid-cols-2">
            <div className="sm:col-span-2">
              <Label htmlFor={id("sitio")}>Sitio de SharePoint</Label>
              <Input id={id("sitio")} value={f.sitio_url} placeholder="https://empresa.sharepoint.com/sites/sitio" onChange={(e) => set("sitio_url", e.target.value)} />
            </div>
            <div>
              <Label htmlFor={id("biblioteca")}>Biblioteca</Label>
              <Input id={id("biblioteca")} value={f.biblioteca} placeholder="Documentos compartidos" onChange={(e) => set("biblioteca", e.target.value)} />
            </div>
            <div>
              <Label htmlFor={id("atajo")}>Nombre del acceso directo en OneDrive (obligatorio)</Label>
              <Input
                id={id("atajo")}
                value={f.nombre_atajo}
                required
                aria-describedby={id("atajo-ayuda")}
                onChange={(e) => set("nombre_atajo", e.target.value)}
              />
            </div>
            <p id={id("atajo-ayuda")} className="text-[12px] text-ink-500 sm:col-span-2">
              Es el nombre de la carpeta que aparece en OneDrive al agregar el acceso directo. Es lo único que usa
              el motor para encontrar la carpeta en cada PC; el sitio, la biblioteca y la ruta quedan como
              referencia.
            </p>
          </div>
        )}
        <div>
          <Label htmlFor={id("ruta")}>{f.tipo === "onedrive" ? "Ruta dentro de OneDrive" : "Ruta dentro de la biblioteca"}</Label>
          <Input id={id("ruta")} className="font-mono" value={f.ruta} placeholder="Documentos/Desarrollos/Bases de datos" onChange={(e) => set("ruta", e.target.value)} />
          <p className="mt-1 text-[12px] text-ink-500">Al menos una carpeta; separa con /.</p>
        </div>

        <fieldset className="space-y-2">
          <legend className="font-medium text-ink-800">Ruta en un PC en particular (opcional)</legend>
          <p className="text-[12px] text-ink-500">
            Solo si en ese PC la carpeta quedó en otro lugar. El motor la acepta solo si está dentro de OneDrive.
          </p>
          {f.rutas.map((r, i) => (
            <div key={i} className="grid items-end gap-2 sm:grid-cols-[12rem_minmax(0,1fr)_auto]">
              <div>
                <Label htmlFor={id(`pc-${i}`)}>PC</Label>
                <select
                  id={id(`pc-${i}`)}
                  className="h-9 w-full rounded-sm border border-ink-200 bg-white px-2 text-[13px]"
                  value={r.pc}
                  onChange={(e) => set("rutas", f.rutas.map((x, j) => (j === i ? { ...x, pc: e.target.value } : x)))}
                >
                  {Array.from(new Set([r.pc, ...pcs].filter(Boolean))).map((p) => (
                    <option key={p} value={p}>{p}</option>
                  ))}
                </select>
              </div>
              <div>
                <Label htmlFor={id(`ruta-${i}`)}>Ruta</Label>
                <Input
                  id={id(`ruta-${i}`)}
                  className="font-mono"
                  value={r.ruta}
                  onChange={(e) => set("rutas", f.rutas.map((x, j) => (j === i ? { ...x, ruta: e.target.value } : x)))}
                />
              </div>
              <Button variant="ghost" size="sm" aria-label={`Quitar la ruta de ${r.pc}`} onClick={() => set("rutas", f.rutas.filter((_, j) => j !== i))}>
                <X className="h-4 w-4" aria-hidden="true" />
              </Button>
            </div>
          ))}
          {pcs.length > 0 && (
            <Button variant="outline" size="sm" onClick={() => set("rutas", [...f.rutas, { pc: pcs[0], ruta: "" }])}>
              <Plus className="h-3.5 w-3.5" aria-hidden="true" /> Agregar ruta de un PC
            </Button>
          )}
        </fieldset>

        <label className="flex items-center gap-1.5">
          <input type="checkbox" checked={f.activa} onChange={(e) => set("activa", e.target.checked)} />
          Activa
        </label>

        <div>
          <Label htmlFor={id("nota")}>Nota del cambio</Label>
          <Textarea id={id("nota")} rows={2} maxLength={500} value={nota} placeholder="Qué cambias y por qué" onChange={(e) => { setNota(e.target.value); setError(null); }} />
        </div>
        {error && <MensajeError>{error}</MensajeError>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={guardando}>Cancelar</Button>
          <Button onClick={() => void guardar()} disabled={guardando}>
            {guardando && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            Guardar
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
