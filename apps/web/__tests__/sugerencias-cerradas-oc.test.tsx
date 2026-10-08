/**
 * La página de sugerencias manuales muestra las que se cerraron solas porque
 * apareció su OC en el ERP, con la OC que las cerró. El ERP no dice por qué se hizo
 * una OC: si la que la cerró no tenía nada que ver, la persona tiene que poder
 * verlo para volver a crearla.
 */
import "@testing-library/jest-dom/vitest";
import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import SugerenciasManualesPage from "@/app/sugerencias-manuales/page";

const mocks = vi.hoisted(() => ({
  cerradas: vi.fn(),
  cerrada: {
    id: "s1",
    producto: "83 1109120U8710",
    sucursal_id: "CD REPUESTOS",
    nombre_sucursal: "CD Repuestos",
    unidades: 1,
    creado_en: "2026-08-03T15:00:00Z",
    aprobado: false,
    usado_en_compra: false,
    archivada: true,
    cerrada_por_oc: "5758",
    cerrada_oc_fecha: "2026-08-04",
    cerrada_oc_unidades: 1,
    cerrada_en: "2026-10-09T12:40:00Z",
  },
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    sugerenciasManuales: vi.fn().mockResolvedValue([]),
    recurrentes: vi.fn().mockResolvedValue([]),
    instockResumen: vi.fn().mockRejectedValue(new Error("sin instock")),
    sugerenciasCerradasPorOc: mocks.cerradas,
  },
}));

// Con llaves: si beforeEach devuelve una funcion, vitest la llama al terminar la
// prueba como limpieza, y mockReset() devuelve el propio mock.
beforeEach(() => {
  mocks.cerradas.mockReset();
});

describe("Sugerencias manuales · cerradas por su OC", () => {
  it("muestra la OC que cerró cada una", async () => {
    mocks.cerradas.mockResolvedValue([mocks.cerrada]);
    render(<SugerenciasManualesPage />);

    expect(await screen.findByText("Cerradas por su OC · últimos 14 días")).toBeInTheDocument();
    expect(screen.getByText(/OC N° 5758 del 04-08-2026/)).toBeInTheDocument();
    expect(screen.getByText(/vuelve a crearla/)).toBeInTheDocument();
  });

  it("sin cerradas no aparece la sección, y la lista vacía explica cómo crear una", async () => {
    mocks.cerradas.mockResolvedValue([]);
    render(<SugerenciasManualesPage />);

    expect(await screen.findByText(/No hay sugerencias únicas vigentes/)).toHaveTextContent(
      "una sola vez"
    );
    expect(screen.queryByText(/Cerradas por su OC/)).not.toBeInTheDocument();
  });

  it("si la consulta falla, la página se ve igual", async () => {
    mocks.cerradas.mockImplementation(async () => {
      throw new Error("despliegue viejo");
    });
    render(<SugerenciasManualesPage />);
    // Que la consulta ocurra dentro de la prueba: la falla la ataja la pagina.
    await waitFor(() => expect(mocks.cerradas).toHaveBeenCalled());
    expect(await screen.findByText(/No hay sugerencias únicas vigentes/)).toBeInTheDocument();
    expect(screen.queryByText(/Cerradas por su OC/)).not.toBeInTheDocument();
  });
});
