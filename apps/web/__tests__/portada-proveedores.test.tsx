/**
 * Portada: la lista de proveedores del modal de sugerencia manual ("Varios
 * productos") sale de `GET /api/sugerido/opciones`.
 *
 * Antes la portada bajaba 5.000 filas del sugerido sin filtro (12 MB, 9 a 17 s en
 * Render) solo para sacar los proveedores de ahi, y le faltaban 57 de los 142: los
 * que tenian todas sus filas mas alla de la fila 5.000. Ademas ponia el doble de
 * lenta la carga de la tabla, que corre al mismo tiempo.
 */
import "@testing-library/jest-dom/vitest";
import { render, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import DashboardPage from "@/app/page";
import type { SugeridoFiltros } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  sugerido: vi.fn(),
  sugeridoOpciones: vi.fn(),
  sucursales: vi.fn(),
  kpis: vi.fn(),
  ultimaSincronizacion: vi.fn(),
  modal: vi.fn(),
  router: { replace: vi.fn(), push: vi.fn() },
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    sugerido: mocks.sugerido,
    sugeridoOpciones: mocks.sugeridoOpciones,
    sucursales: mocks.sucursales,
    kpis: mocks.kpis,
    ultimaSincronizacion: mocks.ultimaSincronizacion,
    exportExcel: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("@/lib/auth", () => ({
  getEmail: () => "comprador@ejemplo.cl",
  getEsAdmin: () => false,
  getEsVendedor: () => false,
  getPuedeActualizar: () => false,
  getSoloLectura: () => false,
}));

// Lo pesado de la pantalla (la grilla, los graficos) no interesa aca.
vi.mock("@/components/tabla-sugerido", async () => {
  const { forwardRef } = await import("react");
  return { TablaSugerido: forwardRef(() => null) };
});
vi.mock("@/components/kpi-cards", () => ({ KpiCards: () => null }));
vi.mock("@/components/graficos-dashboard", () => ({ GraficosDashboard: () => null }));
vi.mock("@/components/filtros-sugerido", () => ({ FiltrosSugerido: () => null }));
vi.mock("@/components/configurar-columnas", () => ({ ConfigurarColumnas: () => null }));
vi.mock("@/components/sincronizacion-manual", () => ({ SincronizacionManual: () => null }));
vi.mock("@/components/modal-sugerencia-manual", () => ({
  ModalSugerenciaManual: (props: { proveedores?: string[] }) => {
    mocks.modal(props);
    return null;
  },
}));

const PROVEEDORES = ["AGUACOL SpA", "ANDES RETAIL", "AUTO STOCK LTDA", "GILDEMEISTER"];

/** Los proveedores que recibio el modal en el ultimo render. */
function proveedoresDelModal(): string[] | undefined {
  const llamadas = mocks.modal.mock.calls;
  return llamadas.length ? llamadas[llamadas.length - 1][0].proveedores : undefined;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  mocks.sugerido.mockResolvedValue({ items: [], total: 0, page: 1, limit: 5000 });
  mocks.sugeridoOpciones.mockResolvedValue({
    proveedores: PROVEEDORES, marcas: [], tipos_origen: [], clases_abc: [], sucursales: [],
  });
  mocks.sucursales.mockResolvedValue([{ sucursal_id: "LIN", nombre: "LINDEROS" }]);
  mocks.kpis.mockResolvedValue(null);
  mocks.ultimaSincronizacion.mockResolvedValue({ creado_en: null, detalle: null });
});

describe("Portada: proveedores del modal de sugerencia manual", () => {
  it("salen de /api/sugerido/opciones, todos, y no de 5.000 filas sin filtro", async () => {
    render(<DashboardPage />);
    await waitFor(() => expect(proveedoresDelModal()).toEqual(PROVEEDORES));
    expect(mocks.sugeridoOpciones).toHaveBeenCalledTimes(1);

    // La unica lectura de filas es la de la grilla (con "solo pedir", ordenada).
    await waitFor(() => expect(mocks.sugerido).toHaveBeenCalled());
    for (const [filtros, opciones] of mocks.sugerido.mock.calls as [SugeridoFiltros, { sort?: string }][]) {
      expect(filtros.solo_pedir).toBe(true);
      expect(opciones.sort).toBe("-total_sugerido_suc");
    }
  });

  it("si fallan las sucursales, los proveedores llegan igual", async () => {
    mocks.sucursales.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<DashboardPage />);
    await waitFor(() => expect(proveedoresDelModal()).toEqual(PROVEEDORES));
  });

  it.each([
    // La API de antes no tiene la ruta: pasa mientras Render termina el deploy y
    // Vercel ya publico la web nueva.
    ["404 (API de antes)", new Error("Error 404 en /api/sugerido/opciones")],
    ["502 (Render reiniciandose)", new Error("Error 502 en /api/sugerido/opciones")],
  ])(
    "si falla la lista de opciones con %s, el modal usa los proveedores de la grilla",
    async (_caso, falla) => {
      mocks.sugeridoOpciones.mockRejectedValue(falla);
      mocks.sugerido.mockResolvedValue({
        items: [
          { proveedor: "GILDEMEISTER" }, { proveedor: "AGUACOL SpA" }, { proveedor: null },
          { proveedor: "GILDEMEISTER" },
        ],
        total: 4, page: 1, limit: 5000,
      });
      render(<DashboardPage />);
      await waitFor(() => expect(proveedoresDelModal()).toEqual(["AGUACOL SpA", "GILDEMEISTER"]));
      // No baja nada extra: la unica lectura de filas es la de la grilla.
      expect(mocks.sugerido).toHaveBeenCalledTimes(1);
    }
  );

  it("si la lista de opciones llega, manda ella aunque la grilla traiga menos", async () => {
    mocks.sugerido.mockResolvedValue({
      items: [{ proveedor: "GILDEMEISTER" }], total: 1, page: 1, limit: 5000,
    });
    render(<DashboardPage />);
    await waitFor(() => expect(proveedoresDelModal()).toEqual(PROVEEDORES));
  });
});
