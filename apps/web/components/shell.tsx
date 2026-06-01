"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { LogOut } from "lucide-react";
import { estaAutenticado, getEmail, getEsAdmin, getNombre, logout } from "@/lib/auth";
import { CampanitaNotificaciones } from "@/components/campanita-notificaciones";

type NavItem = { href: string; label: string; soloAdmin?: boolean };
const NAV: NavItem[] = [
  { href: "/", label: "Dashboard" },
  { href: "/compras", label: "Compras" },
  { href: "/catalogo", label: "Catálogo" },
  { href: "/sugerencias-manuales", label: "Sugerencias" },
  { href: "/auditoria", label: "Auditoría" },
  { href: "/exportar", label: "Exportar" },
  { href: "/cargar", label: "Cargar datos", soloAdmin: true },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const esLogin = pathname === "/login";
  const [listo, setListo] = useState(false);

  useEffect(() => {
    if (!esLogin && !estaAutenticado()) {
      router.replace("/login");
      return;
    }
    setListo(true);
  }, [esLogin, pathname, router]);

  // La pantalla de login se muestra sin header.
  if (esLogin) {
    return <main className="relative z-10 mx-auto max-w-[1600px] px-4 py-5">{children}</main>;
  }

  // Evita mostrar contenido protegido antes de verificar la sesion.
  if (!listo) {
    return (
      <div className="flex min-h-screen items-center justify-center text-sm text-ink-400">
        Cargando…
      </div>
    );
  }

  const email = getEmail();
  const nombre = getNombre();
  const esAdmin = getEsAdmin();
  const navVisible = NAV.filter((n) => !n.soloAdmin || esAdmin);

  return (
    <>
      <header className="sticky top-0 z-30 border-b border-ink-200 bg-paper/85 backdrop-blur">
        <div className="mx-auto flex h-16 max-w-[1600px] items-center gap-4 px-4">
          <Link href="/" className="group flex items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src="/curifor-logo.png" alt="Curifor" className="h-7 w-auto" />
            <span className="hidden h-5 w-px bg-ink-300 sm:block" />
            <span className="hidden flex-col sm:flex">
              <span className="font-display text-[17px] font-medium leading-none tracking-tight text-ink-900">
                Sugerido
              </span>
              <span className="mt-0.5 text-[10px] uppercase tracking-[0.14em] text-ink-500">
                de compras
              </span>
            </span>
          </Link>

          <nav className="ml-auto flex items-center text-[13px]">
            {navVisible.map((n) => {
              const activo = pathname === n.href;
              return (
                <Link
                  key={n.href}
                  href={n.href}
                  className={`group relative px-3 py-2 transition-colors ${
                    activo ? "text-ink-900 font-medium" : "text-ink-600 hover:text-ink-900"
                  }`}
                >
                  {n.label}
                  <span
                    className={`absolute left-3 right-3 -bottom-px h-px transition-all ${
                      activo
                        ? "bg-accent-700"
                        : "bg-transparent group-hover:bg-ink-300"
                    }`}
                  />
                </Link>
              );
            })}

            <div className="ml-3 flex items-center gap-2 border-l border-ink-200 pl-3">
              <CampanitaNotificaciones />
              <span className="hidden text-[13px] text-ink-600 md:inline">
                {nombre ?? email}
              </span>
              <button
                onClick={logout}
                title="Cerrar sesión"
                className="flex items-center gap-1 rounded-sm px-2 py-1.5 text-[13px] text-ink-500 transition-colors hover:bg-ink-100 hover:text-ink-900"
              >
                <LogOut size={15} /> Salir
              </button>
            </div>
          </nav>
        </div>
      </header>
      <main className="relative z-10 mx-auto max-w-[1600px] px-4 py-6">{children}</main>
    </>
  );
}
