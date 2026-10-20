import { describe, expect, it } from "vitest";
import {
  COLUMNAS_PRECIOS, KEYS_PRECIOS_DEFAULT, LS_COLUMNAS_PRECIOS, LS_COLUMNAS_PRECIOS_VISTAS, claseEstado, claseVigencia,
  leerColumnasGuardadas, migrarColumnasGuardadas,
} from "@/lib/columnas-precios";

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

// ---------------------------------------------------------------- vigencia

describe("columnas de vigencia", () => {
  const def = (key: string) => COLUMNAS_PRECIOS.find((c) => c.key === key);

  it("«Vigencia» (por fecha de término) es visible por defecto, anclada a la derecha entre Estado y Cambios", () => {
    const vigencia = def("vigente_hasta");
    expect(vigencia?.label).toBe("Vigencia");
    expect(vigencia?.tipo).toBe("vigencia");
    expect(vigencia?.visiblePorDefecto).toBe(true);
    expect(vigencia?.pin).toBe("right");
    expect(vigencia?.ancho).toBeGreaterThanOrEqual(150);
    expect(vigencia?.ancho).toBeLessThanOrEqual(180);
    expect(KEYS_PRECIOS_DEFAULT).toContain("vigente_hasta");

    const orden = COLUMNAS_PRECIOS.map((c) => c.key as string);
    expect(orden.indexOf("vigente_hasta")).toBe(orden.indexOf("estado") + 1);
    expect(orden.indexOf("cambios_pendientes")).toBe(orden.indexOf("vigente_hasta") + 1);
  });

  it("«Vigente desde» existe pero queda oculta", () => {
    expect(def("vigente_desde")?.visiblePorDefecto).toBe(false);
    expect(KEYS_PRECIOS_DEFAULT).not.toContain("vigente_desde");
  });

  it("la ayuda de Vigencia explica «Programado» y «Vencido»", () => {
    const ayuda = def("vigente_hasta")?.ayuda ?? "";
    expect(ayuda).toContain("Programado");
    expect(ayuda).toContain("Vencido");
    expect(ayuda).toContain("volvió a la regla");
  });

  it("las columnas Precio fijo y Congelado avisan que solo muestran lo que rige hoy", () => {
    expect(def("precio_fijo")?.ayuda).toMatch(/Solo si rige hoy/);
    expect(def("congelar")?.ayuda).toMatch(/Solo si rige hoy/);
  });

  it("claseVigencia: un tono distinto para cada estado (el ícono y la palabra siguen siendo la señal)", () => {
    expect(claseVigencia("pronto")).toContain("amber");
    expect(claseVigencia("programado")).toContain("brand");
    expect(claseVigencia("vencido")).toContain("ink-100");
    expect(claseVigencia("lejos")).toContain("bg-white");
    const todas = (["lejos", "pronto", "programado", "vencido"] as const).map(claseVigencia);
    expect(new Set(todas).size).toBe(4);
  });
});

describe("migrarColumnasGuardadas", () => {
  const ANTIGUA = KEYS_PRECIOS_DEFAULT.filter((k) => k !== "vigente_hasta");

  it("a quien ya guardó columnas le suma la nueva visible por defecto", () => {
    const m = migrarColumnasGuardadas(ANTIGUA, null);

    expect(m.columnas).toEqual([...ANTIGUA, "vigente_hasta"]);
  });

  it("una sola vez: ya registrada como vista, si la oculta no vuelve", () => {
    const primera = migrarColumnasGuardadas(ANTIGUA, null);
    const sinVigencia = primera.columnas.filter((k) => k !== "vigente_hasta");

    const segunda = migrarColumnasGuardadas(sinVigencia, primera.vistas);

    expect(segunda.columnas).toEqual(sinVigencia);
    expect(segunda.vistas).toContain("vigente_hasta");
  });

  it("respeta una selección personalizada: solo suma la columna nueva, no trae de vuelta otras", () => {
    const personalizada = ["producto", "glosa", "precio_final", "estado"];

    const m = migrarColumnasGuardadas(personalizada, null);

    expect(m.columnas).toEqual([...personalizada, "vigente_hasta"]);
    expect(m.columnas).not.toContain("costo");
  });

  it("si ya la tenía, no la duplica", () => {
    const m = migrarColumnasGuardadas([...ANTIGUA, "vigente_hasta"], null);

    expect(m.columnas.filter((k) => k === "vigente_hasta")).toHaveLength(1);
  });

  it("registra como vistas todas las columnas de hoy", () => {
    const m = migrarColumnasGuardadas(ANTIGUA, null);

    for (const c of COLUMNAS_PRECIOS) expect(m.vistas).toContain(c.key);
  });

  it("una columna que no era nueva y la persona había quitado no reaparece", () => {
    const sinCosto = ANTIGUA.filter((k) => k !== "costo");

    expect(migrarColumnasGuardadas(sinCosto, null).columnas).not.toContain("costo");
  });
});

