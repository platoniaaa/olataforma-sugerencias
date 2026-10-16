/**
 * La clave escrita no queda en el estado de React despues de cerrar o guardar.
 *
 * La pagina deja montados los dos dialogos (crear/editar y cambiar clave), y el
 * estado vive en ellos, no en el Dialog: con la pestaña en /usuarios la clave en
 * texto plano seguia en memoria (y a la vista con React DevTools) hasta la
 * proxima vez que se abria el dialogo. Para verlo, el Dialog de estos tests
 * dibuja su contenido aunque este cerrado: asi se lee lo que quedo guardado.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { DialogoClave } from "@/components/usuarios/dialogo-clave";
import { FormularioUsuario } from "@/components/usuarios/formulario-usuario";
import type { UsuarioAdmin } from "@/lib/usuarios";

const mocks = vi.hoisted(() => ({ guardar: vi.fn() }));

vi.mock("@/components/ui/dialog", () => ({
  Dialog: ({ open, children }: { open: boolean; children: ReactNode }) => (
    <div data-abierto={open}>{children}</div>
  ),
}));
vi.mock("@/lib/api-client", () => ({ api: {} }));
vi.mock("@/lib/usuarios", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/usuarios")>()),
  usuariosApi: { guardar: mocks.guardar },
}));

beforeEach(() => {
  mocks.guardar.mockReset().mockImplementation(async (d: { email: string }) => ({ ...USUARIO, email: d.email }));
});

const USUARIO: UsuarioAdmin = {
  email: "persona@ejemplo.cl", nombre: "Persona", activo: true, es_admin: false, solo_lectura: false,
  es_vendedor: false, sucursales: [], creado_en: null, es_cuenta_motor: false, permisos_especiales: [],
};

const sinCallbacks = { onClose: () => {}, onGuardado: () => {} };

function escribirClave(etiqueta: string, clave: string) {
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: clave } });
  fireEvent.change(screen.getByLabelText("Repite la clave"), { target: { value: clave } });
}

describe("cambiar clave", () => {
  const props = { usuario: USUARIO, minimoClave: 4, horasSesion: 12, ...sinCallbacks };

  it("al cerrar sin guardar se borra lo escrito", () => {
    const { rerender } = render(<DialogoClave open {...props} />);
    escribirClave("Clave nueva", "secreta99");
    expect(screen.getByLabelText("Clave nueva")).toHaveValue("secreta99");

    rerender(<DialogoClave open={false} {...props} />);
    expect(screen.getByLabelText("Clave nueva")).toHaveValue("");
    expect(screen.getByLabelText("Repite la clave")).toHaveValue("");
  });

  it("al guardar se borra antes de avisar", async () => {
    const onGuardado = vi.fn();
    render(<DialogoClave open {...props} onGuardado={onGuardado} />);
    escribirClave("Clave nueva", "secreta99");
    fireEvent.click(screen.getByRole("button", { name: /Cambiar clave/ }));

    await waitFor(() => expect(onGuardado).toHaveBeenCalled());
    expect(screen.getByLabelText("Clave nueva")).toHaveValue("");
  });
});

describe("crear usuario", () => {
  const props = {
    usuario: null, sucursales: [], errorSucursales: null, correosExistentes: [], minimoClave: 4,
    emailPropio: null, ...sinCallbacks,
  };

  it("al cerrar sin guardar se borra la clave inicial", () => {
    const { rerender } = render(<FormularioUsuario open {...props} />);
    escribirClave("Clave inicial", "secreta99");

    rerender(<FormularioUsuario open={false} {...props} />);
    expect(screen.getByLabelText("Clave inicial")).toHaveValue("");
    expect(screen.getByLabelText("Repite la clave")).toHaveValue("");
  });

  it("al guardar se borra antes de avisar", async () => {
    const onGuardado = vi.fn();
    render(<FormularioUsuario open {...props} onGuardado={onGuardado} />);
    fireEvent.change(screen.getByLabelText("Correo"), { target: { value: "nueva@ejemplo.cl" } });
    escribirClave("Clave inicial", "secreta99");
    fireEvent.click(screen.getByRole("button", { name: /Crear usuario/ }));

    await waitFor(() => expect(onGuardado).toHaveBeenCalled());
    expect(screen.getByLabelText("Clave inicial")).toHaveValue("");
  });
});
