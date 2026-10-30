/**
 * El asistente de chat maneja costos, proveedores y parámetros de compra: el vendedor nunca debe
 * ver el costo, así que su pantalla no lo monta (el servidor además le responde 403).
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Shell } from "@/components/shell";

const mocks = vi.hoisted(() => ({ esVendedor: vi.fn() }));

vi.mock("next/navigation", () => ({
  usePathname: () => "/consulta-productos",
  useRouter: () => ({ replace: vi.fn(), push: vi.fn() }),
}));
vi.mock("next/link", () => ({
  default: ({ href, children, ...resto }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...resto}>{children}</a>
  ),
}));
vi.mock("@/components/sidebar", () => ({ Sidebar: () => null }));
vi.mock("@/components/campanita-notificaciones", () => ({ CampanitaNotificaciones: () => null }));
vi.mock("@/components/chat-bot", () => ({ ChatBot: () => <div data-testid="chat-bot" /> }));
vi.mock("@/lib/auth", () => ({
  estaAutenticado: () => true,
  getEmail: () => "alguien@ejemplo.cl",
  getNombre: () => null,
  getEsVendedor: mocks.esVendedor,
  logout: vi.fn(),
}));

beforeEach(() => mocks.esVendedor.mockReset());
afterEach(cleanup);

describe("asistente de chat en el Shell", () => {
  it("no se monta para el vendedor", async () => {
    mocks.esVendedor.mockReturnValue(true);
    render(<Shell><p>contenido</p></Shell>);
    await screen.findByText("contenido");
    expect(screen.queryByTestId("chat-bot")).not.toBeInTheDocument();
  });

  it("sigue montado para Abastecimiento", async () => {
    mocks.esVendedor.mockReturnValue(false);
    render(<Shell><p>contenido</p></Shell>);
    await waitFor(() => expect(screen.getByTestId("chat-bot")).toBeInTheDocument());
  });
});
