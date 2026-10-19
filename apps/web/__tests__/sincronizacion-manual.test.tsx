/**
 * "Actualizar ahora": la tarjeta de /cargar y la version compacta de la portada.
 *
 * Lo que cuidan estos tests:
 * - La tarjeta dice la misma hora (09:30) y las mismas carpetas que la tarea diaria, y
 *   lo que de verdad tarda el motor: entre 25 y 40 minutos (no "unos 3").
 * - "Actualizar ahora" pide un recalculo, y mientras el PC esta actualizando el motor
 *   el boton queda desactivado y dice por que (nunca hay dos solicitudes vivas).
 * - Si el servidor rechaza con 409, se muestra su mensaje tal cual.
 * - Lo que termino de "Actualizar motor" no se muestra como si fuera un recalculo.
 * - La version compacta (la del inicio) no trae el parrafo largo de /cargar.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { SincronizacionManual } from "@/components/sincronizacion-manual";
import type { EstadoActualizacion } from "@/lib/types";

const mocks = vi.hoisted(() => ({ actualizacionEstado: vi.fn(), solicitarActualizacion: vi.fn() }));

vi.mock("@/lib/api-client", () => ({
  api: {
    actualizacionEstado: mocks.actualizacionEstado,
    solicitarActualizacion: mocks.solicitarActualizacion,
  },
}));

const ESTADO: EstadoActualizacion = {
  id: null, tipo: null, estado: null, mensaje: null, version: null, solicitado_por: null,
  creado_en: null, terminado_en: null, ultima_sincronizacion: null, puede_actualizar: true,
};

const haceMin = (min: number) => new Date(Date.now() - min * 60_000).toISOString();

function estado(over: Partial<EstadoActualizacion>): EstadoActualizacion {
  return { ...ESTADO, id: "s1", solicitado_por: "admin@ejemplo.cl", ...over };
}

const MSG_409 =
  "Ya hay una actualización del motor en curso (pedida a las 09:41). Tarda 1 a 2 minutos: " +
  "espera a que termine para pedir otra cosa.";

beforeEach(() => {
  mocks.actualizacionEstado.mockReset();
  mocks.solicitarActualizacion.mockReset();
  mocks.actualizacionEstado.mockResolvedValue(ESTADO);
});

describe("SincronizacionManual", () => {
  it("en /cargar dice la misma hora y las mismas carpetas que la tarea diaria", async () => {
    render(<SincronizacionManual />);
    const texto = await screen.findByText(/Si la tarea de las 09:30 no corrió/);
    expect(texto).toHaveTextContent(/con los Excel de las carpetas de Fuentes de datos/);
    expect(screen.queryByText(/10:00/)).not.toBeInTheDocument();
  });

  it("dice lo que tarda de verdad el motor: entre 25 y 40 minutos", async () => {
    render(<SincronizacionManual />);
    const texto = await screen.findByText(/Si la tarea de las 09:30 no corrió/);
    expect(texto).toHaveTextContent("Tarda entre 25 y 40 minutos.");
    expect(screen.queryByText(/3 minutos/)).not.toBeInTheDocument();
  });

  it("mientras recalcula muestra cuanto va, con el mismo plazo", async () => {
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ tipo: "recalcular", estado: "en_curso", creado_en: haceMin(12.5) })
    );
    render(<SincronizacionManual />);
    const aviso = await screen.findByText(/^Recalculando con los Excel/);
    expect(aviso).toHaveTextContent("Tarda entre 25 y 40 minutos (van 12)");
    expect(screen.getByRole("button", { name: /Actualizando/ })).toBeDisabled();
  });

  it("'Actualizar ahora' pide un recalculo", async () => {
    mocks.solicitarActualizacion.mockResolvedValue({
      ...estado({ tipo: "recalcular", estado: "pendiente", creado_en: haceMin(0) }),
      ya_en_curso: false,
    });
    render(<SincronizacionManual />);
    fireEvent.click(await screen.findByRole("button", { name: /Actualizar ahora/ }));
    await screen.findByText(/Pedido enviado. Esperando al computador que calcula el sugerido/);
    expect(mocks.solicitarActualizacion).toHaveBeenCalledWith("recalcular");
  });

  it("con una actualizacion del motor viva, el boton queda desactivado y dice por que", async () => {
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ tipo: "actualizar_motor", estado: "en_curso", creado_en: haceMin(1) })
    );
    render(<SincronizacionManual />);
    const motivo = await screen.findByText(/^Hay una actualización del motor en curso/);
    expect(motivo).toHaveTextContent(
      /\(pedida (hoy|ayer) a las \d\d:\d\d\)\. Tarda 1 a 2 minutos: cuando termine se puede recalcular\./
    );
    const boton = screen.getByRole("button", { name: /Actualizar ahora/ });
    expect(boton).toBeDisabled();
    expect(boton).toHaveAccessibleDescription(motivo.textContent ?? "");
    // No es un recalculo en curso: nada de "Actualizando" ni "Recalculando".
    expect(screen.queryByText(/Actualizando/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Recalculando/)).not.toBeInTheDocument();
  });

  it("si el servidor rechaza con 409, muestra su mensaje y sigue la solicitud viva", async () => {
    mocks.solicitarActualizacion.mockRejectedValue(Object.assign(new Error(MSG_409), { status: 409 }));
    render(<SincronizacionManual />);
    const boton = await screen.findByRole("button", { name: /Actualizar ahora/ });
    // Otra pestania pidio actualizar el motor: esta recien se entera al leer el estado.
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ tipo: "actualizar_motor", estado: "en_curso", creado_en: haceMin(1) })
    );
    fireEvent.click(boton);
    expect(await screen.findByText(MSG_409)).toBeInTheDocument();
    await waitFor(() => expect(boton).toBeDisabled());
    expect(mocks.actualizacionEstado).toHaveBeenCalledTimes(2);
  });

  it("un error que no es 409 se muestra como alerta", async () => {
    mocks.solicitarActualizacion.mockRejectedValue(
      Object.assign(new Error("No tienes permiso para actualizar los datos."), { status: 403 })
    );
    render(<SincronizacionManual />);
    fireEvent.click(await screen.findByRole("button", { name: /Actualizar ahora/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent(
      "No tienes permiso para actualizar los datos."
    );
  });

  it("lo que termino de 'Actualizar motor' no se muestra como un recalculo listo", async () => {
    mocks.actualizacionEstado.mockResolvedValue(
      estado({
        tipo: "actualizar_motor",
        estado: "ok",
        mensaje: "Motor actualizado de d3f556c a e50c697 (4 cambios).",
        version: "e50c697 arreglar-job-diario",
        creado_en: haceMin(3),
        terminado_en: haceMin(2),
      })
    );
    render(<SincronizacionManual />);
    const boton = await screen.findByRole("button", { name: /Actualizar ahora/ });
    await waitFor(() => expect(mocks.actualizacionEstado).toHaveBeenCalled());
    expect(boton).toBeEnabled();
    expect(screen.queryByText(/Listo/)).not.toBeInTheDocument();
    expect(screen.queryByText(/Motor actualizado/)).not.toBeInTheDocument();
  });

  it("con la API de antes (sin 'tipo'), lo que esta en curso es un recalculo", async () => {
    const viejo: Partial<EstadoActualizacion> = estado({ estado: "en_curso", creado_en: haceMin(2) });
    delete viejo.tipo;
    delete viejo.version;
    mocks.actualizacionEstado.mockResolvedValue(viejo);
    render(<SincronizacionManual />);
    expect(await screen.findByText(/^Recalculando con los Excel/)).toBeInTheDocument();
  });

  it("la version compacta de la portada tambien se bloquea mientras se actualiza el motor", async () => {
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ tipo: "actualizar_motor", estado: "pendiente", creado_en: haceMin(0) })
    );
    render(<SincronizacionManual compacto />);
    expect(
      await screen.findByText(/^Hay una actualización del motor esperando al computador del motor/)
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Actualizar ahora/ })).toBeDisabled();
    expect(screen.queryByText(/Si la tarea de las 09:30 no corrió/)).not.toBeInTheDocument();
  });
});
