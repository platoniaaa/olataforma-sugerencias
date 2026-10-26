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
 * 7. Que haya DOS modos y que se note cual es: el Excel corto (una plantilla de cinco columnas,
 *    para tocar pocos productos) y el completo (el archivo que se baja para editar, con las once
 *    columnas editables). El modo se declara al servidor, se recuerda y, al cambiarlo, se
 *    descarta lo que habia a medias.
 *
 * Los tests de abajo que no hablan de modos corren en el modo completo (el unico que existia):
 * el `beforeEach` lo deja guardado.
 */
import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { CargaPreciosExcel, COLUMNAS_EDITABLES, COLUMNAS_SOLO_LECTURA } from "@/components/carga-precios-excel";
import type { CargaPreciosVistaPrevia } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  descargar: vi.fn(),
  plantilla: vi.fn(),
  previa: vi.fn(),
  cargar: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    exportarPrecios: mocks.descargar,
    descargarPlantillaCarga: mocks.plantilla,
    vistaPreviaCargaPrecios: mocks.previa,
    cargarPrecios: mocks.cargar,
  },
}));

const CLAVE_MODO = "precios_carga_modo";

const BASE: CargaPreciosVistaPrevia = {
  archivo: "lista.csv", filas: 39830, sin_cambios: 39826, a_cambiar: 2, por_campo: { tipo: 1, precio_fijo: 1 },
  efecto: { suben: 1, bajan: 0, sin_cambio_de_precio: 1, con_precio_nuevo: 0 },
  quitan_total: 0, quitan: {}, quitan_ejemplos: [], umbral_quitas: 10,
  fijan_total: 0, fijan: {}, umbral_masiva: 200, factor_redondeado_total: 0, factor_redondeado: [],
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
  mocks.plantilla.mockReset().mockResolvedValue("plantilla_precios_corta.xlsx");
  mocks.previa.mockReset().mockResolvedValue(BASE);
  mocks.cargar.mockReset().mockResolvedValue(OK);
  // Estas pruebas nacieron cuando solo habia el archivo completo: lo dejan elegido. Las del
  // modo corto y las de la eleccion de modo lo cambian a proposito.
  window.localStorage.setItem(CLAVE_MODO, "completo");
});

afterEach(() => {
  window.localStorage.clear();
});

function abrir(extra: Partial<{ onCargado: () => void; onClose: () => void; totalProductos: number; hoy: string }> = {}) {
  return render(
    <CargaPreciosExcel
      open
      onClose={extra.onClose ?? vi.fn()}
      onCargado={extra.onCargado}
      totalProductos={extra.totalProductos}
      hoy={extra.hoy}
    />,
  );
}

function elegirArchivo(archivo = ARCHIVO) {
  fireEvent.change(screen.getByLabelText("Archivo editado"), { target: { files: [archivo] } });
}

async function subir(archivo = ARCHIVO) {
  elegirArchivo(archivo);
  await screen.findByRole("region", { name: "Qué cambia" });
}

