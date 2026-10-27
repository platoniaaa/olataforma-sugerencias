/**
 * Pestana Datos de Canal Digital: de donde sale lo que se calcula y si esta al dia.
 * Lo que se cuida: cada estado de una fuente se ve con palabra (no solo color), la tabla no pasa de 14 meses,
 * la cobertura se lee como frase con su porcentaje, y hay estado de carga, de error y de bodega sin venta.
 */
import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CanalDigitalPage from "@/app/canal-digital/page";
import { ChipEstado, PestanaDatos } from "@/components/canal-digital/pestana-datos";
import type { DatosCanalDigital, ResumenCanalDigital } from "@/lib/canal-digital";

const mocks = vi.hoisted(() => ({
  datos: vi.fn(),
  resumen: vi.fn(),
  productos: vi.fn(),
  bodegas: vi.fn(),
  getSoloLectura: vi.fn().mockReturnValue(false),
  getEsAdmin: vi.fn().mockReturnValue(false),
}));

vi.mock("@/lib/canal-digital", async (orig) => ({
  ...(await orig<typeof import("@/lib/canal-digital")>()),
  canalDigitalApi: { datos: mocks.datos, resumen: mocks.resumen, productos: mocks.productos, bodegas: mocks.bodegas },
}));
vi.mock("@/lib/auth", () => ({ getSoloLectura: mocks.getSoloLectura, getEsAdmin: mocks.getEsAdmin }));

/** `n` periodos cargados, del mas reciente (sep-2026) al mas antiguo, como los manda el servidor. */
function porMes(n: number) {
  return Array.from({ length: n }, (_, i) => {
    const indice = 2026 * 12 + 8 - i; // meses desde el ano 0; 8 = septiembre
    return {
      periodo: `${Math.floor(indice / 12)}${String((indice % 12) + 1).padStart(2, "0")}`,
      unidades_netas: 1000 + (n - 1 - i),
      unidades_devueltas: 12,
      lineas: i === 0 ? 0 : 700 + (n - 1 - i), // el mes mas reciente se cargo sin lineas del ERP
    };
  });
}

function datos(extra: Partial<DatosCanalDigital> = {}): DatosCanalDigital {
  return {
    ventas: {
      ultimo_periodo_cargado: "202609", meses_sin_cargar: 0, periodo_desde: "202509", filas: 7500, productos: 700,
      lineas: 12345, lineas_periodo_hasta: "202609", por_mes: porMes(14),
    },
    cobertura: {
      productos: 669, con_proveedor: 497, sin_proveedor: 172, proveedor_menos_5_muestras: 30,
      con_costo: 650, sin_costo: 19, costo_sin_respaldo_stock: 40,
      con_stock_bodega: 300, sin_stock_bodega: 369, con_stock_aparte: 25,
      con_transito_a_la_bodega: 12, con_transito_otro_destino: 80,
    },
    fuentes: [
      { nombre: "Ventas del canal", estado: "ok", detalle: "Al día: cargada hasta 09-2026." },
      { nombre: "Stock de la bodega", estado: "falta", detalle: "Ninguno de los 669 productos tiene stock en la bodega." },
      { nombre: "Plazos de entrega", estado: "aviso", detalle: "172 de 669 productos sin proveedor." },
      { nombre: "Costos", estado: "ok", detalle: "Los 669 productos tienen costo." },
      { nombre: "Grupos de reemplazo", estado: "ok", detalle: "Ningún código está en dos grupos." },
      { nombre: "Tránsito", estado: "aviso", detalle: "Ningún producto tiene pedidos en camino a la bodega." },
    ],
    validaciones: [
      { nombre: "Los acumulados cierran en 100%", ok: true, detalle: "619 productos" },
      { nombre: "Conteo por estado", ok: false, detalle: "falta algo" },
    ],
    como_cargar: [
      "Cada mes cerrado se carga una sola vez.",
      "Mientras tanto la sube quien administra el motor, desde la carpeta api, con: python scripts/canal_digital_cargar_ventas.py --publicar-lineas",
      "Al terminar, vuelve a esta pestaña.",
    ],
    ...extra,
  };
}

beforeEach(() => {
  Object.values(mocks).forEach((m) => {
    m.mockReset();
  });
  mocks.getSoloLectura.mockReturnValue(false);
  mocks.getEsAdmin.mockReturnValue(false);
  mocks.datos.mockResolvedValue(datos());
  mocks.bodegas.mockResolvedValue({ bodegas: [], tipos_venta_sugeridos: [] });
});
afterEach(cleanup);

describe("ChipEstado", () => {
  it.each([
    ["ok", "En orden"],
    ["aviso", "Revisar"],
    ["falta", "Falta"],
  ] as const)("el estado %s se lee como la palabra «%s», no solo como un color", (estado, texto) => {
    render(<ChipEstado estado={estado} />);
    expect(screen.getByText(texto)).toHaveAttribute("data-estado", estado);
  });
});

