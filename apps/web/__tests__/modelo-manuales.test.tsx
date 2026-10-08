/**
 * El modulo Modelo explica la pestana de sugerencias manuales (pedido de Ignacio,
 * 08-10-2026): que hace cada modo -Dias, Unidades, Mantener stock- y cada tipo
 * -Individual, Por grupo, Todos, Pegar lista-. Lo que se fija aca es que la
 * seccion exista, que este en el indice y que el ejemplo cuadre con la regla de
 * `sugerido_service._faltante_para_objetivo`.
 */
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ModeloPage from "@/app/modelo/page";

describe("Modelo: sugerencias manuales", () => {
  it("esta en el indice y tiene su seccion", () => {
    const { container } = render(<ModeloPage />);
    expect(screen.getByRole("link", { name: "Sugerencias manuales" })).toHaveAttribute("href", "#manuales");
    expect(container.querySelector("section#manuales")).not.toBeNull();
  });

  it("explica los tres modos y los cuatro tipos", () => {
    const { container } = render(<ModeloPage />);
    const texto = container.querySelector("section#manuales")?.textContent ?? "";
    for (const palabra of ["Días", "Unidades", "Mantener stock", "Individual", "Por grupo", "Todos", "Pegar lista",
      "Fecha límite", "Repetir periódicamente"]) {
      expect(texto).toContain(palabra);
    }
    expect(texto).toContain("Las unidades se calculan una sola vez");
  });

  it("el ejemplo cuadra con la regla: nivel menos stock, transito y sugerido del sistema", () => {
    const demanda = 0.8, stock = 5, transito = 2, sistema = 3;
    const nivelDias = Math.ceil(demanda * 30);
    const faltante = (nivel: number) => Math.max(0, Math.ceil(nivel - (stock + transito + sistema)));
    expect(nivelDias).toBe(24);
    expect(faltante(nivelDias)).toBe(14);
    expect(faltante(12)).toBe(2);

    const { container } = render(<ModeloPage />);
    const texto = container.querySelector("section#manuales")?.textContent ?? "";
    expect(texto).toContain("0,8 × 30 = 24 → 24 − 5 − 2 − 3");
    expect(texto).toContain("17 (los 3 del sistema + 14)");
    expect(texto).toContain("5 (3 + 2)");
  });
});
