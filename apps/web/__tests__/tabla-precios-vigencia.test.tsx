/**
 * La columna «Vigencia» de la lista de precios.
 *
 * Lo que importa cuidar: el chip sale de la fila (estado, fecha y la decisión), una fila sin
 * periodo no dibuja nada, ordenar por la columna deja los vacíos SIEMPRE al final (AG Grid
 * invierte el comparador en el orden descendente), y las columnas Precio fijo / Congelado no
 * muestran como vigente una decisión que no rige.
 */
import "@testing-library/jest-dom/vitest";
import { render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TablaPrecios, colDef } from "@/components/tabla-precios";
import { COLUMNAS_PRECIOS } from "@/lib/columnas-precios";
import { formatoCLP } from "@/lib/formato";
import type { PrecioRow } from "@/lib/types";

const HOY = "2026-10-20";

function fila(producto: string, extra: Partial<PrecioRow> = {}): PrecioRow {
  return {
    producto, glosa: "AMORTIGUADOR", rubro: "17", tipo: "Liviano",
    procedencia_final: "Nacional", factor: 1.78, costo: 1000, stock: 3,
    precio_erp: 1800, precio_final: 1780, estado: "OK", cambios_pendientes: 0,
    precio_fijo: null, margen_fijo: null, congelar: false,
    ...extra,
  } as unknown as PrecioRow;
}

const FIJO_VIGENTE = { precio_fijo: 15000, vigencia: "vigente", vigente_hasta: "2026-11-30", vigencia_dias: 41 } as const;
const FIJO_PROGRAMADO = { precio_fijo: 16000, vigencia: "programada", vigente_desde: "2026-11-05", vigente_hasta: "2026-11-30" } as const;
const FIJO_VENCIDO = { precio_fijo: 17000, vigencia: "vencida", vigente_hasta: "2026-10-12", vigencia_dias: 8 } as const;

const defVigencia = () => COLUMNAS_PRECIOS.find((c) => c.key === "vigente_hasta")!;

describe("columna Vigencia: el chip", () => {
  it("cada fila dibuja el chip de su estado", async () => {
    render(
      <TablaPrecios
        hoy={HOY} onFila={vi.fn()} columnasVisibles={["producto", "vigente_hasta"]}
        rows={[
          fila("17 VIGENTE", FIJO_VIGENTE),
          fila("17 PROGRAMADO", FIJO_PROGRAMADO),
          fila("17 VENCIDO", FIJO_VENCIDO),
        ]}
      />,
    );

    expect(await screen.findByText("Fijo hasta 30-11")).toBeInTheDocument();
    expect(screen.getByText("Programado desde 05-11")).toBeInTheDocument();
    expect(screen.getByText("Vencido 12-10")).toBeInTheDocument();
  });

  it("una fila sin periodo no dibuja nada en esa celda", async () => {
    render(
      <TablaPrecios
        hoy={HOY} onFila={vi.fn()} columnasVisibles={["producto", "vigente_hasta"]}
        rows={[fila("17 LIBRE"), fila("17 VIGENTE", FIJO_VIGENTE)]}
      />,
    );

    await screen.findByText("Fijo hasta 30-11");
    expect(screen.getAllByTestId("chip-vigencia")).toHaveLength(1);
    const libre = screen.getByText("17 LIBRE").closest('[role="row"]') as HTMLElement;
    expect(within(libre).queryByTestId("chip-vigencia")).not.toBeInTheDocument();
  });

  it("nunca dice undefined, null ni NaN, tampoco con filas de una API anterior", async () => {
    const { container } = render(
      <TablaPrecios
        hoy={HOY} onFila={vi.fn()} columnasVisibles={["producto", "vigente_hasta"]}
        rows={[fila("17 VIEJA")]}
      />,
    );

    await screen.findByText("17 VIEJA");
    expect(container.querySelector(".ag-center-cols-container, .ag-pinned-right-cols-container")?.textContent ?? "")
      .not.toMatch(/undefined|null|NaN/);
    expect(screen.queryByTestId("chip-vigencia")).not.toBeInTheDocument();
  });

  it("el chip trae su frase completa en el title", async () => {
    render(
      <TablaPrecios hoy={HOY} onFila={vi.fn()} columnasVisibles={["producto", "vigente_hasta"]}
                    rows={[fila("17 VIGENTE", FIJO_VIGENTE)]} />,
    );

    const chip = await screen.findByTestId("chip-vigencia");
    expect(chip).toHaveAttribute("title", "Precio fijo hasta el 30-11-2026 incluido. El 01-12-2026 vuelve a la regla.");
  });
});

