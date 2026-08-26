/**
 * El título de las 12 columnas de venta mensual.
 *
 * Las columnas son POSICIONALES (`venta_mes_01` es el último mes cerrado) porque
 * nombrarlas por mes obligaría a agregar y borrar columnas de la tabla en cada
 * corrida. El precio de eso es que el título hay que calcularlo, y si se calcula
 * mal la grilla le pone a una columna un mes que no es: el error más caro posible
 * acá, porque el número se ve razonable igual.
 */
import { describe, expect, it } from "vitest";

import { COLUMNAS, conMesReal, etiquetaMes } from "@/lib/columnas";

describe("etiquetaMes", () => {
  it("cuenta hacia atrás desde el último mes cerrado, cruzando el año", () => {
    expect(etiquetaMes("202606", 1)).toBe("Venta jun-26");
    expect(etiquetaMes("202606", 6)).toBe("Venta ene-26");
    expect(etiquetaMes("202606", 7)).toBe("Venta dic-25");
    expect(etiquetaMes("202606", 12)).toBe("Venta jul-25");
  });

  it("no inventa un mes cuando no hay período", () => {
    // Preferimos "Venta Mes 03" -feo pero honesto- a una fecha adivinada.
    expect(etiquetaMes(null, 3)).toBeNull();
    expect(etiquetaMes(undefined, 3)).toBeNull();
    expect(etiquetaMes("2026", 3)).toBeNull();
    expect(etiquetaMes("ago-26", 3)).toBeNull();
    expect(etiquetaMes("202613", 1)).toBeNull();
  });

  it("da lo mismo que el export del backend", () => {
    // `excel_export.etiqueta_mes` hace esta misma cuenta. Si las dos se separan,
    // el Excel que baja el comprador dice un mes y la pantalla otro.
    expect(etiquetaMes("202601", 2)).toBe("Venta dic-25");
    expect(etiquetaMes("202512", 12)).toBe("Venta ene-25");
  });
});

describe("conMesReal", () => {
  const venta = COLUMNAS.find((c) => c.key === "venta_mes_02")!;
  const otra = COLUMNAS.find((c) => c.key === "prom_vta_3m")!;

  it("solo toca las columnas de venta mensual", () => {
    expect(conMesReal(venta, "202606").label).toBe("Venta may-26");
    expect(conMesReal(otra, "202606").label).toBe(otra.label);
  });

  it("deja la etiqueta posicional si no se puede saber el mes", () => {
    expect(conMesReal(venta, null).label).toBe("Venta Mes 02");
  });
});

describe("catálogo de columnas", () => {
  it("los tres promedios vienen visibles y los doce meses no", () => {
    // Doce columnas más en la grilla por defecto la dejan ilegible; los promedios
    // son el resumen que se mira, y el detalle se prende cuando se necesita.
    const visible = (k: string) => COLUMNAS.find((c) => c.key === k)!.visiblePorDefecto;

    expect(["prom_vta_3m", "prom_vta_6m", "prom_vta_12m"].every(visible)).toBe(true);
    expect(
      Array.from({ length: 12 }, (_, i) => `venta_mes_${String(i + 1).padStart(2, "0")}`)
        .some(visible)
    ).toBe(false);
  });
});