describe("el formato, a la vista antes de subir", () => {
  it("lista las once columnas editables y que pasa si se dejan vacias", () => {
    abrir();

    for (const c of COLUMNAS_EDITABLES) {
      const fila = screen.getByRole("row", { name: new RegExp(`^${c.columna}`) });
      expect(within(fila).getByText(c.hace)).toBeInTheDocument();
      expect(within(fila).getByText(c.vacia)).toBeInTheDocument();
    }
    // En el orden en que van en el archivo (las columnas de decision, despues de las 16 de la lista).
    expect(COLUMNAS_EDITABLES.map((c) => c.columna)).toEqual([
      "Tipo", "Procedencia", "Factor", "Precio final", "Obs", "Congelar", "No es producto",
      "Precio fijo", "Margen fijo %", "Desde", "Hasta"]);
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
    // El modo se declara: un archivo que no es de este modo da un 422 claro, no se adivina.
    expect(mocks.previa).toHaveBeenCalledWith(ARCHIVO, expect.any(Function), expect.any(AbortSignal), "completo");
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
    expect(alerta).toHaveTextContent("El archivo tiene 2 errores. No se carga nada hasta corregirlos");
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
    expect(mocks.cargar).toHaveBeenCalledWith(ARCHIVO, { confirmarQuitas: true, confirmarMasiva: false, modo: "completo" });
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

describe("poner muchos precios fijos o factores", () => {
  const MUCHOS = { ...BASE, a_cambiar: 250, fijan_total: 250, fijan: { precio_fijo: 190, factor: 60 } };

  it("avisa cuantos son y por que puede ser una columna ordenada sola", async () => {
    mocks.previa.mockResolvedValue(MUCHOS);
    abrir();

    await subir();

    expect(screen.getByText(/Esta carga deja 250 precios fijos o factores propios nuevos: 190 precios fijos, 60 factores propios\./))
      .toBeInTheDocument();
    expect(screen.getByText(/ordenaste una sola columna/)).toBeInTheDocument();
  });

  it("no deja cargar hasta confirmar, y manda la confirmacion", async () => {
    mocks.previa.mockResolvedValue(MUCHOS);
    abrir();
    await subir();

    const cargarBtn = screen.getByRole("button", { name: "Cargar 250 productos" });
    expect(cargarBtn).toBeDisabled();
    fireEvent.click(screen.getByRole("checkbox", { name: /Entiendo que se fijan 250 valores/ }));
    expect(cargarBtn).toBeEnabled();
    fireEvent.click(cargarBtn);

    await waitFor(() => expect(mocks.cargar).toHaveBeenCalledTimes(1));
    expect(mocks.cargar).toHaveBeenCalledWith(ARCHIVO, { confirmarQuitas: false, confirmarMasiva: true, modo: "completo" });
  });

  it("hasta el umbral no pide nada", async () => {
    mocks.previa.mockResolvedValue({ ...BASE, fijan_total: 200, fijan: { precio_fijo: 200 } });
    abrir();

    await subir();

    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeEnabled();
  });

  it("con un solo valor el texto va en singular", async () => {
    mocks.previa.mockResolvedValue({ ...BASE, umbral_masiva: 0, fijan_total: 1, fijan: { precio_fijo: 1 } });
    abrir();

    await subir();

    expect(screen.getByText(/nuevos: 1 precio fijo\./)).toBeInTheDocument();
  });

  it("elegir otro archivo vuelve a pedir la confirmacion", async () => {
    mocks.previa.mockResolvedValue(MUCHOS);
    abrir();
    await subir();
    fireEvent.click(screen.getByRole("checkbox"));

    await subir(new File(["x"], "otro.csv"));

    expect(screen.getByRole("checkbox")).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Cargar 250 productos" })).toBeDisabled();
  });
});

describe("la vista previa", () => {
  it("al terminar de leer, el foco pasa a la vista previa: abajo, fuera de pantalla, parecia que no pasaba nada", async () => {
    abrir();

    await subir();

    await waitFor(() => expect(screen.getByRole("region", { name: "Qué cambia" })).toHaveFocus());
  });

  it("con un solo error el texto va en singular", async () => {
    mocks.previa.mockResolvedValue({
      ...BASE, errores_total: 1, errores: [{ fila: 3, producto: "71 AAA1", mensaje: "Factor: 0,9 no vale." }],
    });
    abrir();

    await subir();

    expect(screen.getByRole("alert")).toHaveTextContent("El archivo tiene 1 error. No se carga nada hasta corregirlo");
    expect(screen.queryByText(/error\(es\)/)).not.toBeInTheDocument();
  });
});

describe("factores que Excel redondeo", () => {
  it("avisa cuantos productos se tomaron como sin cambios y que se puede hacer", async () => {
    mocks.previa.mockResolvedValue({
      ...BASE, factor_redondeado_total: 3, factor_redondeado: ["71 AAA1", "72 R01", "13 BBB2"],
    });
    abrir();

    await subir();

    expect(screen.getByText(/3 productos traen el Factor redondeado/)).toBeInTheDocument();
    expect(screen.getByText(/71 AAA1, 72 R01, 13 BBB2/)).toBeInTheDocument();
    expect(screen.getByText(/cámbialo en la ficha del producto/)).toBeInTheDocument();
    // Es informativo: no bloquea la carga ni pide confirmar.
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeEnabled();
  });

  it("con uno solo habla en singular", async () => {
    mocks.previa.mockResolvedValue({ ...BASE, factor_redondeado_total: 1, factor_redondeado: ["71 AAA1"] });
    abrir();

    await subir();

    expect(screen.getByText(/1 producto trae el Factor redondeado/)).toBeInTheDocument();
  });

  it("sin redondeos no aparece el aviso", async () => {
    abrir();

    await subir();

    expect(screen.queryByText(/Factor redondeado/)).not.toBeInTheDocument();
  });
});

describe("los avisos de descarga y de lectura", () => {
  it("cada uno muestra lo suyo: el reintento de la descarga no parece un fallo de la lectura", async () => {
    mocks.descargar.mockImplementation((_o: unknown, alReintentar: (i: number, t: number) => void) => {
      alReintentar(2, 4);
      return new Promise(() => {});
    });
    mocks.previa.mockImplementation((_f: File, alReintentar: (i: number, t: number) => void) => {
      alReintentar(1, 4);
      return new Promise(() => {});
    });
    abrir();

    fireEvent.click(screen.getByRole("button", { name: /Descargar para editar/ }));
    elegirArchivo();

    expect(await screen.findByText("Descarga: el servidor no responde. Reintentando (2 de 4)…")).toBeInTheDocument();
    expect(await screen.findByText("Lectura: el servidor no responde. Reintentando (1 de 4)…")).toBeInTheDocument();
  });

  it("elegir un archivo no borra el aviso de la descarga, ni terminar de leer lo pisa", async () => {
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /Descargar para editar/ }));
    expect(await screen.findByText(/Archivo descargado: 39\.830 productos/)).toBeInTheDocument();

    await subir();

    expect(screen.getByText(/Archivo descargado: 39\.830 productos/)).toBeInTheDocument();
  });

  it("el aviso de lectura se va cuando termina de leer", async () => {
    mocks.previa.mockImplementation((_f: File, alReintentar: (i: number, t: number) => void) => {
      alReintentar(1, 4);
      return Promise.resolve(BASE);
    });
    abrir();

    await subir();

    expect(screen.queryByText(/Lectura: el servidor no responde/)).not.toBeInTheDocument();
  });
});

describe("cargar", () => {
  it("sube el mismo archivo que se miro, avisa el resultado y refresca la lista", async () => {
    const onCargado = vi.fn();
    abrir({ onCargado });
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    await waitFor(() => expect(mocks.cargar).toHaveBeenCalledTimes(1));
    expect(mocks.cargar).toHaveBeenCalledWith(ARCHIVO, { confirmarQuitas: false, confirmarMasiva: false, modo: "completo" });
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
    mocks.cargar.mockRejectedValueOnce(new Error("El archivo tiene 1 error. No se cargó nada."));
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
    await waitFor(() => expect(mocks.cargar).toHaveBeenCalledWith(dos, { confirmarQuitas: false, confirmarMasiva: false, modo: "completo" }));
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

// ----------------------------------------------------------------- los dos modos
function elegirModo(nombre: "Excel corto" | "Excel completo para editar") {
  fireEvent.click(screen.getByRole("radio", { name: nombre }));
}

function elegirArchivoCorto(archivo = ARCHIVO) {
  fireEvent.change(screen.getByLabelText("Archivo con tus productos"), { target: { files: [archivo] } });
}

async function subirCorto(archivo = ARCHIVO) {
  elegirArchivoCorto(archivo);
  await screen.findByRole("region", { name: "Qué cambia" });
}

// Lo que el servidor devuelve para una plantilla corta con dos productos: uno con periodo
// (rige hasta el 30-11) y otro programado (empieza el 05-11).
const CORTO: CargaPreciosVistaPrevia = {
  ...BASE, modo: "corto", archivo: "plantilla_precios_corta.xlsx", filas: 2, sin_cambios: 0, a_cambiar: 2,
  por_campo: { precio_fijo: 2, hasta: 1, desde: 1 },
  efecto: { suben: 1, bajan: 0, sin_cambio_de_precio: 1, con_precio_nuevo: 0 },
  programados_total: 1, archivo_viejo_total: 0, columnas_ignoradas: [], sin_hasta_total: 0, sin_hasta: [],
  reemplazos_total: 0, reemplazos: [], mensaje: null,
  cambios: [
    { producto: "71 AAA1", glosa: "AMORTIGUADOR", precio_antes: 10450, precio_despues: 12990,
      campos: [{ campo: "Precio fijo", antes: "(sin precio fijo)", despues: "12.990" },
               { campo: "Hasta", antes: "(sin vencimiento)", despues: "30-11-2026" }],
      vigencia: "Rige hasta el 30-11-2026" },
    { producto: "13 BBB2", glosa: "FILTRO DE ACEITE", precio_antes: 5200, precio_despues: 5200,
      campos: [{ campo: "Precio fijo", antes: "(sin precio fijo)", despues: "6.500" },
               { campo: "Desde", antes: "(sin Desde)", despues: "05-11-2026" }],
      vigencia: "Rige desde el 05-11-2026" },
  ],
  cambios_total: 2,
};

describe("elegir el modo de carga", () => {
  it("ofrece dos opciones con nombre accesible y una explicacion de cada una", () => {
    abrir();

    const grupo = screen.getByRole("group", { name: "¿Cómo quieres cargar?" });
    const corto = within(grupo).getByRole("radio", { name: "Excel corto" });
    const completo = within(grupo).getByRole("radio", { name: "Excel completo para editar" });
    expect(within(grupo).getAllByRole("radio")).toHaveLength(2);
    expect(corto).toHaveAccessibleDescription(/Solo los productos que pones tú/);
    expect(completo).toHaveAccessibleDescription(/Bajas toda la lista/);
    // Son radios nativos: el teclado (flechas) y los lectores de pantalla ya los entienden.
    expect(corto).toHaveAttribute("type", "radio");
    expect(corto).toHaveAttribute("name", completo.getAttribute("name") ?? "");
  });

  it("sin nada guardado parte en el Excel corto, que es lo que se usa para pocos productos", () => {
    window.localStorage.removeItem(CLAVE_MODO);
    abrir();

    expect(screen.getByRole("radio", { name: "Excel corto" })).toBeChecked();
    expect(screen.getByRole("radio", { name: "Excel completo para editar" })).not.toBeChecked();
    expect(screen.getByRole("button", { name: "Descargar plantilla" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Descargar para editar/ })).not.toBeInTheDocument();
  });

  it("recuerda el ultimo modo elegido", () => {
    window.localStorage.setItem(CLAVE_MODO, "corto");
    const { unmount } = abrir();
    expect(screen.getByRole("radio", { name: "Excel corto" })).toBeChecked();
    unmount();

    window.localStorage.setItem(CLAVE_MODO, "completo");
    abrir();
    expect(screen.getByRole("radio", { name: "Excel completo para editar" })).toBeChecked();
    expect(screen.getByRole("button", { name: /Descargar para editar/ })).toBeInTheDocument();
  });

  it("un valor guardado que no es un modo se ignora", () => {
    window.localStorage.setItem(CLAVE_MODO, "otra-cosa");
    abrir();

    expect(screen.getByRole("radio", { name: "Excel corto" })).toBeChecked();
  });

  it("al elegir un modo lo guarda para la proxima vez", () => {
    abrir();

    elegirModo("Excel corto");
    expect(window.localStorage.getItem(CLAVE_MODO)).toBe("corto");
    elegirModo("Excel completo para editar");
    expect(window.localStorage.getItem(CLAVE_MODO)).toBe("completo");
  });

  it("si el navegador no deja guardar, igual funciona y parte en el Excel corto", () => {
    const leer = vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("bloqueado"); });
    const escribir = vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("bloqueado"); });
    try {
      abrir();
      expect(screen.getByRole("radio", { name: "Excel corto" })).toBeChecked();

      elegirModo("Excel completo para editar");

      expect(screen.getByRole("radio", { name: "Excel completo para editar" })).toBeChecked();
      expect(screen.getByRole("button", { name: /Descargar para editar/ })).toBeInTheDocument();
    } finally {
      leer.mockRestore();
      escribir.mockRestore();
    }
  });

  it("cada modo muestra sus propios pasos", () => {
    abrir();
    for (const paso of ["1. Descarga la lista", "2. Edítala en Excel", "3. Súbelo"]) {
      expect(screen.getByRole("heading", { name: paso })).toBeInTheDocument();
    }

    elegirModo("Excel corto");

    for (const paso of ["1. Baja la plantilla", "2. Escribe tus productos", "3. Súbelo"]) {
      expect(screen.getByRole("heading", { name: paso })).toBeInTheDocument();
    }
    expect(screen.queryByRole("heading", { name: "1. Descarga la lista" })).not.toBeInTheDocument();
  });

  it("cambiar de modo descarta el archivo y la vista previa, como Descartar", async () => {
    mocks.previa.mockResolvedValue({ ...BASE, quitan_total: 12, quitan: { precio_fijo: 12 } });
    abrir();
    await subir();
    fireEvent.click(screen.getByRole("checkbox"));
    expect(screen.getByText("lista.csv")).toBeInTheDocument();

    elegirModo("Excel corto");

    expect(screen.queryByRole("region", { name: "Qué cambia" })).not.toBeInTheDocument();
    expect(screen.queryByText("lista.csv")).not.toBeInTheDocument();
    expect(mocks.cargar).not.toHaveBeenCalled();
    // Y al volver, nada queda marcado ni a medias.
    elegirModo("Excel completo para editar");
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "Qué cambia" })).not.toBeInTheDocument();
  });

  it("cambiar de modo borra los errores y avisos del otro", async () => {
    mocks.previa.mockRejectedValue(new Error("Faltan las columnas: Obs."));
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /Descargar para editar/ }));
    expect(await screen.findByText(/Archivo descargado: 39\.830 productos/)).toBeInTheDocument();
    elegirArchivo();
    expect(await screen.findByRole("alert")).toHaveTextContent("Faltan las columnas: Obs.");

    elegirModo("Excel corto");

    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.queryByText(/Archivo descargado/)).not.toBeInTheDocument();
  });

  it("elegir el mismo modo otra vez no descarta nada", async () => {
    abrir();
    await subir();

    elegirModo("Excel completo para editar");

    expect(screen.getByRole("region", { name: "Qué cambia" })).toBeInTheDocument();
  });

  it("los modos no se pueden cambiar mientras lee el archivo", async () => {
    mocks.previa.mockReturnValue(new Promise(() => {}));
    abrir();

    elegirArchivo();

    await screen.findByRole("status");
    expect(screen.getByRole("radio", { name: "Excel corto" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Excel completo para editar" })).toBeDisabled();
  });

  it("ni mientras carga", async () => {
    mocks.cargar.mockReturnValue(new Promise(() => {}));
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    await screen.findByRole("button", { name: /Cargando/ });
    expect(screen.getByRole("radio", { name: "Excel corto" })).toBeDisabled();
    expect(screen.getByRole("radio", { name: "Excel completo para editar" })).toBeDisabled();
  });

  it("una descarga que termina despues de cambiar de modo no deja su aviso en el otro", async () => {
    let terminar: (n: number) => void = () => {};
    mocks.descargar.mockReturnValue(new Promise<number>((r) => { terminar = r; }));
    abrir();
    fireEvent.click(screen.getByRole("button", { name: /Descargar para editar/ }));

    elegirModo("Excel corto");
    // La descarga grande sigue en vuelo: no se lanza otra encima (Render tiene poca memoria).
    expect(screen.getByRole("button", { name: "Descargar plantilla" })).toBeDisabled();
    await act(async () => { terminar(39830); });

    expect(screen.queryByText(/Archivo descargado/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Descargar plantilla" })).toBeEnabled();
  });
});

describe("modo Excel corto", () => {
  beforeEach(() => {
    window.localStorage.setItem(CLAVE_MODO, "corto");
    mocks.previa.mockResolvedValue(CORTO);
  });

  it("explica la plantilla: sus columnas, un ejemplo y las reglas", () => {
    abrir();

    const ejemplo = screen.getByRole("table", { name: "Ejemplo de la plantilla" });
    const cabecera = within(ejemplo).getAllByRole("columnheader").map((c) => c.textContent);
    expect(cabecera).toEqual(["Código", "Precio fijo", "Desde", "Hasta"]);
    // Dos filas de ejemplo, marcadas como tales: nadie las sube por error.
    expect(within(ejemplo).getAllByText("ejemplo")).toHaveLength(2);
    expect(screen.getByText(/Una fila por producto\. Solo se tocan los códigos que pongas/)).toBeInTheDocument();
    expect(screen.getByText(/Los que no estén se ignoran y se listan/)).toBeInTheDocument();
    expect(screen.getByText(/queda sin vencimiento/)).toBeInTheDocument();
    expect(screen.getByText(/Fechas como dd-mm-aaaa/)).toBeInTheDocument();
    expect(screen.getByText(/Celda vacía: no cambia nada\. Para quitar un valor escribe QUITAR/)).toBeInTheDocument();
    expect(screen.getByText(/lo reemplaza: lo verás en la vista previa/)).toBeInTheDocument();
    // No explica la tabla de once columnas del archivo completo.
    expect(screen.queryByRole("row", { name: /^Margen fijo %/ })).not.toBeInTheDocument();
  });

  it("Descargar plantilla pide la plantilla, no la lista de siempre", async () => {
    abrir();

    fireEvent.click(screen.getByRole("button", { name: "Descargar plantilla" }));

    await waitFor(() => expect(mocks.plantilla).toHaveBeenCalledTimes(1));
    expect(mocks.plantilla).toHaveBeenCalledWith("xlsx", expect.any(Function));
    expect(mocks.descargar).not.toHaveBeenCalled();
    expect(await screen.findByText(/Plantilla descargada \(plantilla_precios_corta\.xlsx\)/)).toBeInTheDocument();
    expect(screen.getByText(/No incluye la lista/)).toBeInTheDocument();
  });

  it("mientras baja la plantilla muestra que trabaja y no deja pedirla dos veces", async () => {
    let terminar: (n: string) => void = () => {};
    mocks.plantilla.mockReturnValue(new Promise<string>((r) => { terminar = r; }));
    abrir();

    fireEvent.click(screen.getByRole("button", { name: "Descargar plantilla" }));

    expect(screen.getByRole("button", { name: "Descargar plantilla" })).toBeDisabled();
    await act(async () => { terminar("plantilla_precios_corta.xlsx"); });
    expect(screen.getByRole("button", { name: "Descargar plantilla" })).toBeEnabled();
  });

  it("si la plantilla no baja, lo dice junto al boton con el motivo", async () => {
    mocks.plantilla.mockRejectedValue(new Error("No tienes permiso para editar precios."));
    abrir();

    fireEvent.click(screen.getByRole("button", { name: "Descargar plantilla" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No tienes permiso para editar precios.");
    expect(screen.queryByText(/Plantilla descargada/)).not.toBeInTheDocument();
  });

  it("el reintento de la plantilla se avisa como el de la descarga", async () => {
    mocks.plantilla.mockImplementation((_a: string, alReintentar: (i: number, t: number) => void) => {
      alReintentar(1, 4);
      return new Promise(() => {});
    });
    abrir();

    fireEvent.click(screen.getByRole("button", { name: "Descargar plantilla" }));

    expect(await screen.findByText("Descarga: el servidor no responde. Reintentando (1 de 4)…")).toBeInTheDocument();
  });

  it("elegir el archivo lo lee declarando el modo corto, y el campo tiene su propio nombre", async () => {
    abrir();

    await subirCorto();

    expect(mocks.previa).toHaveBeenCalledWith(ARCHIVO, expect.any(Function), expect.any(AbortSignal), "corto");
    expect(mocks.descargar).not.toHaveBeenCalled();
    expect(screen.queryByLabelText("Archivo editado")).not.toBeInTheDocument();
  });

  it("la vista previa dice que solo se tocan los productos del archivo, con el resto de la lista", async () => {
    abrir({ totalProductos: 39948 });

    await subirCorto();

    expect(screen.getByText("Solo se tocan los 2 productos de tu archivo. Los otros 39.946 quedan como están.")).toBeInTheDocument();
    expect(screen.getByText("Rige hasta el 30-11-2026")).toBeInTheDocument();
    expect(screen.getByText("AMORTIGUADOR")).toBeInTheDocument();
  });

  it("un producto programado dice que hoy no cambia y desde cuando rige", async () => {
    abrir({ hoy: "2026-10-20" });

    await subirCorto();

    expect(screen.getByText("hoy no cambia · rige desde 05-11")).toBeInTheDocument();
    expect(screen.getByText(/1 producto empieza más adelante/)).toBeInTheDocument();
  });

  it("lista los codigos que no estan en la lista", async () => {
    mocks.previa.mockResolvedValue({ ...CORTO, desconocidos_total: 2, desconocidos: ["ZZ 9", "ZZ 10"] });
    abrir();

    await subirCorto();

    expect(screen.getByText(/2 códigos no están en la lista y se ignoran/)).toBeInTheDocument();
    expect(screen.getByText("ZZ 9, ZZ 10")).toBeInTheDocument();
    // Lo que si esta bien igual se puede cargar.
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeEnabled();
  });

  it("con errores por fila no se puede cargar y se dice cual es cada uno", async () => {
    mocks.previa.mockResolvedValue({
      ...CORTO, errores_total: 2,
      errores: [
        { fila: 7, producto: "71 AAA1", mensaje: "Hasta: «11/30/2026» no es una fecha; usa dd-mm-aaaa." },
        { fila: 9, producto: "13 BBB2", mensaje: "Precio fijo: tiene que ser mayor que 0." },
      ],
    });
    abrir();

    await subirCorto();

    const alerta = screen.getByRole("alert");
    expect(alerta).toHaveTextContent("Fila 7");
    expect(alerta).toHaveTextContent("usa dd-mm-aaaa");
    expect(alerta).toHaveTextContent("Fila 9");
    expect(screen.getByRole("button", { name: /Cargar 2 productos/ })).toBeDisabled();
    // La frase de la vista previa, no la regla de la plantilla ("Solo se tocan los códigos que pongas").
    expect(screen.queryByText(/Solo se tocan los \d+ productos de tu archivo/)).not.toBeInTheDocument();
  });

  it("avisa los reemplazos, los precios sin fecha de termino y las columnas ignoradas", async () => {
    mocks.previa.mockResolvedValue({
      ...CORTO,
      reemplazos_total: 1,
      reemplazos: [{ producto: "71 AAA1", decision_anterior: "Margen fijo 35 %", editado_por: null, editado_en: null }],
      sin_hasta_total: 1, sin_hasta: ["13 BBB2"],
      columnas_ignoradas: ["Congelar"],
    });
    abrir();

    await subirCorto();

    expect(screen.getByText(/1 precio fijo reemplaza una decisión que el producto ya tenía/)).toBeInTheDocument();
    expect(screen.getByText(/1 precio fijo queda sin fecha de término/)).toBeInTheDocument();
    expect(screen.getByText(/Estas columnas del archivo no se leen y se ignoran: Congelar/)).toBeInTheDocument();
    // Son avisos: no bloquean la carga.
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeEnabled();
  });

  it("la plantilla sin llenar da un mensaje, no un error", async () => {
    mocks.previa.mockResolvedValue({
      ...CORTO, filas: 0, a_cambiar: 0, cambios: [], cambios_total: 0, programados_total: 0,
      mensaje: "El archivo no tiene ningún producto: llena la plantilla con los códigos que quieras cambiar y súbela de nuevo.",
    });
    abrir();

    await subirCorto();

    expect(screen.getByText(/llena la plantilla con los códigos que quieras cambiar/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cargar 0 productos/ })).toBeDisabled();
  });

  it("sobre 200 pide la casilla de confirmar y manda la confirmacion con el modo", async () => {
    mocks.previa.mockResolvedValue({
      ...CORTO, a_cambiar: 120, fijan_total: 240, fijan: { precio_fijo: 120, hasta: 120 },
    });
    abrir();
    await subirCorto();

    const cargarBtn = screen.getByRole("button", { name: "Cargar 120 productos" });
    expect(cargarBtn).toBeDisabled();
    expect(screen.getByText(/Esta carga deja 240 decisiones de precio nuevas: 120 precios fijos, 120 fechas Hasta\./)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /Entiendo que se fijan 240 valores/ }));
    fireEvent.click(cargarBtn);

    await waitFor(() => expect(mocks.cargar).toHaveBeenCalledTimes(1));
    expect(mocks.cargar).toHaveBeenCalledWith(ARCHIVO, { confirmarQuitas: false, confirmarMasiva: true, modo: "corto" });
  });

  it("cargar sube el mismo archivo con el modo corto y refresca la lista", async () => {
    const onCargado = vi.fn();
    mocks.cargar.mockResolvedValue({ ...OK, modo: "corto", aplicados: 12, precios_distintos: 9 });
    abrir({ onCargado });
    await subirCorto();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    await waitFor(() => expect(mocks.cargar).toHaveBeenCalledTimes(1));
    expect(mocks.cargar).toHaveBeenCalledWith(ARCHIVO, { confirmarQuitas: false, confirmarMasiva: false, modo: "corto" });
    expect(await screen.findByText(/Listo: 12 productos actualizados, 9 cambiaron de precio\./)).toBeInTheDocument();
    expect(onCargado).toHaveBeenCalledTimes(1);
  });

  it("el resultado menciona los que empiezan mas adelante", async () => {
    mocks.cargar.mockResolvedValue({ ...OK, modo: "corto", aplicados: 12, precios_distintos: 9 });
    mocks.previa.mockResolvedValue({ ...CORTO, programados_total: 3 });
    abrir();
    await subirCorto();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    const r = await screen.findByText(/Listo: 12 productos actualizados/);
    expect(r).toHaveTextContent("Listo: 12 productos actualizados, 9 cambiaron de precio. 3 empiezan más adelante y se aplican ese día.");
    expect(r).toHaveTextContent('Los precios nuevos salen en el próximo "Solo diferencias".');
  });

  it("con uno solo programado y ningun precio distinto, habla en singular", async () => {
    mocks.cargar.mockResolvedValue({ ...OK, modo: "corto", aplicados: 1, precios_distintos: 0 });
    mocks.previa.mockResolvedValue({ ...CORTO, programados_total: 1 });
    abrir();
    await subirCorto();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    const r = await screen.findByText(/Listo: 1 producto actualizado/);
    expect(r).toHaveTextContent("Ningún precio cambió. 1 empieza más adelante y se aplica ese día.");
    expect(r).not.toHaveTextContent("Solo diferencias");
  });

  it("sin programados el resultado no menciona nada de eso", async () => {
    mocks.previa.mockResolvedValue({ ...CORTO, programados_total: 0 });
    abrir();
    await subirCorto();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    expect(await screen.findByText(/Listo: 2 productos actualizados/)).not.toHaveTextContent(/más adelante/);
  });

  it("si la carga se corta sin confirmar, refresca la lista y deja reintentar con el mismo archivo", async () => {
    const perdida = Object.assign(new Error("No se pudo confirmar la carga."), { name: "CargaSinConfirmar" });
    mocks.cargar.mockRejectedValueOnce(perdida);
    const onCargado = vi.fn();
    abrir({ onCargado });
    await subirCorto();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    expect(await screen.findByRole("alert")).toHaveTextContent("No se pudo confirmar la carga");
    expect(onCargado).toHaveBeenCalledTimes(1);
    expect(screen.getByRole("button", { name: "Cargar 2 productos" })).toBeEnabled();
  });

  it("descartar vuelve a Elegir archivo y no carga nada", async () => {
    abrir();
    await subirCorto();

    fireEvent.click(screen.getByRole("button", { name: "Descartar" }));

    await waitFor(() => expect(screen.getByRole("button", { name: /Elegir archivo/ })).toHaveFocus());
    expect(mocks.cargar).not.toHaveBeenCalled();
  });
});

describe("modo Excel completo", () => {
  it("lista las once columnas que se pueden editar, con lo que pasa al dejarlas vacias", () => {
    abrir();

    const tabla = screen.getByRole("table");
    expect(within(tabla).getAllByRole("row")).toHaveLength(COLUMNAS_EDITABLES.length + 1);   // + el encabezado
    for (const nombre of ["Precio fijo", "Margen fijo %", "Desde", "Hasta"]) {
      expect(within(tabla).getByRole("row", { name: new RegExp(`^${nombre}`) })).toBeInTheDocument();
    }
  });

  it("explica lo nuevo: Precio fijo muestra lo guardado, Factor y Margen son la misma decision, y el periodo es uno", () => {
    abrir();

    expect(screen.getByText(/Fija el margen en % sobre la venta/)).toBeInTheDocument();
    expect(screen.getByText(/Muestra lo que hay guardado, aunque su periodo no rija hoy/)).toBeInTheDocument();
    expect(screen.getByText(/Factor y Margen fijo % son la misma decisión: cambia solo uno/)).toBeInTheDocument();
    expect(screen.getByText(/Desde y Hasta valen para el precio fijo, el margen fijo y el congelado/)).toBeInTheDocument();
  });

  it("deja a la vista las columnas de solo lectura, cada una con su motivo", () => {
    abrir();

    expect(screen.getByRole("heading", { name: /Solo lectura: si las cambias, se ignoran/ })).toBeInTheDocument();
    const lista = screen.getByRole("list", { name: "Columnas de solo lectura" });
    const items = within(lista).getAllByRole("listitem");
    // Las trece de solo lectura, en el orden del archivo, y la Referencia, que tampoco se toca.
    expect(items).toHaveLength(COLUMNAS_SOLO_LECTURA.length + 1);
    expect(COLUMNAS_SOLO_LECTURA.map((c) => c.columna)).toEqual([
      "Producto", "Glosa", "Rubro", "Costo", "Precio ERP", "Precio calculado", "Estado", "Stock",
      "En transito", "Ultima venta", "Descuento máximo", "Descuento+1", "Vigencia"]);
    for (const c of COLUMNAS_SOLO_LECTURA) {
      expect(within(lista).getByText(`${c.columna}: ${c.motivo}`)).toBeInTheDocument();
    }
    expect(within(lista).getByText(/^Referencia: no la toques/)).toBeInTheDocument();
    // Ninguna columna esta en las dos listas: o se edita o es de solo lectura.
    for (const c of COLUMNAS_SOLO_LECTURA) {
      expect(COLUMNAS_EDITABLES.map((e) => e.columna)).not.toContain(c.columna);
    }
    // Un candado por cada una: la marca no depende solo del texto gris.
    expect(lista.querySelectorAll("svg")).toHaveLength(items.length);
  });

  it("avisa que el archivo pesa y puede tardar", () => {
    abrir();

    expect(screen.getByText(/archivo grande \(más de 10 MB\)/)).toBeInTheDocument();
  });

  it("un archivo corto subido en modo completo muestra el 422 del servidor tal cual", async () => {
    const motivo = "Este archivo es de la plantilla corta, pero elegiste el archivo completo para editar. Cambia de modo o descarga el archivo de nuevo.";
    mocks.previa.mockRejectedValue(new Error(motivo));
    abrir();

    elegirArchivo();

    expect(await screen.findByRole("alert")).toHaveTextContent(motivo);
    expect(screen.queryByRole("region", { name: "Qué cambia" })).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Elegir archivo/ })).toBeEnabled();
  });

  it("un archivo bajado antes de las columnas nuevas avisa que esas no se leyeron", async () => {
    mocks.previa.mockResolvedValue({ ...BASE, modo: "completo", archivo_viejo_total: 39830 });
    abrir();

    await subir();

    expect(screen.getByText(/39\.830 filas son de un archivo bajado antes de las columnas/)).toBeInTheDocument();
  });

  it("el resultado tambien menciona los productos que empiezan mas adelante", async () => {
    mocks.previa.mockResolvedValue({ ...BASE, modo: "completo", programados_total: 2 });
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    const r = await screen.findByText(/Listo: 2 productos actualizados/);
    expect(r).toHaveTextContent("1 cambió de precio. 2 empiezan más adelante y se aplican ese día.");
  });

  it("no cuenta mas programados que productos cargados", async () => {
    mocks.cargar.mockResolvedValue({ ...OK, aplicados: 1, precios_distintos: 0 });
    mocks.previa.mockResolvedValue({ ...BASE, modo: "completo", programados_total: 5 });
    abrir();
    await subir();

    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));

    expect(await screen.findByText(/Listo: 1 producto actualizado/)).toHaveTextContent("1 empieza más adelante y se aplica ese día.");
  });
});
