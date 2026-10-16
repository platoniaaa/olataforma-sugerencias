"use client";

// Cambiar la clave de alguien. La que tenia no se puede ver ni recuperar (el
// servidor guarda solo un hash): se reemplaza por una nueva, escrita dos veces
// o generada al azar. Solo viaja la clave; el resto del usuario queda igual.
//
// Cambiar la clave no corta una sesion que ya esta abierta (el token sigue
// valiendo hasta que vence): la pantalla lo dice, y desactivar si la corta.
import { useEffect, useState } from "react";
import { AlertCircle, KeyRound, Loader2 } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { AvisoMotor } from "@/components/usuarios/aviso-motor";
import { CampoClave } from "@/components/usuarios/campo-clave";
import { type UsuarioAdmin, errorClave, usuariosApi } from "@/lib/usuarios";

interface Props {
  open: boolean;
  usuario: UsuarioAdmin | null;
  minimoClave: number | null;
  /** Cuanto dura una sesion (del servidor). null = no llego: se dice sin numero. */
  horasSesion: number | null;
  onClose: () => void;
  onGuardado: (u: UsuarioAdmin, mensaje: string) => void;
}

export function DialogoClave({ open, usuario, minimoClave, horasSesion, onClose, onGuardado }: Props) {
  const [clave, setClave] = useState("");
  const [repetida, setRepetida] = useState("");
  const [entiendeMotor, setEntiendeMotor] = useState(false);
  const [intentado, setIntentado] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Se limpia al abrir y al cerrar: la clave escrita no queda en memoria mientras
  // la pestaña siga en /usuarios.
  useEffect(() => {
    setClave("");
    setRepetida("");
    setEntiendeMotor(false);
    setIntentado(false);
    setError(null);
  }, [open, usuario]);

  if (!usuario) return null;
  const motor = usuario.es_cuenta_motor;
  const problema = errorClave(clave, repetida, minimoClave);

  async function guardar() {
    if (!usuario) return;
    setIntentado(true);
    if (problema || (motor && !entiendeMotor)) return;
    setGuardando(true);
    setError(null);
    try {
      const u = await usuariosApi.guardar({ email: usuario.email, password: clave });
      setClave("");
      setRepetida("");
      onGuardado(
        u,
        `Clave cambiada para ${u.email}. Pásasela por un medio que no sea el correo.` +
          (motor ? " El motor no va a publicar hasta que se actualice esta clave en el PC donde corre." : ""),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cambiar la clave.");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <Dialog
      open={open}
      onClose={() => { if (!guardando) onClose(); }}
      title="Cambiar clave"
      description={`Clave nueva para ${usuario.nombre ? `${usuario.nombre} (${usuario.email})` : usuario.email}.`}
      className="max-w-md"
    >
      <form
        className="space-y-4 text-[13px] text-ink-700"
        onSubmit={(e) => { e.preventDefault(); void guardar(); }}
        noValidate
      >
        <p className="text-[12.5px] text-ink-600">
          La anterior deja de servir para entrar. Si la persona tiene la sesión abierta, sigue
          dentro hasta que se le venza ({horasSesion != null ? `${horasSesion} horas como máximo` : "unas horas"}).
          Para sacarla antes, desactiva la cuenta.
        </p>
        <CampoClave
          id="clave-nueva"
          etiqueta="Clave nueva"
          clave={clave}
          repetida={repetida}
          onChange={(c, r) => { setClave(c); setRepetida(r); setError(null); }}
          minimo={minimoClave}
          error={intentado ? problema : null}
          disabled={guardando}
          autoFocus
        />

        {motor && (
          <AvisoMotor
            id="clave-entiende-motor"
            entendido={entiendeMotor}
            onChange={setEntiendeMotor}
            disabled={guardando}
          />
        )}

        {error && (
          <p role="alert" className="flex items-start gap-2 rounded-sm border border-rose-200 bg-rose-50 px-3 py-2 text-rose-800">
            <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> {error}
          </p>
        )}

        <div className="flex flex-wrap items-center justify-end gap-2 border-t border-ink-100 pt-4">
          <Button type="button" variant="outline" onClick={onClose} disabled={guardando}>
            Cancelar
          </Button>
          <Button type="submit" disabled={guardando || (motor && !entiendeMotor)}>
            {guardando ? <Loader2 size={15} className="animate-spin" /> : <KeyRound size={15} />}
            {guardando ? "Guardando…" : "Cambiar clave"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
