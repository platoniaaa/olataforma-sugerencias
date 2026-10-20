import { describe, expect, it } from "vitest";
import { COLUMNAS_PRECIOS, KEYS_PRECIOS_DEFAULT, claseEstado } from "@/lib/columnas-precios";

describe("columnas de la lista de precios", () => {
  it("las visibles por defecto incluyen lo que se manda al ERP y lo que hay que revisar", () => {
    for (const k of ["producto", "precio_final", "estado", "cambios_pendientes", "costo", "stock"]) {
      expect(KEYS_PRECIOS_DEFAULT).toContain(k);
    }
  });

  it("la ayuda del stock dice la regla de bodegas de hoy: todas menos dañados, devolución y scrap", () => {
    const ayuda = COLUMNAS_PRECIOS.find((c) => c.key === "stock")?.ayuda ?? "";
    expect(ayuda).toMatch(/todas las bodegas de curifor/i);
    for (const excluida of ["dañados", "devolución", "scrap"]) expect(ayuda).toContain(excluida);
    // La regla anterior (solo las REAL) dejaba sin precio lo que si se vende.
    expect(ayuda).not.toMatch(/solo bodegas reales/i);
  });

  it("no hay claves repetidas", () => {
    const keys = COLUMNAS_PRECIOS.map((c) => c.key);
    expect(new Set(keys).size).toBe(keys.length);
  });

  it("el estado que hay que mirar antes de exportar se pinta en rojo", () => {
    expect(claseEstado("SIN REVISION")).toContain("rose");
    expect(claseEstado("OK")).toContain("emerald");
    expect(claseEstado("FIJO")).toContain("sky");
    // Un estado desconocido no revienta: gris.
    expect(claseEstado("lo que sea")).toContain("ink");
    expect(claseEstado(null)).toContain("ink");
  });
});