describe("PestanaDatos", () => {
  it("pide los datos de la bodega y muestra una tarjeta por fuente con su estado en palabras", async () => {
    render(<PestanaDatos bodega="430" />);
    await screen.findByText("Ventas del canal");
    expect(mocks.datos).toHaveBeenCalledWith("430");
    const fuentes = within(screen.getByLabelText("Fuentes de datos"));
    expect(fuentes.getAllByRole("listitem")).toHaveLength(6);
    // cada estado aparece con su palabra: 3 en orden, 2 a revisar, 1 que falta
    expect(fuentes.getAllByText("En orden")).toHaveLength(3);
    expect(fuentes.getAllByText("Revisar")).toHaveLength(2);
    expect(fuentes.getAllByText("Falta")).toHaveLength(1);
    const tarjeta = fuentes.getByText("Stock de la bodega").closest("li") as HTMLElement;
    expect(within(tarjeta).getByText("Falta")).toBeInTheDocument();
    expect(within(tarjeta).getByText(/Ninguno de los 669 productos/)).toBeInTheDocument();
  });

  it("la tabla de ventas muestra mes, unidades netas, devueltas y lineas, con formato chileno", async () => {
    render(<PestanaDatos bodega="430" />);
    const tabla = await screen.findByRole("table");
    expect(within(tabla).getAllByRole("columnheader").map((c) => c.textContent)).toEqual([
      "Mes", "Unidades netas", "Devueltas", "Líneas",
    ]);
    const filas = within(tabla).getAllByRole("row");
    expect(filas).toHaveLength(1 + 14);
    // la primera fila es el mes mas reciente (sep-2026) y es un mes cargado sin lineas
    const primera = within(filas[1]).getAllByRole("cell");
    expect(primera.map((c) => c.textContent)).toEqual(["09-2026", "1.013", "12", "—"]);
    expect(within(filas[1]).getByLabelText("Sin líneas del ERP")).toBeInTheDocument();
    expect(within(filas[2]).getAllByRole("cell").map((c) => c.textContent)).toEqual(["08-2026", "1.012", "12", "712"]);
    expect(screen.getByText(/Cargada desde 09-2025 hasta 09-2026/)).toBeInTheDocument();
    expect(screen.getByText(/12\.345 líneas del ERP \(hasta 09-2026\)/)).toBeInTheDocument();
  });

  it("aunque lleguen mas, la tabla no pasa de 14 meses", async () => {
    mocks.datos.mockResolvedValue(datos({ ventas: { ...datos().ventas, por_mes: porMes(16) } }));
    render(<PestanaDatos bodega="430" />);
    const tabla = await screen.findByRole("table");
    expect(within(tabla).getAllByRole("row")).toHaveLength(1 + 14);
  });

  it("la cobertura se lee como frase con su porcentaje", async () => {
    render(<PestanaDatos bodega="430" />);
    await screen.findByText("Cobertura: cuántos productos tienen cada dato");
    expect(screen.getByText("172 de 669 productos sin proveedor: usan 3 días de respaldo (25,7 %).")).toBeInTheDocument();
    expect(screen.getByText("30 tienen un proveedor con menos de 5 pedidos medidos.")).toBeInTheDocument();
    expect(screen.getByText(/19 de 669 productos sin costo: su valor a pedir sale en \$0 \(2,8 %\)/)).toBeInTheDocument();
    expect(screen.getByText(/300 de 669 productos tienen stock en la bodega \(44,8 %\); 369 no tienen/)).toBeInTheDocument();
    expect(screen.getByText(/12 de 669 productos tienen pedidos en camino a la bodega \(1,8 %\)/)).toBeInTheDocument();
    // cuanto esta cubierto, tambien como numero (no solo como barra)
    expect(screen.getByText("74,3 % cubierto")).toBeInTheDocument();
  });

  it("muestra las validaciones con la que falla a la vista", async () => {
    render(<PestanaDatos bodega="430" />);
    expect(await screen.findByLabelText("Falla")).toBeInTheDocument();
    expect(screen.getByLabelText("Pasa")).toBeInTheDocument();
    expect(screen.getByText(/Conteo por estado\./)).toBeInTheDocument();
  });

  it("muestra los pasos para cargar un mes, con el comando aparte", async () => {
    render(<PestanaDatos bodega="430" />);
    const titulo = await screen.findByText("Cómo cargar un mes nuevo de venta");
    const pasos = within(titulo.closest("section") as HTMLElement).getAllByRole("listitem");
    expect(pasos).toHaveLength(3);
    expect(pasos[0]).toHaveTextContent("Cada mes cerrado se carga una sola vez.");
    const comando = within(pasos[1]).getByText(/^python scripts\/canal_digital_cargar_ventas\.py/);
    expect(comando.tagName).toBe("CODE");
    expect(pasos[1]).toHaveTextContent("desde la carpeta api, con:");
  });

  it("mientras carga muestra un aviso y no la tabla", () => {
    mocks.datos.mockReturnValue(new Promise(() => {}));
    render(<PestanaDatos bodega="430" />);
    expect(screen.getByRole("status")).toHaveTextContent("Cargando datos…");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });

  it("si el servidor falla muestra el motivo y deja reintentar", async () => {
    mocks.datos.mockRejectedValueOnce(new Error("La bodega 999 no existe"));
    render(<PestanaDatos bodega="999" />);
    expect(await screen.findByRole("alert")).toHaveTextContent("La bodega 999 no existe");
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Reintentar/ }));
    expect(await screen.findByText("Ventas del canal")).toBeInTheDocument();
    expect(mocks.datos).toHaveBeenCalledTimes(2);
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("una bodega sin venta lo dice en vez de mostrar una tabla vacia, y sigue explicando como cargar", async () => {
    mocks.datos.mockResolvedValue(
      datos({
        ventas: {
          ultimo_periodo_cargado: null, meses_sin_cargar: null, periodo_desde: null, filas: 0, productos: 0,
          lineas: 0, lineas_periodo_hasta: null, por_mes: [],
        },
        cobertura: {
          productos: 0, con_proveedor: 0, sin_proveedor: 0, proveedor_menos_5_muestras: 0, con_costo: 0, sin_costo: 0,
          costo_sin_respaldo_stock: 0, con_stock_bodega: 0, sin_stock_bodega: 0, con_stock_aparte: 0,
          con_transito_a_la_bodega: 0, con_transito_otro_destino: 0,
        },
        fuentes: [{ nombre: "Ventas del canal", estado: "falta", detalle: "Todavía no hay ningún mes cerrado cargado." }],
      })
    );
    render(<PestanaDatos bodega="431" />);
    expect(await screen.findByText(/Todavía no hay venta cargada para esta bodega/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
    expect(screen.getByText(/la cobertura se calcula cuando haya venta cargada/)).toBeInTheDocument();
    expect(screen.getByText("Cómo cargar un mes nuevo de venta")).toBeInTheDocument();
    expect(screen.getByText("Falta")).toBeInTheDocument();
  });

  it("Actualizar vuelve a pedir los datos", async () => {
    render(<PestanaDatos bodega="430" />);
    await screen.findByText("Ventas del canal");
    fireEvent.click(screen.getByRole("button", { name: /Actualizar/ }));
    await waitFor(() => expect(mocks.datos).toHaveBeenCalledTimes(2));
    expect(await screen.findByRole("button", { name: /Actualizar/ })).toBeEnabled();
  });
});

describe("CanalDigitalPage: pestana Datos", () => {
  function resumen(): ResumenCanalDigital {
    return {
      aviso: {
        periodos: ["202510", "202609"], semanas: ["2025-10-27", "2026-10-19"], fecha_referencia: "2026-10-01",
        productos: 669, sin_proveedor: 172, ultimo_mes_con_ventas: "202609", codigos_en_dos_grupos: 0,
        ultimo_periodo_cargado: "202609", meses_sin_cargar: 0,
      },
      estados: { CLASIFICADO: 619, NUEVO: 31, "SIN MOVIMIENTO": 19 },
      clusters: [],
      totales: { productos: 669, productos_que_piden: 170, unidades_sugeridas: 381, sugerido_pesos: 3_959_837 },
      validaciones: [],
      provisorio: [],
    };
  }

  beforeEach(() => {
    mocks.resumen.mockResolvedValue(resumen());
    mocks.productos.mockResolvedValue({ total: 0, items: [], aviso: resumen().aviso });
  });

  it("Datos va despues de Productos y antes de Bodegas y Politica, y no pide nada hasta que se abre", async () => {
    render(<CanalDigitalPage />);
    await screen.findByText("Piden reposición hoy");
    expect(screen.getAllByRole("tab").map((t) => t.textContent)).toEqual([
      "Sugerido", "Clusters", "Productos", "Datos", "Bodegas", "Política",
    ]);
    expect(mocks.datos).not.toHaveBeenCalled();
  });

  it("al abrir Datos pide los de la bodega 430 y los muestra", async () => {
    render(<CanalDigitalPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Datos" }));
    expect(await screen.findByText("Stock de la bodega")).toBeInTheDocument();
    expect(mocks.datos).toHaveBeenCalledWith("430");
    expect(screen.getByRole("tab", { name: "Datos" })).toHaveAttribute("aria-selected", "true");
  });
});
