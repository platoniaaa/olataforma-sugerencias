/**
 * Guardar sin fecha límite crea una sugerencia que no vence nunca: sigue sumando las
 * mismas unidades a la compra todos los días hasta que alguien la borre a mano. Pasó
 * en producción (carga masiva del 28-07-2026, 95 productos sin fecha), así que el
 * modal tiene que pedir confirmación explícita antes de dejarlo pasar.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ModalSugerenciaManual } from "@/components/modal-sugerencia-manual";
import type { Sucursal } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  crearSugerenciaManual: vi.fn().mockResolvedValue({}),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    crearSugerenciaManual: mocks.crearSugerenciaManual,
    crearSugerenciaMasiva: vi.fn(),
    crearRecurrente: vi.fn(),
    productos: vi.fn().mockResolvedValue({ items: [] }),
    contar: vi.fn().mockResolvedValue(0),
    // La vista previa no es parte de lo que se prueba aquí; al fallar deja preview
    // en null, que es el mismo estado que antes de tipear.
    previsualizarDias: vi.fn().mockRejectedValue(new Error("sin preview")),
    previsualizarObjetivo: vi.fn().mockRejectedValue(new Error("sin preview")),
  },
}));

const sucursales = [{ sucursal_id: "LINDEROS", nombre: "LINDEROS" }] as Sucursal[];

function montar() {
  return render(
    <ModalSugerenciaManual
      open
      onClose={() => {}}
      onGuardado={() => {}}
      sucursales={sucursales}
      productoInicial="ABC123"
      sucursalInicial="LINDEROS"
      soloIndividual
    />
  );
}

const AVISO = /Esto no va a vencer nunca/i;

describe("ModalSugerenciaManual · fecha límite", () => {
  it("no guarda sin fecha límite: primero pide confirmación", async () => {
    mocks.crearSugerenciaManual.mockClear();
    montar();

    fireEvent.change(screen.getByLabelText(/Días de inventario/i), {
      target: { value: "30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(await screen.findByText(AVISO)).toBeInTheDocument();
    expect(mocks.crearSugerenciaManual).not.toHaveBeenCalled();
  });

  it("confirmando el aviso guarda igual, sin vencimiento", async () => {
    mocks.crearSugerenciaManual.mockClear();
    montar();

    fireEvent.change(screen.getByLabelText(/Días de inventario/i), {
      target: { value: "30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    fireEvent.click(await screen.findByRole("button", { name: /Guardar sin fecha límite/i }));

    await waitFor(() => expect(mocks.crearSugerenciaManual).toHaveBeenCalledTimes(1));
    expect(mocks.crearSugerenciaManual).toHaveBeenCalledWith(
      expect.objectContaining({ dias_inventario: 30, expira_en: undefined })
    );
  });

  it("'Volver y poner fecha' cierra el aviso sin guardar nada", async () => {
    mocks.crearSugerenciaManual.mockClear();
    montar();

    fireEvent.change(screen.getByLabelText(/Días de inventario/i), {
      target: { value: "30" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    fireEvent.click(await screen.findByRole("button", { name: /Volver y poner fecha/i }));

    await waitFor(() => expect(screen.queryByText(AVISO)).not.toBeInTheDocument());
    expect(mocks.crearSugerenciaManual).not.toHaveBeenCalled();
  });

  it("con fecha límite guarda directo, sin preguntar", async () => {
    mocks.crearSugerenciaManual.mockClear();
    montar();

    fireEvent.change(screen.getByLabelText(/Días de inventario/i), {
      target: { value: "30" },
    });
    fireEvent.change(screen.getByLabelText(/Fecha límite/i), {
      target: { value: "2099-01-15" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(mocks.crearSugerenciaManual).toHaveBeenCalledTimes(1));
    expect(mocks.crearSugerenciaManual).toHaveBeenCalledWith(
      expect.objectContaining({ expira_en: "2099-01-15" })
    );
    expect(screen.queryByText(AVISO)).not.toBeInTheDocument();
  });

  it("el formulario incompleto se avisa antes que la fecha límite", () => {
    mocks.crearSugerenciaManual.mockClear();
    montar();

    // Sin cantidad: el aviso de vencimiento no debe tapar el error de validación.
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    expect(screen.getByText(/Ingresa los días de inventario/i)).toBeInTheDocument();
    expect(screen.queryByText(AVISO)).not.toBeInTheDocument();
  });
});
