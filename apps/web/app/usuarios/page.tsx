"use client";

// Usuarios: quien entra a la plataforma y con que permisos. Solo admin.
//
// Existe desde el 16-10-2026. Antes los usuarios se manejaban solo por la API
// (POST /api/admin/usuarios) y eso lo sabia hacer una persona; esta pantalla es
// para que cualquier admin pueda crear, editar, desactivar y cambiar claves
// sola. El gate real es el 403 del servidor (el router entero exige admin); la
// redireccion de abajo es para quien llega escribiendo la URL.
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  AlertCircle, Bot, CheckCircle2, KeyRound, Loader2, Pencil, Search, ShieldCheck, UserPlus, Users,
} from "lucide-react";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DialogoClave } from "@/components/usuarios/dialogo-clave";
import { FormularioUsuario } from "@/components/usuarios/formulario-usuario";
import { getEmail, getEsAdmin } from "@/lib/auth";
import type { Sucursal } from "@/lib/types";
import { NOTA_PERMISOS_ESPECIALES, type UsuarioAdmin, etiquetaPermiso, usuariosApi } from "@/lib/usuarios";

export default function UsuariosPage() {
  const router = useRouter();
  const [permitido, setPermitido] = useState(false);
  const [emailPropio, setEmailPropio] = useState<string | null>(null);
  const [usuarios, setUsuarios] = useState<UsuarioAdmin[] | null>(null);
  // null = todavia no llega (o fallo): el formulario no marca nada como "ya no esta".
  const [sucursales, setSucursales] = useState<Sucursal[] | null>(null);
  const [errorSucursales, setErrorSucursales] = useState<string | null>(null);
  const [minimoClave, setMinimoClave] = useState<number | null>(null);
  const [horasSesion, setHorasSesion] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [busqueda, setBusqueda] = useState("");
  // null = cerrado; { usuario: null } = crear; { usuario } = editar.
  const [formulario, setFormulario] = useState<{ usuario: UsuarioAdmin | null } | null>(null);
  const [cambiarClave, setCambiarClave] = useState<UsuarioAdmin | null>(null);
  // El boton que abrio el dialogo: al cerrarlo el foco vuelve ahi, y quien usa
  // teclado no tiene que recorrer la lista entera de nuevo.
  const abridor = useRef<HTMLElement | null>(null);

  // Si alguien sin permisos cae aca por URL, lo mandamos al inicio (como Cargar datos).
  useEffect(() => {
    if (!getEsAdmin()) {
      router.replace("/");
      return;
    }
    setEmailPropio(getEmail());
    setPermitido(true);
  }, [router]);

  const cargar = useCallback(async () => {
    try {
      setUsuarios(await usuariosApi.listar());
      setError(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo cargar la lista de usuarios.");
    }
  }, []);

  useEffect(() => {
    if (!permitido) return;
    void cargar();
    usuariosApi.sucursales()
      .then((s) => { setSucursales(s); setErrorSucursales(null); })
      .catch(() => setErrorSucursales("No se pudo cargar la lista de sucursales. Recarga la página para reintentar."));
    // Sin la regla igual se puede guardar: el servidor valida el largo y su
    // mensaje se muestra tal cual.
    usuariosApi.reglas()
      .then((r) => { setMinimoClave(r.largo_minimo_clave); setHorasSesion(r.horas_sesion ?? null); })
      .catch(() => { setMinimoClave(null); setHorasSesion(null); });
  }, [permitido, cargar]);

  useEffect(() => {
    if (formulario !== null || cambiarClave !== null || !abridor.current) return;
    abridor.current.focus();
    abridor.current = null;
  }, [formulario, cambiarClave]);

  const abrirDesde = (e: React.MouseEvent<HTMLElement>, abrir: () => void) => {
    abridor.current = e.currentTarget;
    setAviso(null);
    abrir();
  };

  const nombreSucursal = useCallback(
    (id: string) => sucursales?.find((s) => s.sucursal_id === id)?.nombre ?? id,
    [sucursales],
  );

  const visibles = useMemo(() => {
    const q = busqueda.trim().toLowerCase();
    return (usuarios ?? [])
      .filter((u) => !q || u.email.toLowerCase().includes(q) || (u.nombre ?? "").toLowerCase().includes(q))
      // Los activos primero; dentro de cada grupo queda el orden por correo del servidor.
      .sort((a, b) => Number(b.activo) - Number(a.activo));
  }, [usuarios, busqueda]);

  const correos = useMemo(() => (usuarios ?? []).map((u) => u.email), [usuarios]);
  const activos = (usuarios ?? []).filter((u) => u.activo).length;
  const desactivados = (usuarios ?? []).length - activos;

  const alGuardar = (_u: UsuarioAdmin, mensaje: string) => {
    setFormulario(null);
    setCambiarClave(null);
    setAviso(mensaje);
    void cargar();
  };

  if (!permitido) return null;

  return (
    <div className="mx-auto max-w-5xl space-y-5">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-ink-900">
            <Users size={20} className="text-brand" aria-hidden="true" /> Usuarios
          </h1>
          <p className="max-w-2xl text-[13px] text-ink-500">
            Quién entra a la plataforma y con qué permisos. Nadie se borra: quien deja de trabajar
            se desactiva, y lo que hizo sigue en Auditoría.
          </p>
        </div>
        <Button onClick={(e) => abrirDesde(e, () => setFormulario({ usuario: null }))}>
          <UserPlus size={15} /> Crear usuario
        </Button>
      </header>

      {aviso && (
        <p role="status" className="flex items-start gap-2 rounded-sm border border-emerald-200 bg-emerald-50 px-3 py-2 text-[13px] text-emerald-800">
          <CheckCircle2 size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> {aviso}
        </p>
      )}

      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-3 rounded-sm border border-rose-200 bg-rose-50 px-3 py-2 text-[13px] text-rose-800">
          <span className="flex items-start gap-2">
            <AlertCircle size={16} className="mt-0.5 shrink-0" aria-hidden="true" /> {error}
          </span>
          <Button size="sm" variant="outline" onClick={() => void cargar()}>Reintentar</Button>
        </div>
      )}

      {usuarios === null && !error && (
        <p className="flex items-center gap-2 text-[13px] text-ink-500">
          <Loader2 size={15} className="animate-spin" aria-hidden="true" /> Cargando usuarios…
        </p>
      )}

      {usuarios && (
        <>
          <div className="flex flex-wrap items-center gap-3">
            <div className="relative w-full sm:w-72">
              <Search size={15} className="pointer-events-none absolute left-2.5 top-2.5 text-ink-400" aria-hidden="true" />
              <Input
                type="search"
                aria-label="Buscar por correo o nombre"
                placeholder="Buscar por correo o nombre"
                value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)}
                className="pl-8"
              />
            </div>
            <p className="text-[12.5px] text-ink-500">
              {activos} {activos === 1 ? "activo" : "activos"} · {desactivados}{" "}
              {desactivados === 1 ? "desactivado" : "desactivados"}
            </p>
          </div>

          <ul aria-label="Usuarios" className="divide-y divide-ink-100 rounded-sm border border-ink-200 bg-white shadow-card">
            {visibles.length === 0 && (
              <li className="px-4 py-6 text-center text-[13px] text-ink-500">
                {usuarios.length === 0 ? "Todavía no hay usuarios." : `Nadie calza con “${busqueda.trim()}”.`}
              </li>
            )}
            {visibles.map((u) => {
              const propio = emailPropio != null && u.email.toLowerCase() === emailPropio.toLowerCase();
              return (
                <li
                  key={u.email}
                  aria-label={u.nombre || u.email}
                  className={`flex flex-wrap items-start justify-between gap-3 px-4 py-3 ${u.activo ? "" : "bg-paper-100/70"}`}
                >
                  {/* basis-60: en un telefono los botones bajan a otra linea en vez
                      de dejarle al nombre dos letras de ancho. */}
                  <div className="min-w-0 flex-1 basis-60 space-y-0.5">
                    <p className="flex flex-wrap items-center gap-x-2 gap-y-1">
                      <span className={`break-words text-[13.5px] font-medium ${u.activo ? "text-ink-900" : "text-ink-500"}`}>
                        {u.nombre || u.email}
                      </span>
                      {propio && <span className="text-[12px] text-ink-500">(tú)</span>}
                      {u.es_admin && (
                        <Badge className="gap-1 border border-brand-200 bg-brand-50 text-brand-700">
                          <ShieldCheck size={11} aria-hidden="true" /> Admin
                        </Badge>
                      )}
                      {u.solo_lectura && (
                        <Badge className="border border-ink-200 bg-ink-100 text-ink-700">Solo lectura</Badge>
                      )}
                      {u.es_vendedor && (
                        <Badge className="border border-accent-100 bg-accent-50 text-accent-800">Vendedor</Badge>
                      )}
                      {!u.activo && (
                        <Badge className="border border-rose-200 bg-rose-50 text-rose-700">Desactivado</Badge>
                      )}
                      {u.es_cuenta_motor && (
                        <Badge
                          className="gap-1 border border-amber-300 bg-amber-50 text-amber-800"
                          title="El motor entra con esta cuenta para publicar el sugerido."
                        >
                          <Bot size={11} aria-hidden="true" /> La usa el motor
                        </Badge>
                      )}
                    </p>
                    {u.nombre && <p className="break-words text-[12.5px] text-ink-500">{u.email}</p>}
                    {u.sucursales.length > 0 && (
                      <p className="text-[12.5px] text-ink-600">
                        {u.es_vendedor ? "Pide por" : "Solo ve"}: {u.sucursales.map(nombreSucursal).join(", ")}
                      </p>
                    )}
                    {!u.es_admin && u.permisos_especiales.length > 0 && (
                      <p className="text-[12.5px] text-ink-600">
                        Permisos especiales: {u.permisos_especiales.map(etiquetaPermiso).join(" · ")}
                      </p>
                    )}
                  </div>
                  <div className="flex shrink-0 flex-wrap gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Editar a ${u.email}`}
                      onClick={(e) => abrirDesde(e, () => setFormulario({ usuario: u }))}
                    >
                      <Pencil size={14} aria-hidden="true" /> Editar
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      aria-label={`Cambiar la clave de ${u.email}`}
                      onClick={(e) => abrirDesde(e, () => setCambiarClave(u))}
                    >
                      <KeyRound size={14} aria-hidden="true" /> Cambiar clave
                    </Button>
                  </div>
                </li>
              );
            })}
          </ul>

          <p className="text-[12px] text-ink-500">
            Los permisos especiales (editar precios, configurar el modelo, ver accesos y pedir
            “Actualizar ahora”) van por correo. {NOTA_PERMISOS_ESPECIALES} Los admin ya los tienen todos.
          </p>
        </>
      )}

      <FormularioUsuario
        open={formulario !== null}
        usuario={formulario?.usuario ?? null}
        sucursales={sucursales}
        errorSucursales={errorSucursales}
        correosExistentes={correos}
        minimoClave={minimoClave}
        emailPropio={emailPropio}
        onClose={() => setFormulario(null)}
        onGuardado={alGuardar}
      />
      <DialogoClave
        open={cambiarClave !== null}
        usuario={cambiarClave}
        minimoClave={minimoClave}
        horasSesion={horasSesion}
        onClose={() => setCambiarClave(null)}
        onGuardado={alGuardar}
      />
    </div>
  );
}
