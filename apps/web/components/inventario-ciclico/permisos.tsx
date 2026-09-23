"use client";

// Quien usa el inventario ciclico y con que rol. El usuario (login y clave) se crea
// en Usuarios; aqui solo se le da el rol. Los admin de la plataforma ya son admin aqui.
import { useEffect, useState } from "react";
import { Loader2, Trash2, UserPlus } from "lucide-react";
import { inventarioApi, type RolFila } from "@/lib/inventario-ciclico";

export function Permisos() {
  const [filas, setFilas] = useState<RolFila[]>([]);
  const [sucursales, setSucursales] = useState<string[]>([]);
  const [email, setEmail] = useState("");
  const [rol, setRol] = useState<"bodega" | "admin">("bodega");
  const [elegidas, setElegidas] = useState<string[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = async () => {
    try {
      const [r, s] = await Promise.all([inventarioApi.roles(), inventarioApi.sucursales()]);
      setFilas(r);
      setSucursales(s);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    }
  };

  useEffect(() => {
    cargar();
  }, []);

  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      await inventarioApi.guardarRol(email.trim().toLowerCase(), rol, rol === "bodega" ? elegidas : []);
      setEmail("");
      setElegidas([]);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  };

  const quitar = async (f: RolFila) => {
    if (!confirm(`¿Quitarle a ${f.email} el acceso al inventario cíclico?`)) return;
    try {
      await inventarioApi.quitarRol(f.email);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo quitar");
    }
  };

  const editar = (f: RolFila) => {
    setEmail(f.email);
    setRol(f.rol);
    setElegidas(f.sucursales ?? []);
  };

  return (
    <div className="max-w-3xl space-y-3">
      <div className="rounded-sm border border-ink-200 bg-white p-4 shadow-card">
        <p className="text-[13px] text-ink-600">
          La persona necesita un usuario de la plataforma (se crea en <b>Usuarios</b>). Aquí solo se le da el rol.
          Bodega sin sucursales marcadas ve todas.
        </p>
        <div className="mt-3 flex flex-wrap items-end gap-2">
          <label className="text-[12.5px] text-ink-700">
            Email
            <input
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="nombre@curifor.com"
              className="mt-0.5 block h-9 w-64 rounded-sm border border-ink-200 px-2 text-[13px]"
            />
          </label>
          <label className="text-[12.5px] text-ink-700">
            Rol
            <select
              value={rol}
              onChange={(e) => setRol(e.target.value as "bodega" | "admin")}
              className="mt-0.5 block h-9 rounded-sm border border-ink-200 bg-white px-2 text-[13px]"
            >
              <option value="bodega">Bodega (cuenta)</option>
              <option value="admin">Administrador (carga y revisa)</option>
            </select>
          </label>
          <button
            type="button"
            onClick={guardar}
            disabled={guardando || !email.includes("@")}
            className="inline-flex h-9 items-center gap-1.5 rounded-sm bg-ink-900 px-3 text-[13px] font-medium text-paper hover:bg-accent-700 disabled:opacity-40"
          >
            {guardando ? <Loader2 size={14} className="animate-spin" /> : <UserPlus size={14} />}
            Guardar
          </button>
        </div>
        {rol === "bodega" && (
          <div className="mt-3 flex flex-wrap gap-x-4 gap-y-1">
            {sucursales.map((s) => (
              <label key={s} className="flex items-center gap-1.5 text-[13px] text-ink-700">
                <input
                  type="checkbox"
                  checked={elegidas.includes(s)}
                  onChange={(e) =>
                    setElegidas((prev) => (e.target.checked ? [...prev, s] : prev.filter((x) => x !== s)))
                  }
                />
                {s}
              </label>
            ))}
          </div>
        )}
      </div>

      {error && <p className="rounded-sm bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>}

      <ul className="divide-y divide-ink-100 rounded-sm border border-ink-200 bg-white shadow-card">
        {filas.length === 0 && (
          <li className="px-3 py-4 text-center text-[13px] text-ink-500">
            Nadie asignado todavía. Los administradores de la plataforma ya tienen acceso como admin.
          </li>
        )}
        {filas.map((f) => (
          <li key={f.email} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-[13px]">
            <button type="button" onClick={() => editar(f)} className="min-w-0 text-left hover:text-brand">
              <p className="font-medium text-ink-900">
                {f.nombre ?? f.email}
                {!f.tiene_usuario && (
                  <span className="ml-2 rounded bg-amber-50 px-1.5 py-0.5 text-[11px] font-semibold text-amber-800">
                    Sin usuario: créalo en Usuarios
                  </span>
                )}
              </p>
              <p className="text-[12px] text-ink-500">
                {f.nombre ? `${f.email} · ` : ""}
                {f.rol === "admin" ? "Administrador" : `Bodega · ${f.sucursales?.join(", ") ?? "todas las sucursales"}`}
              </p>
            </button>
            <button
              type="button"
              onClick={() => quitar(f)}
              className="text-ink-400 hover:text-red-600"
              aria-label={`Quitar a ${f.email}`}
            >
              <Trash2 size={15} />
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
