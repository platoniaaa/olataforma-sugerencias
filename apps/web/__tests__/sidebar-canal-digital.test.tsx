/**
 * "Canal Digital" es una version provisoria: el menu se lo ofrece solo a un admin hasta que se decida
 * mostrarlo al equipo. El gate real de los datos es el servidor; esto cuida que nadie vea algo nuevo
 * sin que se haya decidido.
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

beforeEach(() => mocks.esAdmin.mockReset());

describe("menu de Canal Digital", () => {
  it("un admin lo ve", () => {
    mocks.esAdmin.mockReturnValue(true);
    render(<Sidebar open onClose={() => undefined} />);
    expect(screen.getByRole("link", { name: "Canal Digital" })).toHaveAttribute("href", "/canal-digital");
  });

  it("quien no es admin no ve nada nuevo", () => {
    mocks.esAdmin.mockReturnValue(false);
    render(<Sidebar open onClose={() => undefined} />);
    expect(screen.queryByRole("link", { name: "Canal Digital" })).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Sugerido" })).toBeInTheDocument();
  });
});
