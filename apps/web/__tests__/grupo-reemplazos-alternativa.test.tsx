/**
 * La tarjeta "Historial de reemplazos" desaparece cuando el código no tiene reemplazos. La vista del
 * vendedor quiere UN solo gráfico de ventas: el del grupo si lo hay y, si no, el del código solo. Por
 * eso la tarjeta acepta una `alternativa` que se muestra únicamente cuando no hay grupo.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GrupoReemplazos } from "@/components/grupo-reemplazos";
import type { GrupoVentas } from "@/lib/types";

const mocks = vi.hoisted(() => ({ consultaGrupoVentas: vi.fn() }));

vi.mock("@/lib/api-client", () => ({ api: { consultaGrupoVentas: mocks.consultaGrupoVentas, grupoVentas: vi.fn() } }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...resto }: { href: string; children: React.ReactNode }) => (
    <a href={href} {...resto}>{children}</a>
  ),
}));
// recharts necesita medir el contenedor y jsdom no mide nada.
vi.mock("recharts", async () => {
  const real = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    BarChart: () => <div data-testid="barras-grupo" />,
  };
});

const miembro = (producto: string, es_vigente: boolean) => ({
  producto, es_vigente, sku_ford: null, venta_12m: 10, venta_total: 20, ultimo_mes_con_venta: "202610",
  stock: 3, cuenta_en_el_total: true, motivo_fuera: null,
});

const CON_GRUPO: GrupoVentas = {
  producto: "A", vigente: "B", sucursal: null,
  miembros: [miembro("A", false), miembro("B", true)],
  meses: [{ mes: "202610", A: 4, B: 6 }], total_venta_12m: 20, total_stock: 6,
};
const SIN_GRUPO: GrupoVentas = { producto: "A", miembros: [], meses: [] };

const ALTERNATIVA = <div data-testid="alternativa">venta del código solo</div>;

beforeEach(() => {
  mocks.consultaGrupoVentas.mockReset();
});
afterEach(cleanup);

describe("GrupoReemplazos con alternativa", () => {
  it("con reemplazos muestra el historial y NO la alternativa", async () => {
    mocks.consultaGrupoVentas.mockResolvedValue(CON_GRUPO);
    render(<GrupoReemplazos producto="A" consulta alternativa={ALTERNATIVA} />);

    expect(await screen.findByText("Historial de reemplazos")).toBeInTheDocument();
    expect(screen.queryByTestId("alternativa")).not.toBeInTheDocument();
  });

  it("sin reemplazos muestra la alternativa en lugar de nada", async () => {
    mocks.consultaGrupoVentas.mockResolvedValue(SIN_GRUPO);
    render(<GrupoReemplazos producto="A" consulta alternativa={ALTERNATIVA} />);

    expect(await screen.findByTestId("alternativa")).toBeInTheDocument();
    expect(screen.queryByText("Historial de reemplazos")).not.toBeInTheDocument();
  });

  it("mientras carga no muestra la alternativa (no debe parpadear antes de saber si hay grupo)", () => {
    mocks.consultaGrupoVentas.mockReturnValue(new Promise(() => undefined));
    render(<GrupoReemplazos producto="A" consulta alternativa={ALTERNATIVA} />);
    expect(screen.queryByTestId("alternativa")).not.toBeInTheDocument();
  });

  it("si el servidor falla, muestra la alternativa: el vendedor no se queda sin ventas", async () => {
    mocks.consultaGrupoVentas.mockRejectedValue(new Error("sin conexión"));
    render(<GrupoReemplazos producto="A" consulta alternativa={ALTERNATIVA} />);
    expect(await screen.findByTestId("alternativa")).toBeInTheDocument();
  });

  it("sin alternativa, un código sin reemplazos sigue sin mostrar nada (como en el catálogo)", async () => {
    mocks.consultaGrupoVentas.mockResolvedValue(SIN_GRUPO);
    const { container } = render(<GrupoReemplazos producto="A" consulta />);
    await waitFor(() => expect(mocks.consultaGrupoVentas).toHaveBeenCalled());
    expect(container).toBeEmptyDOMElement();
  });

  it("con una sucursal elegida lo dice y la pide al servidor", async () => {
    mocks.consultaGrupoVentas.mockResolvedValue({ ...CON_GRUPO, sucursal: "LINDEROS" });
    render(<GrupoReemplazos producto="A" consulta sucursalId="LINDEROS" />);

    expect(await screen.findByText(/\(solo LINDEROS\)/)).toBeInTheDocument();
    expect(mocks.consultaGrupoVentas).toHaveBeenCalledWith("A", "LINDEROS");
  });
});
