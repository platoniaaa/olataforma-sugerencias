/**
 * Editar la lista de precios en Excel: bajar, editar y volver a cargar.
 *
 * Lo que estos tests cuidan:
 *
 * 1. Que el formato este a la vista ANTES de subir: que columnas se editan y que hace
 *    cada una, incluido lo que pasa si se deja vacia.
 * 2. Que un archivo con errores NO se pueda cargar, y que se diga fila por fila.
 * 3. Que lo que se omite (conflictos, codigos que no estan, filas sin referencia) se
 *    vea: callar lo que no se cargo hace creer que se cargo.
 * 4. Que cargar suba el mismo archivo que se miro, y refresque la lista.
 * 5. Que una carga que QUITA decisiones (celdas vacias) lo diga, y pida confirmacion si
 *    son muchas: un .xlsx con celdas de error las entrega vacias.
 * 6. Que una lectura lenta que llega tarde no deje una tabla de un archivo con el nombre
 *    de otro.
 */
import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { CargaPreciosExcel, COLUMNAS_EDITABLES } from "@/components/carga-precios-excel";
import type { CargaPreciosVistaPrevia } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  descargar: vi.fn(),
  previa: vi.fn(),
  cargar: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    exportarPrecios: mocks.descargar,
    vistaPreviaCargaPrecios: mocks.previa,
    cargarPrecios: mocks.cargar,
  },
}));

const BASE: CargaPreciosVistaPrevia = {
  archivo: "lista.csv", filas: 39830, sin_cambios: 39826, a_cambiar: 2, por_campo: { tipo: 1, precio_fijo: 1 },
  efecto: { suben: 1, bajan: 0, sin_cambio_de_precio: 1, con_precio_nuevo: 0 },
  quitan_total: 0, quitan: {}, quitan_ejemplos: [], umbral_quitas: 10,
  errores: [], errores_total: 0, conflictos: [], conflictos_total: 0,
  desconocidos: [], desconocidos_total: 0, sin_referencia: [], sin_referencia_total: 0,
  cambios: [
    { producto: "35 34106879122", glosa: "DISCO DE FRENO", precio_antes: 209542, precio_despues: 221315,
      campos: [{ campo: "Precio fijo", antes: "(sin precio fijo)", despues: "221.315" }] },
    { producto: "71 AAA1", glosa: "AMORTIGUADOR", precio_antes: 17800, precio_despues: 17800,
      campos: [{ campo: "Obs", antes: "(vacía)", despues: "revisar" }] },
  ],
  cambios_total: 2,
};

const OK = {
  aplicados: 2, por_campo: { tipo: 1, precio_fijo: 1 }, precios_distintos: 1, sin_cambios: 39826,
  omitidos: { conflictos: 0, desconocidos: 0, sin_referencia: 0 },
};

const ARCHIVO = new File(["Producto;Referencia"], "lista.csv", { type: "text/csv" });

// Con llaves: si beforeEach devuelve una funcion, vitest la llama al terminar la
// prueba como limpieza, y mockReset() devuelve el propio mock.
beforeEach(() => {
  mocks.descargar.mockReset().mockResolvedValue(39830);
  mocks.previa.mockReset().mockResolvedValue(BASE);
  mocks.cargar.mockReset().mockResolvedValue(OK);
});

function abrir(extra: Partial<{ onCargado: () => void; onClose: () => void }> = {}) {
  return render(<CargaPreciosExcel open onClose={extra.onClose ?? vi.fn()} onCargado={extra.onCargado} />);
}

function elegirArchivo(archivo = ARCHIVO) {
  fireEvent.change(screen.getByLabelText("Archivo editado"), { target: { files: [archivo] } });
}

async function subir(archivo = ARCHIVO) {
  elegirArchivo(archivo);
  await screen.findByRole("region", { name: "Qué cambia" });
}

