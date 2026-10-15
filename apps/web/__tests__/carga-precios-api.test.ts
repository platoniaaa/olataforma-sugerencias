/**
 * El cliente de la carga de precios. La carga ESCRIBE: si la respuesta se pierde, no se
 * sabe si quedo cargada. Una conexion cortada y un 502/503/504 del proxy son lo mismo
 * (el endpoint es sincrono y hace commit aunque el proxy corte), y los dos tienen que
 * decir "no se pudo confirmar", no "no se pudo cargar".
 */
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ARCHIVO = new File(["x"], "lista.csv");
let fetchMock: ReturnType<typeof vi.fn>;

async function cargar() {
  vi.resetModules();
  return import("@/lib/api-client");
}

beforeEach(() => {
  fetchMock = vi.fn();
  vi.stubGlobal("fetch", fetchMock);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("cargarPrecios", () => {
  it.each([502, 503, 504])("un %s no se muestra como fallo definitivo", async (status) => {
    const { api, MENSAJE_CARGA_SIN_CONFIRMAR } = await cargar();
    fetchMock.mockResolvedValue(new Response("<html>Bad Gateway</html>", { status }));

    await expect(api.cargarPrecios(ARCHIVO)).rejects.toThrow(MENSAJE_CARGA_SIN_CONFIRMAR);
    expect(fetchMock).toHaveBeenCalledTimes(1);          // y no se reintenta: escribe
  });

  it("una conexion cortada dice lo mismo", async () => {
    const { api, MENSAJE_CARGA_SIN_CONFIRMAR } = await cargar();
    fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

    await expect(api.cargarPrecios(ARCHIVO)).rejects.toThrow(MENSAJE_CARGA_SIN_CONFIRMAR);
  });

  it("un error con detalle se muestra tal cual", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "El archivo tiene 2 error(es). No se cargó nada." }), {
        status: 422, headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(api.cargarPrecios(ARCHIVO)).rejects.toThrow("El archivo tiene 2 error(es). No se cargó nada.");
  });

  it("manda las confirmaciones solo cuando se piden", async () => {
    const { api } = await cargar();
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ aplicados: 0 }), { status: 200 }));

    await api.cargarPrecios(ARCHIVO);
    await api.cargarPrecios(ARCHIVO, { confirmarQuitas: true });
    await api.cargarPrecios(ARCHIVO, { confirmarMasiva: true });

    const cuerpo = (i: number) => (fetchMock.mock.calls[i][1].body as FormData);
    expect(cuerpo(0).get("confirmar_quitas")).toBeNull();
    expect(cuerpo(0).get("confirmar_masiva")).toBeNull();
    expect(cuerpo(1).get("confirmar_quitas")).toBe("true");
    expect(cuerpo(1).get("confirmar_masiva")).toBeNull();
    expect(cuerpo(1).get("archivo")).toBeInstanceOf(File);
    expect(cuerpo(2).get("confirmar_masiva")).toBe("true");
    expect(cuerpo(2).get("confirmar_quitas")).toBeNull();
  });
  it("un 200 con el cuerpo cortado tambien dice que no se pudo confirmar", async () => {
    const { api, MENSAJE_CARGA_SIN_CONFIRMAR } = await cargar();
    const cuerpo = new ReadableStream({
      start(c) {
        c.enqueue(new TextEncoder().encode('{"aplicados": 3, "por_ca'));
        c.error(new TypeError("network error"));
      },
    });
    fetchMock.mockResolvedValue(new Response(cuerpo, { status: 200 }));

    const error = await api.cargarPrecios(ARCHIVO).catch((e) => e);

    expect(error.message).toBe(MENSAJE_CARGA_SIN_CONFIRMAR);
    // El componente se apoya en el nombre para refrescar la lista de atras.
    expect(error.name).toBe("CargaSinConfirmar");
  });

  it("un 200 con una pagina del proxy en vez de JSON tampoco es un resultado", async () => {
    const { api, MENSAJE_CARGA_SIN_CONFIRMAR } = await cargar();
    fetchMock.mockResolvedValue(new Response("<html>Gateway</html>", { status: 200 }));

    await expect(api.cargarPrecios(ARCHIVO)).rejects.toThrow(MENSAJE_CARGA_SIN_CONFIRMAR);
  });
});

describe("vistaPreviaCargaPrecios", () => {
  it("un 200 con el cuerpo cortado dice que no hay servidor, no 'network error'", async () => {
    const { api, MENSAJE_SIN_SERVIDOR } = await cargar();
    const cuerpo = new ReadableStream({
      start(c) {
        c.enqueue(new TextEncoder().encode('{"filas": 3, "a_ca'));
        c.error(new TypeError("network error"));
      },
    });
    fetchMock.mockResolvedValue(new Response(cuerpo, { status: 200 }));

    await expect(api.vistaPreviaCargaPrecios(ARCHIVO)).rejects.toThrow(MENSAJE_SIN_SERVIDOR);
  });

  it("cancelar la lectura corta los reintentos: no se vuelve a subir el archivo", async () => {
    vi.useFakeTimers();
    try {
      const { api } = await cargar();
      fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
      const control = new AbortController();

      const lectura = api.vistaPreviaCargaPrecios(ARCHIVO, undefined, control.signal);
      const resultado = lectura.catch((e) => e);
      await vi.advanceTimersByTimeAsync(0);
      expect(fetchMock).toHaveBeenCalledTimes(1);

      control.abort();
      const error = await resultado;
      await vi.advanceTimersByTimeAsync(120_000);

      expect(error.name).toBe("AbortError");
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(vi.getTimerCount()).toBe(0);
    } finally {
      vi.useRealTimers();
    }
  });
});
