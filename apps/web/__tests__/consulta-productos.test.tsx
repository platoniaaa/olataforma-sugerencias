/**
 * Consulta de productos del vendedor: lista con buscador y detalle con stock, reemplazos y
 * ventas. Lo que se cuida: que se pueda buscar y entrar a un producto, que el vendedor tenga el
 * acceso en su menú y que en ninguna pantalla aparezca el costo.
 */
import "@testing-library/jest-dom/vitest";
import type { ReactNode } from "react";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { Sidebar } from "@/components/sidebar";
import ConsultaProductosPage from "@/app/consulta-productos/page";
import DetalleConsultaPage from "@/app/consulta-productos/[producto]/page";
import type { ConsultaDetalle, ConsultaProducto } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  consultaProductos: vi.fn(),
  consultaDetalle: vi.fn(),
  consultaSucursales: vi.fn(),
  esVendedor: vi.fn(),
}));

vi.mock("next/navigation", () => ({ usePathname: () => "/consulta-productos" }));
vi.mock("next/link", () => ({
  default: ({ href, children, ...resto }: { href: string; children: ReactNode }) => (
    <a href={href} {...resto}>{children}</a>
  ),
}));
vi.mock("@/lib/api-client", async (importOriginal) => {
  const real = await importOriginal<typeof import("@/lib/api-client")>();
  return {
    mensajeLectura: real.mensajeLectura,
    MENSAJE_SIN_SERVIDOR: real.MENSAJE_SIN_SERVIDOR,
    api: {
      consultaProductos: mocks.consultaProductos,
      consultaDetalle: mocks.consultaDetalle,
      consultaSucursales: mocks.consultaSucursales,
    },
  };
});
// Los gráficos tienen sus propias pruebas: aquí solo importa que se pidan por la ruta de consulta.
vi.mock("@/components/grafico-ventas", () => ({
  GraficoVentas: ({ producto, consulta, sucursalId }: { producto: string; consulta?: boolean; sucursalId?: string }) => (
    <div data-testid="grafico-ventas">{producto}|{String(consulta)}|{sucursalId ?? ""}</div>
  ),
}));
vi.mock("@/components/grafico-stock-sucursal", () => ({
  GraficoStockSucursal: ({ filas, transito }: { filas: unknown[]; transito?: unknown[] }) => (
    <div data-testid="grafico-stock">{filas.length} filas|{transito?.length ?? 0} transitos</div>
  ),
}));
vi.mock("@/components/grupo-reemplazos", () => ({
  GrupoReemplazos: ({ producto, consulta, sucursalId, alternativa }: {
    producto: string; consulta?: boolean; sucursalId?: string; alternativa?: React.ReactNode;
  }) => (
    <div data-testid="grupo-reemplazos">{producto}|{String(consulta)}|{sucursalId ?? ""}{alternativa}</div>
  ),
}));
vi.mock("@/lib/auth", () => ({
  getEmail: () => "vendedor@ejemplo.cl",
  getNombre: () => null,
  getEsAdmin: () => false,
  getEsVendedor: mocks.esVendedor,
  getPuedeCalibrar: () => false,
  getSoloLectura: () => false,
  logout: vi.fn(),
}));
vi.mock("@/lib/inventario-ciclico", () => ({
  inventarioApi: { yo: () => Promise.resolve({ rol: null, sucursales: null }) },
  rolGuardado: () => null,
}));

const FILTRO: ConsultaProducto = {
  producto: "70 2723982", glosa: "FILTRO DE ACEITE", familia: "FILTROS", subfamilia: null,
  procedencia: null, categoria: null, unidad: "UN", precio: 8500, stock_total: 0, en_transito: 0, reemplazo: null,
};
const TERMINAL: ConsultaProducto = {
  producto: "19 SZ6Z3B437B", glosa: "TERMINAL DE DIRECCION", familia: "DIRECCION", subfamilia: null,
  procedencia: "IMPORTADO", categoria: null, unidad: "UN", precio: 45000, stock_total: 7, en_transito: 5,
  reemplazo: "19 SZ6Z3B437C, 19 SZ6Z3B437D",
};