describe("el formato, a la vista antes de subir", () => {
  it("lista las siete columnas editables y que pasa si se dejan vacias", () => {
    abrir();

    for (const c of COLUMNAS_EDITABLES) {
      const fila = screen.getByRole("row", { name: new RegExp(`^${c.columna}`) });
      expect(within(fila).getByText(c.hace)).toBeInTheDocument();
      expect(within(fila).getByText(c.vacia)).toBeInTheDocument();
    }
    expect(COLUMNAS_EDITABLES.map((c) => c.columna)).toEqual([
      "Tipo", "Procedencia", "Factor", "Precio final", "Obs", "Congelar", "No es producto"]);
    expect(screen.getByText(/Solo se carga lo que cambies/)).toBeInTheDocument();
    expect(screen.getByText(/ordenes columnas sueltas/i)).toBeInTheDocument();
    // Tres pasos numerados: descargar, editar, subir.
    for (const paso of ["1. Descarga la lista", "2. Edítala en Excel", "3. Súbelo"]) {
      expect(screen.getByRole("heading", { name: paso })).toBeInTheDocument();
    }
    expect(screen.getByText(/No toques la última columna/)).toBeInTheDocument();
  });

  it("descargar pide el archivo para editar, que no es la lista completa de siempre", async () => {
    abrir();

    fireEvent.click(screen.getByRole("button", { name: /Descargar para editar/ }));

    await waitFor(() => expect(mocks.descargar).toHaveBeenCalledTimes(1));
    expect(mocks.descargar.mock.calls[0][0]).toEqual({ soloDiferencias: false, formato: "editable" });
    expect(await screen.findByText(/39\.830 productos/)).toBeInTheDocument();
  });

  it("una descarga que termina despues de cerrar el dialogo no deja avisos viejos al reabrir", async () => {
    let terminar: (n: number) => void = () => {};
    mocks.descargar.mockReturnValue(new Promise<number>((r) => { terminar = r; }));
    const { rerender } = abrir();
    fireEvent.click(screen.getByRole("button", { name: /Descargar para editar/ }));

    rerender(<CargaPreciosExcel open={false} onClose={vi.fn()} />);
    rerender(<CargaPreciosExcel open onClose={vi.fn()} />);
    await act(async () => { terminar(39830); });

    expect(screen.queryByText(/Archivo descargado/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Descargar para editar/ })).toBeEnabled();
  });
});

