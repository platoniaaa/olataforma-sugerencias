/**
 * La pantalla InStock mezcla dos origenes en una sola tabla y eso es lo que puede
 * confundir: lo que viene de la **pauta** del fabricante se recarga solo en cada
 * corrida del motor, y lo que se agrega **a mano** sobrevive a esa recarga.
 *
 * De ahi sale la regla que se prueba aca: el basurero solo aparece en los manuales.
 * Ofrecerlo en uno de la pauta seria mentir -el backend responde 409 y, aunque
 * borrara, la proxima carga lo repondria igual-.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import InstockPage from "@/app/instock/page";
import type { RepuestoInstock } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  instockLista: vi.fn(),
  agregarInstock: vi.fn().mockResolvedValue({ ya_estaba: false }),
  quitarInstock: vi.fn().mockResolvedValue(undefined),
  getSoloLectura: vi.fn().mockReturnValue(false),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    instockLista: mocks.instockLista,
    agregarInstock: mocks.agregarInstock,
    quitarInstock: mocks.quitarInstock,
  },
}));

vi.mock("@/lib/auth", () => ({ getSoloLectura: mocks.getSoloLectura }));

function fila(p: Partial<RepuestoInstock>): RepuestoInstock {
  return {
    producto: "17 DE-PAUTA",
    part_number: null,
    marca: "FORD",
    modelos: "Transit",
    operacion: null,
    minimo: 2,
    activo: true,
    origen: "pauta",
    motivo: null,
    creado_por: null,
    creado_en: null,
    ...p,
  };
}

const LISTA = [
  fila({}),
  fila({
    producto: "19 A-MANO",
    origen: "manual",
    minimo: 3,
    motivo: "se quiebra siempre",
    creado_por: "ana@curifor.com",
  }),
];

beforeEach(() => {
  vi.clearAllMocks();
  mocks.instockLista.mockResolvedValue(LISTA);
  mocks.agregarInstock.mockResolvedValue({ ya_estaba: false });
  mocks.getSoloLectura.mockReturnValue(false);
});

function quitarDe(producto: string) {
  const celda = screen.getByText(producto).closest("tr")!;
  return celda.querySelector('button[title="Quitar de la lista"]');
}

describe("Pantalla InStock", () => {
  it("solo deja quitar los que se agregaron a mano", async () => {
    render(<InstockPage />);
    await screen.findByText("19 A-MANO");

    expect(quitarDe("19 A-MANO")).not.toBeNull();
    expect(quitarDe("17 DE-PAUTA")).toBeNull();
  });

  it("agrega el repuesto y vuelve a leer la lista", async () => {
    render(<InstockPage />);
    await screen.findByText("19 A-MANO");
    expect(mocks.instockLista).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Agregar repuesto/i }));
    fireEvent.change(screen.getByPlaceholderText(/19 MB3Z19N619A/), {
      target: { value: "  19 NUEVO  " },
    });
    fireEvent.change(screen.getByPlaceholderText(/se quiebra seguido/i), {
      target: { value: "lo pidio el taller" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Agregar" }));

    await waitFor(() =>
      expect(mocks.agregarInstock).toHaveBeenCalledWith({
        producto: "19 NUEVO",
        minimo: 2,
        motivo: "lo pidio el taller",
      })
    );
    // Sin la relectura la fila recien agregada no aparece hasta recargar la pagina.
    await waitFor(() => expect(mocks.instockLista).toHaveBeenCalledTimes(2));
  });

  it("si el backend rechaza el codigo, lo dice y no cierra el formulario", async () => {
    mocks.agregarInstock.mockRejectedValue(
      new Error("99 NO-EXISTE no esta en el catalogo")
    );
    render(<InstockPage />);
    await screen.findByText("19 A-MANO");

    fireEvent.click(screen.getByRole("button", { name: /Agregar repuesto/i }));
    fireEvent.change(screen.getByPlaceholderText(/19 MB3Z19N619A/), {
      target: { value: "99 NO-EXISTE" },
    });
    fireEvent.click(screen.getByRole("button", { name: "Agregar" }));

    expect(await screen.findByText(/no esta en el catalogo/i)).toBeInTheDocument();
    // El codigo tecleado sigue ahi para corregirlo.
    expect(screen.getByPlaceholderText(/19 MB3Z19N619A/)).toHaveValue("99 NO-EXISTE");
  });

  it("el de solo lectura mira la lista pero no la toca", async () => {
    mocks.getSoloLectura.mockReturnValue(true);
    render(<InstockPage />);
    await screen.findByText("19 A-MANO");

    expect(screen.queryByRole("button", { name: /Agregar repuesto/i })).toBeNull();
    expect(quitarDe("19 A-MANO")).toBeNull();
  });
});
