/**
 * /cargar: "Motor del PC titular" junto a "Actualizar ahora".
 *
 * Lo que cuidan estos tests:
 * - La tarjeta es solo de admin y muestra la version que informo el motor en la
 *   ultima corrida del panel de Fuentes de datos, con su fecha y el PC.
 * - "Actualizar motor" pide confirmacion con el texto acordado; Cancelar no pide nada.
 *   Al confirmar pide `actualizar_motor` y sigue el estado como "Actualizar ahora".
 * - Las dos tarjetas leen el mismo buzon: lo vivo de una desactiva la otra y dice por
 *   que; un 409 se muestra con el mensaje del servidor.
 * - Con la API de antes (sin "tipo") el boton no se puede usar: esa API recalcularia.
 * - El resultado muestra el mensaje del PC y la version que quedo.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import CargarPage from "@/app/cargar/page";
import { TEXTO_CONFIRMAR_MOTOR } from "@/components/motor-pc-titular";
import type { Corrida, Panel } from "@/lib/fuentes-datos";
import type { EstadoActualizacion } from "@/lib/types";

const mocks = vi.hoisted(() => {
  const replace = vi.fn();
  return {
    actualizacionEstado: vi.fn(),
    solicitarActualizacion: vi.fn(),
    panel: vi.fn(),
    esAdmin: true,
    replace,
    router: { replace, push: vi.fn() },
  };
});

vi.mock("@/lib/api-client", () => ({
  api: {
    actualizacionEstado: mocks.actualizacionEstado,
    solicitarActualizacion: mocks.solicitarActualizacion,
    cargarSugerido: vi.fn(),
  },
}));

// Solo se reemplaza la llamada al panel: los formatos de fecha y PC son los reales.
vi.mock("@/lib/fuentes-datos", async (importOriginal) => ({
  ...(await importOriginal<typeof import("@/lib/fuentes-datos")>()),
  fuentesApi: { panel: mocks.panel },
}));

vi.mock("@/lib/auth", () => ({ getEsAdmin: () => mocks.esAdmin }));
vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...rest }: { href: string; children: ReactNode }) => (
    <a href={href} {...rest}>
      {children}
    </a>
  ),
}));
vi.mock("@/components/panel-motor-sombra", () => ({ PanelMotorSombra: () => null }));

const AHORA = "2026-10-16T15:00:00Z"; // 12:00 en Chile (UTC-3 desde septiembre)

const haceMin = (min: number) => new Date(Date.now() - min * 60_000).toISOString();

const ESTADO: EstadoActualizacion = {
  id: null, tipo: null, estado: null, mensaje: null, version: null, solicitado_por: null,
  creado_en: null, terminado_en: null, ultima_sincronizacion: null, puede_actualizar: true,
};

function estado(over: Partial<EstadoActualizacion>): EstadoActualizacion {
  return { ...ESTADO, id: "s1", solicitado_por: "admin@ejemplo.cl", ...over };
}

function corrida(over: Partial<Corrida> = {}): Corrida {
  return {
    id: "c1", pc: "PC-TITULAR", alias: "PC de la jefa", tipo: "oficial", titular: true, publico: true,
    iniciada_en: "2026-10-16T12:34:00Z", terminada_en: "2026-10-16T13:02:00Z", duracion_min: 28,
    resultado: "ok", resultado_texto: "Publicó", motivo_texto: null, config_origen: "plataforma",
    config_version: 3, version_motor: "d3f556c arreglar-job-diario", resumen: {},
    ...over,
  };
}

function panel(ultima: Corrida | null = corrida()): Panel {
  return {
    modo: "prueba", modo_texto: "En prueba", version: 3, pc_titular: "PC-TITULAR",
    pc_titular_alias: "PC de la jefa", ahora: AHORA,
    franja: { nivel: "verde", ultima_corrida: ultima, alertas: [] },
    corrida_id: ultima?.id ?? null, dato_de_corrida: null, fuentes: [], reconoce: [],
    carpetas_por_pc: [],
    activacion: { puede_activar: false, motivo: null, corridas_necesarias: 2, corridas_en_verde: 0 },
    sembrar_desde: [],
  };
}

const MSG_409 =
  "Ya hay un recálculo en curso (pedido a las 09:41). Tarda entre 25 y 40 minutos: espera a " +
  "que termine para pedir otra cosa.";

/** La tarjeta del motor: el bloque que contiene su titulo. */
async function tarjetaMotor() {
  const titulo = await screen.findByText("Motor del PC titular");
  return titulo.closest(".shadow-card") as HTMLElement;
}