describe("la vista previa", () => {
  it("al elegir un archivo lo lee y muestra que cambia, producto por producto", async () => {
    abrir();

    await subir();

    // El tercer argumento permite cancelar la lectura si deja de interesar.
    expect(mocks.previa).toHaveBeenCalledWith(ARCHIVO, expect.any(Function), expect.any(AbortSignal));
    expect(screen.getByText("39.830 filas leídas")).toBeInTheDocument();
    expect(screen.getByText("2 productos se cargarán")).toBeInTheDocument();
    expect(screen.getByText("35 34106879122")).toBeInTheDocument();
    expect(screen.getByText(/\$209\.542 → \$221\.315/)).toBeInTheDocument();
    expect(screen.getByText("no cambia")).toBeInTheDocument();
    expect(screen.getByText(/Precios: 1 sube, 0 bajan, 0 pasan de sin precio a tener uno y 1 no cambia de precio/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeEnabled();
  });

  it("con un solo producto habla en singular", async () => {
    mocks.previa.mockResolvedValue({ ...BASE, a_cambiar: 1, cambios_total: 1, cambios: [BASE.cambios[0]] });
    abrir();

    await subir();

    expect(screen.getByText("1 producto se cargará")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cargar 1 producto" })).toBeEnabled();
  });

  it("con errores no se puede cargar, se dice fila por fila y no afirma que algo se cargara", async () => {
    mocks.previa.mockResolvedValue({
      ...BASE, a_cambiar: 1, errores_total: 2,
      errores: [
        { fila: 3, producto: "71 AAA1", mensaje: "Factor: 0,9 no vale. Tiene que ser mayor que 1 y hasta 10." },
        { fila: 9, producto: "13 BBB2", mensaje: 'Tipo: "Livano" no existe en la política.' },
      ],
    });
    abrir();

    await subir();

    const alerta = screen.getByRole("alert");
    expect(alerta).toHaveTextContent("El archivo tiene 2 error(es). No se carga nada");
    expect(alerta).toHaveTextContent("Fila 3");
    expect(alerta).toHaveTextContent("Factor: 0,9 no vale");
    expect(alerta).toHaveTextContent('Tipo: "Livano" no existe');
    expect(screen.getByRole("button", { name: /Cargar 1 producto/ })).toBeDisabled();
    // Ni el "se cargarán" ni la tabla de cambios: la carga es todo o nada.
    expect(screen.queryByText(/se cargarán|se cargará/)).not.toBeInTheDocument();
    expect(screen.queryByText("35 34106879122")).not.toBeInTheDocument();
    expect(screen.getByText("1 producto con cambios válido")).toBeInTheDocument();
  });

  it("dice lo que omite: conflictos, codigos que no estan y filas sin referencia", async () => {
    mocks.previa.mockResolvedValue({
      ...BASE,
      conflictos_total: 1,
      conflictos: [{ fila: 5, producto: "71 CCC3", mensaje: "Este producto cambió en la plataforma." }],
      desconocidos_total: 3, desconocidos: ["71 NO-EXISTE", "13 TAMPOCO"],
      sin_referencia_total: 1, sin_referencia: ["99 A MANO"],
    });
    abrir();

    await subir();

    expect(screen.getByText(/1 producto no se cargará: cambió en la plataforma/)).toBeInTheDocument();
    expect(screen.getByText(/71 CCC3/)).toBeInTheDocument();
    expect(screen.getByText(/3 códigos no están en la lista y se ignoran/)).toBeInTheDocument();
    expect(screen.getByText(/71 NO-EXISTE, 13 TAMPOCO … y 1 más/)).toBeInTheDocument();
    expect(screen.getByText(/1 fila no trae Referencia y se ignora/)).toBeInTheDocument();
    expect(screen.getByText("5 se omiten")).toBeInTheDocument();
    // Lo que si esta bien igual se puede cargar.
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeEnabled();
  });

  it("un archivo sin cambios lo dice y no ofrece cargar", async () => {
    mocks.previa.mockResolvedValue({ ...BASE, a_cambiar: 0, cambios: [], cambios_total: 0, sin_cambios: 39830 });
    abrir();

    await subir();

    expect(screen.getByText(/no trae ningún cambio que cargar/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cargar 0 productos/ })).toBeDisabled();
  });

  it("si el archivo no sirve muestra el motivo del servidor y deja elegir otro", async () => {
    mocks.previa.mockRejectedValue(new Error("Faltan las columnas: Obs. Descarga el archivo de nuevo."));
    abrir();

    elegirArchivo();

    expect(await screen.findByText(/Faltan las columnas: Obs/)).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Qué cambia" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Elegir archivo/ })).toBeEnabled();
  });

  it("descartar vuelve al principio sin llamar a cargar", async () => {
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Descartar" }));

    expect(screen.queryByRole("region", { name: "Qué cambia" })).not.toBeInTheDocument();
    expect(mocks.cargar).not.toHaveBeenCalled();
  });
});

describe("quitar decisiones", () => {
  const QUITAN_POCAS = { ...BASE, quitan_total: 3, quitan: { precio_fijo: 2, congelar: 1 },
                         quitan_ejemplos: [{ producto: "71 AAA1", campo: "Precio fijo" }] };
  const QUITAN_MUCHAS = { ...BASE, quitan_total: 12, quitan: { precio_fijo: 12 },
                          quitan_ejemplos: [{ producto: "71 Q00", campo: "Precio fijo" }] };

  it("avisa que la carga quita decisiones y por que puede ser un error de Excel", async () => {
    mocks.previa.mockResolvedValue(QUITAN_POCAS);
    abrir();

    await subir();

    expect(screen.getByText(/Esta carga quita 3 decisiones: 2 precio fijo, 1 congelado/)).toBeInTheDocument();
    expect(screen.getByText(/celdas con error \(#N\/D, #REF!\)/)).toBeInTheDocument();
    // Pocas: no hace falta confirmar.
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeEnabled();
  });

  it("si son muchas pide confirmar y manda la confirmacion", async () => {
    mocks.previa.mockResolvedValue(QUITAN_MUCHAS);
    abrir();
    await subir();

    const cargarBtn = screen.getByRole("button", { name: "Cargar 2 productos" });
    expect(cargarBtn).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /Entiendo que se quitan 12 decisiones/ }));
    expect(cargarBtn).toBeEnabled();
    fireEvent.click(cargarBtn);

    await waitFor(() => expect(mocks.cargar).toHaveBeenCalledTimes(1));
    expect(mocks.cargar).toHaveBeenCalledWith(ARCHIVO, { confirmarQuitas: true });
  });

  it("elegir otro archivo vuelve a pedir la confirmacion", async () => {
    mocks.previa.mockResolvedValue(QUITAN_MUCHAS);
    abrir();
    await subir();
    fireEvent.click(screen.getByRole("checkbox"));

    await subir(new File(["x"], "otro.csv"));

    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeDisabled();
  });
});

describe("cargar", () => {
  it("sube el mismo archivo que se miro, avisa el resultado y refresca la lista", async () => {
    const onCargado = vi.fn();
    abrir({ onCargado });
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    await waitFor(() => expect(mocks.cargar).toHaveBeenCalledTimes(1));
    expect(mocks.cargar).toHaveBeenCalledWith(ARCHIVO, { confirmarQuitas: false });
    const resultado = await screen.findByText(/Listo: 2 productos actualizados, 1 cambió de precio/);
    expect(resultado).toBeInTheDocument();
    expect(resultado).toHaveTextContent('Los precios nuevos salen en el próximo "Solo diferencias"');
    expect(onCargado).toHaveBeenCalledTimes(1);
  });

  it("el foco pasa al resultado cuando termina (el boton que lo tenia desaparece)", async () => {
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    await screen.findByText(/Listo: 2 productos actualizados/);
    expect(screen.getByRole("status")).toHaveFocus();
  });

  it("con un solo producto y ningun precio distinto habla en singular y no promete precios nuevos", async () => {
    mocks.cargar.mockResolvedValue({ ...OK, aplicados: 1, precios_distintos: 0 });
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    const r = await screen.findByText(/Listo: 1 producto actualizado/);
    expect(r).toHaveTextContent("Ningún precio cambió.");
    expect(r).not.toHaveTextContent("Solo diferencias");
  });

  it("avisa lo que quedo sin cargar", async () => {
    mocks.cargar.mockResolvedValue({
      aplicados: 1, por_campo: { tipo: 1 }, precios_distintos: 0, sin_cambios: 39826,
      omitidos: { conflictos: 2, desconocidos: 1, sin_referencia: 0 },
    });
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    // Solo lo que no es cero, con "está" para uno.
    expect(await screen.findByText(/No se cargaron: 2 con conflicto, 1 que no está en la lista\./)).toBeInTheDocument();
    expect(screen.getByText(/Descarga el archivo de nuevo y repite esos cambios/)).toBeInTheDocument();
  });

  it("una carga donde todo se omitio no dice que la lista ya estaba como el archivo", async () => {
    mocks.cargar.mockResolvedValue({
      aplicados: 0, por_campo: {}, precios_distintos: 0, sin_cambios: 39826,
      omitidos: { conflictos: 3, desconocidos: 0, sin_referencia: 0 },
    });
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    expect(await screen.findByText(/No se cargó nada: todos los cambios del archivo se omitieron/)).toBeInTheDocument();
    expect(screen.queryByText(/No había nada que cargar/)).not.toBeInTheDocument();
    expect(screen.getByText(/3 con conflicto/)).toBeInTheDocument();
  });

  it("una carga que no tenia nada que hacer lo dice con claridad", async () => {
    mocks.cargar.mockResolvedValue({
      aplicados: 0, por_campo: {}, precios_distintos: 0, sin_cambios: 39830,
      omitidos: { conflictos: 0, desconocidos: 0, sin_referencia: 0 },
    });
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    expect(await screen.findByText(/No había nada que cargar/)).toBeInTheDocument();
  });

  it("si la carga falla muestra el error y deja reintentar con el mismo archivo", async () => {
    mocks.cargar.mockRejectedValueOnce(new Error("El archivo tiene 1 error(es). No se cargó nada."));
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No se cargó nada");
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeEnabled();
    expect(screen.getByRole("region", { name: "Qué cambia" })).toBeInTheDocument();
  });

  it("mientras carga no se puede apretar de nuevo ni elegir otro archivo, ni cerrar", async () => {
    let terminar: (v: unknown) => void = () => {};
    mocks.cargar.mockReturnValue(new Promise((r) => { terminar = r; }));
    const onClose = vi.fn();
    abrir({ onClose });
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    expect(await screen.findByRole("button", { name: /Cargando/ })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Elegir archivo/ })).toBeDisabled();
    expect(screen.getByLabelText("Archivo editado")).toBeDisabled();
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).not.toHaveBeenCalled();
    terminar(OK);
    await screen.findByText(/2 productos actualizados/);
    expect(mocks.cargar).toHaveBeenCalledTimes(1);
  });
});