function pagina(items: ConsultaProducto[], total = items.length) {
  return { items, total, page: 1, limit: 50 };
}

beforeEach(() => {
  mocks.consultaProductos.mockReset();
  mocks.consultaDetalle.mockReset();
  mocks.consultaSucursales.mockReset();
  mocks.consultaSucursales.mockResolvedValue({ producto: "", sucursales: [] });
  mocks.esVendedor.mockReset();
  sessionStorage.clear();
});
afterEach(cleanup);

describe("menú del vendedor", () => {
  it("tiene Productos al lado de sus requerimientos y nada de abastecimiento", () => {
    mocks.esVendedor.mockReturnValue(true);
    render(<Sidebar open onClose={() => undefined} />);
    expect(screen.getByRole("link", { name: "Productos" })).toHaveAttribute("href", "/consulta-productos");
    expect(screen.getByRole("link", { name: "Nuevo requerimiento" })).toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Precios" })).not.toBeInTheDocument();
    expect(screen.queryByRole("link", { name: "Catálogo" })).not.toBeInTheDocument();
  });
});

describe("lista de productos", () => {
  it("muestra cada producto con su precio, su stock y un enlace a su detalle", async () => {
    mocks.consultaProductos.mockResolvedValue(pagina([TERMINAL, FILTRO]));
    render(<ConsultaProductosPage />);

    const enlace = await screen.findByRole("link", { name: /19 SZ6Z3B437B/ });
    expect(enlace).toHaveAttribute("href", "/consulta-productos/19%20SZ6Z3B437B");
    expect(enlace).toHaveTextContent("TERMINAL DE DIRECCION");
    expect(enlace).toHaveTextContent("Tiene 2 reemplazos");
    expect(enlace).toHaveTextContent("Stock 7");
    // Lo que viene en camino se ve en la lista, para no pedir de más.
    expect(enlace).toHaveTextContent("+5 en tránsito");
    expect(screen.getByRole("link", { name: /70 2723982/ })).not.toHaveTextContent("en tránsito");
    expect(screen.getByRole("link", { name: /70 2723982/ })).toHaveTextContent("Sin stock");
    expect(screen.queryByText(/costo/i)).not.toBeInTheDocument();
  });

  it("busca al escribir y manda el texto al servidor", async () => {
    mocks.consultaProductos.mockResolvedValue(pagina([FILTRO]));
    render(<ConsultaProductosPage />);
    await screen.findByRole("link", { name: /70 2723982/ });

    fireEvent.change(screen.getByLabelText("Buscar producto"), { target: { value: "filtro" } });

    await waitFor(() =>
      expect(mocks.consultaProductos).toHaveBeenLastCalledWith(
        { q: "filtro", con_stock: false }, { page: 1, limit: 50 }),
      { timeout: 2000 });
  });

  it("pide solo los que tienen stock cuando se marca la casilla", async () => {
    mocks.consultaProductos.mockResolvedValue(pagina([TERMINAL]));
    render(<ConsultaProductosPage />);
    await screen.findByRole("link", { name: /19 SZ6Z3B437B/ });

    fireEvent.click(screen.getByLabelText("Solo productos con stock"));

    await waitFor(() =>
      expect(mocks.consultaProductos).toHaveBeenLastCalledWith(
        { q: undefined, con_stock: true }, { page: 1, limit: 50 }),
      { timeout: 2000 });
  });

  it("dice qué pasó cuando no hay resultados", async () => {
    mocks.consultaProductos.mockResolvedValue(pagina([]));
    sessionStorage.setItem("consulta_productos_q", "zzz");
    render(<ConsultaProductosPage />);
    expect(await screen.findByText(/No encontramos productos con «zzz»/)).toBeInTheDocument();
  });

  it("ofrece ver más cuando hay más productos que los mostrados y los suma", async () => {
    mocks.consultaProductos
      .mockResolvedValueOnce(pagina([TERMINAL], 2))
      .mockResolvedValueOnce({ items: [FILTRO], total: 2, page: 2, limit: 50 });
    render(<ConsultaProductosPage />);
    await screen.findByRole("link", { name: /19 SZ6Z3B437B/ });

    fireEvent.click(screen.getByRole("button", { name: "Ver más productos" }));

    expect(await screen.findByRole("link", { name: /70 2723982/ })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: /19 SZ6Z3B437B/ })).toBeInTheDocument();
    expect(mocks.consultaProductos).toHaveBeenLastCalledWith(
      { q: undefined, con_stock: false }, { page: 2, limit: 50 });
    expect(screen.queryByRole("button", { name: "Ver más productos" })).not.toBeInTheDocument();
  });

  it("si falla, avisa en palabras del vendedor y deja reintentar", async () => {
    // Un corte de red llega como TypeError("Failed to fetch"): el vendedor no debe leer eso.
    mocks.consultaProductos.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    mocks.consultaProductos.mockResolvedValue(pagina([FILTRO]));
    render(<ConsultaProductosPage />);

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("No se pudo conectar con el servidor");
    expect(aviso).not.toHaveTextContent("Failed to fetch");
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("link", { name: /70 2723982/ })).toBeInTheDocument();
  });

  it("un error del servidor no enseña la ruta de la API ni el texto buscado", async () => {
    sessionStorage.setItem("consulta_productos_q", "filtro");
    mocks.consultaProductos.mockRejectedValue(new Error("Error 500 en /api/consulta/productos?q=filtro&page=1"));
    render(<ConsultaProductosPage />);

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("No se pudo cargar la información");
    expect(aviso).not.toHaveTextContent("/api/");
    expect(aviso).not.toHaveTextContent("500");
  });

  it("recuerda 'Solo productos con stock' al volver desde el detalle", async () => {
    mocks.consultaProductos.mockResolvedValue(pagina([TERMINAL]));
    const primera = render(<ConsultaProductosPage />);
    await screen.findByRole("link", { name: /19 SZ6Z3B437B/ });
    fireEvent.click(screen.getByLabelText("Solo productos con stock"));
    await waitFor(() =>
      expect(mocks.consultaProductos).toHaveBeenLastCalledWith(
        expect.objectContaining({ con_stock: true }), expect.anything()));

    // Se va al detalle (la lista se desmonta) y vuelve: la casilla sigue marcada y se pide con stock.
    primera.unmount();
    mocks.consultaProductos.mockClear();
    render(<ConsultaProductosPage />);
    await waitFor(() => expect(screen.getByLabelText("Solo productos con stock")).toBeChecked());
    await waitFor(() =>
      expect(mocks.consultaProductos).toHaveBeenLastCalledWith(
        expect.objectContaining({ con_stock: true }), expect.anything()));
  });

  it("una respuesta vacía que ya venía en camino no pisa la búsqueda siguiente", async () => {
    // 'zzz' queda en vuelo; se escribe otra letra y la respuesta vacía de 'zzz' llega durante la pausa.
    let responderZzz: (v: ReturnType<typeof pagina>) => void = () => undefined;
    mocks.consultaProductos.mockResolvedValueOnce(pagina([FILTRO]));
    render(<ConsultaProductosPage />);
    await screen.findByRole("link", { name: /70 2723982/ });

    mocks.consultaProductos.mockImplementationOnce(() => new Promise((res) => { responderZzz = res; }));
    fireEvent.change(screen.getByLabelText("Buscar producto"), { target: { value: "zzz" } });
    await waitFor(() => expect(mocks.consultaProductos).toHaveBeenCalledTimes(2), { timeout: 2000 });
    mocks.consultaProductos.mockImplementation(() => new Promise(() => undefined));
    fireEvent.change(screen.getByLabelText("Buscar producto"), { target: { value: "zzzy" } });
    responderZzz(pagina([], 0));
    await new Promise((r) => setTimeout(r, 50));

    // La respuesta vacía de 'zzz' se descartó: no afirma que 'zzzy' no tiene resultados.
    expect(screen.queryByText(/No encontramos productos/)).not.toBeInTheDocument();
    expect(screen.queryByText(/No hay productos para mostrar/)).not.toBeInTheDocument();
  });

  it("si una búsqueda nueva falla, no deja la lista anterior debajo del aviso", async () => {
    mocks.consultaProductos.mockResolvedValueOnce(pagina([FILTRO]));
    render(<ConsultaProductosPage />);
    await screen.findByRole("link", { name: /70 2723982/ });

    mocks.consultaProductos.mockRejectedValue(new TypeError("Failed to fetch"));
    fireEvent.change(screen.getByLabelText("Buscar producto"), { target: { value: "zzz" } });
    expect(await screen.findByRole("alert", {}, { timeout: 2000 })).toHaveTextContent("No se pudo conectar");
    expect(screen.queryByRole("link", { name: /70 2723982/ })).not.toBeInTheDocument();
  });

  it("no dice 'no encontramos' mientras se escribe otra búsqueda", async () => {
    mocks.consultaProductos.mockResolvedValue(pagina([], 0));
    render(<ConsultaProductosPage />);
    await screen.findByText(/No hay productos para mostrar/);

    // Con la búsqueda anterior vacía, escribir otra letra no puede afirmar un resultado que no se buscó.
    mocks.consultaProductos.mockImplementation(() => new Promise(() => undefined));
    fireEvent.change(screen.getByLabelText("Buscar producto"), { target: { value: "zzzy" } });
    expect(screen.queryByText(/No encontramos productos/)).not.toBeInTheDocument();
    expect(screen.getByText("Buscando…")).toBeInTheDocument();
  });
});

