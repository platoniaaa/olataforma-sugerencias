"use client";

// Piezas que comparten el panel, el detalle y el editor de Fuentes de datos.
import { useEffect, useState } from "react";
import { AlertCircle, AlertTriangle, CheckCircle2, CircleDashed, Loader2, XCircle } from "lucide-react";
import { Dialog } from "@/components/ui/dialog";
import { Button } from "@/components/ui/button";
import { Label, Textarea } from "@/components/ui/input";
import { cn } from "@/lib/utils";
import { NIVELES, type Nivel } from "@/lib/fuentes-datos";

const ICONOS: Record<Nivel, typeof CheckCircle2> = {
  rojo: XCircle,
  amarillo: AlertTriangle,
  verde: CheckCircle2,
  gris: CircleDashed,
};

/** Semaforo con icono y etiqueta: el color nunca va solo. */
export function NivelBadge({ nivel, etiqueta, className }: { nivel: Nivel; etiqueta: string; className?: string }) {
  const Icono = ICONOS[nivel];
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1 rounded-sm border px-1.5 py-0.5 text-[11.5px] font-semibold",
        NIVELES[nivel].fila,
        className
      )}
    >
      <Icono className="h-3.5 w-3.5 shrink-0" aria-hidden="true" />
      {etiqueta}
    </span>
  );
}

export function MensajeError({ children }: { children: React.ReactNode }) {
  return (
    <p role="alert" className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-sm text-rose-800">
      <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" aria-hidden="true" /> <span>{children}</span>
    </p>
  );
}

export function MensajeOk({ children }: { children: React.ReactNode }) {
  return (
    <p role="status" className="rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-sm text-emerald-800">
      {children}
    </p>
  );
}

export function Cargando({ texto = "Cargando…" }: { texto?: string }) {
  return (
    <p className="flex items-center gap-2 text-sm text-ink-500">
      <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" /> {texto}
    </p>
  );
}

/**
 * Dialogo para una accion que deja una version nueva: pide la nota (obligatoria
 * salvo que `notaOpcional`), muestra el error del servidor junto al boton y no
 * se cierra hasta que la accion termina bien.
 */
export function DialogoNota({
  open,
  titulo,
  descripcion,
  boton,
  notaOpcional = false,
  placeholder = "Qué cambia y por qué",
  onClose,
  onConfirmar,
  children,
}: {
  open: boolean;
  titulo: string;
  descripcion?: string;
  boton: string;
  notaOpcional?: boolean;
  placeholder?: string;
  onClose: () => void;
  onConfirmar: (nota: string) => Promise<void>;
  children?: React.ReactNode;
}) {
  const [nota, setNota] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);

  useEffect(() => {
    if (open) {
      setNota("");
      setError(null);
      setEnviando(false);
    }
  }, [open]);

  const confirmar = async () => {
    if (!notaOpcional && !nota.trim()) {
      setError("Escribe una nota: qué cambias y por qué. Queda en el historial.");
      return;
    }
    setEnviando(true);
    setError(null);
    try {
      await onConfirmar(nota.trim());
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setEnviando(false);
    }
  };

  return (
    <Dialog open={open} onClose={() => !enviando && onClose()} title={titulo} description={descripcion}>
      <div className="space-y-3">
        {children}
        <div>
          <Label htmlFor="dialogo-nota">Nota{notaOpcional ? " (opcional)" : ""}</Label>
          <Textarea
            id="dialogo-nota"
            rows={3}
            maxLength={500}
            value={nota}
            placeholder={placeholder}
            disabled={enviando}
            onChange={(e) => {
              setNota(e.target.value);
              setError(null);
            }}
          />
        </div>
        {error && <MensajeError>{error}</MensajeError>}
        <div className="flex justify-end gap-2">
          <Button variant="outline" onClick={onClose} disabled={enviando}>
            Cancelar
          </Button>
          <Button onClick={() => void confirmar()} disabled={enviando}>
            {enviando && <Loader2 className="h-4 w-4 animate-spin" aria-hidden="true" />}
            {boton}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}