describe("leerColumnasGuardadas", () => {
  /** Un almacén en memoria, con las mismas dos operaciones que usa la pantalla. */
  function almacen(inicial: Record<string, string> = {}) {
    const datos = new Map(Object.entries(inicial));
    return {
      datos,
      getItem: (k: string) => datos.get(k) ?? null,
      setItem: (k: string, v: string) => void datos.set(k, v),
    };
  }
  const ANTIGUA = KEYS_PRECIOS_DEFAULT.filter((k) => k !== "vigente_hasta");

  it("sin nada guardado devuelve null (la pantalla usa los defaults) y registra lo visto", () => {
    const a = almacen();

    expect(leerColumnasGuardadas(a)).toBeNull();
    expect(JSON.parse(a.datos.get(LS_COLUMNAS_PRECIOS_VISTAS) ?? "[]")).toContain("vigente_hasta");
  });

  it("con una selección anterior a la vigencia, la devuelve con «Vigencia» sumada", () => {
    const a = almacen({ [LS_COLUMNAS_PRECIOS]: JSON.stringify(ANTIGUA) });

    expect(leerColumnasGuardadas(a)).toEqual([...ANTIGUA, "vigente_hasta"]);
  });

  it("la segunda visita respeta que la persona la haya ocultado", () => {
    const a = almacen({ [LS_COLUMNAS_PRECIOS]: JSON.stringify(ANTIGUA) });
    const primera = leerColumnasGuardadas(a) ?? [];
    // La pantalla guarda lo que muestra; la persona oculta «Vigencia» y vuelve otro día.
    a.setItem(LS_COLUMNAS_PRECIOS, JSON.stringify(primera.filter((k) => k !== "vigente_hasta")));

    expect(leerColumnasGuardadas(a)).toEqual(ANTIGUA);
  });

  it("quien oculta la columna desde su primera visita tampoco la ve reaparecer", () => {
    const a = almacen();
    expect(leerColumnasGuardadas(a)).toBeNull();
    a.setItem(LS_COLUMNAS_PRECIOS, JSON.stringify(ANTIGUA));

    expect(leerColumnasGuardadas(a)).toEqual(ANTIGUA);
  });

  it("un valor roto se ignora, como si no hubiera nada guardado", () => {
    expect(leerColumnasGuardadas(almacen({ [LS_COLUMNAS_PRECIOS]: "{no es json" }))).toBeNull();
    expect(leerColumnasGuardadas(almacen({ [LS_COLUMNAS_PRECIOS]: JSON.stringify({ a: 1 }) }))).toBeNull();
    expect(leerColumnasGuardadas(almacen({ [LS_COLUMNAS_PRECIOS]: JSON.stringify([]) }))).toBeNull();
    // Unas vistas rotas no tiran la selección buena.
    const a = almacen({ [LS_COLUMNAS_PRECIOS]: JSON.stringify(ANTIGUA), [LS_COLUMNAS_PRECIOS_VISTAS]: "{roto" });
    expect(leerColumnasGuardadas(a)).toEqual([...ANTIGUA, "vigente_hasta"]);
  });

  it("si el navegador no deja leer o escribir (ventana privada), no revienta", () => {
    const bloqueado = {
      getItem: () => { throw new Error("SecurityError"); },
      setItem: () => { throw new Error("QuotaExceededError"); },
    };
    expect(leerColumnasGuardadas(bloqueado)).toBeNull();
    // Si solo falla escribir, la selección que se pudo leer sirve igual.
    const soloLectura = {
      getItem: (k: string) => (k === LS_COLUMNAS_PRECIOS ? JSON.stringify(ANTIGUA) : null),
      setItem: () => { throw new Error("QuotaExceededError"); },
    };
    expect(leerColumnasGuardadas(soloLectura)).toEqual([...ANTIGUA, "vigente_hasta"]);
  });
});
