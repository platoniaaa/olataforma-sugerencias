/**
 * La descarga del archivo del ERP no se rinde a la primera.
 *
 * El 09-10-2026 un usuario vio "Failed to fetch" al bajar "Solo diferencias": el
 * servidor de Render se estaba reiniciando. `fetch` rechaza con TypeError cuando
 * no hay una respuesta utilizable, y la pantalla mostraba ese texto crudo. Ahora
 * reintenta solo y, si no vuelve, dice qué pasó. Como el archivo del ERP registra
 * un envío al descargarse, cada descarga lleva un identificador: si la respuesta se
 * pierde, el reintento recibe el mismo archivo y no uno vacío.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const respuesta = (status: number, cuerpo = "SKU;Precio_Optimo;Descuento\r\n") =>
  new Response(cuerpo, {
    status,
    headers: { "X-Filas": "7", "Content-Disposition": 'attachment; filename="precios.csv"' },
  });

const caida = () => new TypeError("Failed to fetch");

let fetchMock: ReturnType<typeof vi.fn>;

async function cargar() {
  vi.resetModules();
  return import("@/lib/api-client");
}

/** El parámetro `lote` de cada llamada a fetch. */
const lotes = () =>
  fetchMock.mock.calls.map((c) => new URL(String(c[0])).searchParams.get("lote"));

beforeEach(() => {
  vi.useFakeTimers();
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
  URL.createObjectURL = vi.fn(() => "blob:prueba");
  URL.revokeObjectURL = vi.fn();
  vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});

