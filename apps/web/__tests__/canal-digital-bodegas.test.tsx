/**
 * Pestana Bodegas y selector de bodega de Canal Digital.
 * Lo que se cuida: el selector solo aparece con mas de una bodega y todo se recarga al cambiar; el formulario guarda
 * solo lo que cambio y deja ver cada error del servidor; una lista obligatoria no queda vacia; quien es de solo
 * lectura no edita; solo admin agrega bodegas; y el aviso de que los tipos de venta aplican desde la proxima carga.
 */
import "@testing-library/jest-dom/vitest";
import { act, cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import CanalDigitalPage from "@/app/canal-digital/page";
import { PestanaBodegas } from "@/components/canal-digital/pestana-bodegas";
import type { BodegaCD, BodegasCanalDigital, ResumenCanalDigital } from "@/lib/canal-digital";

const mocks = vi.hoisted(() => ({
  bodegas: vi.fn(),
  guardarBodega: vi.fn(),
  crearBodega: vi.fn(),
  resumen: vi.fn(),
  productos: vi.fn(),
  politica: vi.fn(),
  datos: vi.fn(),
  getSoloLectura: vi.fn().mockReturnValue(false),
  getEsAdmin: vi.fn().mockReturnValue(false),
}));

vi.mock("@/lib/canal-digital", async (orig) => ({
  ...(await orig<typeof import("@/lib/canal-digital")>()),
  canalDigitalApi: {
    bodegas: mocks.bodegas,
    guardarBodega: mocks.guardarBodega,
    crearBodega: mocks.crearBodega,
    resumen: mocks.resumen,
    productos: mocks.productos,
    politica: mocks.politica,
    datos: mocks.datos,
  },
}));
vi.mock("@/lib/auth", () => ({ getSoloLectura: mocks.getSoloLectura, getEsAdmin: mocks.getEsAdmin }));

const TIPOS_SUGERIDOS = ["VTA ML", "VTA SHOPIFY", "VTA WALMART", "VTA PARIS"];

function bodega430(extra: Partial<BodegaCD> = {}): BodegaCD {
  return {
    bodega: "430", nombre: "Canal digital 430", activa: true, tipos_venta: [...TIPOS_SUGERIDOS],
    r_semanas: 1, ventana_meses: 12, nuevo_meses: 6, corte_a_pct: 80, corte_b_pct: 95, gestion_dias: 1,
    bodegas_stock: ["BODEGA ML"], bodegas_aparte: ["BODEGA ML-FULL"], bodegas_informativas: ["CD REPUESTOS"],
    ...extra,
  };
}

function bodega500(extra: Partial<BodegaCD> = {}): BodegaCD {
  return bodega430({
    bodega: "500", nombre: "Canal 500", tipos_venta: ["VTA ML"], r_semanas: 2, nuevo_meses: 3,
    bodegas_stock: ["BODEGA 500"], bodegas_aparte: [], bodegas_informativas: [], ...extra,
  });
}

const lista = (...b: BodegaCD[]): BodegasCanalDigital => ({ bodegas: b, tipos_venta_sugeridos: TIPOS_SUGERIDOS });

function resumen(productos = 669): ResumenCanalDigital {
  return {
    aviso: {
      periodos: ["202510", "202609"], semanas: ["2025-10-27", "2026-10-19"], fecha_referencia: "2026-10-01",
      productos, sin_proveedor: 196, ultimo_mes_con_ventas: "202609", codigos_en_dos_grupos: 0,
      ultimo_periodo_cargado: "202609", meses_sin_cargar: 0,
    },
    estados: { CLASIFICADO: productos, NUEVO: 0, "SIN MOVIMIENTO": 0 },
    clusters: [],
    totales: { productos, productos_que_piden: 170, unidades_sugeridas: 381, sugerido_pesos: 3_959_837 },
    validaciones: [],
    provisorio: [],
  };
}

function diferida<T>() {
  let resolver!: (v: T) => void;
  const promesa = new Promise<T>((r) => {
    resolver = r;
  });
  return { promesa, resolver };
}

/** Lo que responde el servidor al guardar: la bodega ya guardada mas los campos que cambiaron y los avisos. */
const guardada = (b: BodegaCD, cambios: string[], avisos: string[] = []) => ({ ...b, cambios, avisos });

beforeEach(() => {
  Object.values(mocks).forEach((m) => m.mockReset());
  mocks.getSoloLectura.mockReturnValue(false);
  mocks.getEsAdmin.mockReturnValue(false);
  mocks.bodegas.mockResolvedValue(lista(bodega430()));
  mocks.resumen.mockResolvedValue(resumen());
  mocks.productos.mockResolvedValue({ total: 0, items: [], aviso: resumen().aviso });
  mocks.politica.mockResolvedValue({ bodega: "430", modos: ["formula"], problemas: [], filas: [] });
});
afterEach(cleanup);

const guardarBtn = () => screen.getByRole("button", { name: /Guardar parámetros/ });
const grupo = (nombre: string) => screen.getByRole("group", { name: nombre });
const TIPOS = "Tipos de venta que cuentan como venta del canal";
const STOCK = "Bodegas cuyo stock cuenta como disponible";

function formulario(props: Partial<React.ComponentProps<typeof PestanaBodegas>> = {}) {
  const alAbrir = {
    onReintentar: vi.fn(), onGuardada: vi.fn(), onCreada: vi.fn(),
  };
  const todas = {
    bodega: "430", datos: lista(bodega430()), error: null, puedeEditar: true, esAdmin: false, ...alAbrir, ...props,
  };
  render(<PestanaBodegas {...todas} />);
  return alAbrir;
}

describe("PestanaBodegas: el formulario", () => {
  it("muestra cada parametro con su etiqueta clara, su ayuda y el valor guardado (numeros con coma)", () => {
    formulario({ datos: lista(bodega430({ gestion_dias: 1.5 })) });
    expect(screen.getByLabelText("Nombre de la bodega")).toHaveValue("Canal digital 430");
    expect(screen.getByLabelText(/Bodega activa/)).toBeChecked();
    expect(screen.getByLabelText("Semanas entre revisiones")).toHaveValue("1");
    expect(screen.getByLabelText("Meses para considerar nuevo un producto")).toHaveValue("6");
    expect(screen.getByLabelText("Días de gestión que se suman al plazo")).toHaveValue("1,5");
    expect(screen.getByLabelText("Corte A del Pareto (%)")).toHaveValue("80");
    expect(screen.getByLabelText("Corte B del Pareto (%)")).toHaveValue("95");
    expect(screen.getByText("Corte A / Corte B del Pareto (%)")).toBeInTheDocument();
    // las listas, como chips
    expect(within(grupo(TIPOS)).getAllByRole("listitem").map((l) => l.textContent)).toEqual(TIPOS_SUGERIDOS);
    expect(within(grupo(STOCK)).getByText("BODEGA ML")).toBeInTheDocument();
    expect(within(grupo("Bodegas que se muestran aparte (no suman)")).getByText("BODEGA ML-FULL")).toBeInTheDocument();
    expect(within(grupo("Bodegas solo informativas")).getByText("CD REPUESTOS")).toBeInTheDocument();
    // ayuda en lenguaje de Abastecimiento
    expect(screen.getByText(/Cada cuántas semanas se revisa y se repone/)).toBeInTheDocument();
    expect(screen.getByText(/Su stock se suma al disponible del producto/)).toBeInTheDocument();
  });

  it("la ventana se ve como dato fijo de 12 meses: no hay donde cambiarla", () => {
    formulario();
    expect(screen.getByText(/Ventana de venta: 12 meses, fija/)).toBeInTheDocument();
    expect(screen.queryByLabelText(/ventana/i)).not.toBeInTheDocument();
  });

  it("avisa que guardar recalcula todo y que los tipos de venta aplican desde la proxima carga", () => {
    formulario();
    expect(screen.getByText(/Al guardar, el resumen y los sugeridos de esta bodega se recalculan/)).toBeInTheDocument();
    expect(screen.getByText(/desde la próxima carga de líneas del ERP/)).toBeInTheDocument();
    expect(screen.getByText(/no se vuelve a filtrar/)).toBeInTheDocument();
  });

  it("Guardar parece deshabilitado sin cambios y se habilita al editar", () => {
    formulario();
    expect(guardarBtn()).toBeDisabled();
    expect(screen.getByRole("button", { name: /Descartar cambios/ })).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Semanas entre revisiones"), { target: { value: "2" } });
    expect(guardarBtn()).toBeEnabled();
    fireEvent.change(screen.getByLabelText("Semanas entre revisiones"), { target: { value: "1" } });
    expect(guardarBtn()).toBeDisabled(); // volver al valor guardado deja de ser un cambio
  });

  it("guarda solo lo que cambio, con el numero ya convertido (coma decimal)", async () => {
    mocks.guardarBodega.mockResolvedValue(guardada(bodega430({ gestion_dias: 2.5, nombre: "Canal ML" }), ["nombre", "gestion_dias"]));
    const { onGuardada } = formulario();
    fireEvent.change(screen.getByLabelText("Días de gestión que se suman al plazo"), { target: { value: "2,5" } });
    fireEvent.change(screen.getByLabelText("Nombre de la bodega"), { target: { value: "  Canal ML " } });
    fireEvent.click(guardarBtn());
    await waitFor(() => expect(mocks.guardarBodega).toHaveBeenCalledTimes(1));
    expect(mocks.guardarBodega).toHaveBeenCalledWith("430", { gestion_dias: 2.5, nombre: "Canal ML" });
    expect(await screen.findByText(/Parámetros guardados\. El resumen y los sugeridos de esta bodega se recalcularon/)).toBeInTheDocument();
    expect(onGuardada).toHaveBeenCalledTimes(1);
    // a la pagina le llega la bodega sin los campos de la respuesta (cambios, avisos)
    expect(onGuardada.mock.calls[0][0]).toEqual(bodega430({ gestion_dias: 2.5, nombre: "Canal ML" }));
    expect(guardarBtn()).toBeDisabled(); // ya no hay nada pendiente
    expect(screen.getByLabelText("Nombre de la bodega")).toHaveValue("Canal ML");
  });

  it("cada parametro viaja con su nombre: cortes, nuevo, semanas y activa", async () => {
    mocks.guardarBodega.mockResolvedValue(guardada(bodega430(), []));
    formulario();
    fireEvent.change(screen.getByLabelText("Corte A del Pareto (%)"), { target: { value: "70" } });
    fireEvent.change(screen.getByLabelText("Corte B del Pareto (%)"), { target: { value: "90,5" } });
    fireEvent.change(screen.getByLabelText("Meses para considerar nuevo un producto"), { target: { value: "4" } });
    fireEvent.change(screen.getByLabelText("Semanas entre revisiones"), { target: { value: "3" } });
    fireEvent.click(screen.getByLabelText(/Bodega activa/));
    fireEvent.click(guardarBtn());
    await waitFor(() => expect(mocks.guardarBodega).toHaveBeenCalled());
    expect(mocks.guardarBodega.mock.calls[0][1]).toEqual({
      corte_a_pct: 70, corte_b_pct: 90.5, nuevo_meses: 4, r_semanas: 3, activa: false,
    });
  });

  it("un error del servidor se ve (todos los problemas) y los cambios no se pierden", async () => {
    mocks.guardarBodega.mockRejectedValue(
      new Error("El corte A (96) debe ser menor que el corte B (95), y el corte B no puede pasar de 100.\n«Semanas entre revisiones» debe estar entre 0 y 8 (llegó 9).")
    );
    const { onGuardada } = formulario();
    fireEvent.change(screen.getByLabelText("Corte A del Pareto (%)"), { target: { value: "96" } });
    fireEvent.click(guardarBtn());
    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(/El corte A \(96\) debe ser menor que el corte B/);
    expect(alerta).toHaveTextContent(/debe estar entre 0 y 8/);
    expect(screen.queryByText(/Parámetros guardados/)).not.toBeInTheDocument();
    expect(onGuardada).not.toHaveBeenCalled();
    expect(screen.getByLabelText("Corte A del Pareto (%)")).toHaveValue("96");
    expect(guardarBtn()).toBeEnabled(); // se puede corregir y reintentar
  });

  it("tras un error, guardar de nuevo borra el error anterior", async () => {
    mocks.guardarBodega.mockRejectedValueOnce(new Error("No se pudo guardar"));
    mocks.guardarBodega.mockResolvedValueOnce(guardada(bodega430({ r_semanas: 2 }), ["r_semanas"]));
    formulario();
    fireEvent.change(screen.getByLabelText("Semanas entre revisiones"), { target: { value: "2" } });
    fireEvent.click(guardarBtn());
    expect(await screen.findByRole("alert")).toBeInTheDocument();
    fireEvent.click(guardarBtn());
    expect(await screen.findByText(/Parámetros guardados/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("si cambio los tipos de venta, muestra el aviso del servidor: aplica a las cargas futuras", async () => {
    const aviso = "Los tipos de venta nuevos se aplican desde la próxima carga de líneas del ERP: la venta ya guardada se filtró con los tipos anteriores y no se vuelve a filtrar.";
    mocks.guardarBodega.mockResolvedValue(guardada(bodega430({ tipos_venta: ["VTA ML"] }), ["tipos_venta"], [aviso]));
    formulario();
    for (const t of ["VTA SHOPIFY", "VTA WALMART", "VTA PARIS"]) {
      fireEvent.click(within(grupo(TIPOS)).getByRole("button", { name: `Quitar ${t}` }));
    }
    fireEvent.click(guardarBtn());
    await waitFor(() => expect(mocks.guardarBodega).toHaveBeenCalledWith("430", { tipos_venta: ["VTA ML"] }));
    expect(await screen.findByText(aviso)).toBeInTheDocument();
  });

  it("Descartar cambios vuelve a lo guardado", () => {
    formulario();
    fireEvent.change(screen.getByLabelText("Nombre de la bodega"), { target: { value: "Otro" } });
    fireEvent.click(within(grupo(STOCK)).getByRole("button", { name: "Quitar BODEGA ML" }));
    fireEvent.click(screen.getByRole("button", { name: /Descartar cambios/ }));
    expect(screen.getByLabelText("Nombre de la bodega")).toHaveValue("Canal digital 430");
    expect(within(grupo(STOCK)).getByText("BODEGA ML")).toBeInTheDocument();
    expect(guardarBtn()).toBeDisabled();
  });

  it("un numero que no es numero se marca y no deja guardar", () => {
    formulario();
    fireEvent.change(screen.getByLabelText("Semanas entre revisiones"), { target: { value: "dos" } });
    expect(screen.getByText("Escribe un número.")).toBeInTheDocument();
    expect(screen.getByLabelText("Semanas entre revisiones")).toBeInvalid();
    expect(guardarBtn()).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Semanas entre revisiones"), { target: { value: "" } });
    expect(guardarBtn()).toBeDisabled();
    fireEvent.change(screen.getByLabelText("Semanas entre revisiones"), { target: { value: "2" } });
    expect(screen.queryByText("Escribe un número.")).not.toBeInTheDocument();
    expect(guardarBtn()).toBeEnabled();
  });

  it("un numero fuera de rango lo juzga el servidor: se manda tal cual y su mensaje se ve", async () => {
    mocks.guardarBodega.mockRejectedValue(new Error("«Semanas entre revisiones» debe estar entre 0 y 8 (llegó 9)."));
    formulario();
    fireEvent.change(screen.getByLabelText("Semanas entre revisiones"), { target: { value: "9" } });
    fireEvent.click(guardarBtn());
    expect(await screen.findByRole("alert")).toHaveTextContent("entre 0 y 8");
    expect(mocks.guardarBodega.mock.calls[0][1]).toEqual({ r_semanas: 9 });
  });
});

describe("PestanaBodegas: las listas como chips", () => {
  it("quitar un tipo de venta lo saca y lo ofrece de nuevo entre los sugeridos", () => {
    formulario();
    const g = grupo(TIPOS);
    expect(within(g).queryByText("Sugeridos:")).not.toBeInTheDocument(); // ya estan los cuatro
    fireEvent.click(within(g).getByRole("button", { name: "Quitar VTA SHOPIFY" }));
    expect(within(g).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["VTA ML", "VTA WALMART", "VTA PARIS"]);
    expect(guardarBtn()).toBeEnabled();
    // un clic en la sugerencia lo devuelve: la lista queda igual que la guardada, asi que no hay cambio
    fireEvent.click(within(g).getByRole("button", { name: "VTA SHOPIFY" }));
    expect(within(g).getAllByRole("listitem")).toHaveLength(4);
    expect(guardarBtn()).toBeDisabled();
  });

  it("se agrega escribiendo y con Enter; varios separados por coma; sin vacios ni repetidos", () => {
    formulario();
    const g = grupo(TIPOS);
    const caja = within(g).getByLabelText("Agregar tipo de venta");
    fireEvent.change(caja, { target: { value: " VTA FALABELLA , ,VTA RIPLEY, VTA ML " } });
    fireEvent.keyDown(caja, { key: "Enter" });
    expect(within(g).getAllByRole("listitem").map((l) => l.textContent)).toEqual([
      ...TIPOS_SUGERIDOS, "VTA FALABELLA", "VTA RIPLEY",
    ]);
    expect(caja).toHaveValue("");
    // el boton Agregar hace lo mismo y esta apagado con la caja vacia
    const agregar = within(g).getByRole("button", { name: "Agregar" });
    expect(agregar).toBeDisabled();
    fireEvent.change(caja, { target: { value: "VTA LIDER" } });
    fireEvent.click(agregar);
    expect(within(g).getByText("VTA LIDER")).toBeInTheDocument();
  });

  it("las bodegas del ERP se comparan sin signos ni mayusculas: 'bodega-ml' ya esta", () => {
    formulario();
    const g = grupo(STOCK);
    fireEvent.change(within(g).getByLabelText("Agregar bodega que suma al disponible"), { target: { value: "bodega-ml, BODEGA 2" } });
    fireEvent.keyDown(within(g).getByLabelText("Agregar bodega que suma al disponible"), { key: "Enter" });
    expect(within(g).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["BODEGA ML", "BODEGA 2"]);
  });

  it("una lista obligatoria vacia lo dice y no deja guardar; una opcional vacia dice Ninguna", () => {
    formulario();
    fireEvent.click(within(grupo(STOCK)).getByRole("button", { name: "Quitar BODEGA ML" }));
    expect(within(grupo(STOCK)).getByText("Debe quedar al menos uno.")).toBeInTheDocument();
    expect(guardarBtn()).toBeDisabled();
    fireEvent.click(within(grupo("Bodegas solo informativas")).getByRole("button", { name: "Quitar CD REPUESTOS" }));
    expect(within(grupo("Bodegas solo informativas")).getByText("Ninguna.")).toBeInTheDocument();
    for (const t of TIPOS_SUGERIDOS) fireEvent.click(within(grupo(TIPOS)).getByRole("button", { name: `Quitar ${t}` }));
    expect(within(grupo(TIPOS)).getByText("Debe quedar al menos uno.")).toBeInTheDocument();
  });

  it("los tipos de venta ofrecen las sugerencias que faltan", () => {
    formulario({ datos: lista(bodega500()), bodega: "500" });
    const g = grupo(TIPOS);
    expect(within(g).getByText("Sugeridos:")).toBeInTheDocument();
    for (const t of ["VTA SHOPIFY", "VTA WALMART", "VTA PARIS"]) {
      expect(within(g).getByRole("button", { name: t })).toBeInTheDocument();
    }
    expect(within(g).queryByRole("button", { name: "VTA ML" })).not.toBeInTheDocument(); // esa ya esta
    // las listas de bodegas no tienen sugerencias
    expect(within(grupo(STOCK)).queryByText("Sugeridos:")).not.toBeInTheDocument();
  });
});

describe("PestanaBodegas: solo lectura", () => {
  it("se ve todo pero no se puede cambiar nada ni guardar", () => {
    formulario({ puedeEditar: false });
    expect(screen.getByLabelText("Nombre de la bodega")).toBeDisabled();
    expect(screen.getByLabelText(/Bodega activa/)).toBeDisabled();
    for (const n of ["Semanas entre revisiones", "Corte A del Pareto (%)", "Corte B del Pareto (%)"]) {
      expect(screen.getByLabelText(n)).toBeDisabled();
    }
    // los chips se leen pero no tienen X ni caja para agregar
    expect(within(grupo(TIPOS)).getAllByRole("listitem")).toHaveLength(4);
    expect(screen.queryByRole("button", { name: /Quitar/ })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Agregar tipo de venta")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Guardar parámetros/ })).not.toBeInTheDocument();
    expect(screen.getByText(/Tu usuario es de solo lectura/)).toBeInTheDocument();
  });
});

describe("PestanaBodegas: estados de la lista", () => {
  it("mientras carga lo dice, y no muestra formulario", () => {
    formulario({ datos: null });
    expect(screen.getByRole("status")).toHaveTextContent("Cargando bodegas…");
    expect(screen.queryByLabelText("Nombre de la bodega")).not.toBeInTheDocument();
  });

  it("si falla la lista muestra el motivo y deja reintentar", () => {
    const { onReintentar } = formulario({ datos: null, error: "No se pudieron cargar las bodegas" });
    expect(screen.getByRole("alert")).toHaveTextContent("No se pudieron cargar las bodegas");
    expect(screen.queryByText("Cargando bodegas…")).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Reintentar/ }));
    expect(onReintentar).toHaveBeenCalledTimes(1);
  });

  it("una bodega que no esta en la lista se avisa en vez de mostrar un formulario ajeno", () => {
    formulario({ bodega: "999" });
    expect(screen.getByText(/No se encontró la bodega 999/)).toBeInTheDocument();
    expect(screen.queryByLabelText("Nombre de la bodega")).not.toBeInTheDocument();
  });

  it("al cambiar la bodega elegida el formulario pasa a los valores de esa bodega", () => {
    const datos = lista(bodega430(), bodega500());
    const props = {
      datos, error: null, puedeEditar: true, esAdmin: false, onReintentar: vi.fn(), onGuardada: vi.fn(), onCreada: vi.fn(),
    };
    const { rerender } = render(<PestanaBodegas bodega="430" {...props} />);
    fireEvent.change(screen.getByLabelText("Nombre de la bodega"), { target: { value: "Cambio sin guardar" } });
    rerender(<PestanaBodegas bodega="500" {...props} />);
    expect(screen.getByLabelText("Nombre de la bodega")).toHaveValue("Canal 500");
    expect(screen.getByLabelText("Semanas entre revisiones")).toHaveValue("2");
    expect(within(grupo(TIPOS)).getAllByRole("listitem").map((l) => l.textContent)).toEqual(["VTA ML"]);
    expect(guardarBtn()).toBeDisabled(); // lo escrito en la otra bodega no se arrastra
    expect(screen.getByText("Bodega 500")).toBeInTheDocument();
  });
});

describe("PestanaBodegas: agregar bodega", () => {
  it("solo admin ve el boton", () => {
    formulario({ esAdmin: false });
    expect(screen.queryByRole("button", { name: "Agregar bodega" })).not.toBeInTheDocument();
    cleanup();
    formulario({ esAdmin: true });
    expect(screen.getByRole("button", { name: "Agregar bodega" })).toBeInTheDocument();
  });

  it("pide codigo y nombre; crear queda apagado sin codigo y cancelar cierra el formulario", () => {
    formulario({ esAdmin: true });
    fireEvent.click(screen.getByRole("button", { name: "Agregar bodega" }));
    const seccion = screen.getByRole("region", { name: "Agregar bodega" });
    expect(within(seccion).getByLabelText("Código de la bodega")).toBeInTheDocument();
    expect(within(seccion).getByLabelText("Nombre de la nueva bodega")).toBeInTheDocument();
    expect(within(seccion).getByRole("button", { name: /Crear bodega/ })).toBeDisabled();
    fireEvent.change(within(seccion).getByLabelText("Código de la bodega"), { target: { value: "  " } });
    expect(within(seccion).getByRole("button", { name: /Crear bodega/ })).toBeDisabled();
    fireEvent.click(within(seccion).getByRole("button", { name: "Cancelar" }));
    expect(screen.queryByRole("region", { name: "Agregar bodega" })).not.toBeInTheDocument();
    expect(mocks.crearBodega).not.toHaveBeenCalled();
  });

  it("crea la bodega, se la entrega a la pagina y avisa que ya se ven sus parametros", async () => {
    mocks.crearBodega.mockResolvedValue(bodega500({ nombre: "Canal Walmart" }));
    const { onCreada } = formulario({ esAdmin: true });
    fireEvent.click(screen.getByRole("button", { name: "Agregar bodega" }));
    fireEvent.change(screen.getByLabelText("Código de la bodega"), { target: { value: "500" } });
    fireEvent.change(screen.getByLabelText("Nombre de la nueva bodega"), { target: { value: "Canal Walmart" } });
    fireEvent.click(screen.getByRole("button", { name: /Crear bodega/ }));
    await waitFor(() => expect(mocks.crearBodega).toHaveBeenCalledWith("500", "Canal Walmart"));
    await waitFor(() => expect(onCreada).toHaveBeenCalledWith(bodega500({ nombre: "Canal Walmart" })));
    expect(screen.queryByRole("region", { name: "Agregar bodega" })).not.toBeInTheDocument();
    expect(await screen.findByText(/Bodega 500 creada/)).toBeInTheDocument();
  });

  it("un codigo repetido o invalido se muestra y no se crea nada", async () => {
    mocks.crearBodega.mockRejectedValue(new Error("La bodega 500 ya existe"));
    const { onCreada } = formulario({ esAdmin: true });
    fireEvent.click(screen.getByRole("button", { name: "Agregar bodega" }));
    fireEvent.change(screen.getByLabelText("Código de la bodega"), { target: { value: "500" } });
    fireEvent.click(screen.getByRole("button", { name: /Crear bodega/ }));
    expect(await screen.findByRole("alert")).toHaveTextContent("La bodega 500 ya existe");
    expect(onCreada).not.toHaveBeenCalled();
    expect(screen.getByRole("region", { name: "Agregar bodega" })).toBeInTheDocument(); // sigue abierto para corregir
    expect(screen.getByRole("button", { name: /Crear bodega/ })).toBeEnabled();
  });
});

describe("CanalDigitalPage: selector de bodega", () => {
  const dosBodegas = () => mocks.bodegas.mockResolvedValue(lista(bodega430(), bodega500()));
  const selector = () => screen.findByRole("combobox", { name: "Bodega" });

  it("con una sola bodega no hay selector; con mas de una aparece con codigo y nombre", async () => {
    const { unmount } = render(<CanalDigitalPage />);
    await screen.findByText("Piden reposición hoy");
    await waitFor(() => expect(mocks.bodegas).toHaveBeenCalled());
    expect(screen.queryByRole("combobox", { name: "Bodega" })).not.toBeInTheDocument();
    unmount();
    cleanup();
    dosBodegas();
    render(<CanalDigitalPage />);
    const sel = await selector();
    expect(within(sel).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "430 · Canal digital 430", "500 · Canal 500",
    ]);
    expect(sel).toHaveValue("430");
  });

  it("empieza en la 430 y todo se pide con ella", async () => {
    dosBodegas();
    render(<CanalDigitalPage />);
    await selector();
    expect(mocks.resumen).toHaveBeenCalledWith("430");
    await waitFor(() => expect(mocks.productos).toHaveBeenCalled());
    expect(mocks.productos.mock.calls[0][0]).toBe("430");
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("bodega 430");
  });

  it("al cambiar de bodega se recarga todo: resumen, tabla de Sugerido y el titulo", async () => {
    dosBodegas();
    mocks.resumen.mockImplementation(async (b: string) => resumen(b === "500" ? 111 : 669));
    render(<CanalDigitalPage />);
    expect(await screen.findByText("669")).toBeInTheDocument();
    fireEvent.change(await selector(), { target: { value: "500" } });
    expect(await screen.findByText("111")).toBeInTheDocument();
    expect(screen.queryByText("669")).not.toBeInTheDocument();
    expect(mocks.resumen).toHaveBeenLastCalledWith("500");
    await waitFor(() => expect(mocks.productos.mock.calls.some((c) => c[0] === "500")).toBe(true));
    expect(screen.getByRole("heading", { level: 1 })).toHaveTextContent("bodega 500");
  });

  it("mientras llega el resumen de la nueva bodega no deja a la vista el de la anterior", async () => {
    dosBodegas();
    const lenta = diferida<ResumenCanalDigital>();
    mocks.resumen.mockImplementation((b: string) => (b === "500" ? lenta.promesa : Promise.resolve(resumen(669))));
    render(<CanalDigitalPage />);
    await screen.findByText("669");
    fireEvent.change(await selector(), { target: { value: "500" } });
    await waitFor(() => expect(screen.queryByText("Piden reposición hoy")).not.toBeInTheDocument());
    expect(screen.queryByText("669")).not.toBeInTheDocument();
    await act(async () => lenta.resolver(resumen(111)));
    expect(await screen.findByText("111")).toBeInTheDocument();
  });

  it("una respuesta tardia de la bodega anterior se descarta y no pisa la nueva", async () => {
    dosBodegas();
    const vieja = diferida<ResumenCanalDigital>();
    mocks.resumen.mockImplementation((b: string) => (b === "430" ? vieja.promesa : Promise.resolve(resumen(111))));
    render(<CanalDigitalPage />);
    fireEvent.change(await selector(), { target: { value: "500" } });
    expect(await screen.findByText("111")).toBeInTheDocument();
    await act(async () => vieja.resolver(resumen(669)));
    expect(screen.getByText("111")).toBeInTheDocument();
    expect(screen.queryByText("669")).not.toBeInTheDocument();
  });

  it("el error de una bodega se limpia al pasar a otra", async () => {
    dosBodegas();
    mocks.resumen.mockImplementation(async (b: string) => {
      if (b === "430") throw new Error("La politica de la bodega 430 no es valida");
      return resumen(111);
    });
    render(<CanalDigitalPage />);
    expect(await screen.findByText(/no es valida/)).toBeInTheDocument();
    fireEvent.change(await selector(), { target: { value: "500" } });
    expect(await screen.findByText("111")).toBeInTheDocument();
    expect(screen.queryByText(/no es valida/)).not.toBeInTheDocument();
  });

  it("las demas pestanas usan la bodega elegida: Politica y Datos piden la de ahora", async () => {
    dosBodegas();
    mocks.datos.mockRejectedValue(new Error("sin datos")); // basta con ver con que bodega se pide
    render(<CanalDigitalPage />);
    const sel = await selector();
    fireEvent.click(screen.getByRole("tab", { name: "Política" }));
    await waitFor(() => expect(mocks.politica).toHaveBeenCalledWith("430"));
    fireEvent.change(sel, { target: { value: "500" } });
    await waitFor(() => expect(mocks.politica).toHaveBeenLastCalledWith("500"));
    fireEvent.click(screen.getByRole("tab", { name: "Datos" }));
    await waitFor(() => expect(mocks.datos).toHaveBeenCalledWith("500"));
    // y al volver a la 430 se vuelve a pedir con la 430
    fireEvent.change(sel, { target: { value: "430" } });
    await waitFor(() => expect(mocks.datos).toHaveBeenLastCalledWith("430"));
  });

  it("al cambiar de bodega se suelta el cluster elegido en la anterior", async () => {
    dosBodegas();
    mocks.resumen.mockResolvedValue({
      ...resumen(),
      clusters: [
        {
          cluster: "AAA", frecuencia: "A", piezas: "A", valor: "A", productos: 30, unidades_12m: 11000, pct_unidades: 0.74,
          valor_12m: 74_000_000, pct_valor: 0.52, modo: "formula", nivel_servicio: 0.95, z: 1.65, minimo_fijo: null,
          productos_que_piden: 10, unidades_sugeridas: 137, sugerido_pesos: 1_234_931,
        },
      ],
    });
    render(<CanalDigitalPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Clusters" }));
    fireEvent.click(await screen.findByLabelText("Cluster AAA: 30 productos"));
    expect(await screen.findByText("Cluster AAA ✕")).toBeInTheDocument();
    fireEvent.change(await selector(), { target: { value: "500" } });
    await waitFor(() => expect(screen.queryByText("Cluster AAA ✕")).not.toBeInTheDocument());
    expect(mocks.productos.mock.calls.at(-1)?.[0]).toBe("500");
    expect(mocks.productos.mock.calls.at(-1)?.[1].cluster).toBeUndefined();
  });

  it("una bodega desactivada se sigue consultando pero la pantalla lo avisa", async () => {
    mocks.bodegas.mockResolvedValue(lista(bodega430(), bodega500({ activa: false })));
    render(<CanalDigitalPage />);
    const sel = await selector();
    expect(screen.queryByText(/Esta bodega está desactivada/)).not.toBeInTheDocument();
    expect(within(sel).getByRole("option", { name: /500 · Canal 500 \(desactivada\)/ })).toBeInTheDocument();
    fireEvent.change(sel, { target: { value: "500" } });
    expect(await screen.findByText(/Esta bodega está desactivada/)).toBeInTheDocument();
    expect(await screen.findByText("Piden reposición hoy")).toBeInTheDocument(); // y los numeros se ven
  });

  it("si falla la lista de bodegas la pantalla sigue con la 430 y la pestana Bodegas muestra el motivo", async () => {
    mocks.bodegas.mockRejectedValue(new Error("No se pudieron cargar las bodegas"));
    render(<CanalDigitalPage />);
    expect(await screen.findByText("Piden reposición hoy")).toBeInTheDocument();
    expect(screen.queryByRole("combobox", { name: "Bodega" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Bodegas" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudieron cargar las bodegas");
    mocks.bodegas.mockResolvedValue(lista(bodega430()));
    fireEvent.click(screen.getByRole("button", { name: /Reintentar/ }));
    expect(await screen.findByLabelText("Nombre de la bodega")).toHaveValue("Canal digital 430");
  });
});

describe("CanalDigitalPage: pestana Bodegas", () => {
  it("abre el formulario de la bodega elegida, y al cambiar el selector pasa a la otra", async () => {
    mocks.bodegas.mockResolvedValue(lista(bodega430(), bodega500()));
    render(<CanalDigitalPage />);
    const sel = await screen.findByRole("combobox", { name: "Bodega" });
    fireEvent.click(screen.getByRole("tab", { name: "Bodegas" }));
    expect(await screen.findByLabelText("Nombre de la bodega")).toHaveValue("Canal digital 430");
    fireEvent.change(sel, { target: { value: "500" } });
    await waitFor(() => expect(screen.getByLabelText("Nombre de la bodega")).toHaveValue("Canal 500"));
    expect(screen.getByRole("tab", { name: "Bodegas" })).toHaveAttribute("aria-selected", "true");
  });

  it("guardar recalcula los totales de arriba y el selector muestra el nombre nuevo", async () => {
    mocks.bodegas.mockResolvedValue(lista(bodega430(), bodega500()));
    mocks.guardarBodega.mockResolvedValue(guardada(bodega430({ nombre: "Canal ML", corte_a_pct: 70 }), ["nombre", "corte_a_pct"]));
    render(<CanalDigitalPage />);
    await screen.findByText("Piden reposición hoy");
    fireEvent.click(screen.getByRole("tab", { name: "Bodegas" }));
    const llamadas = mocks.resumen.mock.calls.length;
    mocks.resumen.mockResolvedValue(resumen(700));
    fireEvent.change(await screen.findByLabelText("Corte A del Pareto (%)"), { target: { value: "70" } });
    fireEvent.change(screen.getByLabelText("Nombre de la bodega"), { target: { value: "Canal ML" } });
    fireEvent.click(guardarBtn());
    await screen.findByText(/Parámetros guardados/);
    await waitFor(() => expect(mocks.resumen.mock.calls.length).toBe(llamadas + 1));
    expect(await screen.findByText("700")).toBeInTheDocument();
    expect(within(screen.getByRole("combobox", { name: "Bodega" })).getByRole("option", { name: "430 · Canal ML" })).toBeInTheDocument();
  });

  it("un usuario de solo lectura ve los parametros y no puede cambiarlos", async () => {
    mocks.getSoloLectura.mockReturnValue(true);
    render(<CanalDigitalPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Bodegas" }));
    expect(await screen.findByLabelText("Nombre de la bodega")).toBeDisabled();
    expect(screen.queryByRole("button", { name: /Guardar parámetros/ })).not.toBeInTheDocument();
  });

  it("el admin agrega una bodega: aparece el selector y queda elegida la nueva, con todo recargado", async () => {
    mocks.getEsAdmin.mockReturnValue(true);
    mocks.crearBodega.mockResolvedValue(bodega500());
    mocks.resumen.mockImplementation(async (b: string) => resumen(b === "500" ? 111 : 669));
    render(<CanalDigitalPage />);
    await screen.findByText("669");
    expect(screen.queryByRole("combobox", { name: "Bodega" })).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: "Bodegas" }));
    fireEvent.click(await screen.findByRole("button", { name: "Agregar bodega" }));
    fireEvent.change(screen.getByLabelText("Código de la bodega"), { target: { value: "500" } });
    fireEvent.change(screen.getByLabelText("Nombre de la nueva bodega"), { target: { value: "Canal 500" } });
    fireEvent.click(screen.getByRole("button", { name: /Crear bodega/ }));
    const sel = await screen.findByRole("combobox", { name: "Bodega" });
    expect(sel).toHaveValue("500");
    expect(within(sel).getAllByRole("option").map((o) => o.textContent)).toEqual([
      "430 · Canal digital 430", "500 · Canal 500",
    ]);
    expect(await screen.findByText("111")).toBeInTheDocument();
    expect(mocks.resumen).toHaveBeenLastCalledWith("500");
    expect(screen.getByLabelText("Nombre de la bodega")).toHaveValue("Canal 500");
    expect(screen.getByText(/Bodega 500 creada/)).toBeInTheDocument();
  });

  it("quien no es admin no ve 'Agregar bodega'", async () => {
    render(<CanalDigitalPage />);
    fireEvent.click(await screen.findByRole("tab", { name: "Bodegas" }));
    await screen.findByLabelText("Nombre de la bodega");
    expect(screen.queryByRole("button", { name: "Agregar bodega" })).not.toBeInTheDocument();
  });
});
