/**
 * Pantalla de Canal Digital (bodega 430): resumen por cluster, productos y politica.
 * Lo que se cuida: los 27 clusters siempre se ven, lo provisorio nunca se esconde, la politica
 * se guarda completa y solo la ve el menu de los admin.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CanalDigitalPage from "@/app/canal-digital/page";
import { EditorPolitica, zParaNivel } from "@/components/canal-digital/editor-politica";
import { ResumenClusters } from "@/components/canal-digital/resumen-clusters";
import type { ClusterResumen, FilaPoliticaCD, ResumenCanalDigital } from "@/lib/canal-digital";

const mocks = vi.hoisted(() => ({
  resumen: vi.fn(),
  productos: vi.fn(),
  pasoAPaso: vi.fn(),
  politica: vi.fn(),
  guardarPolitica: vi.fn(),
  exportarCSV: vi.fn(),
  getSoloLectura: vi.fn().mockReturnValue(false),
}));

vi.mock("@/lib/canal-digital", async (orig) => ({
  ...(await orig<typeof import("@/lib/canal-digital")>()),
  canalDigitalApi: {
    resumen: mocks.resumen,
    productos: mocks.productos,
    pasoAPaso: mocks.pasoAPaso,
    politica: mocks.politica,
    guardarPolitica: mocks.guardarPolitica,
    exportarCSV: mocks.exportarCSV,
  },
}));
vi.mock("@/lib/auth", () => ({ getSoloLectura: mocks.getSoloLectura }));

const LETRAS = ["A", "B", "C"];

function clusters(): ClusterResumen[] {
  const out: ClusterResumen[] = [];
  for (const f of LETRAS)
    for (const p of LETRAS)
      for (const v of LETRAS) {
        const aaa = f + p + v === "AAA";
        out.push({
          cluster: f + p + v, frecuencia: f, piezas: p, valor: v,
          productos: aaa ? 30 : 0, unidades_12m: aaa ? 11000 : 0, pct_unidades: aaa ? 0.74 : 0,
          valor_12m: aaa ? 74_000_000 : 0, pct_valor: aaa ? 0.52 : 0,
          modo: f === "C" ? "contra_pedido" : "formula", nivel_servicio: f === "C" ? null : 0.95,
          z: f === "C" ? null : 1.65, minimo_fijo: null,
          productos_que_piden: aaa ? 10 : 0, unidades_sugeridas: aaa ? 137 : 0, sugerido_pesos: aaa ? 1_234_931 : 0,
        });
      }
  return out;
}

function resumen(extra: Partial<ResumenCanalDigital> = {}): ResumenCanalDigital {
  return {
    aviso: {
      periodos: ["202510", "202609"], semanas: ["2025-10-27", "2026-10-19"], fecha_referencia: "2026-10-01",
      productos: 669, sin_proveedor: 196, ultimo_mes_con_ventas: "202609", codigos_en_dos_grupos: 0,
      ultimo_periodo_cargado: "202609", meses_sin_cargar: 0,
    },
    estados: { CLASIFICADO: 619, NUEVO: 31, "SIN MOVIMIENTO": 19 },
    clusters: clusters(),
    totales: { productos: 669, productos_que_piden: 170, unidades_sugeridas: 381, sugerido_pesos: 3_959_837 },
    validaciones: [
      { nombre: "Los acumulados cierran en 100%", ok: true, detalle: "619 productos" },
      { nombre: "Conteo por estado", ok: false, detalle: "falta algo" },
    ],
    provisorio: ["La politica de los 27 clusters son los valores del brief, sin confirmar."],
    ...extra,
  };
}

function politicaFilas(): FilaPoliticaCD[] {
  return clusters().map((c) => ({
    cluster: c.cluster, modo: c.modo, nivel_servicio: c.nivel_servicio, z: c.z, minimo_fijo: c.minimo_fijo,
  }));
}

beforeEach(() => {
  Object.values(mocks).forEach((m) => m.mockReset());
  mocks.getSoloLectura.mockReturnValue(false);
  mocks.resumen.mockResolvedValue(resumen());
  mocks.productos.mockResolvedValue({ total: 0, items: [], aviso: resumen().aviso });
  mocks.politica.mockResolvedValue({
    bodega: "430", modos: ["formula", "contra_pedido", "minimo_fijo"], problemas: [], filas: politicaFilas(),
  });
});
afterEach(cleanup);

describe("zParaNivel", () => {
  it("coincide con la tabla normal dentro de la tolerancia del backend (0,01)", () => {
    expect(Math.abs(zParaNivel(0.9) - 1.2816)).toBeLessThan(0.01);
    expect(Math.abs(zParaNivel(0.95) - 1.6449)).toBeLessThan(0.01);
    expect(Math.abs(zParaNivel(0.97) - 1.8808)).toBeLessThan(0.01);
    expect(Math.abs(zParaNivel(0.98) - 2.0537)).toBeLessThan(0.01);
  });
});

describe("ResumenClusters", () => {
  it("muestra los 27 clusters aunque la mayoria este vacia, y los vacios no se pueden elegir", () => {
    const onElegir = vi.fn();
    render(<ResumenClusters clusters={clusters()} onElegir={onElegir} />);
    expect(screen.getAllByRole("button")).toHaveLength(27);
    const vacio = screen.getByLabelText("Cluster ABC: 0 productos");
    expect(vacio).toBeDisabled();
    fireEvent.click(screen.getByLabelText("Cluster AAA: 30 productos"));
    expect(onElegir).toHaveBeenCalledWith("AAA");
  });
});

describe("EditorPolitica", () => {
  it("pasar a contra pedido limpia nivel, z y minimo; guarda las 27 filas", async () => {
    mocks.guardarPolitica.mockImplementation(async (_b: string, filas: FilaPoliticaCD[]) => ({
      bodega: "430", modos: ["formula", "contra_pedido", "minimo_fijo"], problemas: [], filas,
    }));
    const onGuardada = vi.fn();
    render(<EditorPolitica bodega="430" puedeEditar onGuardada={onGuardada} />);
    const modo = await screen.findByLabelText("Modo del cluster AAA");
    expect(screen.getByRole("button", { name: /Guardar política/ })).toBeDisabled();
    fireEvent.change(modo, { target: { value: "contra_pedido" } });
    expect(screen.getByLabelText("Nivel de servicio del cluster AAA")).toBeDisabled();
    expect(screen.getByLabelText("Nivel de servicio del cluster AAA")).toHaveValue("");
    fireEvent.click(screen.getByRole("button", { name: /Guardar política/ }));
    await waitFor(() => expect(mocks.guardarPolitica).toHaveBeenCalledTimes(1));
    const filas = mocks.guardarPolitica.mock.calls[0][1] as FilaPoliticaCD[];
    expect(filas).toHaveLength(27);
    expect(filas[0]).toMatchObject({ cluster: "AAA", modo: "contra_pedido", nivel_servicio: null, z: null });
    await waitFor(() => expect(onGuardada).toHaveBeenCalled());
    expect(await screen.findByText("Política guardada.")).toBeInTheDocument();
  });

  it("cambiar el nivel de servicio recalcula z, y un error del servidor se muestra sin guardar", async () => {
    mocks.guardarPolitica.mockRejectedValue(new Error("El cluster AAA tiene un z que no corresponde"));
    render(<EditorPolitica bodega="430" puedeEditar onGuardada={vi.fn()} />);
    const nivel = await screen.findByLabelText("Nivel de servicio del cluster AAA");
    fireEvent.change(nivel, { target: { value: "98" } });
    expect(Number((screen.getByLabelText("z del cluster AAA") as HTMLInputElement).value)).toBeCloseTo(2.05, 1);
    fireEvent.click(screen.getByRole("button", { name: /Guardar política/ }));
    expect(await screen.findByText(/no corresponde/)).toBeInTheDocument();
    expect(screen.queryByText("Política guardada.")).not.toBeInTheDocument();
  });

  it("un usuario de solo lectura ve la politica pero no puede editarla", async () => {
    render(<EditorPolitica bodega="430" puedeEditar={false} onGuardada={vi.fn()} />);
    expect(await screen.findByLabelText("Modo del cluster AAA")).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Guardar política/ })).not.toBeInTheDocument();
    expect(screen.getByText(/solo lectura/)).toBeInTheDocument();
  });
});

describe("CanalDigitalPage", () => {
  it("abre en Sugerido: pide solo lo que hoy se debe pedir, ordenado por valor, sin filtros de estado", async () => {
    render(<CanalDigitalPage />);
    await waitFor(() => expect(mocks.productos).toHaveBeenCalled());
    expect(mocks.productos.mock.calls[0][1]).toMatchObject({ solo_pide: true, orden: "sugerido" });
    expect(screen.getByRole("tab", { name: "Sugerido" })).toHaveAttribute("aria-selected", "true");
    expect(screen.queryByText("Solo los que piden hoy")).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Estado")).not.toBeInTheDocument();
    // el orden de las pestanas es el acordado
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual(["Sugerido", "Clusters", "Productos", "Política"]);
  });

  it("muestra los totales arriba, lo provisorio y, en Clusters, las validaciones (con la que falla a la vista)", async () => {
    render(<CanalDigitalPage />);
    expect(await screen.findByText("Piden reposición hoy")).toBeInTheDocument();
    expect(screen.getByText("170")).toBeInTheDocument();
    expect(screen.getByText(/Versión provisoria/)).toBeInTheDocument();
    expect(screen.getByText(/valores del brief/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Clusters" }));
    expect(await screen.findByLabelText("Falla")).toBeInTheDocument();
    expect(screen.getByLabelText("Pasa")).toBeInTheDocument();
    expect(screen.getByText(/196 productos sin proveedor/)).toBeInTheDocument();
  });

  it("elegir un cluster lleva a Productos filtrado por ese cluster", async () => {
    render(<CanalDigitalPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Clusters" }));
    fireEvent.click(await screen.findByLabelText("Cluster AAA: 30 productos"));
    await waitFor(() => expect(mocks.productos.mock.calls.some((c) => c[1].cluster === "AAA")).toBe(true));
    expect(screen.getByText("Cluster AAA ✕")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Cluster AAA ✕"));
    await waitFor(() => expect(mocks.productos.mock.calls.at(-1)?.[1]).toMatchObject({ cluster: undefined }));
  });

  it("avisa cuantos meses cerrados faltan por cargar, y no avisa cuando esta al dia", async () => {
    mocks.resumen.mockResolvedValue(
      resumen({ aviso: { ...resumen().aviso, meses_sin_cargar: 2 } })
    );
    const { unmount } = render(<CanalDigitalPage />);
    expect(await screen.findByText(/faltan 2 meses cerrados/)).toBeInTheDocument();
    unmount();
    cleanup();
    mocks.resumen.mockResolvedValue(resumen());
    render(<CanalDigitalPage />);
    await screen.findByText("Piden reposición hoy");
    expect(screen.queryByText(/meses? cerrados?\. La demanda/)).not.toBeInTheDocument();
  });

  it("sin venta cargada avisa en vez de mostrar una grilla vacia", async () => {
    mocks.resumen.mockResolvedValue(
      resumen({ totales: { productos: 0, productos_que_piden: 0, unidades_sugeridas: 0, sugerido_pesos: 0 } })
    );
    render(<CanalDigitalPage />);
    expect(await screen.findByText(/Todavía no hay venta del canal/)).toBeInTheDocument();
    expect(screen.queryByText("Piden reposición hoy")).not.toBeInTheDocument();
  });

  it("si el servidor falla muestra el motivo", async () => {
    mocks.resumen.mockRejectedValue(new Error("La politica de la bodega 430 no es valida"));
    render(<CanalDigitalPage />);
    expect(await screen.findByText(/no es valida/)).toBeInTheDocument();
  });

  it("pestanas: la politica abre su editor", async () => {
    render(<CanalDigitalPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Política" }));
    expect(await screen.findByLabelText("Modo del cluster AAA")).toBeInTheDocument();
    expect(within(screen.getByRole("tablist")).getByRole("tab", { name: "Política" })).toHaveAttribute("aria-selected", "true");
  });
});