describe("textos con cantidad 1 y avisos de la segunda revision", () => {
  it("con un solo elemento de cada cosa, todo concuerda", async () => {
    mocks.previa.mockResolvedValue({
      ...BASE, filas: 1, a_cambiar: 1, cambios_total: 1, cambios: [BASE.cambios[0]],
      efecto: { suben: 0, bajan: 1, sin_cambio_de_precio: 0, con_precio_nuevo: 1 },
      conflictos_total: 1, conflictos: [{ fila: 2, producto: "71 AAA1", mensaje: "x" }],
    });
    abrir();

    await subir();

    expect(screen.getByText("1 fila leída")).toBeInTheDocument();
    expect(screen.getByText("1 se omite")).toBeInTheDocument();
    expect(screen.getByText(/Precios: 0 suben, 1 baja, 1 pasa de sin precio a tener uno y 0 no cambian de precio/)).toBeInTheDocument();
  });

  it("lo que una carga quita se muestra con ejemplos de productos", async () => {
    // Con mas de 300 cambios la tabla no los muestra todos: los ejemplos son lo unico
    // que dice QUE productos perderian su decision.
    mocks.previa.mockResolvedValue({
      ...BASE, quitan_total: 12, quitan: { precio_fijo: 12 },
      quitan_ejemplos: [
        { producto: "71 Q00", campo: "Precio fijo" }, { producto: "71 Q01", campo: "Precio fijo" },
      ],
    });
    abrir();

    await subir();

    expect(screen.getByText(/Por ejemplo: 71 Q00 \(precio fijo\), 71 Q01 \(precio fijo\)…/)).toBeInTheDocument();
  });

  it("si Cargar falla, el aviso recibe el foco: abajo del dialogo no se veria", async () => {
    mocks.cargar.mockRejectedValueOnce(new Error("No se pudo confirmar la carga."));
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("No se pudo confirmar la carga");
    expect(alerta).toHaveFocus();
  });

  it("descartar devuelve el foco a Elegir archivo", async () => {
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Descartar" }));

    await waitFor(() => expect(screen.getByRole("button", { name: /Elegir archivo/ })).toHaveFocus());
  });

  it("cerrar y reabrir con una descarga en curso no deja lanzar otra encima", async () => {
    let terminar: (n: number) => void = () => {};
    mocks.descargar.mockReturnValue(new Promise<number>((r) => { terminar = r; }));
    const { rerender } = abrir();
    fireEvent.click(screen.getByRole("button", { name: /Descargar para editar/ }));

    rerender(<CargaPreciosExcel open={false} onClose={vi.fn()} />);
    rerender(<CargaPreciosExcel open onClose={vi.fn()} />);

    // La primera sigue en vuelo: el boton espera, y un clic no la duplica.
    expect(screen.getByRole("button", { name: /Descargar para editar/ })).toBeDisabled();
    expect(mocks.descargar).toHaveBeenCalledTimes(1);
    await act(async () => { terminar(39830); });
    expect(screen.getByRole("button", { name: /Descargar para editar/ })).toBeEnabled();
  });
});

