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

  it("el margen fijo muestra la cuenta con el margen, y le gana al proveedor", () => {
    const t = explicacionPrecio(con({ margen_fijo: 35, factor: 1.5385, precio_calculado: 4129, tipo: "Sugerido" }));
    expect(t).toContain("×");
    expect(t).toContain("margen 35");
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

// ---------------------------------------------------------------- vigencia
//
// `precio_fijo`, `margen_fijo` y `congelar` son la decisión GUARDADA. Si su periodo está
// programado o vencido el precio sale de la regla, y la línea no puede decir que lo puso una
// persona. Las nueve pruebas de arriba (una ficha sin `vigencia`) no cambian.
const HOY = "2026-10-20";

describe("explicacionPrecio con vigencia", () => {
  it("un precio fijo que rige con Hasta agrega hasta cuando", () => {
    expect(explicacionPrecio(con({ precio_fijo: 9990, vigencia: "vigente", vigente_hasta: "2026-11-30" }), HOY))
      .toBe("Precio fijo puesto a mano · hasta el 30-11");
  });

  it("vigente sin Hasta queda como siempre", () => {
    expect(explicacionPrecio(con({ precio_fijo: 9990, vigencia: "vigente", vigente_hasta: null }), HOY))
      .toBe("Precio fijo puesto a mano");
  });

  it("de otro año muestra el año", () => {
    expect(explicacionPrecio(con({ precio_fijo: 9990, vigencia: "vigente", vigente_hasta: "2027-01-15" }), HOY))
      .toBe("Precio fijo puesto a mano · hasta el 15-01-2027");
  });

  it("congelado y margen respetan el periodo cuando rigen", () => {
    expect(explicacionPrecio(con({ congelar: true, vigencia: "vigente", vigente_hasta: "2026-11-30" }), HOY))
      .toBe("Congelado: no sigue al costo · hasta el 30-11");
    const margen = explicacionPrecio(
      con({ margen_fijo: 35, factor: 1.5385, precio_calculado: 4129, vigencia: "vigente", vigente_hasta: "2026-11-30" }), HOY);
    expect(margen).toContain("margen 35");
    expect(margen).toMatch(/ · hasta el 30-11$/);
  });

  it("la fecha no se agrega a una línea que habla de otra cosa (sin stock le gana al margen)", () => {
    const t = explicacionPrecio(con({ margen_fijo: 35, stock: 0, stock_transito: 0, vigencia: "vigente", vigente_hasta: "2026-11-30" }), HOY);
    expect(t).toBe("Sin stock ni tránsito → 0");
  });

  it("programado: NO dice «Precio fijo puesto a mano»; explica la regla y cuando empieza", () => {
    const t = explicacionPrecio(
      con({ precio_fijo: 12990, vigencia: "programada", vigente_desde: "2026-11-05", vigente_hasta: "2026-11-30" }), HOY);
    expect(t).not.toContain("puesto a mano");
    expect(t).toContain("Hoy sigue la regla");
    expect(t).toContain("×");
    expect(t).toContain("1,78");
    expect(t).toContain("empieza el 05-11");
    expect(t).toContain("12.990");
  });

  it("vencido: dice que volvió a la regla y que la decisión sigue guardada", () => {
    const t = explicacionPrecio(con({ precio_fijo: 12990, vigencia: "vencida", vigente_hasta: "2026-10-12" }), HOY);
    expect(t).not.toContain("puesto a mano");
    expect(t).toContain("Venció el 12-10: volvió a la regla");
    expect(t).toContain("×");
    expect(t).toContain("sigue guardado");
  });

  it("congelado vencido: no se explica como congelado", () => {
    const t = explicacionPrecio(con({ congelar: true, congelado_precio: 14000, vigencia: "vencida", vigente_hasta: "2026-10-12" }), HOY);
    expect(t).not.toContain("Congelado: no sigue al costo");
    expect(t).toContain("El precio congelado de");
    expect(t).toContain("14.000");
  });

  it("margen programado: usa la cuenta de la regla, sin el margen", () => {
    const t = explicacionPrecio(
      con({ margen_fijo: 35, factor: 1.78, vigencia: "programada", vigente_desde: "2026-11-05" }), HOY);
    expect(t).not.toContain("(margen 35");
    expect(t).toContain("×");
    expect(t).toContain("El margen fijo de 35,0 %");
  });

  it("si la regla tampoco da precio (sin stock), lo dice en vez de inventar una cuenta", () => {
    const t = explicacionPrecio(
      con({ precio_fijo: 12990, stock: 0, stock_transito: 0, vigencia: "programada", vigente_desde: "2026-11-05" }), HOY);
    expect(t).toContain("sin stock ni tránsito → 0");
  });

  it("programada sin Desde (dato incompleto) no imprime undefined", () => {
    const t = explicacionPrecio(con({ precio_fijo: 12990, vigencia: "programada", vigente_desde: null }), HOY);
    expect(t).not.toMatch(/undefined|null|NaN/);
  });

  it("una ficha sin vigencia se comporta como siempre", () => {
    expect(explicacionPrecio(con({ precio_fijo: 9990, vigencia: null }), HOY)).toBe("Precio fijo puesto a mano");
    expect(explicacionPrecio(con({ precio_fijo: 9990 }), HOY)).toBe("Precio fijo puesto a mano");
  });
});
