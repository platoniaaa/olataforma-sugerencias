/**
 * Inventario ciclico: la semana siempre se guarda por su lunes, y la tarjeta de
 * conteo de bodega manda al backend exactamente lo que se tipeo.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Conteo } from "@/components/inventario-ciclico/conteo";
import type { ItemInventario } from "@/lib/inventario-ciclico";

const mocks = vi.hoisted(() => ({ req: vi.fn() }));

vi.mock("@/lib/api-client", () => ({
  req: mocks.req,
  mensajeError: vi.fn().mockResolvedValue("error"),
}));

import { etiquetaSemana, lunesDe } from "@/lib/inventario-ciclico";

function item(over: Partial<ItemInventario> = {}): ItemInventario {
  return {
    id: "i1",
    semana: "2026-09-21",
    sucursal_id: "LINDEROS",
    producto: "P-A",
    descripcion: "Filtro aceite",
    clase: "A",
    cantidad_sistema: 10,
    costo_unitario: 1000,
    requiere_evidencia: false,
    cantidad_contada: null,
    observacion: null,
    contado_por: null,
    contado_en: null,
    diferencia: null,
    diferencia_valor: null,
    estado: "pendiente",
    evidencias: [],
    ...over,
  };
}

describe("semanas", () => {
  it("cualquier dia cae en su lunes", () => {
    expect(lunesDe(new Date(2026, 8, 23))).toBe("2026-09-21"); // miercoles
    expect(lunesDe(new Date(2026, 8, 27))).toBe("2026-09-21"); // domingo
    expect(lunesDe(new Date(2026, 8, 21))).toBe("2026-09-21"); // lunes
  });

  it("etiqueta en formato chileno", () => {
    expect(etiquetaSemana("2026-09-21")).toBe("Semana del 21-09-2026");
  });
});

describe("Conteo", () => {
  it("muestra el avance y guarda la cantidad contada", async () => {
    const guardado = item({ cantidad_contada: 8, diferencia: -2, estado: "con_diferencia" });
    mocks.req.mockResolvedValue(new Response(JSON.stringify(guardado), { status: 200 }));
    const onCambio = vi.fn();
    render(
      <Conteo items={[item(), item({ id: "i2", producto: "P-B", cantidad_contada: 3 })]} esAdmin={false} onCambio={onCambio} />
    );

    expect(screen.getByText("1 de 2 contados")).toBeInTheDocument();

    const [input] = screen.getAllByLabelText("Contado");
    fireEvent.change(input, { target: { value: "8" } });
    fireEvent.click(screen.getAllByRole("button", { name: /Guardar/ })[0]);

    await waitFor(() => expect(onCambio).toHaveBeenCalledWith(guardado));
    const [ruta, init] = mocks.req.mock.calls[0];
    expect(ruta).toBe("/api/inventario-ciclico/items/i1");
    expect(JSON.parse(init.body)).toEqual({ cantidad_contada: 8 });
  });

  it("avisa cuando el producto requiere evidencia", () => {
    render(<Conteo items={[item({ requiere_evidencia: true })]} esAdmin={false} onCambio={() => {}} />);
    expect(screen.getByText("Este producto requiere evidencia.")).toBeInTheDocument();
  });
});
