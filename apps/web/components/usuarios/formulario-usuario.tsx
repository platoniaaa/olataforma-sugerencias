"use client";

// Crear o editar un usuario. Nunca se borra: quien deja de trabajar se desactiva,
// y lo que hizo (sugerencias, requerimientos, auditoria) sigue con su nombre.
//
// Al editar se manda solo lo que cambio: el servidor deja como estaba todo lo que
// no llega, y asi cambiar el nombre no puede tocar los roles.
import { useEffect, useMemo, useState } from "react";
import { AlertCircle, Loader2, Save, UserPlus } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { Input, Label } from "@/components/ui/input";
import { AvisoMotor } from "@/components/usuarios/aviso-motor";
import { CampoClave } from "@/components/usuarios/campo-clave";
import type { Sucursal } from "@/lib/types";
import {
  NOTA_PERMISOS_ESPECIALES,
  type DatosUsuario,
  type UsuarioAdmin,
  type UsuarioGuardar,
  cambiosUsuario,
  datosDe,
  errorClave,
  etiquetaPermiso,
  hayCambios,
  tocaAlMotor,
  usuariosApi,
} from "@/lib/usuarios";

const VACIO: DatosUsuario = {
  nombre: "", es_admin: false, solo_lectura: false, es_vendedor: false, activo: true, sucursales: [],
};

const ROLES: { campo: "es_admin" | "solo_lectura" | "es_vendedor"; etiqueta: string; ayuda: string }[] = [
  { campo: "es_admin", etiqueta: "Admin", ayuda: "Administra la plataforma: usuarios, carga de datos y todo lo demás." },
  { campo: "solo_lectura", etiqueta: "Solo lectura", ayuda: "Ve todo, pero no puede crear ni modificar sugerencias ni requerimientos." },
  { campo: "es_vendedor", etiqueta: "Vendedor de sucursal", ayuda: "Solo arma y sigue los requerimientos de sus sucursales." },
];

interface Props {
  open: boolean;
  /** null = usuario nuevo. */
  usuario: UsuarioAdmin | null;
  sucursales: Sucursal[];
  errorSucursales: string | null;
  minimoClave: number | null;
  /** Correo de quien esta usando la pantalla: no puede quitarse el admin ni desactivarse. */
  emailPropio: string | null;
  onClose: () => void;
  onGuardado: (u: UsuarioAdmin, mensaje: string) => void;
}