const DETALLE: ConsultaDetalle = {
  ...TERMINAL,
  sub_categoria: null, tipo_producto: null, sub_modelo: "FOCUS", cilindrada: null,
  combustible: null, anio: "2015",
  stock_por_sucursal: [
    { bodega: "CURICO", sucursal_id: "CURICO", stock: 4, origen: null },
    { bodega: "LINDEROS", sucursal_id: "LINDEROS", stock: 3, origen: null },
    { bodega: "TALCA", sucursal_id: "TALCA", stock: 0, origen: null },
  ],
  transito_por_sucursal: [
    { sucursal_id: "TALCA", cantidad: 6, pedido_desde: "2026-06-12" },
    { sucursal_id: "02 LINDEROS", cantidad: 3, pedido_desde: null },
  ],
  reemplazo_ford: {
    producto: "19 SZ6Z3B437B", reemplazado_por: "19 SZ6Z3B437C", reemplazado_por_ford: "SZ6Z/3B437/C/",
    cadena: "SZ6Z/3B437/B/ > SZ6Z/3B437/C/", reemplaza_a: [], sucesor_confirmado: true,
    agrupado: true, aviso: null, extraido_en: "2026-10-26T09:00:00",
  },
};

describe("detalle de un producto", () => {
  it("muestra precio, stock por sucursal, reemplazos y pide ventas por la ruta de consulta", async () => {
    mocks.consultaDetalle.mockResolvedValue(DETALLE);
    render(<DetalleConsultaPage params={{ producto: encodeURIComponent("19 SZ6Z3B437B") }} />);

    expect(await screen.findByRole("heading", { name: "19 SZ6Z3B437B" })).toBeInTheDocument();
    expect(mocks.consultaDetalle).toHaveBeenCalledWith("19 SZ6Z3B437B");
    expect(screen.getByText("Precio de venta")).toBeInTheDocument();
    // Solo se listan las sucursales con stock, de mayor a menor (Talca tiene tránsito, pero no stock).
    const bodegas = within(screen.getByRole("heading", { name: "Detalle por bodega" }).closest("section")!);
    const filas = bodegas.getAllByRole("row").map((f) => f.textContent ?? "");
    expect(filas.some((f) => f.includes("CURICO") && f.includes("4"))).toBe(true);
    expect(filas.some((f) => f.includes("TALCA"))).toBe(false);
    // Reemplazos del mix, navegables dentro de la misma vista.
    expect(screen.getByRole("link", { name: "19 SZ6Z3B437D" })).toHaveAttribute(
      "href", "/consulta-productos/19%20SZ6Z3B437D");
    // Lo que dice FORD.
    expect(screen.getByText("FORD dio de baja este código")).toBeInTheDocument();
    // Ventas y grupo de reemplazos por la ruta de consulta (sin costo).
    // El gráfico de stock por sucursal recibe todas las filas de stock del producto.
    expect(screen.getByTestId("grafico-stock")).toHaveTextContent("3 filas|2 transitos");
    // Tarjeta y tabla de tránsito: ya vienen 9 unidades, 6 a Talca (que no tiene stock) y 3 a Linderos.
    expect(screen.getByText("En tránsito")).toBeInTheDocument();
    expect(screen.getByText("Unidades en tránsito")).toBeInTheDocument();
    const enTransito = within(screen.getByRole("heading", { name: "Unidades en tránsito" }).closest("section")!);
    const filasTransito = enTransito.getAllByRole("row").map((f) => f.textContent ?? "");
    expect(filasTransito.some((f) => f.includes("TALCA") && f.includes("6") && f.includes("12-06-2026"))).toBe(true);
    expect(filasTransito.some((f) => f.includes("LINDEROS") && f.includes("Sin fecha"))).toBe(true);
    expect(screen.getByTestId("grafico-ventas")).toHaveTextContent("19 SZ6Z3B437B|true");
    expect(screen.getByTestId("grupo-reemplazos")).toHaveTextContent("19 SZ6Z3B437B|true");
    expect(screen.queryByText(/costo/i)).not.toBeInTheDocument();
  });

  it("sin sucursales con venta no muestra el filtro", async () => {
    mocks.consultaDetalle.mockResolvedValue(DETALLE);
    render(<DetalleConsultaPage params={{ producto: encodeURIComponent("19 SZ6Z3B437B") }} />);
    await screen.findByRole("heading", { name: "19 SZ6Z3B437B" });
    expect(screen.queryByLabelText("Ver ventas de")).not.toBeInTheDocument();
  });

  it("filtra las ventas y el historial de reemplazos por sucursal y recuerda la elección", async () => {
    mocks.consultaDetalle.mockResolvedValue(DETALLE);
    mocks.consultaSucursales.mockResolvedValue({ producto: "19 SZ6Z3B437B", sucursales: ["CURICO", "LINDEROS"] });
    render(<DetalleConsultaPage params={{ producto: encodeURIComponent("19 SZ6Z3B437B") }} />);

    const filtro = await screen.findByLabelText("Ver ventas de");
    expect(mocks.consultaSucursales).toHaveBeenCalledWith("19 SZ6Z3B437B");
    // Sin elegir: todas las sucursales, y los gráficos no reciben sucursal.
    expect(filtro).toHaveValue("");
    expect(screen.getByRole("option", { name: "Todas las sucursales" })).toBeInTheDocument();
    expect(screen.getByRole("option", { name: "LINDEROS" })).toBeInTheDocument();
    expect(screen.getByTestId("grafico-ventas")).toHaveTextContent("19 SZ6Z3B437B|true|");
    expect(screen.getByTestId("grafico-ventas")).not.toHaveTextContent("LINDEROS");
    // Un solo gráfico de ventas: el del código va como alternativa DENTRO del grupo de reemplazos.
    expect(screen.getByTestId("grupo-reemplazos")).toContainElement(screen.getByTestId("grafico-ventas"));
    expect(screen.getAllByTestId("grafico-ventas")).toHaveLength(1);

    fireEvent.change(filtro, { target: { value: "LINDEROS" } });

    // Las dos gráficas piden la venta de esa sucursal.
    expect(screen.getByTestId("grafico-ventas")).toHaveTextContent("19 SZ6Z3B437B|true|LINDEROS");
    expect(screen.getByTestId("grupo-reemplazos")).toHaveTextContent("19 SZ6Z3B437B|true|LINDEROS");
    const aviso = screen.getByText(/Mostrando la venta de/);
    expect(aviso).toHaveTextContent("LINDEROS");
    // El stock de las tarjetas y del gráfico es de todas las sucursales: el texto lo dice.
    expect(aviso).toHaveTextContent("El stock de arriba es de todas las sucursales");
    expect(sessionStorage.getItem("consulta_productos_sucursal")).toBe("LINDEROS");

    // Y volver a "todas" quita el filtro.
    fireEvent.change(filtro, { target: { value: "" } });
    expect(screen.getByTestId("grafico-ventas")).not.toHaveTextContent("LINDEROS");
  });

  it("al abrir otro producto aplica la sucursal elegida antes si también vendió ahí", async () => {
    sessionStorage.setItem("consulta_productos_sucursal", "CURICO");
    mocks.consultaDetalle.mockResolvedValue(DETALLE);
    mocks.consultaSucursales.mockResolvedValue({ producto: "19 SZ6Z3B437B", sucursales: ["CURICO", "TALCA"] });
    render(<DetalleConsultaPage params={{ producto: encodeURIComponent("19 SZ6Z3B437B") }} />);

    await waitFor(() => expect(screen.getByLabelText("Ver ventas de")).toHaveValue("CURICO"));
    expect(screen.getByTestId("grafico-ventas")).toHaveTextContent("|CURICO");
  });

  it("si la sucursal recordada no vendió este producto, vuelve a todas", async () => {
    sessionStorage.setItem("consulta_productos_sucursal", "OVALLE");
    mocks.consultaDetalle.mockResolvedValue(DETALLE);
    mocks.consultaSucursales.mockResolvedValue({ producto: "19 SZ6Z3B437B", sucursales: ["CURICO"] });
    render(<DetalleConsultaPage params={{ producto: encodeURIComponent("19 SZ6Z3B437B") }} />);

    await screen.findByLabelText("Ver ventas de");
    expect(screen.getByLabelText("Ver ventas de")).toHaveValue("");
  });

  it("si el producto no existe, lo dice y deja volver a la lista", async () => {
    // El 404 real de getJSON: nunca debe llegar al vendedor con la ruta de la API.
    mocks.consultaDetalle.mockRejectedValue(new Error("Error 404 en /api/consulta/productos/NO%20EXISTE"));
    render(<DetalleConsultaPage params={{ producto: "NO%20EXISTE" }} />);

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("Este producto no está en el catálogo.");
    expect(aviso).not.toHaveTextContent("/api/");
    expect(screen.getByRole("link", { name: /Volver a productos/ })).toHaveAttribute(
      "href", "/consulta-productos");
    // Reintentar no sirve de nada si el producto no existe.
    expect(screen.queryByRole("button", { name: "Reintentar" })).not.toBeInTheDocument();
  });

  it("si falla el servidor, avisa sin códigos y deja reintentar", async () => {
    mocks.consultaDetalle.mockRejectedValueOnce(new TypeError("Failed to fetch"));
    mocks.consultaDetalle.mockResolvedValue(DETALLE);
    render(<DetalleConsultaPage params={{ producto: encodeURIComponent("19 SZ6Z3B437B") }} />);

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("No se pudo conectar con el servidor");
    expect(aviso).not.toHaveTextContent("Failed to fetch");
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));
    expect(await screen.findByRole("heading", { name: "19 SZ6Z3B437B" })).toBeInTheDocument();
    expect(mocks.consultaDetalle).toHaveBeenCalledTimes(2);
  });

  it("no pide las ventas de 'todas' antes de saber la sucursal recordada", async () => {
    sessionStorage.setItem("consulta_productos_sucursal", "CURICO");
    mocks.consultaDetalle.mockResolvedValue(DETALLE);
    mocks.consultaSucursales.mockResolvedValue({ producto: "19 SZ6Z3B437B", sucursales: ["CURICO", "TALCA"] });
    render(<DetalleConsultaPage params={{ producto: encodeURIComponent("19 SZ6Z3B437B") }} />);

    await waitFor(() => expect(screen.getByTestId("grafico-ventas")).toBeInTheDocument());
    // El gráfico se monta una sola vez y ya con la sucursal: sin parpadeo de 'todas' ni pedido de más.
    expect(screen.getByTestId("grafico-ventas")).toHaveTextContent("|CURICO");
    expect(screen.getByTestId("grupo-reemplazos")).toHaveTextContent("|CURICO");
  });
});
