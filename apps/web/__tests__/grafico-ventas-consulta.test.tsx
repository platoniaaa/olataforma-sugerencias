/**
 * Único gráfico de ventas de la vista del vendedor cuando el código no tiene reemplazos. Si falla
 * o no hubo ventas, la tarjeta debe decirlo en vez de desaparecer: el vendedor no puede distinguir
 * "no hay venta" de "no cargó". En las pantallas de Abastecimiento no cambia nada (sigue sin pintar).
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { GraficoVentas } from "@/components/grafico-ventas";

const mocks = vi.hoisted(() => ({
  consultaVentas: vi.fn(),
  catalogoVentas: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: { consultaVentas: mocks.consultaVentas, catalogoVentas: mocks.catalogoVentas },
}));
vi.mock("recharts", async () => {
  const real = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...real,
    ResponsiveContainer: ({ children }: { children: React.ReactNode }) => <div>{children}</div>,
    BarChart: () => <div data-testid="barras" />,
  };
});

beforeEach(() => {
  mocks.consultaVentas.mockReset();
  mocks.catalogoVentas.mockReset();
});
afterEach(cleanup);

const vacio = { producto: "P", sucursal_id: "", meses_general: [], meses_sucursal: [], total_general: 0, total_sucursal: 0 };

describe("GraficoVentas en la vista del vendedor", () => {
  it("si el producto no vendió en 12 meses, lo dice", async () => {
    mocks.consultaVentas.mockResolvedValue(vacio);
    render(<GraficoVentas producto="P" consulta />);
    expect(await screen.findByText("Sin ventas en los últimos 12 meses.")).toBeInTheDocument();
    expect(mocks.consultaVentas).toHaveBeenCalledWith("P", undefined);
  });

  it("si falla la carga, lo dice y no se queda oculto al cambiar de sucursal", async () => {
    mocks.consultaVentas.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    const { rerender } = render(<GraficoVentas producto="P" consulta sucursalId="LINDEROS" />);
    expect(await screen.findByText(/No se pudo cargar la venta/)).toBeInTheDocument();
    expect(screen.queryByText(/Failed to fetch/)).not.toBeInTheDocument();

    mocks.consultaVentas.mockResolvedValue({
      ...vacio, sucursal_id: "CURICO",
      meses_general: [{ mes: "202510", cantidad: 4 }], total_general: 4,
    });
    rerender(<GraficoVentas producto="P" consulta sucursalId="CURICO" />);
    await waitFor(() => expect(screen.queryByText(/No se pudo cargar la venta/)).not.toBeInTheDocument());
    expect(screen.getByText("Venta últimos 12 meses")).toBeInTheDocument();
  });

  it("al cambiar de sucursal no deja las cifras de la anterior bajo el título nuevo", async () => {
    mocks.consultaVentas.mockResolvedValueOnce({
      ...vacio, sucursal_id: "CURICO",
      meses_general: [{ mes: "202510", cantidad: 54 }], meses_sucursal: [{ mes: "202510", cantidad: 9 }],
      total_general: 54, total_sucursal: 9,
    });
    const { rerender } = render(<GraficoVentas producto="P" consulta sucursalId="CURICO" />);
    await screen.findByText(/CURICO/);

    // La respuesta de LINDEROS tarda: mientras tanto no se puede leer "LINDEROS 9 u".
    mocks.consultaVentas.mockImplementationOnce(() => new Promise(() => undefined));
    rerender(<GraficoVentas producto="P" consulta sucursalId="LINDEROS" />);
    await waitFor(() => expect(screen.getByText(/Cargando/)).toBeInTheDocument());
    expect(screen.queryByText(/9/)).not.toBeInTheDocument();
  });

  it("en las pantallas de Abastecimiento no cambia: sin ventas no pinta nada", async () => {
    mocks.catalogoVentas.mockResolvedValue(vacio);
    const { container } = render(<GraficoVentas producto="P" />);
    await waitFor(() => expect(mocks.catalogoVentas).toHaveBeenCalled());
    await new Promise((r) => setTimeout(r, 20));
    expect(container).toBeEmptyDOMElement();
  });
});
