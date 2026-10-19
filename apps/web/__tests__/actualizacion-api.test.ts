/**
 * El cliente del buzon del PC del motor (/api/actualizacion/solicitar) y de las
 * opciones del sugerido.
 *
 * - "Actualizar ahora" se pide SIN cuerpo, como siempre: es lo que entiende cualquier
 *   version de la API (sin cuerpo = recalcular).
 * - "Actualizar motor" manda {"tipo": "actualizar_motor"}.
 * - El error lleva el codigo: la tarjeta distingue el 409 (ya hay otra solicitud viva)
 *   y muestra el texto del servidor tal cual. Sin respuesta: el texto de siempre.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

let fetchMock: ReturnType<typeof vi.fn>;

async function cargar() {
  vi.resetModules();
  return import("@/lib/api-client");
}

function json(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("solicitarActualizacion", () => {
  it("recalcular va sin cuerpo", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(json({ id: "s1", tipo: "recalcular", estado: "pendiente" }));

    await api.solicitarActualizacion();
    const [url, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(url).toMatch(/\/api\/actualizacion\/solicitar$/);
    expect(init.method).toBe("POST");
    expect(init.body).toBeUndefined();
  });

  it("actualizar_motor manda el tipo", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(json({ id: "s2", tipo: "actualizar_motor", estado: "pendiente" }));

    const r = await api.solicitarActualizacion("actualizar_motor");
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit];
    expect(JSON.parse(String(init.body))).toEqual({ tipo: "actualizar_motor" });
    expect((init.headers as Record<string, string>)["Content-Type"]).toBe("application/json");
    expect(r.tipo).toBe("actualizar_motor");
  });

  it("un 409 trae el texto del servidor y el codigo", async () => {
    const { api } = await cargar();
    const detalle =
      "Ya hay un recálculo en curso (pedido a las 09:41). Tarda entre 25 y 40 minutos: espera " +
      "a que termine para pedir otra cosa.";
    fetchMock.mockResolvedValue(json({ detail: detalle }, 409));

    const e = await api.solicitarActualizacion("actualizar_motor").catch((x: unknown) => x);
    expect(e).toBeInstanceOf(Error);
    expect((e as Error).message).toBe(detalle);
    expect((e as { status: number }).status).toBe(409);
  });

  it("un 403 sin detalle dice que no se pudo pedir", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(new Response("", { status: 403 }));

    await expect(api.solicitarActualizacion("actualizar_motor")).rejects.toThrow(
      "No se pudo pedir la actualización del motor"
    );
  });

  it("sin respuesta del servidor, el texto de siempre en vez de 'Failed to fetch'", async () => {
    const { api, MENSAJE_SIN_SERVIDOR } = await cargar();
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    const e = await api.solicitarActualizacion().catch((x: unknown) => x);
    expect((e as Error).message).toBe(MENSAJE_SIN_SERVIDOR);
    expect((e as { status: number }).status).toBe(0);
  });
});

describe("sugeridoOpciones", () => {
  it("lee /api/sugerido/opciones", async () => {
    const { api } = await cargar();
    const opciones = { proveedores: ["A", "B"], marcas: [], tipos_origen: [], clases_abc: [], sucursales: [] };
    fetchMock.mockResolvedValue(json(opciones));

    expect(await api.sugeridoOpciones()).toEqual(opciones);
    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/sugerido\/opciones$/);
  });
});
