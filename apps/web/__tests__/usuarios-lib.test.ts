/**
 * Reglas de la pantalla de Usuarios que no dependen de como se dibuja.
 *
 * El POST de usuarios cambia solo los campos que llegan, asi que `cambiosUsuario`
 * es lo que evita que editar un nombre le quite el admin a alguien. Y la cuenta
 * del motor no se puede tocar sin aviso: si le cambian la clave, el motor deja de
 * publicar.
 */
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  type UsuarioAdmin,
  cambiosUsuario,
  datosDe,
  errorClave,
  generarClave,
  hayCambios,
  tocaAlMotor,
  usuariosApi,
} from "@/lib/usuarios";
import { MENSAJE_SIN_SERVIDOR } from "@/lib/api-client";

const mocks = vi.hoisted(() => ({ req: vi.fn(), reqConReintentos: vi.fn(), sucursalesGeneral: vi.fn() }));

vi.mock("@/lib/api-client", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/api-client")>()),
  req: mocks.req,
  reqConReintentos: mocks.reqConReintentos,
  api: { sucursales: mocks.sucursalesGeneral },
}));

beforeEach(() => {
  mocks.req.mockReset();
  mocks.reqConReintentos.mockReset();
  mocks.sucursalesGeneral.mockReset();
});

const USUARIO: UsuarioAdmin = {
  email: "persona@ejemplo.cl", nombre: "Persona", activo: true, es_admin: true, solo_lectura: false,
  es_vendedor: false, sucursales: ["LINDEROS", "CURICO"], creado_en: null,
  es_cuenta_motor: false, permisos_especiales: [],
};
const MOTOR: UsuarioAdmin = { ...USUARIO, email: "admin@curifor.com", es_cuenta_motor: true };

const respuesta = (status: number, cuerpo: unknown) =>
  new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });

describe("cambiosUsuario", () => {
  it("sin cambios manda solo el correo", () => {
    const c = cambiosUsuario(USUARIO, datosDe(USUARIO));
    expect(c).toEqual({ email: "persona@ejemplo.cl" });
    expect(hayCambios(c)).toBe(false);
  });

  it("cambiar el nombre no manda los roles", () => {
    const c = cambiosUsuario(USUARIO, { ...datosDe(USUARIO), nombre: "  Otro nombre " });
    expect(c).toEqual({ email: "persona@ejemplo.cl", nombre: "Otro nombre" });
  });

  it("las mismas sucursales en otro orden no son un cambio", () => {
    const c = cambiosUsuario(USUARIO, { ...datosDe(USUARIO), sucursales: ["CURICO", "LINDEROS"] });
    expect(hayCambios(c)).toBe(false);
  });

  it("quitar todas las sucursales se manda como lista vacia", () => {
    const c = cambiosUsuario(USUARIO, { ...datosDe(USUARIO), sucursales: [] });
    expect(c).toEqual({ email: "persona@ejemplo.cl", sucursales: [] });
  });
});

describe("tocaAlMotor", () => {
  it("una cuenta comun nunca pide el aviso", () => {
    expect(tocaAlMotor(USUARIO, { email: USUARIO.email, password: "x", es_admin: false, activo: false })).toBe(false);
    expect(tocaAlMotor(null, { email: "nueva@ejemplo.cl", password: "x" })).toBe(false);
  });

  it("en la del motor lo piden la clave, quitar el admin y desactivar", () => {
    expect(tocaAlMotor(MOTOR, { email: MOTOR.email, password: "nueva1234" })).toBe(true);
    expect(tocaAlMotor(MOTOR, { email: MOTOR.email, es_admin: false })).toBe(true);
    expect(tocaAlMotor(MOTOR, { email: MOTOR.email, activo: false })).toBe(true);
  });

  it("en la del motor lo pide marcarla como vendedor: le cierra ventas, equivalencias y precios", () => {
    expect(tocaAlMotor(MOTOR, { email: MOTOR.email, es_vendedor: true, sucursales: ["LINDEROS"] })).toBe(true);
    expect(tocaAlMotor(MOTOR, { email: MOTOR.email, es_vendedor: false })).toBe(false);
  });

  it("en la del motor no lo piden el nombre ni las sucursales", () => {
    expect(tocaAlMotor(MOTOR, { email: MOTOR.email, nombre: "Motor", sucursales: [] })).toBe(false);
    expect(tocaAlMotor(MOTOR, { email: MOTOR.email, activo: true, es_admin: true })).toBe(false);
  });
});

