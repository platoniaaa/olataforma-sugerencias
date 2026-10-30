/**
 * Gráfico de stock por sucursal de la vista del vendedor. Lo que se cuida: que cada sucursal
 * sume todas sus bodegas, que no se dibujen sucursales sin stock y que el gráfico tenga un
 * texto equivalente para quien no lo puede ver.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { GraficoStockSucursal, stockPorSucursal, stockYTransitoPorSucursal } from "@/components/grafico-stock-sucursal";
import type { StockSucursalRow, TransitoSucursal } from "@/lib/types";

// recharts necesita medir el contenedor y jsdom no mide nada: aquí importa lo que rodea al gráfico.
vi.mock("recharts", async () => {
  const real = await vi.importActual<typeof import("recharts")>("recharts");
  return {
    ...real,
    ResponsiveContainer: ({ height, children }: { height: number; children: React.ReactNode }) => (
      <div data-testid="contenedor" data-alto={height}>{children}</div>
    ),
    BarChart: () => <div data-testid="barras" />,
  };
});

afterEach(cleanup);

const fila = (sucursal_id: string | null, bodega: string | null, stock: number): StockSucursalRow =>
  ({ sucursal_id, bodega, stock, origen: null });

describe("stockPorSucursal", () => {
  it("suma las bodegas de una misma sucursal y ordena de mayor a menor", () => {
    const r = stockPorSucursal([
      fila("LINDEROS", "LINDEROS", 3),
      fila("CURICO", "CURICO", 4),
      fila("LINDEROS", "LINDEROS 2", 2),
    ]);
    expect(r).toEqual([
      { sucursal: "LINDEROS", stock: 5 },
      { sucursal: "CURICO", stock: 4 },
    ]);
  });

  it("no dibuja las sucursales sin stock ni las de stock negativo", () => {
    expect(stockPorSucursal([fila("TALCA", "TALCA", 0), fila("OVALLE", "OVALLE", -2)])).toEqual([]);
  });

  it("una fila sin sucursal cuenta con su bodega y, si tampoco tiene, como 'Sin sucursal'", () => {
    expect(stockPorSucursal([fila(null, "BODEGA ML", 6), fila(null, null, 1), fila("  ", null, 2)])).toEqual([
      { sucursal: "BODEGA ML", stock: 6 },
      { sucursal: "Sin sucursal", stock: 3 },
    ]);
  });

  it("empata por nombre para que el orden sea estable", () => {
    const r = stockPorSucursal([fila("TALCA", "T", 2), fila("CURICO", "C", 2)]);
    expect(r.map((x) => x.sucursal)).toEqual(["CURICO", "TALCA"]);
  });
});

const tr = (sucursal_id: string | null, cantidad: number, pedido_desde: string | null = null): TransitoSucursal =>
  ({ sucursal_id, cantidad, pedido_desde });

describe("stockYTransitoPorSucursal", () => {
  it("une el tránsito escrito con el código del ERP con el stock de la misma sucursal", () => {
    const r = stockYTransitoPorSucursal(
      [fila("LINDEROS", "LINDEROS", 5), fila("CURICO", "CURICO", 4)],
      [tr("02 LINDEROS", 3), tr("CURICO", 10)]
    );
    expect(r).toEqual([
      { sucursal: "LINDEROS", stock: 5, transito: 3 },
      { sucursal: "CURICO", stock: 4, transito: 10 },
    ]);
  });

  it("dibuja una sucursal con tránsito pero sin stock: es a la que no hay que pedirle más", () => {
    const r = stockYTransitoPorSucursal([fila("CURICO", "CURICO", 2)], [tr("TALCA", 6)]);
    expect(r).toEqual([
      { sucursal: "CURICO", stock: 2, transito: 0 },
      { sucursal: "TALCA", stock: 0, transito: 6 },
    ]);
  });

  it("ignora tránsito en cero y lo que no tiene sucursal va como 'Sin sucursal'", () => {
    expect(stockYTransitoPorSucursal([], [tr("TALCA", 0), tr(null, 2)])).toEqual([
      { sucursal: "Sin sucursal", stock: 0, transito: 2 },
    ]);
  });
});

describe("GraficoStockSucursal", () => {
  it("con tránsito cambia el título, suma el total y lo dice en el texto equivalente", () => {
    render(
      <GraficoStockSucursal
        filas={[fila("CURICO", "CURICO", 4)]}
        transito={[tr("CURICO", 10), tr("TALCA", 6)]}
      />
    );
    expect(screen.getByText("Stock y tránsito por sucursal")).toBeInTheDocument();
    expect(screen.getByText(/u en tránsito/)).toHaveTextContent("16 u en tránsito");
    expect(
      screen.getByRole("img", { name: "Stock por sucursal: CURICO 4 y 10 en tránsito, TALCA sin stock y 6 en tránsito" })
    ).toBeInTheDocument();
    // Dos barras por sucursal: más alto que con una.
    expect(screen.getByTestId("contenedor")).toHaveAttribute("data-alto", String(2 * 58 + 56));
  });

  it("sin tránsito se ve como antes", () => {
    render(<GraficoStockSucursal filas={[fila("CURICO", "CURICO", 4)]} transito={[]} />);
    expect(screen.getByText("Stock por sucursal")).toBeInTheDocument();
    expect(screen.queryByText(/en tránsito/)).not.toBeInTheDocument();
  });

  it("resume el stock en texto y se ajusta al número de sucursales", () => {
    render(<GraficoStockSucursal filas={[fila("CURICO", "CURICO", 4), fila("LINDEROS", "LINDEROS", 3)]} />);

    expect(screen.getByRole("img", { name: "Stock por sucursal: CURICO 4, LINDEROS 3" })).toBeInTheDocument();
    expect(screen.getByText("Stock por sucursal")).toBeInTheDocument();
    expect(screen.getByText(/en 2 sucursales/)).toBeInTheDocument();
    expect(screen.getByTestId("contenedor")).toHaveAttribute("data-alto", String(2 * 34 + 28));
  });

  it("dice 'sucursal' en singular cuando hay una sola", () => {
    render(<GraficoStockSucursal filas={[fila("CURICO", "CURICO", 4)]} />);
    expect(screen.getByText(/en 1 sucursal$/)).toBeInTheDocument();
  });

  it("no muestra nada si el producto no tiene stock", () => {
    const { container } = render(<GraficoStockSucursal filas={[fila("CURICO", "CURICO", 0)]} />);
    expect(container).toBeEmptyDOMElement();
  });
});