describe("tercera revision: lo que la pantalla hacia mal", () => {
  it("si la respuesta de la carga se perdio, la lista de atras se refresca igual", async () => {
    // El servidor pudo hacer commit: sin refrescar, la tabla seguia con los precios viejos.
    const perdida = Object.assign(new Error("No se pudo confirmar la carga."), { name: "CargaSinConfirmar" });
    mocks.cargar.mockRejectedValueOnce(perdida);
    const onCargado = vi.fn();
    abrir({ onCargado });
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    await screen.findByRole("alert");
    expect(onCargado).toHaveBeenCalledTimes(1);
  });

  it("un rechazo comun de la carga no refresca la lista: no se escribio nada", async () => {
    mocks.cargar.mockRejectedValueOnce(new Error("El archivo tiene 2 errores."));
    const onCargado = vi.fn();
    abrir({ onCargado });
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    await screen.findByRole("alert");
    expect(onCargado).not.toHaveBeenCalled();
  });

  it("un error de descarga que llega tarde no se pega encima del resultado", async () => {
    let fallar: (e: Error) => void = () => {};
    mocks.descargar.mockReturnValue(new Promise<number>((_, rechazar) => { fallar = rechazar; }));
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /Descargar para editar/ }));
    await subir();
    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));
    await screen.findByText(/Listo: 2 productos actualizados/);

    await act(async () => { fallar(new Error("No se pudo conectar con el servidor.")); });

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByText(/Listo: 2 productos actualizados/)).toBeInTheDocument();
  });

  it("un error de otra operacion no le quita el foco a la casilla de confirmar", async () => {
    let fallar: (e: Error) => void = () => {};
    mocks.descargar.mockReturnValue(new Promise<number>((_, rechazar) => { fallar = rechazar; }));
    mocks.previa.mockResolvedValue({ ...BASE, quitan_total: 12, quitan: { precio_fijo: 12 } });
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /Descargar para editar/ }));
    await subir();
    const casilla = screen.getByRole("checkbox");
    casilla.focus();

    await act(async () => { fallar(new Error("No se pudo conectar con el servidor.")); });

    expect(await screen.findByRole("alert")).toBeInTheDocument();
    expect(casilla).toHaveFocus();
  });

  it("elegir otro archivo o cerrar el dialogo cancela la lectura que ya no interesa", async () => {
    const senales: AbortSignal[] = [];
    mocks.previa.mockImplementation((_f: File, _r: unknown, senal: AbortSignal) => {
      senales.push(senal);
      return new Promise(() => {});
    });
    const { rerender } = abrir();

    elegirArchivo(new File(["a"], "a.csv"));
    elegirArchivo(new File(["b"], "b.csv"));

    expect(senales[0].aborted).toBe(true);
    expect(senales[1].aborted).toBe(false);
    rerender(<CargaPreciosExcel open={false} onClose={vi.fn()} />);
    expect(senales[1].aborted).toBe(true);
  });

  it("con un solo elemento, los avisos de la vista previa concuerdan", async () => {
    mocks.previa.mockResolvedValue({
      ...BASE,
      conflictos_total: 1, conflictos: [{ fila: 2, producto: "71 AAA1", mensaje: "x" }],
      desconocidos_total: 1, desconocidos: ["ZZ 1"],
      sin_referencia_total: 1, sin_referencia: ["ZZ 2"],
    });
    abrir();

    await subir();

    expect(screen.getByText(/1 producto no se cargará: cambió en la plataforma/)).toBeInTheDocument();
    expect(screen.getByText("1 código no está en la lista y se ignora.")).toBeInTheDocument();
    expect(screen.getByText("1 fila no trae Referencia y se ignora (¿fila agregada a mano?).")).toBeInTheDocument();
    expect(screen.queryByText(/\(s\)/)).not.toBeInTheDocument();
  });

  it("con varios elementos, los avisos van en plural", async () => {
    mocks.previa.mockResolvedValue({
      ...BASE,
      conflictos_total: 3, conflictos: [{ fila: 2, producto: "71 AAA1", mensaje: "x" }],
      desconocidos_total: 2, desconocidos: ["ZZ 1", "ZZ 3"],
      sin_referencia_total: 4, sin_referencia: ["ZZ 2"],
    });
    abrir();

    await subir();

    expect(screen.getByText(/3 productos no se cargarán: cambiaron en la plataforma/)).toBeInTheDocument();
    expect(screen.getByText("2 códigos no están en la lista y se ignoran.")).toBeInTheDocument();
    expect(screen.getByText("4 filas no traen Referencia y se ignoran (¿filas agregadas a mano?).")).toBeInTheDocument();
  });

  it("si todo se omitio por conflicto no dice que el archivo no trae cambios", async () => {
    mocks.previa.mockResolvedValue({
      ...BASE, a_cambiar: 0, cambios: [], cambios_total: 0,
      conflictos_total: 3, conflictos: [{ fila: 2, producto: "71 AAA1", mensaje: "x" }],
    });
    abrir();

    await subir();

    expect(screen.queryByText(/no trae ningún cambio/)).not.toBeInTheDocument();
    expect(screen.getByText(/No hay nada que cargar: los cambios del archivo se omiten/)).toBeInTheDocument();
  });

  it("el campo de archivo oculto no es una parada de Tab", () => {
    abrir();

    expect(screen.getByLabelText("Archivo editado")).toHaveAttribute("tabindex", "-1");
  });
});

