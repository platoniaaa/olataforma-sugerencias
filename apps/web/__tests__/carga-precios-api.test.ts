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
      new Response(JSON.stringify({ detail: "El archivo tiene 2 errores. No se cargó nada." }), {
        status: 422, headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(api.cargarPrecios(ARCHIVO)).rejects.toThrow("El archivo tiene 2 errores. No se cargó nada.");
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

// --------------------------------------------------------------- los dos modos de carga
// La pantalla declara el modo ("corto": la plantilla de cinco columnas; "completo": el archivo
// que se baja para editar) en vez de dejar que el servidor lo adivine: asi un archivo que no es
// del modo elegido da un 422 claro y no se carga como otra cosa. Sin modo, el campo no viaja y
// el servidor decide por las columnas ("auto"), como hasta ahora.
const cuerpoDe = (i: number) => fetchMock.mock.calls[i][1].body as FormData;

describe("el modo viaja en el formulario, y solo si se declara", () => {
  const respuestaPrevia = () => new Response(JSON.stringify({ filas: 0 }), { status: 200 });

  it("la vista previa manda `modo` a la misma ruta, y sin modo no manda nada", async () => {
    const { api } = await cargar();
    fetchMock.mockImplementation(async () => respuestaPrevia());

    await api.vistaPreviaCargaPrecios(ARCHIVO);
    await api.vistaPreviaCargaPrecios(ARCHIVO, undefined, undefined, "corto");
    await api.vistaPreviaCargaPrecios(ARCHIVO, undefined, undefined, "completo");

    for (let i = 0; i < 3; i++) expect(String(fetchMock.mock.calls[i][0])).toMatch(/\/api\/precios\/carga\/vista-previa$/);
    expect(cuerpoDe(0).get("modo")).toBeNull();
    expect(cuerpoDe(1).get("modo")).toBe("corto");
    expect(cuerpoDe(2).get("modo")).toBe("completo");
    expect(cuerpoDe(1).get("archivo")).toBeInstanceOf(File);
  });

  it("la carga manda `modo` junto con las confirmaciones, y sin modo no manda nada", async () => {
    const { api } = await cargar();
    fetchMock.mockImplementation(async () => new Response(JSON.stringify({ aplicados: 0 }), { status: 200 }));

    await api.cargarPrecios(ARCHIVO, { confirmarQuitas: true });
    await api.cargarPrecios(ARCHIVO, { confirmarMasiva: true, modo: "corto" });
    await api.cargarPrecios(ARCHIVO, { modo: "completo" });

    expect(String(fetchMock.mock.calls[1][0])).toMatch(/\/api\/precios\/carga$/);
    expect(cuerpoDe(0).get("modo")).toBeNull();
    expect(cuerpoDe(1).get("modo")).toBe("corto");
    expect(cuerpoDe(1).get("confirmar_masiva")).toBe("true");
    expect(cuerpoDe(1).get("confirmar_quitas")).toBeNull();
    expect(cuerpoDe(2).get("modo")).toBe("completo");
  });

  it.each([502, 503, 504])("la carga en modo corto con un %s tampoco se reintenta ni se da por fallida", async (status) => {
    const { api, MENSAJE_CARGA_SIN_CONFIRMAR } = await cargar();
    fetchMock.mockResolvedValue(new Response("<html>Bad Gateway</html>", { status }));

    const error = await api.cargarPrecios(ARCHIVO, { modo: "corto" }).catch((e) => e);

    expect(error.message).toBe(MENSAJE_CARGA_SIN_CONFIRMAR);
    expect(error.name).toBe("CargaSinConfirmar");
    expect(fetchMock).toHaveBeenCalledTimes(1);          // escribe: no se repite
  });

  it("una conexion cortada o un cuerpo cortado en modo corto dicen lo mismo", async () => {
    const { api, MENSAJE_CARGA_SIN_CONFIRMAR } = await cargar();
    fetchMock.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    fetchMock.mockResolvedValueOnce(new Response("<html>Gateway</html>", { status: 200 }));

    await expect(api.cargarPrecios(ARCHIVO, { modo: "corto" })).rejects.toThrow(MENSAJE_CARGA_SIN_CONFIRMAR);
    await expect(api.cargarPrecios(ARCHIVO, { modo: "corto" })).rejects.toThrow(MENSAJE_CARGA_SIN_CONFIRMAR);
    expect(fetchMock).toHaveBeenCalledTimes(2);
  });

  it("un 422 del servidor por un archivo que no es del modo elegido se muestra tal cual", async () => {
    const { api } = await cargar();
    const detail = "Este archivo es de la plantilla corta, pero elegiste el archivo completo. Cambia el modo o descarga el archivo de nuevo.";
    // Una respuesta nueva por llamada: el cuerpo de una Response se puede leer una sola vez.
    fetchMock.mockImplementation(async () =>
      new Response(JSON.stringify({ detail }), { status: 422, headers: { "Content-Type": "application/json" } }),
    );

    await expect(api.vistaPreviaCargaPrecios(ARCHIVO, undefined, undefined, "completo")).rejects.toThrow(detail);
    await expect(api.cargarPrecios(ARCHIVO, { modo: "completo" })).rejects.toThrow(detail);
  });

  it("la lectura en modo corto se puede abortar: se corta el pedido y no se reintenta", async () => {
    vi.useFakeTimers();
    try {
      const { api } = await cargar();
      fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));
      const control = new AbortController();

      const resultado = api.vistaPreviaCargaPrecios(ARCHIVO, undefined, control.signal, "corto").catch((e) => e);
      await vi.advanceTimersByTimeAsync(0);
      control.abort();
      const error = await resultado;
      await vi.advanceTimersByTimeAsync(120_000);

      expect(error.name).toBe("AbortError");
      expect(fetchMock).toHaveBeenCalledTimes(1);
      expect(cuerpoDe(0).get("modo")).toBe("corto");
    } finally {
      vi.useRealTimers();
    }
  });
});

