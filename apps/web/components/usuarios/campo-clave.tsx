"use client";

// Clave nueva + repetirla, con la opcion de generar una al azar en el navegador.
// Lo usan el alta (clave inicial) y el cambio de clave. La clave guardada nunca
// se muestra (el servidor ni siquiera la tiene: guarda un hash); lo unico que se
// puede ver es la que se esta escribiendo o la recien generada, antes de guardar.
import { useState } from "react";
import { Check, Copy, Dices, Eye, EyeOff } from "lucide-react";
import { Input, Label } from "@/components/ui/input";
import { generarClave } from "@/lib/usuarios";

interface Props {
  id: string;
  etiqueta: string;
  clave: string;
  repetida: string;
  onChange: (clave: string, repetida: string) => void;
  /** null mientras no llega la regla del servidor: no se muestra el minimo. */
  minimo: number | null;
  error?: string | null;
  disabled?: boolean;
}

export function CampoClave({ id, etiqueta, clave, repetida, onChange, minimo, error, disabled }: Props) {
  const [mostrar, setMostrar] = useState(false);
  const [generada, setGenerada] = useState(false);
  const [copiada, setCopiada] = useState(false);
  const puedeCopiar = typeof navigator !== "undefined" && Boolean(navigator.clipboard);

  const generar = () => {
    const nueva = generarClave(Math.max(10, minimo ?? 0));
    onChange(nueva, nueva);
    // Recien generada hay que poder leerla para pasarsela a la persona.
    setMostrar(true);
    setGenerada(true);
    setCopiada(false);
  };

  const copiar = async () => {
    try {
      await navigator.clipboard.writeText(clave);
      setCopiada(true);
    } catch {
      setCopiada(false);
    }
  };

  const tipo = mostrar ? "text" : "password";

  return (
    <fieldset className="space-y-2" disabled={disabled}>
      <div>
        <Label htmlFor={`${id}-nueva`}>{etiqueta}</Label>
        <div className="flex gap-2">
          <Input
            id={`${id}-nueva`}
            type={tipo}
            autoComplete="new-password"
            value={clave}
            onChange={(e) => {
              onChange(e.target.value, repetida);
              setGenerada(false);
              setCopiada(false);
            }}
            aria-invalid={Boolean(error)}
            aria-describedby={`${id}-ayuda`}
            className="font-mono"
          />
          <button
            type="button"
            onClick={() => setMostrar((v) => !v)}
            aria-pressed={mostrar}
            aria-label={mostrar ? "Ocultar la clave" : "Mostrar la clave"}
            className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-sm border border-ink-200 bg-white text-ink-600 hover:bg-paper-100"
          >
            {mostrar ? <EyeOff size={15} /> : <Eye size={15} />}
          </button>
        </div>
      </div>
      <div>
        <Label htmlFor={`${id}-repetida`}>Repite la clave</Label>
        <Input
          id={`${id}-repetida`}
          type={tipo}
          autoComplete="new-password"
          value={repetida}
          onChange={(e) => onChange(clave, e.target.value)}
          aria-invalid={Boolean(error)}
          className="font-mono"
        />
      </div>
      <div className="flex flex-wrap items-center gap-2">
        <button
          type="button"
          onClick={generar}
          className="inline-flex h-8 items-center gap-1.5 rounded-sm border border-ink-200 bg-white px-3 text-[13px] text-ink-700 hover:bg-paper-100"
        >
          <Dices size={14} /> Generar una al azar
        </button>
        {generada && puedeCopiar && (
          <button
            type="button"
            onClick={() => void copiar()}
            className="inline-flex h-8 items-center gap-1.5 rounded-sm px-2 text-[13px] text-ink-700 hover:bg-ink-100"
          >
            {copiada ? <Check size={14} /> : <Copy size={14} />} {copiada ? "Copiada" : "Copiar"}
          </button>
        )}
      </div>
      <p id={`${id}-ayuda`} className="text-[12px] text-ink-500">
        {minimo != null ? `Mínimo ${minimo} caracteres. ` : ""}
        {generada
          ? "Anótala o cópiala antes de guardar: después no se puede volver a ver."
          : "La clave guardada no se puede ver; solo se reemplaza por una nueva."}
      </p>
      {error && (
        <p role="alert" className="text-[12.5px] text-rose-700">
          {error}
        </p>
      )}
    </fieldset>
  );
}
