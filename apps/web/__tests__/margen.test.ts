import { describe, expect, it } from "vitest";

import { factorDesdeMargen, margenDesdeFactor } from "@/lib/margen";

describe("margen sobre la venta", () => {
  it("35 % de margen es factor 1,5385", () => {
    expect(factorDesdeMargen(35)).toBe(1.5385);
  });

  it("el factor 1,78 de la política equivale a 43,8 % sobre la venta", () => {
    expect(margenDesdeFactor(1.78)).toBe(43.8);
  });

  it("fuera de 0 a 100 no hay factor", () => {
    expect(factorDesdeMargen(0)).toBeNull();
    expect(factorDesdeMargen(100)).toBeNull();
    expect(factorDesdeMargen(null)).toBeNull();
  });

  it("ida y vuelta", () => {
    expect(margenDesdeFactor(factorDesdeMargen(35)!)).toBe(35);
  });
});
