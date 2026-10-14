/**
 * Política de precios: crear un tipo, asignárselo a un rubro, ver qué cambia y
 * guardar todo junto.
 *
 * El 14-10-2026 la política dijo "el rubro 35 va con factor 1,88" y la pantalla
 * no podía: el factor es por tipo y el rubro 35 compartía "Liviano" con otros 30
 * rubros. Lo que estos tests cuidan:
 *
 * 1. Que un tipo nuevo no pueda pisar uno que ya existe, ni con otra mayúscula
 *    ni con el alias ("Baterias" es "Bateria").
 * 2. Que al servidor viaje solo lo que cambió, y "que sigan al rubro" solo para
 *    rubros que cambian en ese guardado.
 * 3. Que el flujo completo mande UN guardado con todo, después de mostrar qué cambia.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import PoliticasPreciosPage from "@/app/precios/politicas/page";
import { cambioPolitica, errorTipoNuevo, filasTipoNuevo } from "@/lib/politica-precios";
import type { PoliticaFactor, PoliticaRubro, VistaPreviaPolitica } from "@/lib/types";

const FACTORES: PoliticaFactor[] = [
  { tipo: "Bateria", procedencia: "Nacional", factor: 1.33, descuento_max: 0, margen_post: null },
  { tipo: "Liviano", procedencia: "Nacional", factor: 1.78, descuento_max: 20, margen_post: null },
  { tipo: "Liviano", procedencia: "Importado", factor: 1.89, descuento_max: 20, margen_post: null },
];
const RUBROS: PoliticaRubro[] = [
  { rubro: "34", tipo: "Liviano", procedencia_forzada: null },
  { rubro: "35", tipo: "Liviano", procedencia_forzada: null },
];
const VISTA: VistaPreviaPolitica = {
  productos_revisados: 1534, cambian: 385, suben: 385, bajan: 0, variacion_mediana: 0.0562,
  rubros: [{
    rubro: "35", tipo_antes: "Liviano", tipo_despues: "Rubro 35",
    procedencia_antes: null, procedencia_despues: null,
    productos: 1534, siguen_al_rubro: 1439, por_glosa: 2, decididos: 5, cambian: 385,
    manuales: [{ tipo: "Filtro Liviano", productos: 93 }], manuales_con_precio: 78,
    procedencias: { Nacional: 1534 },
    factor_antes: { Nacional: 1.78, Importado: 1.89 }, factor_despues: { Nacional: 1.88, Importado: 1.88 },
    seguir_al_rubro: false,
  }],
  ejemplos: [{ producto: "35 34106879122", glosa: "DISCO DE FRENO", precio_antes: 209542, precio_despues: 221315 }],
};

const mocks = vi.hoisted(() => ({
  factores: vi.fn(),
  rubros: vi.fn(),
  vista: vi.fn(),
  guardar: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    politicaFactores: mocks.factores,
    politicaRubros: mocks.rubros,
    vistaPreviaPolitica: mocks.vista,
    guardarPolitica: mocks.guardar,
  },
}));

vi.mock("@/lib/auth", () => ({ getPuedePrecios: () => true }));

// Con llaves: si beforeEach devuelve una funcion, vitest la llama al terminar la
// prueba como limpieza, y mockReset() devuelve el propio mock.
beforeEach(() => {
  mocks.factores.mockReset().mockResolvedValue(FACTORES);
  mocks.rubros.mockReset().mockResolvedValue(RUBROS);
  mocks.vista.mockReset().mockResolvedValue(VISTA);
  mocks.guardar.mockReset().mockResolvedValue({
    factores: ["Rubro 35/Nacional: nuevo 1.88"], rubros: ["rubro 35: (Liviano, None) -> (Rubro 35, None)"],
    seguir_al_rubro: { productos: 93, por_tipo: { "Filtro Liviano": 93 } },
    recalculo: { productos: 39830, cambios: 2000, productos_con_cambios: 1532, por_campo: { precio: 466, tipo: 1532 } },
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

const FORM = { nombre: "Rubro 35", nacional: "1,88", importado: "1,88", descuento: "20" };

describe("errorTipoNuevo", () => {
  const tipos = ["Bateria", "Liviano"];

  it("acepta un tipo nuevo con factores escritos con coma", () => {
    expect(errorTipoNuevo(FORM, tipos)).toBeNull();
    expect(filasTipoNuevo(FORM).map((f) => [f.procedencia, f.factor, f.descuento_max])).toEqual([
      ["Nacional", 1.88, 20], ["Importado", 1.88, 20],
    ]);
  });

  it("no deja pisar un tipo que existe, ni con otra mayúscula ni con el alias", () => {
    expect(errorTipoNuevo({ ...FORM, nombre: "liviano" }, tipos)).toMatch(/Ya existe/);
    expect(errorTipoNuevo({ ...FORM, nombre: "Baterias" }, tipos)).toMatch(/Ya existe/);
    expect(errorTipoNuevo({ ...FORM, nombre: "sugerido" }, tipos)).toMatch(/Ya existe/);
  });

  it("pide nombre, factores sobre 1 y un descuento de 0 a 100", () => {
    expect(errorTipoNuevo({ ...FORM, nombre: " " }, tipos)).toMatch(/nombre/);
    expect(errorTipoNuevo({ ...FORM, nacional: "1" }, tipos)).toMatch(/factor nacional/);
    expect(errorTipoNuevo({ ...FORM, importado: "" }, tipos)).toMatch(/factor importado/);
    expect(errorTipoNuevo({ ...FORM, descuento: "120" }, tipos)).toMatch(/descuento/);
    expect(errorTipoNuevo({ ...FORM, descuento: "0" }, tipos)).toBeNull();
  });
});

describe("cambioPolitica", () => {
  it("manda solo lo que cambió", () => {
    const factores = [...FACTORES, ...filasTipoNuevo(FORM)];
    const rubros = RUBROS.map((r) => (r.rubro === "35" ? { ...r, tipo: "Rubro 35" } : r));

    const c = cambioPolitica(factores, FACTORES, rubros, RUBROS, ["35"]);

    expect(c.factores.map((f) => `${f.tipo}/${f.procedencia}`)).toEqual(["Rubro 35/Nacional", "Rubro 35/Importado"]);
    expect(c.rubros).toEqual([{ rubro: "35", tipo: "Rubro 35", procedencia_forzada: null }]);
    expect(c.seguir_al_rubro).toEqual(["35"]);
  });

  it("no manda un factor vacío ni 'que sigan al rubro' de un rubro que no cambia", () => {
    const factores = FACTORES.map((f) => (f.tipo === "Liviano" && f.procedencia === "Nacional" ? { ...f, factor: Number.NaN } : f));

    const c = cambioPolitica(factores, FACTORES, RUBROS, RUBROS, ["34"]);

    expect(c).toEqual({ factores: [], rubros: [], seguir_al_rubro: [] });
  });
});

describe("Política de precios · tipo nuevo para un rubro", () => {
  it("crea el tipo, lo asigna al rubro 35, muestra qué cambia y guarda todo junto", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    render(<PoliticasPreciosPage />);
    await screen.findByLabelText("Tipo del rubro 35");

    // 1. El tipo nuevo.
    fireEvent.change(screen.getByLabelText("Nombre del tipo"), { target: { value: "Rubro 35" } });
    fireEvent.change(screen.getByLabelText("Factor nacional"), { target: { value: "1,88" } });
    fireEvent.change(screen.getByLabelText("Factor importado"), { target: { value: "1,88" } });
    fireEvent.change(screen.getByLabelText("Descuento máx. %"), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: /Agregar tipo/ }));
    expect(screen.getByText("nuevo · sin guardar")).toBeInTheDocument();

    // 2. Se lo asigna al rubro 35: el tipo nuevo ya aparece en el selector.
    const selector = screen.getByLabelText("Tipo del rubro 35");
    expect(within(selector).getByRole("option", { name: "Rubro 35" })).toBeInTheDocument();
    fireEvent.change(selector, { target: { value: "Rubro 35" } });

    // 3. Antes de guardar dice qué cambia.
    expect(await screen.findByText(/385 productos cambian de precio/)).toBeInTheDocument();
    expect(mocks.vista).toHaveBeenLastCalledWith({
      factores: [
        { tipo: "Rubro 35", procedencia: "Nacional", factor: 1.88, descuento_max: 20, margen_post: null },
        { tipo: "Rubro 35", procedencia: "Importado", factor: 1.88, descuento_max: 20, margen_post: null },
      ],
      rubros: [{ rubro: "35", tipo: "Rubro 35", procedencia_forzada: null }],
      seguir_al_rubro: [],
    });
    expect(screen.getByText(/Factor nacional \(1\.534 productos\): 1,78 → 1,88/)).toBeInTheDocument();

    // Los filtros con tipo escrito a mano se suman solo si se marca.
    fireEvent.click(screen.getByRole("checkbox", { name: /Que también sigan al rubro los 93/ }));
    await waitFor(() =>
      expect(mocks.vista).toHaveBeenLastCalledWith(expect.objectContaining({ seguir_al_rubro: ["35"] })));

    // 4. Un solo guardado con todo.
    fireEvent.click(screen.getByRole("button", { name: /Guardar cambios/ }));
    await waitFor(() => expect(mocks.guardar).toHaveBeenCalledTimes(1));
    expect(mocks.guardar.mock.calls[0][0]).toEqual(expect.objectContaining({
      rubros: [{ rubro: "35", tipo: "Rubro 35", procedencia_forzada: null }],
      seguir_al_rubro: ["35"],
    }));
    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("Cambian 385 precios"));
    // Cuenta precios, como la vista previa, no productos con cualquier cambio.
    expect(await screen.findByText(/Cambiaron 466 precios; 93 productos dejaron su tipo/)).toBeInTheDocument();
    // Recarga lo guardado: el tipo ya no figura como "sin guardar".
    expect(mocks.factores).toHaveBeenCalledTimes(2);
  });

  it("un nombre repetido no se agrega y dice por qué", async () => {
    render(<PoliticasPreciosPage />);
    await screen.findByLabelText("Tipo del rubro 35");

    fireEvent.change(screen.getByLabelText("Nombre del tipo"), { target: { value: "LIVIANO" } });
    fireEvent.change(screen.getByLabelText("Factor nacional"), { target: { value: "1,88" } });
    fireEvent.change(screen.getByLabelText("Factor importado"), { target: { value: "1,88" } });
    fireEvent.change(screen.getByLabelText("Descuento máx. %"), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: /Agregar tipo/ }));

    expect(screen.getByRole("alert")).toHaveTextContent(/Ya existe el tipo "LIVIANO"/);
    expect(screen.queryByText("nuevo · sin guardar")).not.toBeInTheDocument();
  });

  it("descartar vuelve a lo guardado sin llamar al servidor", async () => {
    render(<PoliticasPreciosPage />);
    const selector = await screen.findByLabelText("Tipo del rubro 34");
    fireEvent.change(selector, { target: { value: "Bateria" } });
    await screen.findByRole("region", { name: "Cambios sin guardar" });

    fireEvent.click(screen.getByRole("button", { name: "Descartar" }));

    expect(screen.getByLabelText("Tipo del rubro 34")).toHaveValue("Liviano");
    expect(screen.queryByRole("region", { name: "Cambios sin guardar" })).not.toBeInTheDocument();
    expect(mocks.guardar).not.toHaveBeenCalled();
  });

  it("mientras guarda no se puede editar: un cambio hecho a medio guardar se perdía al recargar", async () => {
    // El 14-10-2026 el rubro 35 se eligió mientras corría un guardado; al terminar,
    // la página recargó lo del servidor y el cambio desapareció sin aviso.
    vi.spyOn(window, "confirm").mockReturnValue(true);
    let terminar: (v: unknown) => void = () => {};
    mocks.guardar.mockReturnValue(new Promise((r) => { terminar = r; }));
    render(<PoliticasPreciosPage />);
    fireEvent.change(await screen.findByLabelText("Tipo del rubro 34"), { target: { value: "Bateria" } });
    await screen.findByText(/385 productos cambian de precio/);

    fireEvent.click(screen.getByRole("button", { name: /Guardar cambios/ }));

    await waitFor(() => expect(screen.getByLabelText("Tipo del rubro 35")).toBeDisabled());
    expect(screen.getByLabelText("Factor Liviano Nacional")).toBeDisabled();
    expect(screen.getByLabelText("Nombre del tipo")).toBeDisabled();
    terminar({ factores: [], rubros: [], seguir_al_rubro: { productos: 0, por_tipo: {} }, recalculo: null });
    await waitFor(() => expect(screen.getByLabelText("Tipo del rubro 35")).not.toBeDisabled());
  });

  it("un tipo nuevo que ningún rubro usa avisa que guardarlo no cambia precios", async () => {
    mocks.vista.mockResolvedValue({ ...VISTA, productos_revisados: 0, cambian: 0, suben: 0,
                                    variacion_mediana: null, rubros: [], ejemplos: [] });
    const confirmar = vi.spyOn(window, "confirm").mockReturnValue(false);
    render(<PoliticasPreciosPage />);
    await screen.findByLabelText("Tipo del rubro 35");
    fireEvent.change(screen.getByLabelText("Nombre del tipo"), { target: { value: "Rubro 35" } });
    fireEvent.change(screen.getByLabelText("Factor nacional"), { target: { value: "1,88" } });
    fireEvent.change(screen.getByLabelText("Factor importado"), { target: { value: "1,88" } });
    fireEvent.change(screen.getByLabelText("Descuento máx. %"), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: /Agregar tipo/ }));

    expect(await screen.findByText(/todavía no está en ningún rubro/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Guardar cambios/ }));
    expect(confirmar).toHaveBeenCalledWith(expect.stringContaining('"Rubro 35" todavía no está en ningún rubro'));
    expect(mocks.guardar).not.toHaveBeenCalled();
  });

  async function agregarTipoRubro35() {
    render(<PoliticasPreciosPage />);
    await screen.findByLabelText("Tipo del rubro 35");
    fireEvent.change(screen.getByLabelText("Nombre del tipo"), { target: { value: "Rubro 35" } });
    fireEvent.change(screen.getByLabelText("Factor nacional"), { target: { value: "1,88" } });
    fireEvent.change(screen.getByLabelText("Factor importado"), { target: { value: "1,88" } });
    fireEvent.change(screen.getByLabelText("Descuento máx. %"), { target: { value: "20" } });
    fireEvent.click(screen.getByRole("button", { name: /Agregar tipo/ }));
  }

  it("si un tipo sin rubro igual mueve precios (alguien lo tiene escrito a mano), no dice que no cambia nada", async () => {
    mocks.vista.mockResolvedValue({ ...VISTA, productos_revisados: 1, cambian: 1, suben: 1, rubros: [] });
    await agregarTipoRubro35();

    expect(await screen.findByText(/1 productos cambian de precio/)).toBeInTheDocument();
    expect(screen.queryByText(/todavía no está en ningún rubro/)).not.toBeInTheDocument();
  });

  it("vaciar un factor de un tipo nuevo lo marca como error en vez de borrarlo", async () => {
    // Borrarlo dejaba guardar el tipo con una sola procedencia: los productos de la
    // otra quedaban sin precio.
    await agregarTipoRubro35();
    fireEvent.change(screen.getByLabelText("Factor Rubro 35 Importado"), { target: { value: "" } });

    expect(await screen.findByText(/Factor fuera de rango en Rubro 35 \/ Importado/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Guardar cambios/ }));
    expect(mocks.guardar).not.toHaveBeenCalled();
  });

  it("si la respuesta se pierde pero el servidor ya lo guardó, lo dice en vez de mostrar el error", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mocks.guardar.mockRejectedValue(new Error("No se pudo conectar con el servidor."));
    render(<PoliticasPreciosPage />);
    fireEvent.change(await screen.findByLabelText("Tipo del rubro 34"), { target: { value: "Bateria" } });
    await screen.findByText(/385 productos cambian de precio/);
    // Lo que devuelve el servidor despues del corte: el cambio ya esta.
    mocks.rubros.mockResolvedValue(RUBROS.map((r) => (r.rubro === "34" ? { ...r, tipo: "Bateria" } : r)));

    fireEvent.click(screen.getByRole("button", { name: /Guardar cambios/ }));

    expect(await screen.findByText(/quedó guardado, aunque la respuesta del servidor no llegó/)).toBeInTheDocument();
    expect(screen.queryByText("No se pudo conectar con el servidor.")).not.toBeInTheDocument();
  });

  it("si de verdad no se guardó, muestra el error y deja los cambios para reintentar", async () => {
    vi.spyOn(window, "confirm").mockReturnValue(true);
    mocks.guardar.mockRejectedValue(new Error("No se pudo conectar con el servidor."));
    render(<PoliticasPreciosPage />);
    fireEvent.change(await screen.findByLabelText("Tipo del rubro 34"), { target: { value: "Bateria" } });
    await screen.findByText(/385 productos cambian de precio/);

    fireEvent.click(screen.getByRole("button", { name: /Guardar cambios/ }));

    expect(await screen.findByText("No se pudo conectar con el servidor.")).toBeInTheDocument();
    expect(screen.getByLabelText("Tipo del rubro 34")).toHaveValue("Bateria");
  });
});