describe("descargarPlantillaCarga", () => {
  let nombresGuardados: string[];

  beforeEach(() => {
    nombresGuardados = [];
    URL.createObjectURL = vi.fn(() => "blob:plantilla");
    URL.revokeObjectURL = vi.fn();
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      nombresGuardados.push(this.download);
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const archivoXlsx = () =>
    new Response("PK-plantilla", {
      status: 200,
      headers: { "Content-Disposition": 'attachment; filename="plantilla_precios_corta.xlsx"' },
    });

  it("pide la plantilla xlsx por defecto y guarda el blob con el nombre del servidor", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(archivoXlsx());

    const nombre = await api.descargarPlantillaCarga();

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/precios\/carga\/plantilla\?archivo=xlsx$/);
    expect(nombresGuardados).toEqual(["plantilla_precios_corta.xlsx"]);
    expect(URL.createObjectURL).toHaveBeenCalledTimes(1);
    expect(URL.revokeObjectURL).toHaveBeenCalledTimes(1);
    expect(nombre).toBe("plantilla_precios_corta.xlsx");
  });

  it("pide el csv cuando se lo piden, y es un GET: no manda cuerpo", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(new Response("Código;Precio fijo", {
      status: 200, headers: { "Content-Disposition": 'attachment; filename="plantilla_precios_corta.csv"' },
    }));

    await api.descargarPlantillaCarga("csv");

    expect(String(fetchMock.mock.calls[0][0])).toMatch(/\/api\/precios\/carga\/plantilla\?archivo=csv$/);
    expect(fetchMock.mock.calls[0][1]?.method ?? "GET").toBe("GET");
    expect(fetchMock.mock.calls[0][1]?.body).toBeUndefined();
    expect(nombresGuardados).toEqual(["plantilla_precios_corta.csv"]);
  });

  it("si el navegador esconde Content-Disposition, el nombre de respaldo coincide con el formato pedido", async () => {
    const { api } = await cargar();
    fetchMock.mockImplementation(async () => new Response("x", { status: 200 }));

    await api.descargarPlantillaCarga("xlsx");
    await api.descargarPlantillaCarga("csv");

    // Con ".xlsx" sobre un CSV, Excel lo rechaza por "formato o extension no validos".
    expect(nombresGuardados).toEqual(["plantilla_precios_corta.xlsx", "plantilla_precios_corta.csv"]);
  });

  it("un error con detalle (por ejemplo, sin permiso) se muestra tal cual y no baja nada", async () => {
    const { api } = await cargar();
    fetchMock.mockResolvedValue(
      new Response(JSON.stringify({ detail: "No tienes permiso para editar precios." }), {
        status: 403, headers: { "Content-Type": "application/json" },
      }),
    );

    await expect(api.descargarPlantillaCarga()).rejects.toThrow("No tienes permiso para editar precios.");
    expect(nombresGuardados).toEqual([]);
  });

  it("una conexion cortada dice que no hay servidor, no 'Failed to fetch'", async () => {
    vi.useFakeTimers();
    try {
      const { api, MENSAJE_SIN_SERVIDOR } = await cargar();
      fetchMock.mockRejectedValue(new TypeError("Failed to fetch"));

      const resultado = api.descargarPlantillaCarga().catch((e) => e);
      await vi.advanceTimersByTimeAsync(120_000);

      expect((await resultado).message).toBe(MENSAJE_SIN_SERVIDOR);
      expect(nombresGuardados).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("es una lectura: un 502 se reintenta, avisa y termina bajando el archivo", async () => {
    vi.useFakeTimers();
    try {
      const { api } = await cargar();
      fetchMock.mockResolvedValueOnce(new Response("<html>Bad Gateway</html>", { status: 502 }));
      fetchMock.mockResolvedValueOnce(archivoXlsx());
      const avisos: [number, number][] = [];

      const resultado = api.descargarPlantillaCarga("xlsx", (i, t) => avisos.push([i, t]));
      await vi.advanceTimersByTimeAsync(3_000);
      await resultado;

      expect(fetchMock).toHaveBeenCalledTimes(2);
      expect(avisos).toEqual([[1, 4]]);
      expect(nombresGuardados).toEqual(["plantilla_precios_corta.xlsx"]);
    } finally {
      vi.useRealTimers();
    }
  });

  it("un 503 que nunca se arregla termina con el mensaje de sin servidor", async () => {
    vi.useFakeTimers();
    try {
      const { api, MENSAJE_SIN_SERVIDOR } = await cargar();
      fetchMock.mockImplementation(async () => new Response("<html>Unavailable</html>", { status: 503 }));

      const resultado = api.descargarPlantillaCarga().catch((e) => e);
      await vi.advanceTimersByTimeAsync(120_000);

      expect((await resultado).message).toBe(MENSAJE_SIN_SERVIDOR);
      expect(nombresGuardados).toEqual([]);
    } finally {
      vi.useRealTimers();
    }
  });
});
