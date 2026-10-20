/**
 * La lista de precios con vigencia: el filtro «Vigencia», el recuadro «Vencen en 7 días» y
 * la columna nueva para quien ya había guardado sus columnas.
 *
 * La tabla, la ficha y el resto de los modales se reemplazan por piezas mínimas: lo que se
 * prueba acá es lo que la PÁGINA hace con ellos (qué le pide a la API, qué les pasa).
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PreciosPage from "@/app/precios/page";
import { KEYS_PRECIOS_DEFAULT } from "@/lib/columnas-precios";
import type { PrecioResumen } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  precios: vi.fn(),
  filtros: vi.fn(),
  resumen: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    precios: mocks.precios,
    preciosFiltros: mocks.filtros,
    preciosResumen: mocks.resumen,
  },
}));
vi.mock("@/lib/auth", () => ({ getPuedePrecios: () => true }));
vi.mock("@/components/tutorial-precios", () => ({ TutorialPrecios: () => null }));
vi.mock("@/components/carga-precios-excel", () => ({ CargaPreciosExcel: () => null }));
vi.mock("@/components/configurar-columnas-precios", () => ({ ConfigurarColumnasPrecios: () => null }));
vi.mock("@/components/tabla-precios", () => ({
  TablaPrecios: (p: { columnasVisibles: string[]; hoy?: string; onFila: (f: unknown) => void }) => (
    <div data-testid="tabla" data-columnas={p.columnasVisibles.join(",")} data-hoy={p.hoy ?? ""}>
      <button onClick={() => p.onFila({ producto: "71 X", estado: "OK" })}>abrir ficha</button>
    </div>
  ),
}));
vi.mock("@/components/ficha-precio", () => ({
  PROCEDENCIAS: ["Nacional", "Importado"],
  ModalProducto: (p: { producto: string; hoy?: string }) => (
    <div data-testid="ficha" data-hoy={p.hoy ?? ""}>{p.producto}</div>
  ),
}));

const RESUMEN: PrecioResumen = {
  productos: 39948, con_cambios: 0, por_estado: {}, ultimo_recalculo: null, ultimo_envio: null,
  overrides: 3163, pendientes_envio: 0,
};

const vigencias = (extra: Partial<NonNullable<PrecioResumen["vigencias"]>> = {}) => ({
  hoy: "2026-10-20", vigentes: 0, programadas: 0, vencidas: 0, vencen_7_dias: 0, por_aplicar: 0, ...extra,
});

beforeEach(() => {
  localStorage.clear();
  mocks.precios.mockReset().mockResolvedValue({ items: [], total: 0, page: 1, limit: 2000 });
  mocks.filtros.mockReset().mockResolvedValue({ rubros: [], tipos: [], procedencias: [], estados: ["OK", "FIJO"] });
  mocks.resumen.mockReset().mockResolvedValue({ ...RESUMEN, vigencias: vigencias() });
});

afterEach(() => {
  localStorage.clear();
});

async function abrir() {
  render(<PreciosPage />);
  await screen.findByText("Lista de precios");
  await waitFor(() => expect(mocks.resumen).toHaveBeenCalled());
}

/** Los filtros con que se pidió la lista por última vez. */
const ultimosFiltros = () => mocks.precios.mock.calls[mocks.precios.mock.calls.length - 1][0];

describe("recuadro «Vencen en 7 días»", () => {
  it("mientras nadie ha puesto un periodo, no aparece", async () => {
    await abrir();
    await waitFor(() => expect(screen.getByText("Productos")).toBeInTheDocument());

    expect(screen.queryByText("Vencen en 7 días")).not.toBeInTheDocument();
  });

  it("con una API que todavía no trae vigencias, la pantalla abre igual", async () => {
    mocks.resumen.mockResolvedValue(RESUMEN);
    await abrir();

    expect(await screen.findByText("Productos")).toBeInTheDocument();
    expect(screen.queryByText("Vencen en 7 días")).not.toBeInTheDocument();
    expect(screen.queryByText(/ya vencidos/)).not.toBeInTheDocument();
  });

  it("con periodos muestra cuántos vencen esta semana y cuántos ya vencieron", async () => {
    mocks.resumen.mockResolvedValue({ ...RESUMEN, vigencias: vigencias({ vigentes: 12, vencidas: 2, vencen_7_dias: 3 }) });
    await abrir();

    const recuadro = (await screen.findByText("Vencen en 7 días")).closest("button") as HTMLElement;
    expect(recuadro).toHaveTextContent("3");
    expect(recuadro).toHaveTextContent("y 2 ya vencidos");
    expect(recuadro).toHaveTextContent("Clic para filtrar");
  });

  it("avisa los vencidos que quedaron sin precio y el ERP sigue con el de la campaña", async () => {
    mocks.resumen.mockResolvedValue({
      ...RESUMEN, vigencias: vigencias({ vigentes: 1, vencidas: 2, vencidas_sin_precio: 2 }),
    });
    await abrir();

    const aviso = (await screen.findByText("Vencidos sin precio")).closest("div, button") as HTMLElement;
    expect(aviso).toHaveTextContent("2");
    expect(aviso).toHaveTextContent("el ERP sigue con el precio de la campaña");
  });

  it("sin vencidos sin precio no muestra ese recuadro", async () => {
    mocks.resumen.mockResolvedValue({ ...RESUMEN, vigencias: vigencias({ vigentes: 12, vencidas: 2, vencen_7_dias: 3 }) });
    await abrir();

    await screen.findByText("Vencen en 7 días");
    expect(screen.queryByText("Vencidos sin precio")).not.toBeInTheDocument();
  });

  it("un clic filtra lo que vence pronto y lo ya vencido; otro clic lo quita", async () => {
    mocks.resumen.mockResolvedValue({ ...RESUMEN, vigencias: vigencias({ vigentes: 12, vencidas: 2, vencen_7_dias: 3 }) });
    await abrir();

    fireEvent.click((await screen.findByText("Vencen en 7 días")).closest("button") as HTMLElement);

    await waitFor(() => expect(ultimosFiltros().vigencia).toEqual(["vence_7d", "vencida"]));
    expect(screen.getByText("Filtrando · clic para quitar")).toBeInTheDocument();

    fireEvent.click(screen.getByText("Vencen en 7 días").closest("button") as HTMLElement);

    await waitFor(() => expect(ultimosFiltros().vigencia).toBeUndefined());
    expect(screen.queryByText("Filtrando · clic para quitar")).not.toBeInTheDocument();
  });

  it("si solo hay periodos programados, el recuadro se ve pero no ofrece filtrar (no hay qué mostrar)", async () => {
    mocks.resumen.mockResolvedValue({ ...RESUMEN, vigencias: vigencias({ programadas: 4 }) });
    await abrir();

    const recuadro = await screen.findByText("Vencen en 7 días");
    expect(recuadro.closest("button")).toBeNull();
    // (El recuadro de «Con cambios sin revisar» sí ofrece filtrar: se mira solo el de vigencias.)
    expect(within(recuadro.parentElement as HTMLElement).queryByText("Clic para filtrar")).not.toBeInTheDocument();
  });
});

