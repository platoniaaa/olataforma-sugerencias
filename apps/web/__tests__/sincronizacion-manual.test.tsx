/**
 * "Actualizar ahora" en /cargar: la tarjeta de la tarea diaria dice 09:30 y "las
 * carpetas de Fuentes de datos"; el boton de abajo no puede decir otra hora ni otra
 * carpeta. La version compacta (la del inicio, que ve el equipo) no trae ese parrafo.
 */
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SincronizacionManual } from "@/components/sincronizacion-manual";

const mocks = vi.hoisted(() => ({ actualizacionEstado: vi.fn() }));

vi.mock("@/lib/api-client", () => ({
  api: { actualizacionEstado: mocks.actualizacionEstado, solicitarActualizacion: vi.fn() },
}));

const ESTADO = {
  id: null, estado: null, mensaje: null, solicitado_por: null, creado_en: null, terminado_en: null,
  ultima_sincronizacion: null, puede_actualizar: true,
};

beforeEach(() => {
  mocks.actualizacionEstado.mockReset();
  mocks.actualizacionEstado.mockResolvedValue(ESTADO);
});

describe("SincronizacionManual", () => {
  it("en /cargar dice la misma hora y las mismas carpetas que la tarea diaria", async () => {
    render(<SincronizacionManual />);
    const texto = await screen.findByText(/Si la tarea de las 09:30 no corrió/);
    expect(texto).toHaveTextContent(/con los Excel de las carpetas de Fuentes de datos/);
    expect(screen.queryByText(/10:00/)).not.toBeInTheDocument();
  });
});