describe("errorClave", () => {
  it("vacia, corta y distinta", () => {
    expect(errorClave("", "", 4)).toBe("Escribe la clave.");
    expect(errorClave("abc", "abc", 4)).toBe("La clave tiene que tener al menos 4 caracteres.");
    expect(errorClave("abcd", "abce", 4)).toBe("Las dos claves no coinciden.");
    expect(errorClave("abcd", "abcd", 4)).toBeNull();
  });

  it("sin la regla del servidor no inventa un minimo", () => {
    expect(errorClave("a", "a", null)).toBeNull();
  });
});

describe("generarClave", () => {
  it("tiene el largo pedido y no usa letras que se confunden", () => {
    for (let i = 0; i < 50; i++) {
      const c = generarClave(12);
      expect(c).toHaveLength(12);
      expect(c).not.toMatch(/[0O1lI]/);
    }
  });

  it("no repite la misma", () => {
    const vistas = new Set(Array.from({ length: 20 }, () => generarClave()));
    expect(vistas.size).toBe(20);
  });
});

describe("usuariosApi", () => {
  it("una API anterior a la pantalla (sin campos nuevos) se lee como cuenta comun", async () => {
    mocks.reqConReintentos.mockResolvedValue(respuesta(200, [
      { email: "vieja@ejemplo.cl", nombre: null, activo: true, es_admin: false, solo_lectura: false,
        es_vendedor: false, sucursales: [], creado_en: null },
    ]));
    const [u] = await usuariosApi.listar();
    expect(u.es_cuenta_motor).toBe(false);
    expect(u.permisos_especiales).toEqual([]);
  });

  it("el error 400 del servidor llega tal cual", async () => {
    mocks.req.mockResolvedValue(respuesta(400, { detail: "Un vendedor necesita al menos una sucursal asignada." }));
    await expect(usuariosApi.guardar({ email: "v@ejemplo.cl", es_vendedor: true }))
      .rejects.toThrow("Un vendedor necesita al menos una sucursal asignada.");
  });

  it("sin servidor dice que no se pudo conectar", async () => {
    mocks.req.mockRejectedValue(new TypeError("Failed to fetch"));
    await expect(usuariosApi.guardar({ email: "v@ejemplo.cl", nombre: "V" })).rejects.toThrow(MENSAJE_SIN_SERVIDOR);
  });

  it("las sucursales para asignar salen de la ruta de admin, sin el filtro de quien mira", async () => {
    const lista = [{ sucursal_id: "LINDEROS", nombre: "Linderos", region: null, abastece_desde_cd: null, prioridad_cd: 1 }];
    mocks.reqConReintentos.mockResolvedValue(respuesta(200, lista));
    expect(await usuariosApi.sucursales()).toEqual(lista);
    expect(mocks.reqConReintentos).toHaveBeenCalledWith("/api/admin/usuarios/sucursales");
    expect(mocks.sucursalesGeneral).not.toHaveBeenCalled();
  });

  it("una API anterior a esa ruta (404) usa la lista general", async () => {
    mocks.reqConReintentos.mockResolvedValue(respuesta(404, { detail: "Not Found" }));
    mocks.sucursalesGeneral.mockResolvedValue([]);
    expect(await usuariosApi.sucursales()).toEqual([]);
    expect(mocks.sucursalesGeneral).toHaveBeenCalledTimes(1);
  });

  it("guardar manda el JSON por POST a la ruta de admin", async () => {
    mocks.req.mockResolvedValue(respuesta(200, { ...USUARIO }));
    await usuariosApi.guardar({ email: USUARIO.email, password: "nueva1234" });
    expect(mocks.req).toHaveBeenCalledWith("/api/admin/usuarios", expect.objectContaining({
      method: "POST",
      body: JSON.stringify({ email: USUARIO.email, password: "nueva1234" }),
    }));
  });
});
