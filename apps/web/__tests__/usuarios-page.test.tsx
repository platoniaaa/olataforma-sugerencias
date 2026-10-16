/**
 * Pantalla de Usuarios (solo admin), 16-10-2026.
 *
 * Hasta ahora los usuarios se manejaban solo por la API, y eso lo sabia hacer
 * una persona. Lo que estos tests cuidan:
 *
 * 1. Que quien no es admin no vea la pantalla (ni la pida al servidor).
 * 2. Que al editar viaje SOLO lo que cambio: el servidor deja igual lo que no
 *    llega, y cambiar un nombre no puede quitarle el admin a nadie.
 * 3. Que cambiarle la clave, quitarle el admin o desactivar la cuenta del motor
 *    pida una confirmacion explicita: si no, el motor deja de publicar.
 * 4. Que el error del servidor se vea tal cual.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import UsuariosPage from "@/app/usuarios/page";
import type { Sucursal } from "@/lib/types";
import { AVISO_MOTOR, type UsuarioAdmin } from "@/lib/usuarios";

const base: Omit<UsuarioAdmin, "email"> = {
  nombre: null, activo: true, es_admin: false, solo_lectura: false, es_vendedor: false,
  sucursales: [], creado_en: null, es_cuenta_motor: false, permisos_especiales: [],
};

const PROPIO: UsuarioAdmin = { ...base, email: "jefa@ejemplo.cl", nombre: "Jefa de prueba", es_admin: true };
const MOTOR: UsuarioAdmin = {
  ...base, email: "admin@curifor.com", nombre: "Cuenta del motor", es_admin: true, es_cuenta_motor: true,
};
const VENDEDOR: UsuarioAdmin = {
  ...base, email: "vendedor@ejemplo.cl", nombre: "Vendedor Uno", es_vendedor: true, sucursales: ["LINDEROS"],
};
const PRECIOS: UsuarioAdmin = {
  ...base, email: "precios@ejemplo.cl", nombre: "Equipo precios", permisos_especiales: ["precios", "calibracion"],
};
const INACTIVO: UsuarioAdmin = { ...base, email: "ex@ejemplo.cl", activo: false };
const USUARIOS = [MOTOR, INACTIVO, PROPIO, PRECIOS, VENDEDOR];

const SUCURSALES: Sucursal[] = [
  { sucursal_id: "LINDEROS", nombre: "Linderos", region: null, abastece_desde_cd: null, prioridad_cd: 1 },
  { sucursal_id: "CURICO", nombre: "Curicó", region: null, abastece_desde_cd: null, prioridad_cd: 2 },
];

const mocks = vi.hoisted(() => ({
  listar: vi.fn(),
  reglas: vi.fn(),
  guardar: vi.fn(),
  sucursales: vi.fn(),
  replace: vi.fn(),
  esAdmin: vi.fn(),
}));

vi.mock("next/navigation", () => ({ useRouter: () => ({ replace: mocks.replace }) }));
vi.mock("@/lib/api-client", () => ({ api: { sucursales: mocks.sucursales } }));
vi.mock("@/lib/auth", () => ({ getEsAdmin: mocks.esAdmin, getEmail: () => "jefa@ejemplo.cl" }));
vi.mock("@/lib/usuarios", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/usuarios")>()),
  usuariosApi: { listar: mocks.listar, reglas: mocks.reglas, guardar: mocks.guardar },
}));

// Con llaves: si beforeEach devuelve una funcion, vitest la llama al terminar la
// prueba como limpieza, y mockReset() devuelve el propio mock.
beforeEach(() => {
  mocks.listar.mockReset().mockResolvedValue(USUARIOS);
  mocks.reglas.mockReset().mockResolvedValue({ largo_minimo_clave: 4 });
  mocks.guardar.mockReset().mockImplementation(async (d: { email: string }) => ({ ...base, email: d.email }));
  mocks.sucursales.mockReset().mockResolvedValue(SUCURSALES);
  mocks.replace.mockReset();
  mocks.esAdmin.mockReset().mockReturnValue(true);
});

afterEach(() => {
  vi.restoreAllMocks();
});

async function abrir() {
  render(<UsuariosPage />);
  await screen.findByRole("list", { name: "Usuarios" });
}

function fila(nombre: string) {
  return within(screen.getByRole("listitem", { name: nombre }));
}

function dialogo() {
  return within(screen.getByRole("dialog"));
}

describe("acceso", () => {
  it("quien no es admin vuelve al inicio y no se le pide nada al servidor", async () => {
    mocks.esAdmin.mockReturnValue(false);
    render(<UsuariosPage />);
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/"));
    expect(mocks.listar).not.toHaveBeenCalled();
    expect(screen.queryByText("Usuarios")).not.toBeInTheDocument();
  });
});

describe("lista", () => {
  it("muestra correo, nombre, roles, sucursales, estado y permisos especiales", async () => {
    await abrir();
    expect(fila("Vendedor Uno").getByText("vendedor@ejemplo.cl")).toBeInTheDocument();
    expect(fila("Vendedor Uno").getByText("Vendedor")).toBeInTheDocument();
    // La sucursal por su nombre, no por el codigo.
    expect(fila("Vendedor Uno").getByText("Pide por: Linderos")).toBeInTheDocument();
    expect(fila("Jefa de prueba").getByText("Admin")).toBeInTheDocument();
    expect(fila("Jefa de prueba").getByText("(tú)")).toBeInTheDocument();
    expect(fila("ex@ejemplo.cl").getByText("Desactivado")).toBeInTheDocument();
    expect(
      fila("Equipo precios").getByText("Permisos especiales: Editar la lista de precios · Configurar el modelo"),
    ).toBeInTheDocument();
    expect(screen.getByText(/Se definen en la configuración del servidor/)).toBeInTheDocument();
    expect(screen.getByText("4 activos · 1 desactivado")).toBeInTheDocument();
  });

  it("marca la cuenta del motor", async () => {
    await abrir();
    expect(fila("Cuenta del motor").getByText("La usa el motor")).toBeInTheDocument();
    expect(fila("Vendedor Uno").queryByText("La usa el motor")).not.toBeInTheDocument();
  });

  it("los desactivados van al final", async () => {
    await abrir();
    const filas = within(screen.getByRole("list", { name: "Usuarios" })).getAllByRole("listitem");
    expect(filas[filas.length - 1]).toHaveAccessibleName("ex@ejemplo.cl");
  });

  it("si la lista no carga lo dice y deja reintentar", async () => {
    mocks.listar.mockRejectedValueOnce(new Error("Requiere permisos de admin"));
    render(<UsuariosPage />);
    expect(await screen.findByText("Requiere permisos de admin")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    await screen.findByRole("list", { name: "Usuarios" });
    expect(mocks.listar).toHaveBeenCalledTimes(2);
  });

  it("filtra por correo o nombre", async () => {
    await abrir();
    fireEvent.change(screen.getByRole("searchbox", { name: "Buscar por correo o nombre" }), {
      target: { value: "vende" },
    });
    expect(screen.getAllByRole("listitem")).toHaveLength(1);
    expect(screen.getByText("Vendedor Uno")).toBeInTheDocument();
  });
});

describe("crear", () => {
  function llenar(correo: string, clave: string, repetida = clave) {
    fireEvent.change(dialogo().getByLabelText("Correo"), { target: { value: correo } });
    fireEvent.change(dialogo().getByLabelText("Nombre"), { target: { value: "Persona Nueva" } });
    fireEvent.change(dialogo().getByLabelText("Clave inicial"), { target: { value: clave } });
    fireEvent.change(dialogo().getByLabelText("Repite la clave"), { target: { value: repetida } });
  }

  it("crea un vendedor con su sucursal", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: /Crear usuario/ }));
    llenar("Nuevo@Ejemplo.cl", "clave1234");
    fireEvent.click(dialogo().getByRole("checkbox", { name: /^Vendedor de sucursal/ }));
    fireEvent.click(dialogo().getByRole("checkbox", { name: "Curicó" }));
    fireEvent.click(dialogo().getByRole("button", { name: /Crear usuario/ }));

    await waitFor(() => expect(mocks.guardar).toHaveBeenCalledTimes(1));
    expect(mocks.guardar).toHaveBeenCalledWith({
      email: "nuevo@ejemplo.cl", password: "clave1234", nombre: "Persona Nueva",
      es_admin: false, solo_lectura: false, es_vendedor: true, sucursales: ["CURICO"],
    });
    expect(await screen.findByText(/Usuario creado: nuevo@ejemplo.cl/)).toBeInTheDocument();
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    // Y se vuelve a pedir la lista para mostrarlo.
    expect(mocks.listar).toHaveBeenCalledTimes(2);
  });

  it("un vendedor sin sucursal no se manda", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: /Crear usuario/ }));
    llenar("nuevo@ejemplo.cl", "clave1234");
    fireEvent.click(dialogo().getByRole("checkbox", { name: /^Vendedor de sucursal/ }));
    fireEvent.click(dialogo().getByRole("button", { name: /Crear usuario/ }));

    expect(await dialogo().findByText(/Un vendedor necesita al menos una sucursal/)).toBeInTheDocument();
    expect(mocks.guardar).not.toHaveBeenCalled();
  });

  it("una clave mas corta que el minimo del servidor no se manda", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: /Crear usuario/ }));
    llenar("nuevo@ejemplo.cl", "abc");
    fireEvent.click(dialogo().getByRole("button", { name: /Crear usuario/ }));

    expect(await dialogo().findByText("La clave tiene que tener al menos 4 caracteres.")).toBeInTheDocument();
    expect(mocks.guardar).not.toHaveBeenCalled();
  });

  it("el error del servidor se muestra tal cual", async () => {
    mocks.guardar.mockRejectedValueOnce(new Error("El correo no es válido."));
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: /Crear usuario/ }));
    llenar("raro@", "clave1234");
    fireEvent.click(dialogo().getByRole("button", { name: /Crear usuario/ }));

    const alerta = await dialogo().findByText("El correo no es válido.");
    expect(alerta.closest("[role=alert]")).not.toBeNull();
    // El formulario sigue abierto con lo escrito, para corregir.
    expect(dialogo().getByLabelText("Correo")).toHaveValue("raro@");
  });
});

describe("editar", () => {
  it("manda solo lo que cambio", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Editar a vendedor@ejemplo.cl" }));
    fireEvent.change(dialogo().getByLabelText("Nombre"), { target: { value: "Vendedor Linderos" } });
    fireEvent.click(dialogo().getByRole("checkbox", { name: "Curicó" }));
    fireEvent.click(dialogo().getByRole("button", { name: /Guardar cambios/ }));

    await waitFor(() => expect(mocks.guardar).toHaveBeenCalledTimes(1));
    expect(mocks.guardar).toHaveBeenCalledWith({
      email: "vendedor@ejemplo.cl", nombre: "Vendedor Linderos", sucursales: ["LINDEROS", "CURICO"],
    });
    expect(await screen.findByText("Cambios guardados para vendedor@ejemplo.cl.")).toBeInTheDocument();
  });

  it("desactivar no borra: manda activo en false", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Editar a precios@ejemplo.cl" }));
    fireEvent.click(dialogo().getByRole("checkbox", { name: /^Cuenta activa/ }));
    fireEvent.click(dialogo().getByRole("button", { name: /Guardar cambios/ }));

    await waitFor(() => expect(mocks.guardar).toHaveBeenCalledWith({ email: "precios@ejemplo.cl", activo: false }));
  });

  it("muestra los permisos especiales en solo lectura", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Editar a precios@ejemplo.cl" }));
    expect(dialogo().getByText("Editar la lista de precios")).toBeInTheDocument();
    expect(dialogo().getByText(/Se definen en la configuración del servidor/)).toBeInTheDocument();
    expect(dialogo().queryByRole("checkbox", { name: /precios/i })).not.toBeInTheDocument();
  });

  it("no deja que el admin se quite el admin ni se desactive", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Editar a jefa@ejemplo.cl" }));
    expect(dialogo().getByRole("checkbox", { name: /^Admin/ })).toBeDisabled();
    expect(dialogo().getByRole("checkbox", { name: /^Cuenta activa/ })).toBeDisabled();
  });

  it("sin cambios no manda nada", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Editar a vendedor@ejemplo.cl" }));
    fireEvent.click(dialogo().getByRole("button", { name: /Guardar cambios/ }));
    expect(await dialogo().findByText("No hay cambios para guardar.")).toBeInTheDocument();
    expect(mocks.guardar).not.toHaveBeenCalled();
  });
});

describe("cambiar clave", () => {
  it("pide repetirla y manda solo la clave", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Cambiar la clave de vendedor@ejemplo.cl" }));
    fireEvent.change(dialogo().getByLabelText("Clave nueva"), { target: { value: "nueva1234" } });
    fireEvent.change(dialogo().getByLabelText("Repite la clave"), { target: { value: "nueva12345" } });
    fireEvent.click(dialogo().getByRole("button", { name: /Cambiar clave/ }));
    expect(await dialogo().findByText("Las dos claves no coinciden.")).toBeInTheDocument();
    expect(mocks.guardar).not.toHaveBeenCalled();

    fireEvent.change(dialogo().getByLabelText("Repite la clave"), { target: { value: "nueva1234" } });
    fireEvent.click(dialogo().getByRole("button", { name: /Cambiar clave/ }));
    await waitFor(() =>
      expect(mocks.guardar).toHaveBeenCalledWith({ email: "vendedor@ejemplo.cl", password: "nueva1234" }));
    expect(await screen.findByText(/Clave cambiada para vendedor@ejemplo.cl/)).toBeInTheDocument();
  });

  it("generar una al azar llena las dos y la deja a la vista para copiarla", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Cambiar la clave de vendedor@ejemplo.cl" }));
    fireEvent.click(dialogo().getByRole("button", { name: /Generar una al azar/ }));
    const nueva = dialogo().getByLabelText("Clave nueva") as HTMLInputElement;
    const repetida = dialogo().getByLabelText("Repite la clave") as HTMLInputElement;
    expect(nueva.value).toHaveLength(10);
    expect(repetida.value).toBe(nueva.value);
    expect(nueva).toHaveAttribute("type", "text");

    fireEvent.click(dialogo().getByRole("button", { name: /Cambiar clave/ }));
    await waitFor(() =>
      expect(mocks.guardar).toHaveBeenCalledWith({ email: "vendedor@ejemplo.cl", password: nueva.value }));
  });

  it("nunca muestra una clave guardada: los campos parten vacios", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Cambiar la clave de vendedor@ejemplo.cl" }));
    expect(dialogo().getByLabelText("Clave nueva")).toHaveValue("");
    expect(dialogo().getByLabelText("Clave nueva")).toHaveAttribute("type", "password");
  });
});

describe("cuenta del motor", () => {
  it("cambiarle la clave pide confirmar que se entiende que el motor deja de publicar", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Cambiar la clave de admin@curifor.com" }));
    expect(dialogo().getByText(new RegExp(AVISO_MOTOR))).toBeInTheDocument();

    fireEvent.change(dialogo().getByLabelText("Clave nueva"), { target: { value: "nueva1234" } });
    fireEvent.change(dialogo().getByLabelText("Repite la clave"), { target: { value: "nueva1234" } });
    const boton = dialogo().getByRole("button", { name: /Cambiar clave/ });
    expect(boton).toBeDisabled();

    fireEvent.click(dialogo().getByRole("checkbox", { name: /Entiendo y quiero hacer el cambio igual/ }));
    expect(boton).toBeEnabled();
    fireEvent.click(boton);
    await waitFor(() =>
      expect(mocks.guardar).toHaveBeenCalledWith({ email: "admin@curifor.com", password: "nueva1234" }));
    expect(await screen.findByText(/El motor no va a publicar hasta que se actualice esta clave/)).toBeInTheDocument();
  });

  it("quitarle el admin pide la misma confirmacion", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Editar a admin@curifor.com" }));
    // Cambiar el nombre no la afecta: no hay aviso.
    fireEvent.change(dialogo().getByLabelText("Nombre"), { target: { value: "Motor" } });
    expect(dialogo().queryByText(new RegExp(AVISO_MOTOR))).not.toBeInTheDocument();

    fireEvent.click(dialogo().getByRole("checkbox", { name: /^Admin/ }));
    expect(dialogo().getByText(new RegExp(AVISO_MOTOR))).toBeInTheDocument();
    expect(dialogo().getByRole("button", { name: /Guardar cambios/ })).toBeDisabled();

    fireEvent.click(dialogo().getByRole("checkbox", { name: /Entiendo y quiero hacer el cambio igual/ }));
    fireEvent.click(dialogo().getByRole("button", { name: /Guardar cambios/ }));
    await waitFor(() =>
      expect(mocks.guardar).toHaveBeenCalledWith({ email: "admin@curifor.com", nombre: "Motor", es_admin: false }));
  });

  it("desactivarla pide la misma confirmacion", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Editar a admin@curifor.com" }));
    fireEvent.click(dialogo().getByRole("checkbox", { name: /^Cuenta activa/ }));
    expect(dialogo().getByText(new RegExp(AVISO_MOTOR))).toBeInTheDocument();
    expect(dialogo().getByRole("button", { name: /Guardar cambios/ })).toBeDisabled();
  });

  it("una cuenta comun no pide confirmacion para cambiar la clave", async () => {
    await abrir();
    fireEvent.click(screen.getByRole("button", { name: "Cambiar la clave de vendedor@ejemplo.cl" }));
    expect(dialogo().queryByText(new RegExp(AVISO_MOTOR))).not.toBeInTheDocument();
  });
});