afterEach(() => {
  vi.useRealTimers();
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe("reqConReintentos", () => {
  it("reintenta un corte de conexión y devuelve la respuesta", async () => {
    const { reqConReintentos } = await cargar();
    fetchMock.mockRejectedValueOnce(caida()).mockResolvedValueOnce(respuesta(200));
    const avisos: [number, number][] = [];

    const p = reqConReintentos("/x", {}, { esperasMs: [10, 10], alReintentar: (i, t) => avisos.push([i, t]) });
    await vi.advanceTimersByTimeAsync(10);

    expect((await p).status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(2);
    expect(avisos).toEqual([[1, 2]]);
  });

  it("reintenta las caídas del proxy: 502, 503 y 504", async () => {
    const { reqConReintentos } = await cargar();
    fetchMock
      .mockResolvedValueOnce(respuesta(502))
      .mockResolvedValueOnce(respuesta(503))
      .mockResolvedValueOnce(respuesta(504))
      .mockResolvedValueOnce(respuesta(200));

    const p = reqConReintentos("/x", {}, { esperasMs: [5, 5, 5] });
    await vi.advanceTimersByTimeAsync(15);

    expect((await p).status).toBe(200);
    expect(fetchMock).toHaveBeenCalledTimes(4);
  });

  it("no reintenta un error de verdad: 404 y 500 se entregan tal cual", async () => {
    const { reqConReintentos } = await cargar();
    for (const status of [404, 500]) {
      fetchMock.mockReset();
      fetchMock.mockResolvedValue(respuesta(status));
      expect((await reqConReintentos("/x", {}, { esperasMs: [5, 5] })).status).toBe(status);
      expect(fetchMock).toHaveBeenCalledTimes(1);
    }
  });

  it("se rinde cuando se acaban los reintentos", async () => {
    const { reqConReintentos } = await cargar();
    fetchMock.mockRejectedValue(caida());

    const p = reqConReintentos("/x", {}, { esperasMs: [5, 5] }).catch((e) => e);
    await vi.advanceTimersByTimeAsync(10);

    expect(await p).toBeInstanceOf(TypeError);
    expect(fetchMock).toHaveBeenCalledTimes(3);
  });

  it("un error que no es de red no se reintenta", async () => {
    const { reqConReintentos } = await cargar();
    fetchMock.mockRejectedValue(new Error("otra cosa"));
    await expect(reqConReintentos("/x", {}, { esperasMs: [5] })).rejects.toThrow("otra cosa");
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});

describe("exportarPrecios", () => {
  it("el archivo del ERP lleva un identificador y lo repite en cada reintento", async () => {
    const { api } = await cargar();
    fetchMock.mockRejectedValueOnce(caida()).mockResolvedValueOnce(respuesta(200));

    const p = api.exportarPrecios({ soloDiferencias: true, formato: "erp" });
    await vi.advanceTimersByTimeAsync(3_000);

    expect(await p).toBe(7);
    const [primero, segundo] = lotes();
    expect(primero).toMatch(/^[0-9a-f-]{36}$/);
    expect(segundo).toBe(primero);
  });

  it("avisa cada reintento para que la pantalla lo muestre", async () => {
    const { api } = await cargar();
    fetchMock.mockRejectedValueOnce(caida()).mockResolvedValueOnce(respuesta(200));
    const avisos: [number, number][] = [];

    const p = api.exportarPrecios({ soloDiferencias: true, formato: "erp" }, (i, t) => avisos.push([i, t]));
    await vi.advanceTimersByTimeAsync(3_000);
    await p;

    expect(avisos).toEqual([[1, 4]]);
  });

  it("una descarga que llegó completa deja la siguiente con otro identificador", async () => {
    const { api } = await cargar();
    fetchMock.mockImplementation(async () => respuesta(200));

    await api.exportarPrecios({ soloDiferencias: true, formato: "erp" });
    await api.exportarPrecios({ soloDiferencias: true, formato: "erp" });

    const [a, b] = lotes();
    expect(a).not.toBe(b);
  });

  it("si la descarga falló, el próximo clic usa el mismo identificador", async () => {
    // El servidor pudo haber registrado el envío antes de que se perdiera la
    // respuesta: con otro identificador, el segundo clic bajaría un archivo vacío.
    const { api } = await cargar();
    fetchMock.mockImplementation(async () => respuesta(500));
    await expect(api.exportarPrecios({ soloDiferencias: true, formato: "erp" })).rejects.toThrow();
    const fallido = lotes()[0];
    expect(fallido).toMatch(/^[0-9a-f-]{36}$/);

    // El segundo clic reutiliza el identificador del intento que falló...
    fetchMock.mockReset();
    fetchMock.mockImplementation(async () => respuesta(200));
    await api.exportarPrecios({ soloDiferencias: true, formato: "erp" });
    expect(lotes()[0]).toBe(fallido);

    // ...y como esta vez el archivo llegó, el tercero ya es otra descarga.
    fetchMock.mockReset();
    fetchMock.mockImplementation(async () => respuesta(200));
    await api.exportarPrecios({ soloDiferencias: true, formato: "erp" });
    expect(lotes()[0]).not.toBe(fallido);
  });

  it("la lista completa no manda identificador: no registra ningún envío", async () => {
    const { api } = await cargar();
    fetchMock.mockImplementation(async () => respuesta(200));
    await api.exportarPrecios({ soloDiferencias: false, formato: "completa" });
    expect(lotes()).toEqual([null]);
  });

  it("si el servidor no vuelve, dice qué pasó y no 'Failed to fetch'", async () => {
    const { api, MENSAJE_SIN_SERVIDOR } = await cargar();
    fetchMock.mockRejectedValue(caida());

    const p = api.exportarPrecios({ soloDiferencias: true, formato: "erp" }).catch((e) => e);
    await vi.advanceTimersByTimeAsync(3_000 + 8_000 + 20_000 + 45_000);

    const e = await p;
    expect(e).toBeInstanceOf(Error);
    expect(e.message).toBe(MENSAJE_SIN_SERVIDOR);
    expect(e.message).not.toMatch(/failed to fetch/i);
    expect(fetchMock).toHaveBeenCalledTimes(5);
  });

  it("un 503 que no se levanta tampoco muestra un mensaje mudo", async () => {
    const { api, MENSAJE_SIN_SERVIDOR } = await cargar();
    fetchMock.mockImplementation(async () => respuesta(503, "<html>Service Unavailable</html>"));

    const p = api.exportarPrecios({ soloDiferencias: true, formato: "erp" }).catch((e) => e);
    await vi.advanceTimersByTimeAsync(80_000);

    expect((await p).message).toBe(MENSAJE_SIN_SERVIDOR);
  });

  it("un error del servidor con detalle se muestra tal cual", async () => {
    const { api } = await cargar();
    fetchMock.mockImplementation(async () =>
      new Response(JSON.stringify({ detail: "El servidor tuvo un error al procesar la solicitud." }), {
        status: 500,
        headers: { "Content-Type": "application/json" },
      })
    );
    await expect(api.exportarPrecios({ soloDiferencias: true, formato: "erp" })).rejects.toThrow(
      "El servidor tuvo un error al procesar la solicitud."
    );
    expect(fetchMock).toHaveBeenCalledTimes(1);
  });
});
