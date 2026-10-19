/**
 * /cargar: "Motor del PC titular" junto a "Actualizar ahora".
 *
 * Lo que cuidan estos tests:
 * - La tarjeta es solo de admin y muestra la version que informo el motor en la
 *   ultima corrida del panel de Fuentes de datos, con su fecha y el PC.
 * - "Actualizar motor" pide confirmacion con el texto acordado; Cancelar no pide nada.
 *   Al confirmar pide `actualizar_motor` y sigue el estado como "Actualizar ahora".
 * - Las dos tarjetas leen el mismo buzon: lo vivo de una desactiva la otra y dice por
 *   que; un 409 se muestra con el mensaje del servidor mientras describa la solicitud
 *   viva de ahora (no reaparece en una posterior).
 * - Con la API de antes (sin "tipo") el boton no se puede usar: esa API recalcularia.
 * - Si no se pudo leer el estado, lo dice y se reintenta solo.
 * - El resultado muestra el mensaje del PC, la version que quedo y que PC lo atendio;
 *   si no fue el titular, lo avisa.
 */
import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import type { ReactNode } from "react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

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

afterEach(() => {
  vi.useRealTimers();
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

  it("si no se pudo leer el estado, lo dice y se reintenta solo hasta poder", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    // Render se esta reiniciando: la primera lectura falla, la API vuelve despues.
    mocks.actualizacionEstado.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    const boton = within(tarjeta).getByRole("button", { name: "Actualizar motor" });
    const aviso = await within(tarjeta).findByText(
      "No se pudo leer el estado del PC del motor. Se reintenta solo."
    );
    expect(boton).toBeDisabled();
    expect(boton).toHaveAccessibleDescription(aviso.textContent ?? "");
    expect(mocks.actualizacionEstado).toHaveBeenCalledTimes(1);

    await act(async () => {
      await vi.advanceTimersByTimeAsync(15_000);
    });
    await waitFor(() => expect(boton).toBeEnabled());
    expect(within(tarjeta).queryByText(/No se pudo leer el estado/)).not.toBeInTheDocument();
    expect(mocks.actualizacionEstado).toHaveBeenCalledTimes(2);
    // Leido el estado, en reposo no se sigue consultando.
    await act(async () => {
      await vi.advanceTimersByTimeAsync(60_000);
    });
    expect(mocks.actualizacionEstado).toHaveBeenCalledTimes(2);
  });

  it("un 409 viejo no explica el bloqueo de una solicitud posterior", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ id: "s0", tipo: "recalcular", estado: "ok", creado_en: haceMin(120), terminado_en: haceMin(90) })
    );
    mocks.solicitarActualizacion.mockRejectedValueOnce(Object.assign(new Error(MSG_409), { status: 409 }));
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    const boton = within(tarjeta).getByRole("button", { name: "Actualizar motor" });
    await waitFor(() => expect(boton).toBeEnabled());

    // Otra persona pidio recalcular; esta pagina no lo sabia: 409.
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ id: "s1", tipo: "recalcular", estado: "en_curso", creado_en: haceMin(5) })
    );
    fireEvent.click(boton);
    const dialogo = screen.getByRole("dialog");
    fireEvent.click(within(dialogo).getByRole("button", { name: "Actualizar motor" }));
    expect(await within(dialogo).findByRole("alert")).toHaveTextContent(MSG_409);
    fireEvent.click(within(dialogo).getByRole("button", { name: "Cancelar" }));
    expect(within(tarjeta).getByText(MSG_409)).toBeInTheDocument();

    // Ese recalculo termina (lo trae la consulta de cada 5 s).
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ id: "s1", tipo: "recalcular", estado: "ok", creado_en: haceMin(40), terminado_en: haceMin(0) })
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    await waitFor(() => expect(within(tarjeta).queryByText(MSG_409)).not.toBeInTheDocument());

    // Mas tarde, en la misma pestania, "Actualizar ahora": un recalculo NUEVO, pendiente.
    const nuevo = estado({ id: "s2", tipo: "recalcular", estado: "pendiente", creado_en: haceMin(0) });
    mocks.solicitarActualizacion.mockResolvedValueOnce({ ...nuevo, ya_en_curso: false });
    mocks.actualizacionEstado.mockResolvedValue(nuevo);
    fireEvent.click(screen.getByRole("button", { name: /Actualizar ahora/ }));

    const motivo = await within(tarjeta).findByText(/^Hay un recálculo esperando al computador del motor/);
    expect(motivo).toHaveTextContent(/\(pedido hoy a las \d\d:\d\d\)/);
    expect(within(tarjeta).queryByText(MSG_409)).not.toBeInTheDocument();
  });

  it("el 409 de 'Actualizar ahora' tampoco reaparece en una solicitud posterior", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    const msg409Motor =
      "Ya hay una actualización del motor en curso (pedida a las 09:41). Tarda 1 a 2 minutos: " +
      "espera a que termine para pedir otra cosa.";
    mocks.solicitarActualizacion.mockRejectedValueOnce(
      Object.assign(new Error(msg409Motor), { status: 409 })
    );
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    const ahora = screen.getByRole("button", { name: /Actualizar ahora/ });
    await waitFor(() => expect(ahora).toBeEnabled());
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ id: "s1", tipo: "actualizar_motor", estado: "en_curso", creado_en: haceMin(1) })
    );
    fireEvent.click(ahora);
    expect(await screen.findByText(msg409Motor)).toBeInTheDocument();

    // Termina esa actualizacion y el admin pide otra desde esta misma pagina.
    mocks.actualizacionEstado.mockResolvedValue(
      estado({ id: "s1", tipo: "actualizar_motor", estado: "ok", creado_en: haceMin(2), terminado_en: haceMin(0) })
    );
    await act(async () => {
      await vi.advanceTimersByTimeAsync(5_000);
    });
    await waitFor(() => expect(screen.queryByText(msg409Motor)).not.toBeInTheDocument());
    const nueva = estado({ id: "s2", tipo: "actualizar_motor", estado: "pendiente", creado_en: haceMin(0) });
    mocks.solicitarActualizacion.mockResolvedValueOnce({ ...nueva, ya_en_curso: false });
    mocks.actualizacionEstado.mockResolvedValue(nueva);
    const boton = within(tarjeta).getByRole("button", { name: "Actualizar motor" });
    await waitFor(() => expect(boton).toBeEnabled());
    fireEvent.click(boton);
    fireEvent.click(within(screen.getByRole("dialog")).getByRole("button", { name: "Actualizar motor" }));

    expect(
      await screen.findByText(/^Hay una actualización del motor esperando al computador del motor/)
    ).toBeInTheDocument();
    expect(screen.queryByText(msg409Motor)).not.toBeInTheDocument();
  });

  it("dice que PC atendio la actualizacion", async () => {
    mocks.actualizacionEstado.mockResolvedValue(
      estado({
        tipo: "actualizar_motor", estado: "ok", agente: "pc-titular",
        mensaje: "Motor actualizado de d3f556c a e50c697 (4 cambios).",
        version: "e50c697 arreglar-job-diario", creado_en: haceMin(3), terminado_en: haceMin(2),
      })
    );
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    expect(await within(tarjeta).findByText("Lo atendió PC de la jefa.")).toBeInTheDocument();
    expect(within(tarjeta).queryByText(/que no es el titular/)).not.toBeInTheDocument();
  });

  it("si la atendio un PC que no es el titular, avisa que el titular no cambio", async () => {
    // El titular sigue siendo el notebook del duenio; el agente esta en el PC de la jefa.
    const p = panel(corrida({ pc: "NB-DUENO", alias: "Notebook del dueño" }));
    p.pc_titular = "NB-DUENO";
    p.pc_titular_alias = "Notebook del dueño";
    p.carpetas_por_pc = [
      { pc: "PC-JEFA", alias: "PC de la jefa", es_titular: false, corrida_id: "c9", tipo: "prueba",
        iniciada_en: "2026-10-16T11:00:00Z", carpetas: [] },
    ];
    mocks.panel.mockResolvedValue(p);
    mocks.actualizacionEstado.mockResolvedValue(
      estado({
        tipo: "actualizar_motor", estado: "ok", agente: "PC-JEFA",
        mensaje: "Motor actualizado de d3f556c a e50c697 (4 cambios).",
        version: "e50c697 arreglar-job-diario", creado_en: haceMin(3), terminado_en: haceMin(2),
      })
    );
    render(<CargarPage />);
    const tarjeta = await tarjetaMotor();
    expect(await within(tarjeta).findByText("Lo atendió PC de la jefa.")).toBeInTheDocument();
    expect(
      await within(tarjeta).findByText(
        "Se actualizó PC de la jefa, que no es el titular. El titular sigue con d3f556c arreglar-job-diario."
      )
    ).toBeInTheDocument();
  });
});
