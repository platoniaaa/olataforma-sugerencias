/**
 * El item "Usuarios" del menu lo ve solo un admin: nadie mas del equipo ve nada
 * nuevo. El gate real es el 403 del servidor; esto cuida que el menu no lo
 * ofrezca a quien no puede usarlo.
 */
import "@testing-library/jest-dom/vitest";
import type { ReactNode } from "react";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/components/sidebar";

const mocks = vi.hoisted(() => ({ esAdmin: vi.fn() }));

vi.mock("next/navigation", () => ({ usePathname: () => "/" }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...resto }: { href: string; children: ReactNode }) => (
    <a href={href} {...resto}>{children}</a>
  ),
}));
vi.mock("@/lib/auth", () => ({
  getEmail: () => "persona@ejemplo.cl",
  getNombre: () => null,
  getEsAdmin: mocks.esAdmin,
  getEsVendedor: () => false,
  getPuedeCalibrar: () => false,
  getSoloLectura: () => false,
  logout: vi.fn(),
}));
vi.mock("@/lib/inventario-ciclico", () => ({
  inventarioApi: { yo: () => Promise.resolve({ rol: null, sucursales: null }) },
  rolGuardado: () => null,
}));

beforeEach(() => {
  mocks.esAdmin.mockReset();
});

describe("menu", () => {
  it("un admin ve Usuarios", () => {
    mocks.esAdmin.mockReturnValue(true);
    render(<Sidebar open onClose={() => undefined} />);
    expect(screen.getByRole("link", { name: "Usuarios" })).toHaveAttribute("href", "/usuarios");
  });

  it("quien no es admin no lo ve", () => {
    mocks.esAdmin.mockReturnValue(false);
    render(<Sidebar open onClose={() => undefined} />);
    expect(screen.queryByRole("link", { name: "Usuarios" })).not.toBeInTheDocument();
    // Y sigue viendo lo de siempre.
    expect(screen.getByRole("link", { name: "Sugerido" })).toBeInTheDocument();
  });
});
