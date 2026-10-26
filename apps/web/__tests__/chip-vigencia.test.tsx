/**
 * El chip de vigencia («Fijo hasta 30-11», «Programado desde 05-11», «Vencido 12-10»).
 *
 * Lo que importa cuidar: cada estado tiene su propio ícono Y su propia palabra (el color
 * nunca es la única señal), el title trae la frase completa, y cuando no hay nada que
 * decir no dibuja nada -ni un «undefined», ni un chip vacío.
 */
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ChipVigencia } from "@/components/chip-vigencia";
import type { PrecioRow } from "@/lib/types";

const HOY = "2026-10-20";
const fijo = { precio_fijo: 12990, margen_fijo: null, congelar: false };

function chip(fila: Partial<PrecioRow>) {
  return render(<ChipVigencia fila={{ ...fijo, ...fila }} hoy={HOY} />);
}

describe("ChipVigencia", () => {
  it("vigente lejos: texto con la fecha, neutro, con el title completo", () => {
    chip({ vigencia: "vigente", vigente_hasta: "2026-11-30", vigencia_dias: 41 });

    const el = screen.getByTestId("chip-vigencia");
    expect(el).toHaveTextContent("Fijo hasta 30-11");
    expect(el).toHaveAttribute("data-tono", "lejos");
    expect(el).toHaveAttribute("title", "Precio fijo hasta el 30-11-2026 incluido. El 01-12-2026 vuelve a la regla.");
    expect(el.querySelector('[data-icono="calendario-reloj"]')).not.toBeNull();
  });

  it("vence en una semana: ámbar Y con los días escritos (no solo color)", () => {
    chip({ vigencia: "vigente", vigente_hasta: "2026-10-23", vigencia_dias: 3 });

    const el = screen.getByTestId("chip-vigencia");
    expect(el).toHaveTextContent("Fijo hasta 23-10 (3 días)");
    expect(el.className).toContain("amber");
    expect(el.querySelector('[data-icono="reloj-arena"]')).not.toBeNull();
  });

  it("mañana y hoy se leen como palabras", () => {
    const { unmount } = chip({ vigencia: "vigente", vigente_hasta: "2026-10-21", vigencia_dias: 1 });
    expect(screen.getByTestId("chip-vigencia")).toHaveTextContent("Fijo hasta mañana");
    unmount();
    chip({ vigencia: "vigente", vigente_hasta: HOY, vigencia_dias: 0 });
    expect(screen.getByTestId("chip-vigencia")).toHaveTextContent("Fijo hasta hoy");
  });

  it("programada: «Programado desde 05-11» con su propio ícono", () => {
    chip({ vigencia: "programada", vigente_desde: "2026-11-05", vigente_hasta: "2026-11-30" });

    const el = screen.getByTestId("chip-vigencia");
    expect(el).toHaveTextContent("Programado desde 05-11");
    expect(el).toHaveAttribute("data-tono", "programado");
    expect(el.querySelector('[data-icono="calendario-rango"]')).not.toBeNull();
    expect(el.getAttribute("title")).toContain("Hasta entonces el producto sigue la regla");
  });

  it("vencida: «Vencido 12-10» con su propio ícono", () => {
    chip({ vigencia: "vencida", vigente_hasta: "2026-10-12", vigencia_dias: 8 });

    const el = screen.getByTestId("chip-vigencia");
    expect(el).toHaveTextContent("Vencido 12-10");
    expect(el).toHaveAttribute("data-tono", "vencido");
    expect(el.querySelector('[data-icono="calendario-x"]')).not.toBeNull();
    expect(el.getAttribute("title")).toBe("Precio fijo vencido el 12-10-2026: el producto volvió a la regla.");
  });

  it("los cuatro estados se distinguen por ícono y por palabra", () => {
    const casos: Partial<PrecioRow>[] = [
      { vigencia: "vigente", vigente_hasta: "2026-11-30", vigencia_dias: 41 },
      { vigencia: "vigente", vigente_hasta: "2026-10-23", vigencia_dias: 3 },
      { vigencia: "programada", vigente_desde: "2026-11-05" },
      { vigencia: "vencida", vigente_hasta: "2026-10-12" },
    ];
    const iconos = new Set<string>();
    const textos = new Set<string>();
    for (const c of casos) {
      const { unmount } = chip(c);
      const el = screen.getByTestId("chip-vigencia");
      iconos.add(el.querySelector("[data-icono]")?.getAttribute("data-icono") ?? "");
      textos.add(el.textContent ?? "");
      unmount();
    }
    expect(iconos.size).toBe(4);
    expect(textos.size).toBe(4);
  });

  it("el sustantivo sale de la decisión: congelado y margen", () => {
    const { unmount } = chip({ vigencia: "vigente", vigente_hasta: "2026-11-30", vigencia_dias: 41, precio_fijo: null, congelar: true });
    expect(screen.getByTestId("chip-vigencia")).toHaveTextContent("Congelado hasta 30-11");
    unmount();
    chip({ vigencia: "vigente", vigente_hasta: "2026-11-30", vigencia_dias: 41, precio_fijo: null, margen_fijo: 35 });
    expect(screen.getByTestId("chip-vigencia")).toHaveTextContent("Margen hasta 30-11");
  });

  it("sin periodo no dibuja nada", () => {
    const { container } = chip({ vigencia: null });
    expect(container).toBeEmptyDOMElement();
  });

  it("sin la propiedad (una API anterior) tampoco", () => {
    const { container } = render(<ChipVigencia fila={fijo} hoy={HOY} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("vigente sin Hasta (el precio queda fijo hasta que alguien lo cambie) no dibuja nada", () => {
    const { container } = chip({ vigencia: "vigente", vigente_desde: "2026-10-01", vigente_hasta: null });
    expect(container).toBeEmptyDOMElement();
  });

  it("nunca imprime undefined, null ni NaN", () => {
    const casos: Partial<PrecioRow>[] = [
      { vigencia: "vigente", vigente_hasta: "2026-10-23" },
      { vigencia: "programada", vigente_desde: "2026-11-05" },
      { vigencia: "vencida", vigente_hasta: null },
    ];
    for (const c of casos) {
      const { container, unmount } = chip(c);
      expect(container.innerHTML).not.toMatch(/undefined|null|NaN/);
      unmount();
    }
  });
});
