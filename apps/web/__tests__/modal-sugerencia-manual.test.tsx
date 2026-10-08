/**
 * El modal de sugerencia manual en frases (opción A, aprobada el 08-10-2026).
 *
 * Lo que tiene que cumplir:
 * - "Una sola vez" nunca queda pidiéndose para siempre por omisión: sale con plazo
 *   de 7 días. Pasó en producción (carga masiva del 28-07-2026, 95 productos sin
 *   fecha): antes se pedía confirmar; ahora el valor por defecto ya es seguro.
 * - "Nunca menos de" y "días de venta" son reglas diarias que piden solo lo que
 *   falta, y antes de guardar se ve cuánto se compra hoy.
 * - Si ya hay algo cargado para el mismo producto y sucursal, se reemplaza salvo
 *   que se elija sumar.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { ModalSugerenciaManual } from "@/components/modal-sugerencia-manual";
import { fechaEnDias } from "@/lib/pedido-especial";
import type { ContextoSugerencia, Sucursal } from "@/lib/types";

const PROD = "25 DG9Z8100A";

// 5 en stock, 2 en camino, el sistema pide 3, se venden 0,8 al día.
const CTX: ContextoSugerencia = {
  stock: 5,
  transito: 2,
  sugerido_sistema: 3,
  demanda_diaria: 0.8,
  en_sugerido: true,
  bodegas: [],
  vigentes: [],
  reglas: [],
};

const mocks = vi.hoisted(() => ({
  crearSugerenciaManual: vi.fn(),
  crearRecurrente: vi.fn(),
  crearSugerenciaMasiva: vi.fn(),
  contextoSugerencia: vi.fn(),
  contar: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    crearSugerenciaManual: mocks.crearSugerenciaManual,
    crearRecurrente: mocks.crearRecurrente,
    crearSugerenciaMasiva: mocks.crearSugerenciaMasiva,
    crearSugerenciasPegadas: vi.fn(),
    contextoSugerencia: mocks.contextoSugerencia,
    contar: mocks.contar,
    productos: vi.fn().mockResolvedValue({ items: [] }),
  },
}));

beforeEach(() => {
  vi.clearAllMocks();
  mocks.crearSugerenciaManual.mockResolvedValue({});
  mocks.crearRecurrente.mockResolvedValue({});
  mocks.crearSugerenciaMasiva.mockResolvedValue({ creadas: 3, omitidas: 0, lote_id: "x" });
  mocks.contextoSugerencia.mockResolvedValue(CTX);
  mocks.contar.mockResolvedValue(3);
});

const sucursales = [{ sucursal_id: "LINDEROS", nombre: "LINDEROS" }] as Sucursal[];

function montar(soloIndividual = true) {
  return render(
    <ModalSugerenciaManual
      open
      onClose={() => {}}
      onGuardado={() => {}}
      sucursales={sucursales}
      productoInicial={PROD}
      sucursalInicial="LINDEROS"
      soloIndividual={soloIndividual}
    />
  );
}

const escribir = (etiqueta: string, valor: string) =>
  fireEvent.change(screen.getByLabelText(etiqueta), { target: { value: valor } });

const LINEA = "5 en stock · 2 en camino · el sistema ya pide 3 · se venden 0,8 al día";

describe("ModalSugerenciaManual · frases", () => {
  it("muestra el stock y calcula lo que se compra mientras se escribe", async () => {
    montar();
    expect(await screen.findByText(LINEA)).toBeInTheDocument();

    escribir("Unidades a agregar", "7");

    expect(screen.getByText("Hoy se compran 10 en total")).toBeInTheDocument();
    expect(
      screen.getByText("3 que pide el sistema + 7 tuyas. Quedas con 17, unos 21 días de venta.")
    ).toBeInTheDocument();
    // Se cierra sola con su OC: nadie aprieta "Marcar como pedido".
    expect(
      screen.getByText("Se borra sola cuando su compra aparece en el ERP. Si nadie la compra, a los 7 días.")
    ).toBeInTheDocument();
  });

  it("una sola vez se guarda con plazo de 7 días, sin preguntar nada", async () => {
    montar();
    await screen.findByText(LINEA);
    escribir("Unidades a agregar", "7");
    fireEvent.click(screen.getByRole("button", { name: "Agregar a la compra" }));

    await waitFor(() => expect(mocks.crearSugerenciaManual).toHaveBeenCalledTimes(1));
    expect(mocks.crearSugerenciaManual).toHaveBeenCalledWith(
      expect.objectContaining({
        producto: PROD,
        sucursal_id: "LINDEROS",
        unidades: 7,
        expira_en: fechaEnDias(7),
        reemplazar: false,
      })
    );
    expect(screen.queryByText(/no va a vencer nunca/i)).not.toBeInTheDocument();
  });

  it("'Nunca' guarda sin plazo y lo advierte", async () => {
    montar();
    await screen.findByText(LINEA);
    fireEvent.click(screen.getByRole("button", { name: "Más opciones" }));
    escribir("Si nadie la compra, borrarla a los", "nunca");
    expect(screen.getByText(/Sin plazo sigue sumándose a la compra/)).toBeInTheDocument();

    escribir("Unidades a agregar", "7");
    fireEvent.click(screen.getByRole("button", { name: "Agregar a la compra" }));

    await waitFor(() => expect(mocks.crearSugerenciaManual).toHaveBeenCalledTimes(1));
    expect(mocks.crearSugerenciaManual.mock.calls[0][0].expira_en).toBeUndefined();
  });

  it("'nunca menos de' guarda una regla diaria y dice cuánto compra hoy", async () => {
    montar();
    await screen.findByText(LINEA);
    escribir("Mínimo en unidades", "12");

    expect(screen.getByText("Hoy se compran 5 en total")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Guardar regla" }));

    await waitFor(() => expect(mocks.crearRecurrente).toHaveBeenCalledTimes(1));
    expect(mocks.crearRecurrente).toHaveBeenCalledWith(
      expect.objectContaining({
        modo: "individual",
        producto: PROD,
        sucursal_id: "LINDEROS",
        stock_objetivo: 12,
        cada_dias: 1,
      })
    );
    expect(mocks.crearSugerenciaManual).not.toHaveBeenCalled();
  });

  it("'días de venta' guarda una regla diaria por días", async () => {
    montar();
    await screen.findByText(LINEA);
    escribir("Días de venta", "30");

    expect(screen.getByText("Hoy se compran 17 en total")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Guardar regla" }));

    await waitFor(() => expect(mocks.crearRecurrente).toHaveBeenCalledTimes(1));
    expect(mocks.crearRecurrente).toHaveBeenCalledWith(
      expect.objectContaining({ dias_inventario: 30, cada_dias: 1 })
    );
  });

  it("sin número no guarda", async () => {
    montar();
    await screen.findByText(LINEA);
    fireEvent.click(screen.getByRole("button", { name: "Agregar a la compra" }));

    expect(screen.getByText("Escribe un número mayor que cero.")).toBeInTheDocument();
    expect(mocks.crearSugerenciaManual).not.toHaveBeenCalled();
  });

  it("sin venta registrada no deja guardar por días", async () => {
    mocks.contextoSugerencia.mockResolvedValue({ ...CTX, demanda_diaria: null });
    montar();
    await screen.findByText(/sin venta registrada/);
    escribir("Días de venta", "30");

    expect(screen.getByText("No se puede calcular")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Guardar regla" }));

    expect(screen.getByRole("alert")).toHaveTextContent(/no tiene venta registrada/);
    expect(mocks.crearRecurrente).not.toHaveBeenCalled();
  });
});

describe("ModalSugerenciaManual · ya hay una para el producto", () => {
  const conUna = {
    ...CTX,
    vigentes: [{ id: "s1", unidades: 5, creado_por: null, creado_en: "2026-10-03T12:00:00" }],
  };

  it("por defecto la reemplaza", async () => {
    mocks.contextoSugerencia.mockResolvedValue(conUna);
    montar();
    expect(await screen.findByText(/Ya hay una sugerencia de 5 unidades/)).toHaveTextContent(
      "del 03-10"
    );
    escribir("Unidades a agregar", "7");
    fireEvent.click(screen.getByRole("button", { name: "Agregar a la compra" }));

    await waitFor(() => expect(mocks.crearSugerenciaManual).toHaveBeenCalledTimes(1));
    expect(mocks.crearSugerenciaManual.mock.calls[0][0].reemplazar).toBe(true);
  });

  it("'Sumar las dos' guarda sin reemplazar", async () => {
    mocks.contextoSugerencia.mockResolvedValue(conUna);
    montar();
    await screen.findByText(/Ya hay una sugerencia de 5 unidades/);
    fireEvent.click(screen.getByRole("button", { name: "Sumar las dos" }));
    escribir("Unidades a agregar", "7");
    fireEvent.click(screen.getByRole("button", { name: "Agregar a la compra" }));

    await waitFor(() => expect(mocks.crearSugerenciaManual).toHaveBeenCalledTimes(1));
    expect(mocks.crearSugerenciaManual.mock.calls[0][0].reemplazar).toBe(false);
  });

  it("muestra la regla que ya existe con sus palabras", async () => {
    mocks.contextoSugerencia.mockResolvedValue({
      ...CTX,
      reglas: [
        { id: "r1", stock_objetivo: 12, dias_inventario: null, unidades: null, creado_por: null },
      ],
    });
    montar();
    expect(
      await screen.findByText(/Ya hay una regla para este producto en/)
    ).toHaveTextContent("nunca menos de 12 unidades");
  });
});

describe("ModalSugerenciaManual · varios productos", () => {
  it("una regla para varios productos se guarda por grupo, todos los días", async () => {
    montar(false);
    fireEvent.click(screen.getByRole("button", { name: /Varios productos/ }));
    escribir("Mínimo en unidades", "12");

    const boton = await screen.findByRole("button", { name: "Guardar regla para 3 productos" });
    fireEvent.click(boton);

    await waitFor(() => expect(mocks.crearRecurrente).toHaveBeenCalledTimes(1));
    expect(mocks.crearRecurrente).toHaveBeenCalledWith(
      expect.objectContaining({
        modo: "grupo",
        stock_objetivo: 12,
        cada_dias: 1,
        filtros: expect.objectContaining({ solo_pedir: true }),
      })
    );
  });

  it("una sola vez para varios productos lleva el mismo plazo", async () => {
    montar(false);
    fireEvent.click(screen.getByRole("button", { name: /Varios productos/ }));
    escribir("Unidades a agregar", "2");
    fireEvent.click(await screen.findByRole("button", { name: "Agregar a 3 productos" }));

    await waitFor(() => expect(mocks.crearSugerenciaMasiva).toHaveBeenCalledTimes(1));
    const [, cantidad, , expira] = mocks.crearSugerenciaMasiva.mock.calls[0];
    expect(cantidad).toEqual({ unidades: 2 });
    expect(expira).toBe(fechaEnDias(7));
  });
});
