/**
 * La línea que explica de dónde salió el precio.
 *
 * El panel mostraba costo, factor y precio calculado como tres filas sueltas de
 * una lista de once. Cuando el precio NO salía de esa cuenta -fijo, congelado,
 * sin stock- nada lo decía: el costo y el factor seguían ahí, invitando a
 * multiplicarlos y a no cuadrar. Estos tests fijan que cada caso se explique
 * solo, y sobre todo que el orden sea el de `precios_service.calcular`.
 */
import { describe, expect, it } from "vitest";

import { explicacionPrecio } from "@/lib/columnas-precios";
import type { PrecioDetalle } from "@/lib/types";

const base = {
  precio_fijo: null, congelar: false, no_producto: false,
  stock: 5, stock_transito: 0, tipo: "Liviano",
  costo: 2684, factor: 1.78, precio_calculado: 4777,
} as unknown as PrecioDetalle;

const con = (extra: Partial<PrecioDetalle>): PrecioDetalle => ({ ...base, ...extra });

describe("explicacionPrecio", () => {
  it("muestra la multiplicación cuando el precio sale de la regla", () => {
    expect(explicacionPrecio(base)).toContain("×");
    expect(explicacionPrecio(base)).toContain("1,78");
  });

  it("el precio fijo gana a todo, incluso sin stock", () => {
    // Es el orden real de `calcular`: 1 fijo, 2 congelado, 3 sin stock.
    expect(explicacionPrecio(con({ precio_fijo: 9990, stock: 0, stock_transito: 0 })))
      .toBe("Precio fijo puesto a mano");
  });

  it("el congelado gana al sin stock", () => {
    expect(explicacionPrecio(con({ congelar: true, stock: 0, stock_transito: 0 })))
      .toBe("Congelado: no sigue al costo");
  });

  it("sin stock ni tránsito lo dice, en vez de mostrar una cuenta que no se aplicó", () => {
    expect(explicacionPrecio(con({ stock: 0, stock_transito: 0 }))).toContain("Sin stock");
  });

  it("el tránsito salva al que no tiene stock", () => {
    expect(explicacionPrecio(con({ stock: 0, stock_transito: 3 }))).toContain("×");
  });

  it("el tipo Sugerido no usa costo por factor", () => {
    expect(explicacionPrecio(con({ tipo: "Sugerido" }))).toContain("proveedor");
  });

  it("sin factor lo dice: es la causa real de SIN REVISION", () => {
    expect(explicacionPrecio(con({ factor: null }))).toContain("Sin factor");
  });

  it("sin costo lo dice", () => {
    expect(explicacionPrecio(con({ costo: null }))).toContain("Sin costo");
  });
});
