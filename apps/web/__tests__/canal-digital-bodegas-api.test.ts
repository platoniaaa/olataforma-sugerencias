/**
 * Cliente de bodegas de Canal Digital: a que ruta llama, que manda y como lee los errores del servidor.
 * No sale a la red: `req` (el fetch con token) se reemplaza por un doble.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import { canalDigitalApi } from "@/lib/canal-digital";

const mocks = vi.hoisted(() => ({ req: vi.fn() }));

vi.mock("@/lib/api-client", async (orig) => ({
  ...(await orig<typeof import("@/lib/api-client")>()),
  req: mocks.req,
}));

const respuesta = (cuerpo: unknown, status = 200) =>
  new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });

beforeEach(() => mocks.req.mockReset());

describe("canalDigitalApi: bodegas", () => {
  it("bodegas() lee la lista con los tipos de venta sugeridos", async () => {
    const cuerpo = { bodegas: [{ bodega: "430" }], tipos_venta_sugeridos: ["VTA ML"] };
    mocks.req.mockResolvedValue(respuesta(cuerpo));
    expect(await canalDigitalApi.bodegas()).toEqual(cuerpo);
    expect(mocks.req).toHaveBeenCalledWith("/api/canal-digital/bodegas");
  });

  it("guardarBodega hace PUT a la bodega con solo los cambios y devuelve la bodega guardada", async () => {
    const guardada = { bodega: "430", r_semanas: 2, cambios: ["r_semanas"], avisos: [] };
    mocks.req.mockResolvedValue(respuesta(guardada));
    expect(await canalDigitalApi.guardarBodega("430", { r_semanas: 2 })).toEqual(guardada);
    const [ruta, init] = mocks.req.mock.calls[0];
    expect(ruta).toBe("/api/canal-digital/bodegas/430");
    expect(init.method).toBe("PUT");
    expect(init.headers).toEqual({ "Content-Type": "application/json" });
    expect(JSON.parse(init.body)).toEqual({ r_semanas: 2 });
  });

  it("el codigo de la bodega va escapado en la ruta", async () => {
    mocks.req.mockResolvedValue(respuesta({}));
    await canalDigitalApi.guardarBodega("A/B", {});
    expect(mocks.req.mock.calls[0][0]).toBe("/api/canal-digital/bodegas/A%2FB");
  });

  it("un 400 de validacion trae todos los problemas: quedan en un solo error, uno por renglon", async () => {
    mocks.req.mockResolvedValue(
      respuesta({ detail: { mensaje: "Hay parámetros que no se pueden guardar", problemas: ["Problema uno.", "Problema dos."] } }, 400)
    );
    await expect(canalDigitalApi.guardarBodega("430", { r_semanas: 99 })).rejects.toThrow("Problema uno.\nProblema dos.");
  });

  it("un 404 o un 403 con texto muestra ese texto; sin cuerpo, uno generico", async () => {
    mocks.req.mockResolvedValueOnce(respuesta({ detail: "La bodega 999 no existe" }, 404));
    await expect(canalDigitalApi.guardarBodega("999", {})).rejects.toThrow("La bodega 999 no existe");
    mocks.req.mockResolvedValueOnce(new Response("", { status: 500 }));
    await expect(canalDigitalApi.guardarBodega("430", {})).rejects.toThrow("No se pudieron guardar los parámetros");
  });

  it("crearBodega hace POST con codigo y nombre; sin nombre no lo manda", async () => {
    mocks.req.mockImplementation(async () => respuesta({ bodega: "500" }, 201)); // una respuesta nueva por llamada
    await canalDigitalApi.crearBodega("500", " Canal 500 ");
    let [ruta, init] = mocks.req.mock.calls[0];
    expect(ruta).toBe("/api/canal-digital/bodegas");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body)).toEqual({ bodega: "500", nombre: " Canal 500 " });
    await canalDigitalApi.crearBodega("501", "   ");
    [, init] = mocks.req.mock.calls[1];
    expect(JSON.parse(init.body)).toEqual({ bodega: "501" });
  });

  it("crearBodega: un 409 dice que la bodega ya existe y un 400 junta los problemas", async () => {
    mocks.req.mockResolvedValueOnce(respuesta({ detail: "La bodega 500 ya existe" }, 409));
    await expect(canalDigitalApi.crearBodega("500", "")).rejects.toThrow("La bodega 500 ya existe");
    mocks.req.mockResolvedValueOnce(
      respuesta({ detail: { mensaje: "x", problemas: ["El código de la bodega debe tener de 1 a 12 letras o números, sin espacios ni signos."] } }, 400)
    );
    await expect(canalDigitalApi.crearBodega("A B", "")).rejects.toThrow(/de 1 a 12 letras o números/);
  });

  it("guardarPolitica sigue juntando los problemas de un 400 como antes", async () => {
    mocks.req.mockResolvedValue(respuesta({ detail: { problemas: ["Falta AAA.", "Sobra ZZZ."] } }, 400));
    await expect(canalDigitalApi.guardarPolitica("430", [])).rejects.toThrow("Falta AAA.\nSobra ZZZ.");
  });
});
