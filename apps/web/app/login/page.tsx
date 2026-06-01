"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ArrowRight } from "lucide-react";
import { Input } from "@/components/ui/input";
import { api } from "@/lib/api-client";
import { estaAutenticado } from "@/lib/auth";

export default function LoginPage() {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [entrando, setEntrando] = useState(false);

  useEffect(() => {
    if (estaAutenticado()) router.replace("/");
  }, [router]);

  const ingresar = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);
    setEntrando(true);
    try {
      await api.login(email.trim().toLowerCase(), password);
      router.replace("/");
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo iniciar sesión");
    } finally {
      setEntrando(false);
    }
  };

  return (
    <div className="relative min-h-[88vh] overflow-hidden">
      {/* Capa decorativa: lineas tecnicas tipo blueprint */}
      <div
        className="pointer-events-none absolute inset-0 opacity-[0.07]"
        style={{
          backgroundImage:
            "linear-gradient(to right, #1c1917 1px, transparent 1px), linear-gradient(to bottom, #1c1917 1px, transparent 1px)",
          backgroundSize: "80px 80px",
        }}
      />
      <div className="relative mx-auto grid min-h-[88vh] max-w-6xl items-center gap-12 px-4 py-12 md:grid-cols-2">
        {/* Columna izquierda: statement editorial */}
        <div className="space-y-8">
          <div className="flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/curifor-logo.png" alt="Curifor" className="h-7 w-auto" />
            <span className="h-5 w-px bg-ink-300" />
            <span className="kicker">Operaciones · Compras</span>
          </div>

          <h1 className="font-display text-[clamp(2.5rem,6vw,4.5rem)] font-medium leading-[0.95] tracking-tightest text-ink-900">
            Sugerido
            <br />
            <span className="italic text-accent-700">de compras.</span>
          </h1>

          <p className="max-w-md text-[15px] leading-relaxed text-ink-600">
            Plataforma operacional para alinear la reposicion de inventario entre
            sucursales. Sugerencias del BI + ajustes del equipo en un solo lugar.
          </p>

          <div className="flex gap-6 border-t border-ink-200 pt-6 text-[12px]">
            <Stat label="Productos" value="409K" />
            <Stat label="Sucursales" value="29" />
            <Stat label="Snapshot" value="diario" />
          </div>
        </div>

        {/* Columna derecha: formulario */}
        <div className="md:pl-8">
          <div className="relative rounded-sm border border-ink-200 bg-white p-8 shadow-card">
            {/* Tag esquina superior */}
            <div className="absolute -top-3 left-6 bg-paper px-2">
              <span className="kicker">Acceso</span>
            </div>

            <h2 className="mb-1 font-display text-2xl font-medium tracking-tight text-ink-900">
              Iniciar sesión
            </h2>
            <p className="mb-6 text-[13px] text-ink-500">
              Usa la cuenta del equipo de compras.
            </p>

            <form onSubmit={ingresar} className="space-y-4">
              <FieldGroup id="email" label="Correo">
                <Input
                  id="email"
                  type="email"
                  autoComplete="username"
                  placeholder="tu.correo@curifor.com"
                  value={email}
                  onChange={(e) => setEmail(e.target.value)}
                  required
                  className="rounded-sm border-ink-200 bg-paper-50 focus-visible:ring-accent-700"
                />
              </FieldGroup>

              <FieldGroup id="pass" label="Contraseña">
                <Input
                  id="pass"
                  type="password"
                  autoComplete="current-password"
                  placeholder="••••••"
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  required
                  className="rounded-sm border-ink-200 bg-paper-50 focus-visible:ring-accent-700"
                />
              </FieldGroup>

              {error && (
                <p className="rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-[13px] text-red-700">
                  {error}
                </p>
              )}

              <button
                type="submit"
                disabled={entrando}
                className="group mt-2 flex w-full items-center justify-between rounded-sm bg-ink-900 px-4 py-3 text-[13px] font-semibold uppercase tracking-wider text-paper transition-all hover:bg-accent-700 disabled:opacity-50"
              >
                <span>{entrando ? "Entrando…" : "Iniciar sesión"}</span>
                <ArrowRight
                  size={15}
                  className="transition-transform group-hover:translate-x-1"
                />
              </button>
            </form>
          </div>

          <p className="mt-4 text-center text-[11px] text-ink-400">
            Curifor S.A. — uso interno
          </p>
        </div>
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="kicker">{label}</p>
      <p className="font-display text-xl font-medium tabular-nums text-ink-900">
        {value}
      </p>
    </div>
  );
}

function FieldGroup({
  id,
  label,
  children,
}: {
  id: string;
  label: string;
  children: React.ReactNode;
}) {
  return (
    <div>
      <label htmlFor={id} className="kicker mb-1.5 block">
        {label}
      </label>
      {children}
    </div>
  );
}
