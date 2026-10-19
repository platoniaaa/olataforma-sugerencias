/**
 * El Excel de la grilla y la orden de compra dicen por que no se pudieron bajar.
 *
 * Mientras se carga el sugerido del dia (o hay otra descarga grande en curso) la API
 * responde 503 con el motivo: las dos juntas pasaban los 512 MB de Render. La
 * pantalla lo muestra tal cual; antes decia siempre "No se pudo generar el archivo".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let fetchMock: ReturnType<typeof vi.fn>;

async function cargar() {
  vi.resetModules();
  return import("@/lib/api-client");
}

const MOTIVO = "Se está cargando el sugerido del día; intenta en un minuto.";

function json(cuerpo: unknown, status: number): Response {
  return new Response(JSON.stringify(cuerpo), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("descargas con la API ocupada", () => {
  it("el Excel de la grilla muestra el motivo del 503", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(json({ detail: MOTIVO }, 503));
    await expect(api.exportExcel({}, [], "-total_sugerido_suc")).rejects.toThrow(MOTIVO);
  });

  it("la orden de compra tambien", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(json({ detail: MOTIVO }, 503));
    await expect(api.exportOrden({ solo_pedir: true })).rejects.toThrow(MOTIVO);
  });

  it("sin motivo en la respuesta, el texto de siempre", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(new Response("Internal Server Error", { status: 500 }));
    await expect(api.exportExcel({}, [], "-total_sugerido_suc")).rejects.toThrow(
      "No se pudo generar el archivo"
    );
  });
});