describe("columna Vigencia: orden y filtro", () => {
  /** Lo que hace AG Grid: llama al comparador y, si el orden es descendente, invierte el resultado. */
  function ordenar(valores: (string | null)[], descendente: boolean) {
    const cmp = colDef(defVigencia()).comparator as (a: unknown, b: unknown, na: unknown, nb: unknown, d: boolean) => number;
    return [...valores].sort((a, b) => {
      const r = cmp(a, b, null, null, descendente);
      return descendente ? r * -1 : r;
    });
  }
  const VALORES = ["2026-12-31", null, "2026-10-12", null, "2026-11-30"];

  it("ascendente: lo que vence primero arriba y los vacíos al final", () => {
    expect(ordenar(VALORES, false)).toEqual(["2026-10-12", "2026-11-30", "2026-12-31", null, null]);
  });

  it("descendente: lo más lejano arriba y los vacíos TAMBIÉN al final", () => {
    expect(ordenar(VALORES, true)).toEqual(["2026-12-31", "2026-11-30", "2026-10-12", null, null]);
  });

  it("ordena por la fecha de término (los vencidos primero) y se puede ordenar", () => {
    const col = colDef(defVigencia());
    expect(col.field).toBe("vigente_hasta");
    expect(col.sortable).toBe(true);
    expect(col.pinned).toBe("right");
    expect(col.width).toBeGreaterThanOrEqual(150);
  });

  it("el filtro de la columna lista lo que se ve («Fijo hasta 30-11»), no fechas crudas", () => {
    const getter = colDef(defVigencia(), HOY).filterValueGetter as (p: { data?: PrecioRow }) => string;

    expect(getter({ data: fila("a", FIJO_VIGENTE) })).toBe("Fijo hasta 30-11");
    expect(getter({ data: fila("b", FIJO_VENCIDO) })).toBe("Vencido 12-10");
    expect(getter({ data: fila("c") })).toBe("");
    expect(getter({})).toBe("");
  });
});

describe("columnas Precio fijo y Congelado: solo lo que rige", () => {
  const valor = (key: "precio_fijo" | "congelar", f: PrecioRow) => {
    const col = colDef(COLUMNAS_PRECIOS.find((c) => c.key === key)!);
    return (col.valueGetter as (p: { data?: PrecioRow }) => unknown)({ data: f });
  };

  it("un precio fijo vigente o sin periodo se ve", () => {
    expect(valor("precio_fijo", fila("a", FIJO_VIGENTE))).toBe(15000);
    expect(valor("precio_fijo", fila("b", { precio_fijo: 9990 }))).toBe(9990);
  });

  it("uno programado o vencido no se muestra como si rigiera", () => {
    expect(valor("precio_fijo", fila("a", FIJO_PROGRAMADO))).toBeNull();
    expect(valor("precio_fijo", fila("b", FIJO_VENCIDO))).toBeNull();
  });

  it("lo mismo con Congelado", () => {
    expect(valor("congelar", fila("a", { congelar: true, vigencia: "vigente" }))).toBe(true);
    expect(valor("congelar", fila("b", { congelar: true, vigencia: "vencida", vigente_hasta: "2026-10-12" }))).toBeNull();
  });

  it("en la grilla: el vencido no aparece en la columna Precio fijo", async () => {
    render(
      <TablaPrecios
        hoy={HOY} onFila={vi.fn()} columnasVisibles={["producto", "precio_fijo"]}
        rows={[fila("17 VIGENTE", FIJO_VIGENTE), fila("17 VENCIDO", FIJO_VENCIDO)]}
      />,
    );

    expect(await screen.findByText(formatoCLP(15000))).toBeInTheDocument();
    expect(screen.queryByText(formatoCLP(17000))).not.toBeInTheDocument();
  });
});
