/**
 * Tabla de unidades en tránsito del detalle del vendedor: lo que ya está pedido y todavía no llega,
 * para que no pida de más. Importa la fecha de la OC: "vienen 5" no es lo mismo si se pidieron ayer
 * que si se pidieron hace cuatro meses.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, describe, expect, it } from "vitest";

import { TablaTransito, fechaCorta, haceCuanto } from "@/components/tabla-transito";

afterEach(cleanup);

const HOY = new Date("2026-10-30T12:00:00");

describe("fechaCorta y haceCuanto", () => {
  it("da vuelta la fecha a día-mes-año", () => {
    expect(fechaCorta("2026-06-12")).toBe("12-06-2026");
    expect(fechaCorta("2026-06-12T00:00:00")).toBe("12-06-2026");
  });

  it("dice hace cuánto se pidió, en días y en meses", () => {
    expect(haceCuanto("2026-10-30", HOY)).toBe("hoy");
    expect(haceCuanto("2026-10-29", HOY)).toBe("hace 1 día");
    expect(haceCuanto("2026-10-18", HOY)).toBe("hace 12 días");
    expect(haceCuanto("2026-09-29", HOY)).toBe("hace 1 mes");
    expect(haceCuanto("2026-06-12", HOY)).toBe("hace 4 meses");
  });

  it("una fecha rota no revienta", () => {
    expect(haceCuanto("no-es-fecha", HOY)).toBe("");
  });
});

describe("TablaTransito", () => {
  it("lista cada sucursal con sus unidades, la fecha del pedido y el total", () => {
    render(
      <TablaTransito
        hoy={HOY}
        filas={[
          { sucursal_id: "02 LINDEROS", cantidad: 3, pedido_desde: "2026-10-18" },
          { sucursal_id: "TALCA", cantidad: 6, pedido_desde: "2026-06-12" },
        ]}
      />
    );
    expect(screen.getByText("Unidades en tránsito")).toBeInTheDocument();
    const filas = screen.getAllByRole("row").map((f) => f.textContent ?? "");
    expect(filas.some((f) => f.includes("LINDEROS") && f.includes("3") && f.includes("18-10-2026") && f.includes("hace 12 días"))).toBe(true);
    expect(filas.some((f) => f.includes("TALCA") && f.includes("hace 4 meses"))).toBe(true);
    // Sin el código del ERP delante, y con el total al pie.
    expect(screen.queryByText("02 LINDEROS")).not.toBeInTheDocument();
    expect(filas.some((f) => f.startsWith("Total") && f.includes("9"))).toBe(true);
  });

  it("dice 'Sin fecha' cuando la OC no trae fecha", () => {
    render(<TablaTransito hoy={HOY} filas={[{ sucursal_id: "CURICO", cantidad: 2, pedido_desde: null }]} />);
    expect(screen.getByText("Sin fecha")).toBeInTheDocument();
  });

  it("sin tránsito lo dice con todas sus letras, en vez de dejar un hueco", () => {
    render(<TablaTransito hoy={HOY} filas={[]} />);
    expect(screen.getByText("No hay unidades en tránsito de este producto.")).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("ignora filas con cantidad cero", () => {
    render(<TablaTransito hoy={HOY} filas={[{ sucursal_id: "CURICO", cantidad: 0, pedido_desde: null }]} />);
    expect(screen.getByText("No hay unidades en tránsito de este producto.")).toBeInTheDocument();
  });
});