export function FormularioUsuario({
  open, usuario, sucursales, errorSucursales, minimoClave, emailPropio, onClose, onGuardado,
}: Props) {
  const nuevo = usuario === null;
  const [email, setEmail] = useState("");
  const [datos, setDatos] = useState<DatosUsuario>(VACIO);
  const [clave, setClave] = useState("");
  const [repetida, setRepetida] = useState("");
  const [entiendeMotor, setEntiendeMotor] = useState(false);
  const [intentado, setIntentado] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Cada vez que se abre parte de lo guardado, no de lo que quedo a medias.
  useEffect(() => {
    if (!open) return;
    setEmail(usuario?.email ?? "");
    setDatos(usuario ? datosDe(usuario) : VACIO);
    setClave("");
    setRepetida("");
    setEntiendeMotor(false);
    setIntentado(false);
    setError(null);
  }, [open, usuario]);

  const propio = !nuevo && emailPropio != null && usuario.email.toLowerCase() === emailPropio.toLowerCase();
  const cambios: UsuarioGuardar = useMemo(
    () => (usuario ? cambiosUsuario(usuario, datos) : { email }),
    [usuario, datos, email],
  );
  const avisarMotor = tocaAlMotor(usuario, cambios);

  // Las sucursales que ya tiene y no estan en la lista (cerradas u ocultas) se
  // muestran igual: si no, guardar se las quitaria sin que nadie lo decida.
  const opciones = useMemo(() => {
    const ids = new Set(sucursales.map((s) => s.sucursal_id));
    const extra = datos.sucursales.filter((s) => !ids.has(s)).map((s) => ({ id: s, nombre: s, fuera: true }));
    return [...sucursales.map((s) => ({ id: s.sucursal_id, nombre: s.nombre ?? s.sucursal_id, fuera: false })), ...extra];
  }, [sucursales, datos.sucursales]);

  const errorCorreo = nuevo && !email.trim().includes("@") ? "Escribe un correo válido." : null;
  const errorDeClave = nuevo ? errorClave(clave, repetida, minimoClave) : null;
  const errorSucursal = datos.es_vendedor && datos.sucursales.length === 0
    ? "Un vendedor necesita al menos una sucursal: es por donde pide."
    : null;

  const set = <K extends keyof DatosUsuario>(k: K, v: DatosUsuario[K]) => {
    setDatos((d) => ({ ...d, [k]: v }));
    setError(null);
  };

  const alternarSucursal = (id: string, marcada: boolean) =>
    set("sucursales", marcada ? [...datos.sucursales, id] : datos.sucursales.filter((s) => s !== id));

  async function guardar() {
    setIntentado(true);
    if (errorCorreo || errorDeClave || errorSucursal) return;
    if (!nuevo && !hayCambios(cambios)) {
      setError("No hay cambios para guardar.");
      return;
    }
    if (avisarMotor && !entiendeMotor) return;

    const payload: UsuarioGuardar = nuevo
      ? {
          email: email.trim().toLowerCase(),
          password: clave,
          nombre: datos.nombre.trim(),
          es_admin: datos.es_admin,
          solo_lectura: datos.solo_lectura,
          es_vendedor: datos.es_vendedor,
          sucursales: datos.sucursales,
        }
      : cambios;

    setGuardando(true);
    setError(null);
    try {
      const u = await usuariosApi.guardar(payload);
      const mensaje = nuevo
        ? `Usuario creado: ${u.email}. Pásale la clave por un medio que no sea el correo.`
        : `Cambios guardados para ${u.email}.` +
          (avisarMotor ? " El motor no va a poder publicar hasta que se actualice su cuenta en el PC donde corre." : "");
      onGuardado(u, mensaje);
    } catch (e) {
      // El mensaje del servidor tal cual: ya viene en español y dice que corregir.
      setError(e instanceof Error ? e.message : "No se pudo guardar.");
    } finally {
      setGuardando(false);
    }
  }

  const campo = (texto: string | null) =>
    intentado && texto ? <p role="alert" className="mt-1 text-[12.5px] text-rose-700">{texto}</p> : null;

  return (
    <Dialog
      open={open}
      onClose={() => { if (!guardando) onClose(); }}
      title={nuevo ? "Crear usuario" : "Editar usuario"}
      description={nuevo
        ? "La persona entra con este correo y la clave que le pongas."
        : "Los usuarios no se borran: se desactivan, y lo que hicieron sigue en Auditoría."}
      className="max-w-xl"
    >
      <form
        className="space-y-5 text-[13px] text-ink-700"
        onSubmit={(e) => { e.preventDefault(); void guardar(); }}
        noValidate
      >
        <fieldset className="space-y-3" disabled={guardando}>
          {nuevo ? (
            <div>
              <Label htmlFor="usuario-correo">Correo</Label>
              <Input
                id="usuario-correo"
                type="email"
                autoComplete="off"
                inputMode="email"
                value={email}
                onChange={(e) => { setEmail(e.target.value); setError(null); }}
                aria-invalid={intentado && Boolean(errorCorreo)}
                placeholder="nombre@ejemplo.cl"
              />
              {campo(errorCorreo)}
            </div>
          ) : (
            <div>
              <p className="mb-1 text-[12.5px] font-medium text-ink-700">Correo</p>
              <p className="text-[13.5px] text-ink-900">{usuario.email}</p>
            </div>
          )}
          <div>
            <Label htmlFor="usuario-nombre">Nombre</Label>
            <Input
              id="usuario-nombre"
              autoComplete="off"
              value={datos.nombre}
              onChange={(e) => set("nombre", e.target.value)}
            />
          </div>
        </fieldset>

        {nuevo && (
          <CampoClave
            id="usuario-clave"
            etiqueta="Clave inicial"
            clave={clave}
            repetida={repetida}
            onChange={(c, r) => { setClave(c); setRepetida(r); setError(null); }}
            minimo={minimoClave}
            error={intentado ? errorDeClave : null}
            disabled={guardando}
          />
        )}

        <fieldset className="space-y-2" disabled={guardando}>
          <legend className="mb-1 text-[12.5px] font-medium text-ink-700">Roles</legend>
          {ROLES.map((r) => {
            const bloqueado = r.campo === "es_admin" && propio && usuario?.es_admin;
            return (
              <label key={r.campo} className="flex cursor-pointer items-start gap-2">
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={datos[r.campo]}
                  disabled={Boolean(bloqueado)}
                  onChange={(e) => set(r.campo, e.target.checked)}
                />
                <span>
                  <span className="font-medium text-ink-900">{r.etiqueta}</span>
                  <span className="block text-[12px] text-ink-500">
                    {bloqueado ? "No puedes quitarte el admin a ti mismo." : r.ayuda}
                  </span>
                </span>
              </label>
            );
          })}
        </fieldset>

        <fieldset className="space-y-2" disabled={guardando}>
          <legend className="mb-1 text-[12.5px] font-medium text-ink-700">Sucursales</legend>
          <p className="text-[12px] text-ink-500">
            {datos.es_vendedor
              ? "Por las que puede pedir. Marca al menos una."
              : "Si marcas alguna, solo ve esas. Sin marcar ve todas."}
          </p>
          {errorSucursales && (
            <p role="alert" className="text-[12.5px] text-rose-700">{errorSucursales}</p>
          )}
          <div className="grid grid-cols-1 gap-x-4 gap-y-1 sm:grid-cols-2">
            {opciones.map((s) => (
              <label key={s.id} className="flex cursor-pointer items-center gap-2">
                <input
                  type="checkbox"
                  checked={datos.sucursales.includes(s.id)}
                  onChange={(e) => alternarSucursal(s.id, e.target.checked)}
                />
                <span>
                  {s.nombre}
                  {s.fuera && <span className="text-[12px] text-ink-500"> (ya no está en la lista)</span>}
                </span>
              </label>
            ))}
          </div>
          {campo(errorSucursal)}
        </fieldset>

        {!nuevo && (
          <fieldset className="space-y-1" disabled={guardando}>
            <legend className="mb-1 text-[12.5px] font-medium text-ink-700">Estado</legend>
            <label className="flex cursor-pointer items-start gap-2">
              <input
                type="checkbox"
                className="mt-0.5"
                checked={datos.activo}
                disabled={propio}
                onChange={(e) => set("activo", e.target.checked)}
              />
              <span>
                <span className="font-medium text-ink-900">Cuenta activa</span>
                <span className="block text-[12px] text-ink-500">
                  {propio
                    ? "No puedes desactivarte a ti mismo."
                    : "Desactivada no puede entrar. No se borra nada de lo que hizo."}
                </span>
              </span>
            </label>
          </fieldset>
        )}

        {!nuevo && (
          <div className="rounded-sm border border-ink-200 bg-paper-100 px-3 py-2.5">
            <p className="text-[12.5px] font-medium text-ink-700">Permisos especiales</p>
            {usuario.es_admin ? (
              <p className="text-[12.5px] text-ink-600">Como admin ya tiene todos.</p>
            ) : usuario.permisos_especiales.length ? (
              <ul className="mt-1 list-disc pl-5 text-[12.5px] text-ink-700">
                {usuario.permisos_especiales.map((p) => <li key={p}>{etiquetaPermiso(p)}</li>)}
              </ul>
            ) : (
              <p className="text-[12.5px] text-ink-600">Ninguno.</p>
            )}
            <p className="mt-1 text-[12px] text-ink-500">
              {NOTA_PERMISOS_ESPECIALES} No se cambian desde esta pantalla.
            </p>
          </div>
        )}

        {avisarMotor && (
          <AvisoMotor
            id="usuario-entiende-motor"
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
          <Button type="submit" disabled={guardando || (avisarMotor && !entiendeMotor)}>
            {guardando ? <Loader2 size={15} className="animate-spin" /> : nuevo ? <UserPlus size={15} /> : <Save size={15} />}
            {guardando ? "Guardando…" : nuevo ? "Crear usuario" : "Guardar cambios"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}