beforeEach(() => {
  mocks.actualizacionEstado.mockReset();
  mocks.solicitarActualizacion.mockReset();
  mocks.panel.mockReset();
  mocks.replace.mockReset();
  mocks.esAdmin = true;
  mocks.actualizacionEstado.mockResolvedValue(ESTADO);
  mocks.panel.mockResolvedValue(panel());
});

describe("Motor del PC titular", () => {
  it("muestra la version de la ultima corrida, con su fecha y el PC", async () => {
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    expect(await within(tarjeta).findByText("d3f556c arreglar-job-diario")).toBeInTheDocument();
    expect(within(tarjeta).getByText(/Según la corrida/)).toHaveTextContent(
      "Según la corrida de hoy a las 09:34 en PC de la jefa."
    );
    expect(within(tarjeta).getByText(/El programa que calcula el sugerido/)).toHaveTextContent(
      "instalado en PC de la jefa"
    );
  });

  it("sin corridas todavia lo dice, en vez de una version vacia", async () => {
    mocks.panel.mockResolvedValue(panel(null));
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    expect(await within(tarjeta).findByText(/Todavía no llega ninguna corrida del motor/)).toBeInTheDocument();
  });

  it("si la ultima corrida es de otro PC, avisa que no es la del titular", async () => {
    mocks.panel.mockResolvedValue(panel(corrida({ pc: "PC-DUENO", alias: "PC del dueño", titular: false })));
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    expect(await within(tarjeta).findByText(/Esa corrida no es del PC titular/)).toBeInTheDocument();
  });

  it("no es de quien no es admin", async () => {
    mocks.esAdmin = false;
    render(<CargarPage />);
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/"));
    expect(screen.queryByText("Motor del PC titular")).not.toBeInTheDocument();
    expect(mocks.panel).not.toHaveBeenCalled();
  });

  it("pide confirmacion; Cancelar no pide nada", async () => {
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    const boton = within(tarjeta).getByRole("button", { name: "Actualizar motor" });
    await waitFor(() => expect(boton).toBeEnabled());
    fireEvent.click(boton);
    const dialogo = screen.getByRole("dialog", { name: "¿Actualizar el motor?" });
    expect(within(dialogo).getByText(TEXTO_CONFIRMAR_MOTOR)).toBeInTheDocument();
    expect(TEXTO_CONFIRMAR_MOTOR).toBe(
      "El PC del motor baja la última versión desde GitHub. No recalcula nada. Tarda 1 a 2 " +
        "minutos; tiene que estar prendido y con sesión iniciada."
    );
    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(mocks.solicitarActualizacion).not.toHaveBeenCalled();
  });

  it("al confirmar pide actualizar_motor, sigue el estado y bloquea 'Actualizar ahora'", async () => {
    mocks.solicitarActualizacion.mockResolvedValue({
      ...estado({ tipo: "actualizar_motor", estado: "pendiente", creado_en: haceMin(0) }),
      ya_en_curso: false,
    });
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    const boton = within(tarjeta).getByRole("button", { name: "Actualizar motor" });
    await waitFor(() => expect(boton).toBeEnabled());
    fireEvent.click(boton);
    const dialogo = screen.getByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Actualizar motor" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(mocks.solicitarActualizacion).toHaveBeenCalledWith("actualizar_motor");
    expect(within(tarjeta).getByText(/^Pedido enviado. Esperando al computador del motor/)).toBeInTheDocument();
    expect(within(tarjeta).getByRole("button", { name: /Actualizando motor/ })).toBeDisabled();

    // La otra tarjeta lee el mismo estado: no deja recalcular y dice por que.
    expect(screen.getByRole("button", { name: /Actualizar ahora/ })).toBeDisabled();
    expect(
      screen.getByText(/^Hay una actualización del motor esperando al computador del motor/)
    ).toBeInTheDocument();
  });

  it("mientras recalcula, 'Actualizar motor' queda desactivado y dice por que", async () => {
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ tipo: "recalcular", estado: "en_curso", creado_en: haceMin(10) })
    );
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    const motivo = await within(tarjeta).findByText(/^Hay un recálculo en curso/);
    expect(motivo).toHaveTextContent(
      /\(pedido (hoy|ayer) a las \d\d:\d\d\)\. Tarda entre 25 y 40 minutos: cuando termine se puede actualizar el motor\./
    );
    expect(within(tarjeta).getByRole("button", { name: "Actualizar motor" })).toBeDisabled();
    // Y la tarjeta de "Actualizar ahora" muestra su propio avance.
    expect(screen.getByText(/^Recalculando con los Excel/)).toBeInTheDocument();
  });

  it("un 409 se muestra con el mensaje del servidor y deja el boton bloqueado", async () => {
    mocks.solicitarActualizacion.mockRejectedValue(Object.assign(new Error(MSG_409), { status: 409 }));
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    const boton = within(tarjeta).getByRole("button", { name: "Actualizar motor" });
    await waitFor(() => expect(boton).toBeEnabled());
    // Otra persona pidio recalcular desde su telefono: esta pagina no lo sabia.
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ tipo: "recalcular", estado: "en_curso", creado_en: haceMin(2) })
    );
    fireEvent.click(boton);
    const dialogo = screen.getByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Actualizar motor" }));

    expect(await within(dialogo).findByRole("alert")).toHaveTextContent(MSG_409);
    await waitFor(() =>
      expect(within(dialogo).getByRole("button", { name: "Actualizar motor" })).toBeDisabled()
    );
    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    expect(within(tarjeta).getByText(MSG_409)).toBeInTheDocument();
    expect(boton).toBeDisabled();
  });

  it("con la API de antes (sin 'tipo') no deja pedir: esa API recalcularia", async () => {
    const viejo: Partial<EstadoActualizacion> = { ...ESTADO };
    delete viejo.tipo;
    delete viejo.version;
    mocks.actualizacionEstado.mockResolvedValue(viejo);
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    expect(
      await within(tarjeta).findByText(/La plataforma todavía no tiene publicada esta función/)
    ).toBeInTheDocument();
    expect(within(tarjeta).getByRole("button", { name: "Actualizar motor" })).toBeDisabled();
    // "Actualizar ahora" sigue funcionando como siempre.
    expect(screen.getByRole("button", { name: /Actualizar ahora/ })).toBeEnabled();
  });

  it("al terminar muestra el mensaje del PC y la version que quedo", async () => {
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
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    const resultado = await within(tarjeta).findByText(/^Motor actualizado de d3f556c a e50c697/);
    expect(resultado).toHaveTextContent(/Terminó (hoy|ayer) a las \d\d:\d\d\./);
    const version = within(tarjeta).getByText(/^Versión en ese PC/);
    expect(version).toHaveTextContent("Versión en ese PC: e50c697 arreglar-job-diario");
    expect(version).toHaveTextContent("La versión instalada de arriba cambia con la próxima corrida");
    // "Actualizar ahora" no lo muestra como un recalculo listo.
    expect(screen.queryByText(/Listo — el equipo ya ve los datos actualizados/)).not.toBeInTheDocument();
  });

  it("si el PC no pudo actualizar, muestra el motivo como alerta", async () => {
    const motivo =
      "No se actualizó: el código del motor en este PC tiene cambios sin subir (2 archivos).";
    mocks.actualizacionEstado.mockResolvedValue(
      estado({
        tipo: "actualizar_motor", estado: "error", mensaje: motivo, version: "d3f556c arreglar-job-diario",
        creado_en: haceMin(3), terminado_en: haceMin(2),
      })
    );
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    const alerta = await within(tarjeta).findByRole("alert");
    expect(alerta).toHaveTextContent(motivo);
    expect(alerta).toHaveTextContent("Versión en ese PC: d3f556c arreglar-job-diario");
  });
});
