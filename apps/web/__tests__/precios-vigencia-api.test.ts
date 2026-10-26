/**
 * El cliente de la lista de precios con vigencia: el filtro viaja repetido (una union en la
 * API) y las fechas de la ficha viajan solo si la persona las cambió.
 *
 * Un `vigencia` mal serializado no da error: devuelve 0 filas sin avisar. Por eso se mira la
 * URL exacta.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let fetchMock: ReturnType<typeof vi.fn>;

async function cargar() {
  vi.resetModules();
  return import("@/lib/api-client");
}

beforeEach(() => {
  fetchMock = vi.fn(async () => new Response(JSON.stringify({ items: [], total: 0, page: 1, limit: 50 }), { status: 200 }));
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

function consulta(i = 0): URLSearchParams {
  const url = String(fetchMock.mock.calls[i][0]);
  return new URL(url, "http://localhost").searchParams;
}

describe("api.precios: filtro de vigencia", () => {
  it("viaja repetido, un parámetro por valor", async () => {
    const { api } = await cargar();

    await api.precios({ vigencia: ["vigente", "vence_7d", "vencida"] });

    expect(consulta().getAll("vigencia")).toEqual(["vigente", "vence_7d", "vencida"]);
    expect(String(fetchMock.mock.calls[0][0])).toContain("vigencia=vigente&vigencia=vence_7d&vigencia=vencida");
  });

  it("sin valores no manda el parámetro", async () => {
    const { api } = await cargar();

    await api.precios({});
    await api.precios({ vigencia: [] });

    expect(consulta(0).has("vigencia")).toBe(false);
    expect(consulta(1).has("vigencia")).toBe(false);
  });

  it("convive con los otros filtros sin pisarlos", async () => {
    const { api } = await cargar();

    await api.precios({ estado: ["FIJO"], vigencia: ["programada"], con_stock: true }, { page: 2, limit: 100 });

    const p = consulta();
    expect(p.getAll("estado")).toEqual(["FIJO"]);
    expect(p.getAll("vigencia")).toEqual(["programada"]);
    expect(p.get("con_stock")).toBe("true");
    expect(p.get("page")).toBe("2");
  });
});

describe("api.guardarPrecioOverride: las fechas", () => {
  async function guardar(payload: Parameters<Awaited<ReturnType<typeof cargar>>["api"]["guardarPrecioOverride"]>[1]) {
    const { api } = await cargar();
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ producto: "71 X" }), { status: 200 }));
    await api.guardarPrecioOverride("71 X", payload);
    return JSON.parse(fetchMock.mock.calls[0][1].body as string) as Record<string, unknown>;
  }

  it("manda las fechas cuando vienen y null para quitar un lado", async () => {
    const cuerpo = await guardar({ precio_fijo: 15000, vigente_desde: "2026-11-05", vigente_hasta: null });

    expect(cuerpo).toEqual({ precio_fijo: 15000, vigente_desde: "2026-11-05", vigente_hasta: null });
  });

  it("si no vienen, no viajan (ausente = no tocar)", async () => {
    const cuerpo = await guardar({ precio_fijo: 15000 });

    expect(cuerpo).not.toHaveProperty("vigente_desde");
    expect(cuerpo).not.toHaveProperty("vigente_hasta");
  });

  it("un 422 de la API se muestra con su mensaje", async () => {
    const { api } = await cargar();
    fetchMock.mockImplementation(async () => new Response(
      JSON.stringify({ detail: "El Desde no puede ser posterior al Hasta." }),
      { status: 422, headers: { "Content-Type": "application/json" } },
    ));

    await expect(api.guardarPrecioOverride("71 X", { vigente_desde: "2026-12-01", vigente_hasta: "2026-11-01" }))
      .rejects.toThrow("El Desde no puede ser posterior al Hasta.");
  });
});
