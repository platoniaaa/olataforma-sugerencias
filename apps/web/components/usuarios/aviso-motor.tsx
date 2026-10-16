"use client";

// El motor publica el sugerido entrando con una cuenta admin de la plataforma
// (EMAILS_MOTOR en el servidor; la clave esta en el .env del PC donde corre).
// Cambiarle la clave, quitarle el admin, desactivarla o marcarla como vendedor
// lo deja sin publicar (o publicando a medias), y nadie se entera hasta que el
// equipo ve datos viejos. Por eso se pide marcar que se entiende antes de dejar
// guardar (`tocaAlMotor` en lib/usuarios.ts). Vendedor ademas no se ofrece en la
// pantalla y el servidor lo rechaza.
import { AlertTriangle } from "lucide-react";
import { AVISO_MOTOR } from "@/lib/usuarios";

interface Props {
  id: string;
  entendido: boolean;
  onChange: (v: boolean) => void;
  disabled?: boolean;
}

export function AvisoMotor({ id, entendido, onChange, disabled }: Props) {
  return (
    <div role="alert" className="space-y-2 rounded-sm border border-amber-300 bg-amber-50 px-3 py-2.5 text-[13px] text-amber-900">
      <p className="flex items-start gap-2 font-medium">
        <AlertTriangle size={16} className="mt-0.5 shrink-0" aria-hidden="true" />
        <span>Esta cuenta la usa el motor. {AVISO_MOTOR}</span>
      </p>
      <label htmlFor={id} className="flex cursor-pointer items-start gap-2 pl-6">
        <input
          id={id}
          type="checkbox"
          className="mt-0.5"
          checked={entendido}
          disabled={disabled}
          onChange={(e) => onChange(e.target.checked)}
        />
        <span>Entiendo y quiero hacer el cambio igual.</span>
      </label>
    </div>
  );
}
