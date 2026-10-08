/**
 * El modulo Modelo explica la pestana de sugerencias manuales. Desde el 08-10-2026
 * el modal funciona con tres frases (una sola vez, nunca menos de N, que alcance
 * para N dias de venta): la seccion tiene que contar eso, estar en el indice y su
 * ejemplo tiene que cuadrar con `sugerido_service._faltante_para_objetivo` y con
 * lo que muestra el modal (`lib/pedido-especial.ts`).
 */
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import ModeloPage from "@/app/modelo/page";
import { calcular } from "@/lib/pedido-especial";
import type { ContextoSugerencia } from "@/lib/types";

const texto = () =>
  render(<ModeloPage />).container.querySelector("section#manuales")?.textContent ?? "";

describe("Modelo: sugerencias manuales", () => {
  it("esta en el indice y tiene su seccion", () => {
    const { container } = render(<ModeloPage />);
    expect(screen.getByRole("link", { name: "Sugerencias manuales" })).toHaveAttribute("href", "#manuales");
    expect(container.querySelector("section#manuales")).not.toBeNull();
  });

  it("explica las tres frases, el reemplazo, cuando se borra y las tres pestanas", () => {
    const t = texto();
    for (const palabra of [
      "una sola vez", "nunca haya menos de", "días de venta",
      "Reemplazarla", "Sumar las dos", "Cuando su compra aparece en el ERP", "a los 7 días",
      "Queda anotada la OC que la cerró",
      "Un producto", "Varios productos", "Pegar lista",
    ]) {
      expect(t).toContain(palabra);
    }
    expect(t).toContain("Las reglas se recalculan todos los días");
    // Lo que ya no existe en el modal no se sigue explicando, y el boton de marcar
    // como pedido no lo usa nadie: no puede ser lo que cierra una sugerencia.
    expect(t).not.toContain("Repetir periódicamente");
    expect(t).not.toContain("como pedid");
  });

  it("el ejemplo cuadra con lo que calcula el modal", () => {
    const ctx: ContextoSugerencia = {
      stock: 5, transito: 2, sugerido_sistema: 3, demanda_diaria: 0.8, en_sugerido: true,
      bodegas: [], vigentes: [], reglas: [],
    };
    expect(calcular("una", ctx, 7)?.total).toBe(10);
    expect(calcular("min", ctx, 12)).toMatchObject({ tuyas: 2, total: 5 });
    expect(calcular("dias", ctx, 30)).toMatchObject({ tuyas: 14, total: 17 });

    const t = texto();
    expect(t).toContain("10 (los 3 del sistema + 7)");
    expect(t).toContain("5 (3 + 2)");
    expect(t).toContain("0,8 × 30 = 24 → 24 − 5 − 2 − 3");
    expect(t).toContain("17 (3 + 14)");
  });
});
