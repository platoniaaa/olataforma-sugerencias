/**
 * Compras: desde el 19-10 los carros salen de las mismas filas que la grilla del
 * sugerido (compras_service usa sugerido_service.listar), asi que suman tambien el
 * minimo InStock que antes se perdia. La pantalla tiene que decirlo: si no, el
 * comprador que compara con la grilla ve unidades "de mas" y no sabe de donde vienen.
 */
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import ComprasPage from "@/app/compras/page";

const mocks = vi.hoisted(() => ({ carros: vi.fn() }));

vi.mock("@/lib/api-client", () => ({ api: { carros: mocks.carros, exportOrden: vi.fn() } }));

beforeEach(() => {
  mocks.carros.mockReset();
  mocks.carros.mockResolvedValue({
    carros: [
      {
        proveedor: "GILDEMEISTER", n_productos: 1, total_unidades: 7, total_clp: 70_000,
        lineas: [
          {
            producto: "95 252122B020", descripcion: "FILTRO", clasificacion_abc: "A", cantidad: 7,
            costo_unitario: 10_000, subtotal_clp: 70_000,
          },
        ],
      },
    ],
    total_proveedores: 1,
    total_clp: 70_000,
    total_unidades: 7,
  });
});

describe("Compras", () => {
  it("explica que la cantidad es la de la grilla, con manuales y minimo InStock", async () => {
    render(<ComprasPage />);
    expect(await screen.findByText("GILDEMEISTER")).toBeInTheDocument();
    const texto = screen.getByText(/El sugerido agrupado por proveedor/);
    expect(texto).toHaveTextContent("Sale de las mismas filas que la grilla del sugerido");
    expect(texto).toHaveTextContent("los ajustes manuales vigentes y el mínimo InStock");
    expect(mocks.carros).toHaveBeenCalledWith({ solo_pedir: true });
  });
});