describe("filtro «Vigencia»", () => {
  it("ofrece Vigente, Vence en 7 días, Programada y Vencida", async () => {
    await abrir();

    fireEvent.click(screen.getByRole("button", { name: /^Vigencia/ }));

    for (const opcion of ["Vigente", "Vence en 7 días", "Programada", "Vencida"]) {
      expect(await screen.findByRole("button", { name: opcion })).toBeInTheDocument();
    }
  });

  it("elegir una opción la pide a la API y aparece «Limpiar»; limpiar la quita", async () => {
    await abrir();
    expect(screen.queryByRole("button", { name: "Limpiar" })).not.toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /^Vigencia/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Vencida" }));

    await waitFor(() => expect(ultimosFiltros().vigencia).toEqual(["vencida"]));
    fireEvent.click(screen.getByRole("button", { name: "Limpiar" }));

    await waitFor(() => expect(ultimosFiltros().vigencia).toBeUndefined());
    expect(screen.queryByRole("button", { name: "Limpiar" })).not.toBeInTheDocument();
  });

  it("varias opciones se piden juntas", async () => {
    await abrir();

    fireEvent.click(screen.getByRole("button", { name: /^Vigencia/ }));
    fireEvent.click(await screen.findByRole("button", { name: "Programada" }));
    fireEvent.click(await screen.findByRole("button", { name: "Vencida" }));

    await waitFor(() => expect(ultimosFiltros().vigencia).toEqual(["programada", "vencida"]));
  });
});

describe("columnas y fecha de hoy", () => {
  it("a quien ya había guardado sus columnas se le suma «Vigencia», y se guarda", async () => {
    const antigua = KEYS_PRECIOS_DEFAULT.filter((k) => k !== "vigente_hasta");
    localStorage.setItem("precios_columnas_visibles", JSON.stringify(antigua));
    await abrir();

    await waitFor(() => expect(screen.getByTestId("tabla").dataset.columnas?.split(",")).toContain("vigente_hasta"));
    await waitFor(() => expect(JSON.parse(localStorage.getItem("precios_columnas_visibles") ?? "[]")).toContain("vigente_hasta"));
  });

  it("si la oculta, no vuelve a aparecer en la visita siguiente", async () => {
    const antigua = KEYS_PRECIOS_DEFAULT.filter((k) => k !== "vigente_hasta");
    localStorage.setItem("precios_columnas_visibles", JSON.stringify(antigua));
    localStorage.setItem("precios_columnas_vistas", JSON.stringify([...antigua, "vigente_hasta"]));
    await abrir();

    await waitFor(() => expect(screen.getByTestId("tabla")).toBeInTheDocument());
    expect(screen.getByTestId("tabla").dataset.columnas?.split(",")).not.toContain("vigente_hasta");
  });

  it("quien nunca guardó columnas ve las de por defecto, con Vigencia", async () => {
    await abrir();

    expect((await screen.findByTestId("tabla")).dataset.columnas?.split(",")).toEqual(KEYS_PRECIOS_DEFAULT);
    expect(KEYS_PRECIOS_DEFAULT).toContain("vigente_hasta");
  });

  it("la tabla y la ficha reciben el «hoy» del servidor", async () => {
    mocks.resumen.mockResolvedValue({ ...RESUMEN, vigencias: vigencias({ hoy: "2026-10-20" }) });
    await abrir();

    await waitFor(() => expect(screen.getByTestId("tabla").dataset.hoy).toBe("2026-10-20"));
    fireEvent.click(screen.getByRole("button", { name: "abrir ficha" }));

    expect((await screen.findByTestId("ficha")).dataset.hoy).toBe("2026-10-20");
  });

  it("«Editar con Excel» queda marcado para el recorrido guiado", async () => {
    await abrir();

    expect(screen.getByRole("button", { name: /Editar con Excel/ })).toHaveAttribute("data-tour", "excel");
  });
});