describe("lecturas lentas y cierre", () => {
  it("la respuesta de un archivo anterior que llega tarde no pisa la del actual", async () => {
    // Elegir uno.csv y, antes de que termine, dos.csv; responde primero dos y despues uno.
    const resolvers: Record<string, (v: CargaPreciosVistaPrevia) => void> = {};
    mocks.previa.mockImplementation((f: File) => new Promise<CargaPreciosVistaPrevia>((r) => { resolvers[f.name] = r; }));
    abrir();
    const uno = new File(["u"], "uno.csv");
    const dos = new File(["d"], "dos.csv");

    elegirArchivo(uno);
    elegirArchivo(dos);
    await act(async () => {
      resolvers["dos.csv"]({ ...BASE, cambios: [{ ...BASE.cambios[0], producto: "PROD-DEL-DOS" }] });
    });
    await act(async () => {
      resolvers["uno.csv"]({ ...BASE, cambios: [{ ...BASE.cambios[0], producto: "PROD-DEL-UNO" }] });
    });

    expect(await screen.findByText("PROD-DEL-DOS")).toBeInTheDocument();
    expect(screen.queryByText("PROD-DEL-UNO")).not.toBeInTheDocument();
    expect(screen.getByText("dos.csv")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));
    await waitFor(() => expect(mocks.cargar).toHaveBeenCalledWith(dos, { confirmarQuitas: false }));
  });

  it("se puede cerrar mientras lee, y al reabrir no queda la lectura vieja", async () => {
    let terminar: (v: CargaPreciosVistaPrevia) => void = () => {};
    mocks.previa.mockReturnValue(new Promise<CargaPreciosVistaPrevia>((r) => { terminar = r; }));
    const onClose = vi.fn();
    const { rerender } = abrir({ onClose });
    elegirArchivo();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledTimes(1);
    rerender(<CargaPreciosExcel open={false} onClose={onClose} />);
    rerender(<CargaPreciosExcel open onClose={onClose} />);
    await act(async () => { terminar(BASE); });

    expect(screen.queryByRole("region", { name: "Qué cambia" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Elegir archivo/ })).toBeEnabled();
  });

  it("mientras lee avisa con una region de estado", async () => {
    mocks.previa.mockReturnValue(new Promise(() => {}));
    abrir();

    elegirArchivo();

    expect(await screen.findByRole("status")).toHaveTextContent("Leyendo el archivo");
  });
});
