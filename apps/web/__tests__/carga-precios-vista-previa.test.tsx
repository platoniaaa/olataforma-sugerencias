/**
 * La vista previa de la carga por Excel ("Qué cambia"), sola, sin el dialogo.
 *
 * Se saco de carga-precios-excel.tsx sin cambiar lo que hace (esas pruebas siguen siendo la
 * red de seguridad del comportamiento). Estas fijan el contrato con el que el dialogo la
 * usa, que es lo que los dos modos de carga van a compartir:
 *
 * 1. El dialogo es dueno del foco: el panel recibe su ref y se puede enfocar.
 * 2. Descartar y Cargar solo avisan; no hacen nada por su cuenta.
 * 3. "Cargar" depende de lo que diga el dialogo (puedeCargar), no de la vista previa.
 * 4. Las casillas de confirmacion avisan y se bloquean mientras se guarda.
 * 5. Que pida confirmacion y que cuente como omitido sale de UNA sola funcion, la misma
 *    que usa el dialogo para habilitar "Cargar".
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { createRef } from "react";
import { describe, expect, it, vi } from "vitest";

import { VistaPrevia, derivadosDePrevia, inicioProgramado } from "@/components/carga-precios/vista-previa";
import type { CargaPreciosVistaPrevia } from "@/lib/types";

const BASE: CargaPreciosVistaPrevia = {
  archivo: "lista.csv", filas: 39830, sin_cambios: 39828, a_cambiar: 2, por_campo: { tipo: 1, precio_fijo: 1 },
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

function dibujar(previa: CargaPreciosVistaPrevia = BASE, extra: Partial<Parameters<typeof VistaPrevia>[0]> = {}) {
  const panelRef = createRef<HTMLElement>();
  const llamadas = {
    onConfirmaQuitas: vi.fn(),
    onConfirmaMasiva: vi.fn(),
    onDescartar: vi.fn(),
    onCargar: vi.fn(),
  };
  render(
    <VistaPrevia
      previa={previa}
      panelRef={panelRef}
      cargando={false}
      puedeCargar
      confirmaQuitas={false}
      confirmaMasiva={false}
      {...llamadas}
      {...extra}
    />,
  );
  return { panelRef, ...llamadas };
}

describe("VistaPrevia", () => {
  it("el panel recibe el ref del dialogo y se puede enfocar", () => {
    const { panelRef } = dibujar();
    const panel = screen.getByRole("region", { name: "Qué cambia" });
    expect(panelRef.current).toBe(panel);
    panelRef.current?.focus();
    expect(panel).toHaveFocus();
  });

  it("muestra el resumen, cada cambio con su glosa y el texto de precios", () => {
    dibujar();
    expect(screen.getByText("39.830 filas leídas")).toBeInTheDocument();
    expect(screen.getByText("2 productos se cargarán")).toBeInTheDocument();
    expect(screen.getByText("DISCO DE FRENO")).toBeInTheDocument();
    expect(screen.getByText("$209.542 → $221.315")).toBeInTheDocument();
    expect(screen.getByText("no cambia")).toBeInTheDocument();
    expect(screen.getByText(/Precios: 1 sube, 0 bajan, 0 pasan de sin precio a tener uno y 1 no cambia de precio\./)).toBeInTheDocument();
  });

  it("Descartar y Cargar solo avisan al dialogo", () => {
    const { onDescartar, onCargar } = dibujar();
    fireEvent.click(screen.getByRole("button", { name: "Descartar" }));
    expect(onDescartar).toHaveBeenCalledTimes(1);
    expect(onCargar).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cargar 2 productos" }));
    expect(onCargar).toHaveBeenCalledTimes(1);
  });

  it("Cargar queda deshabilitado cuando el dialogo dice que no se puede", () => {
    const { onCargar } = dibujar(BASE, { puedeCargar: false });
    const boton = screen.getByRole("button", { name: "Cargar 2 productos" });
    expect(boton).toBeDisabled();
    fireEvent.click(boton);
    expect(onCargar).not.toHaveBeenCalled();
  });

  it("mientras se guarda, nada se toca y se avisa que no se cierre", () => {
    const quitan = { ...BASE, quitan_total: 12, quitan: { obs: 12 }, quitan_ejemplos: [] };
    dibujar(quitan, { cargando: true, puedeCargar: false });
    expect(screen.getByRole("button", { name: "Descartar" })).toBeDisabled();
    expect(screen.getByRole("button", { name: "Cargando…" })).toBeDisabled();
    expect(screen.getByRole("checkbox")).toBeDisabled();
    expect(screen.getByRole("status")).toHaveTextContent("No cierres esta ventana.");
  });

  it("la casilla de quitas aparece al llegar al umbral y avisa lo que marcan", () => {
    const quitan = { ...BASE, quitan_total: 10, quitan: { obs: 10 } };
    const { onConfirmaQuitas } = dibujar(quitan);
    fireEvent.click(screen.getByRole("checkbox", { name: /Entiendo que se quitan 10 decisiones/ }));
    expect(onConfirmaQuitas).toHaveBeenCalledWith(true);
  });

  it("la casilla de quitas refleja lo que el dialogo guarda", () => {
    const quitan = { ...BASE, quitan_total: 10, quitan: { obs: 10 } };
    dibujar(quitan, { confirmaQuitas: true });
    expect(screen.getByRole("checkbox")).toBeChecked();
  });

  it("la casilla de lo masivo avisa lo que marcan y nombra las decisiones", () => {
    const masiva = { ...BASE, fijan_total: 201, fijan: { precio_fijo: 150, factor: 51 } };
    const { onConfirmaMasiva } = dibujar(masiva);
    expect(screen.getByText(/150 precios fijos, 51 factores propios/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("checkbox", { name: /Entiendo que se fijan 201 valores/ }));
    expect(onConfirmaMasiva).toHaveBeenCalledWith(true);
  });

  it("con errores no ofrece casillas ni la tabla de cambios", () => {
    const conErrores = {
      ...BASE,
      errores_total: 1,
      errores: [{ fila: 3, producto: "71 AAA1", mensaje: "Factor no es un número." }],
      quitan_total: 50, quitan: { obs: 50 },
    };
    dibujar(conErrores, { puedeCargar: false });
    expect(screen.getByRole("alert")).toHaveTextContent("El archivo tiene 1 error.");
    expect(screen.getByText(/Factor no es un número\./)).toBeInTheDocument();
    expect(screen.queryByRole("checkbox")).not.toBeInTheDocument();
    expect(screen.queryByText("DISCO DE FRENO")).not.toBeInTheDocument();
  });
});

// -------------------------------------------------------- el Excel corto y el periodo
// La vista previa es la misma para los dos modos. Lo que el Excel corto suma: que SOLO se tocan los
// productos del archivo, los precios fijos que pisan otra decision, los que quedan sin fecha de
// termino y las columnas que no se leen. Y para los dos: el periodo (Desde y Hasta) ya interpretado.
const CORTO: CargaPreciosVistaPrevia = {
  ...BASE, modo: "corto", archivo: "plantilla_precios_corta.xlsx", filas: 3, sin_cambios: 0, a_cambiar: 3,
  por_campo: { precio_fijo: 3, hasta: 2 },
  efecto: { suben: 2, bajan: 0, sin_cambio_de_precio: 1, con_precio_nuevo: 0 },
  programados_total: 0, archivo_viejo_total: 0, columnas_ignoradas: [], sin_hasta_total: 0, sin_hasta: [],
  reemplazos_total: 0, reemplazos: [], mensaje: null,
  cambios: [
    { producto: "71 AAA1", glosa: "AMORTIGUADOR", precio_antes: 10450, precio_despues: 12990,
      campos: [
        { campo: "Precio fijo", antes: "(sin precio fijo)", despues: "12.990" },
        { campo: "Hasta", antes: "(sin vencimiento)", despues: "30-11-2026" },
      ],
      vigencia: "Rige hasta el 30-11-2026" },
    { producto: "13 BBB2", glosa: "FILTRO DE ACEITE", precio_antes: 5200, precio_despues: 5200,
      campos: [{ campo: "Precio fijo", antes: "(sin precio fijo)", despues: "6.500" }],
      vigencia: "Rige desde el 05-11-2026" },
    { producto: "99 CCC3", glosa: "BUJIA", precio_antes: 3000, precio_despues: 3500,
      campos: [{ campo: "Precio fijo", antes: "2.900", despues: "3.500" }], vigencia: null },
  ],
  cambios_total: 3,
};

describe("VistaPrevia en el Excel corto", () => {
  it("dice que solo se tocan los productos del archivo y que el resto queda como esta", () => {
    dibujar({ ...CORTO, a_cambiar: 12, cambios_total: 12 }, { totalProductos: 39948 });
    expect(screen.getByText("Solo se tocan los 12 productos de tu archivo. Los otros 39.936 quedan como están.")).toBeInTheDocument();
  });

  it("sin el total de la lista no inventa una cifra", () => {
    dibujar({ ...CORTO, a_cambiar: 12, cambios_total: 12 });
    expect(screen.getByText("Solo se tocan los 12 productos de tu archivo. El resto de la lista queda como está.")).toBeInTheDocument();
    expect(screen.queryByText(/Los otros/)).not.toBeInTheDocument();
  });

  it("con un solo producto habla en singular", () => {
    dibujar({ ...CORTO, a_cambiar: 1, cambios_total: 1, cambios: [CORTO.cambios[0]] }, { totalProductos: 39948 });
    expect(screen.getByText("Solo se toca el producto de tu archivo. Los otros 39.947 quedan como están.")).toBeInTheDocument();
  });

  it("el archivo completo no lleva esa frase: ahi se compara contra lo que se bajo", () => {
    dibujar({ ...BASE, modo: "completo" }, { totalProductos: 39948 });
    expect(screen.queryByText(/Solo se tocan|Solo se toca/)).not.toBeInTheDocument();
  });

  it("un servidor que no dice el modo se trata como completo", () => {
    dibujar(BASE, { totalProductos: 39948 });
    expect(screen.queryByText(/Solo se tocan|Solo se toca/)).not.toBeInTheDocument();
  });

  it("con errores no afirma que se vaya a tocar nada", () => {
    dibujar({
      ...CORTO, errores_total: 1,
      errores: [{ fila: 7, producto: "71 AAA1", mensaje: "Hasta: «11/30/2026» no es una fecha; usa dd-mm-aaaa." }],
    }, { totalProductos: 39948, puedeCargar: false });
    expect(screen.queryByText(/Solo se tocan/)).not.toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Fila 7");
    expect(screen.getByRole("alert")).toHaveTextContent("usa dd-mm-aaaa");
  });

  it("avisa los precios fijos que pisan un margen fijo o un congelado, con lo que habia", () => {
    dibujar({
      ...CORTO,
      reemplazos_total: 2,
      reemplazos: [
        { producto: "71 AAA1", decision_anterior: "Margen fijo 35 % (vencido el 30-09-2026)", editado_por: "ana@curifor.cl", editado_en: "2026-10-12T14:00:00" },
        { producto: "13 BBB2", decision_anterior: "Congelado en 2.160", editado_por: null, editado_en: null },
      ],
    });
    expect(screen.getByText(/2 precios fijos reemplazan una decisión que el producto ya tenía/)).toBeInTheDocument();
    expect(screen.getByText(/Margen fijo 35 % \(vencido el 30-09-2026\)/)).toBeInTheDocument();
    expect(screen.getByText(/Congelado en 2\.160/)).toBeInTheDocument();
    expect(screen.getByText(/ana@curifor\.cl/)).toBeInTheDocument();
    expect(screen.getByText(/12-10-2026/)).toBeInTheDocument();
  });

  it("con un solo reemplazo habla en singular", () => {
    dibujar({
      ...CORTO, reemplazos_total: 1,
      reemplazos: [{ producto: "13 BBB2", decision_anterior: "Congelado en 2.160", editado_por: null, editado_en: null }],
    });
    expect(screen.getByText(/1 precio fijo reemplaza una decisión que el producto ya tenía/)).toBeInTheDocument();
  });

  it("avisa los precios fijos que quedan sin fecha de termino, con sus codigos", () => {
    dibujar({ ...CORTO, sin_hasta_total: 3, sin_hasta: ["71 AAA1", "13 BBB2"] });
    const aviso = screen.getByText(/3 precios fijos quedan sin fecha de término/);
    expect(aviso).toBeInTheDocument();
    expect(screen.getByText(/queda fijo hasta que alguien lo cambie/i)).toBeInTheDocument();
    expect(screen.getByText(/71 AAA1, 13 BBB2 … y 1 más/)).toBeInTheDocument();
  });

  it("con uno solo, sin fecha de termino va en singular", () => {
    dibujar({ ...CORTO, sin_hasta_total: 1, sin_hasta: ["71 AAA1"] });
    expect(screen.getByText(/1 precio fijo queda sin fecha de término/)).toBeInTheDocument();
  });

  it("sin ninguno de esos casos no hay avisos de reemplazo ni de fecha de termino", () => {
    dibujar(CORTO);
    expect(screen.queryByText(/reemplaz/)).not.toBeInTheDocument();
    expect(screen.queryByText(/sin fecha de término/)).not.toBeInTheDocument();
  });

  it("lista las columnas que el Excel corto no lee", () => {
    dibujar({ ...CORTO, columnas_ignoradas: ["Margen fijo %", "Congelar"] });
    const aviso = screen.getByText(/Estas columnas del archivo no se leen y se ignoran/);
    expect(aviso).toBeInTheDocument();
    expect(screen.getByText(/Margen fijo %, Congelar/)).toBeInTheDocument();
    expect(screen.getByText(/solo usa Código, Precio fijo, Desde, Hasta y Obs/)).toBeInTheDocument();
  });

  it("un codigo que no esta en la lista se cuenta como tal, no como 'se omite'", () => {
    dibujar({ ...CORTO, desconocidos_total: 2, desconocidos: ["ZZ 1", "ZZ 2"] });
    expect(screen.getByText("2 códigos no están en la lista")).toBeInTheDocument();
    expect(screen.queryByText("2 se omiten")).not.toBeInTheDocument();
    expect(screen.getByText(/2 códigos no están en la lista y se ignoran\./)).toBeInTheDocument();
  });

  it("explica de donde vienen las quitas: QUITAR o un reemplazo, nunca una celda vacia", () => {
    dibujar({ ...CORTO, quitan_total: 3, quitan: { precio_fijo: 1, factor: 1, hasta: 1 }, quitan_ejemplos: [] });
    expect(screen.getByText(/Esta carga quita 3 decisiones: 1 precio fijo, 1 margen fijo, 1 fecha Hasta\./)).toBeInTheDocument();
    expect(screen.getByText(/Una celda vacía no quita nada en este archivo/)).toBeInTheDocument();
    expect(screen.queryByText(/celdas con error/)).not.toBeInTheDocument();
  });

  it("un archivo sin cambios dice que ya estan asi, no que el archivo viene vacio", () => {
    dibujar({ ...CORTO, a_cambiar: 0, sin_cambios: 3, cambios: [], cambios_total: 0 }, { puedeCargar: false });
    expect(screen.getByText(/Todos los productos del archivo ya están así/)).toBeInTheDocument();
    expect(screen.queryByText(/Solo se tocan/)).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Cargar 0 productos/ })).toBeDisabled();
  });

  it("la plantilla vacia no es un error: muestra el mensaje del servidor", () => {
    dibujar({
      ...CORTO, filas: 0, a_cambiar: 0, sin_cambios: 0, cambios: [], cambios_total: 0,
      mensaje: "El archivo no tiene ningún producto: llena la plantilla con los códigos que quieras cambiar y súbela de nuevo.",
    }, { puedeCargar: false });
    expect(screen.getByText(/El archivo no tiene ningún producto: llena la plantilla/)).toBeInTheDocument();
    expect(screen.queryByText(/no trae ningún cambio/)).not.toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("lo masivo en el corto habla de precios y fechas, y de la fila de cada codigo", () => {
    dibujar({ ...CORTO, a_cambiar: 90, fijan_total: 215, fijan: { precio_fijo: 100, desde: 80, hasta: 30, congelar: 5 } });
    expect(screen.getByText(/Esta carga deja 215 decisiones de precio nuevas: 100 precios fijos, 80 fechas Desde, 30 fechas Hasta, 5 congelados\./))
      .toBeInTheDocument();
    expect(screen.getByText(/por ejemplo Precio fijo o Hasta/)).toBeInTheDocument();
    expect(screen.queryByText(/Precio final o Factor/)).not.toBeInTheDocument();
    expect(screen.getByRole("checkbox", { name: /Entiendo que se fijan 215 valores/ })).toBeInTheDocument();
  });

  it("los codigos con espacios internos distintos se ven distintos", () => {
    dibujar({
      ...CORTO, a_cambiar: 2, cambios_total: 2, desconocidos_total: 2, desconocidos: ["19  FB5Z15201H", "19 FB5Z15201H"],
      cambios: [
        { ...CORTO.cambios[0], producto: "19  FB5Z15201H" },
        { ...CORTO.cambios[2], producto: "19 FB5Z15201H" },
      ],
    });
    // HTML colapsa los espacios: dos productos distintos se verian identicos sin `whitespace-pre`.
    const celdas = Array.from(document.querySelectorAll("tbody td:first-child .font-mono"));
    expect(celdas.map((c) => c.textContent)).toEqual(["19  FB5Z15201H", "19 FB5Z15201H"]);
    for (const c of celdas) expect(c.className).toContain("whitespace-pre");
    const lista = screen.getByText(/19\s+FB5Z15201H,/);
    expect(lista.className).toContain("whitespace-pre");
    expect(lista.textContent).toContain("19  FB5Z15201H, 19 FB5Z15201H");
  });

  it("los errores por fila tambien conservan los espacios del codigo", () => {
    dibujar({
      ...CORTO,
      errores_total: 1, errores: [{ fila: 4, producto: "19  FB5Z15201H", mensaje: "El código aparece repetido." }],
    }, { puedeCargar: false });
    const codigo = document.querySelector("[role=alert] .font-mono");
    expect(codigo?.textContent).toBe("19  FB5Z15201H");
    expect(codigo?.className).toContain("whitespace-pre");
  });
});

describe("VistaPrevia y el periodo (Desde y Hasta)", () => {
  it("muestra el periodo ya interpretado bajo cada cambio, para notar un dia y mes cambiados", () => {
    dibujar(CORTO, { hoy: "2026-10-20" });
    expect(screen.getByText("Rige hasta el 30-11-2026")).toBeInTheDocument();
    expect(screen.getByText("Rige desde el 05-11-2026")).toBeInTheDocument();
    // El producto sin periodo no lleva ninguna linea de periodo.
    const fila = screen.getByText("99 CCC3").closest("tr") as HTMLElement;
    expect(fila.textContent).not.toMatch(/Rige/);
  });

  it("un programado cuyo precio hoy no cambia lo dice y dice desde cuando rige", () => {
    dibujar(CORTO, { hoy: "2026-10-20" });
    expect(screen.getByText("hoy no cambia · rige desde 05-11")).toBeInTheDocument();
  });

  it("un programado cuyo precio SI cambia hoy muestra el cambio y desde cuando rige la decision", () => {
    dibujar({
      ...CORTO,
      cambios: [{ ...CORTO.cambios[1], precio_antes: 5200, precio_despues: 4900 }, CORTO.cambios[0], CORTO.cambios[2]],
    }, { hoy: "2026-10-20" });
    const fila = screen.getByText("13 BBB2").closest("tr") as HTMLElement;
    expect(fila.textContent).toContain("$5.200 → $4.900");
    expect(fila.textContent).toContain("rige desde 05-11");
    expect(fila.textContent).not.toContain("hoy no cambia");
  });

  it("un periodo que ya empezo no se trata como programado", () => {
    dibujar({
      ...CORTO,
      cambios: [{ ...CORTO.cambios[1], vigencia: "Rige del 01-10-2026 al 30-11-2026" }],
      a_cambiar: 1, cambios_total: 1,
    }, { hoy: "2026-10-20" });
    expect(screen.getByText("no cambia")).toBeInTheDocument();
    expect(screen.queryByText(/hoy no cambia/)).not.toBeInTheDocument();
  });

  it("el dia del Desde ya rige: no es programado", () => {
    dibujar({
      ...CORTO, cambios: [{ ...CORTO.cambios[1], vigencia: "Rige desde el 20-10-2026" }], a_cambiar: 1, cambios_total: 1,
    }, { hoy: "2026-10-20" });
    expect(screen.queryByText(/hoy no cambia/)).not.toBeInTheDocument();
  });

  it("un Desde de otro año muestra el año", () => {
    dibujar({
      ...CORTO, cambios: [{ ...CORTO.cambios[1], vigencia: "Rige del 05-01-2027 al 31-01-2027" }], a_cambiar: 1, cambios_total: 1,
    }, { hoy: "2026-10-20" });
    expect(screen.getByText("hoy no cambia · rige desde 05-01-2027")).toBeInTheDocument();
  });

  it("cuenta los productos que empiezan mas adelante, en cualquiera de los dos modos", () => {
    dibujar({ ...CORTO, programados_total: 3 });
    expect(screen.getByText(/3 productos empiezan más adelante: hasta el día de su Desde siguen la regla, y desde ese día rige lo que pusiste/))
      .toBeInTheDocument();
  });

  it("con uno solo habla en singular", () => {
    dibujar({ ...BASE, modo: "completo", programados_total: 1 });
    expect(screen.getByText(/1 producto empieza más adelante: hasta el día de su Desde sigue la regla/)).toBeInTheDocument();
  });

  it("sin programados no hay aviso", () => {
    dibujar(CORTO);
    expect(screen.queryByText(/empiezan más adelante|empieza más adelante/)).not.toBeInTheDocument();
  });

  it("un archivo completo bajado antes de las columnas de periodo lo avisa", () => {
    dibujar({ ...BASE, modo: "completo", archivo_viejo_total: 40 });
    expect(screen.getByText(/40 filas son de un archivo bajado antes de las columnas Precio fijo, Margen fijo %, Desde y Hasta/)).toBeInTheDocument();
    expect(screen.getByText(/Descarga el archivo de nuevo/)).toBeInTheDocument();
  });

  it("con una sola fila de formato viejo habla en singular", () => {
    dibujar({ ...BASE, modo: "completo", archivo_viejo_total: 1 });
    expect(screen.getByText(/1 fila es de un archivo bajado antes de las columnas/)).toBeInTheDocument();
  });

  it("quitar un Desde o un Hasta se nombra, no sale la clave cruda", () => {
    dibujar({ ...BASE, quitan_total: 4, quitan: { hasta: 3, desde: 1 }, quitan_ejemplos: [] });
    const aviso = screen.getByText(/Esta carga quita 4 decisiones/);
    expect(aviso).toHaveTextContent("3 fecha Hasta, 1 fecha Desde");
    expect(aviso.textContent).not.toMatch(/\bhasta\b|\bdesde\b/);
  });

  it("lo masivo en el archivo completo con fechas deja de decir solo 'precios fijos o factores'", () => {
    dibujar({ ...BASE, fijan_total: 250, fijan: { precio_fijo: 100, hasta: 100, congelar: 50 } });
    expect(screen.getByText(/Esta carga deja 250 decisiones de precio nuevas: 100 precios fijos, 100 fechas Hasta, 50 congelados\./))
      .toBeInTheDocument();
    expect(screen.getByText(/por ejemplo Precio final o Factor/)).toBeInTheDocument();
  });
});

describe("inicioProgramado", () => {
  it("lee el Desde de las dos frases del servidor y dice si empieza despues de hoy", () => {
    expect(inicioProgramado("Rige desde el 05-11-2026", "2026-10-20")).toBe("2026-11-05");
    expect(inicioProgramado("Rige del 05-11-2026 al 30-11-2026", "2026-10-20")).toBe("2026-11-05");
  });

  it("no es programado si ya empezo, si empieza hoy, si solo trae Hasta o si no hay frase", () => {
    expect(inicioProgramado("Rige desde el 20-10-2026", "2026-10-20")).toBeNull();
    expect(inicioProgramado("Rige del 01-10-2026 al 30-11-2026", "2026-10-20")).toBeNull();
    expect(inicioProgramado("Rige hasta el 30-11-2026", "2026-10-20")).toBeNull();
    expect(inicioProgramado(null, "2026-10-20")).toBeNull();
    expect(inicioProgramado(undefined, "2026-10-20")).toBeNull();
    expect(inicioProgramado("otra cosa", "2026-10-20")).toBeNull();
  });

  it("una fecha imposible no se toma por valida", () => {
    expect(inicioProgramado("Rige desde el 31-02-2027", "2026-10-20")).toBeNull();
  });
});

describe("derivadosDePrevia", () => {
  it("sin lectura todo es cero y nada pide confirmar", () => {
    expect(derivadosDePrevia(null)).toEqual({
      hayErrores: false, quitan: 0, pideConfirmar: false, fijan: 0, pideConfirmarMasiva: false, omitidos: 0,
    });
  });

  it("las quitas piden confirmar desde el umbral, lo masivo solo por encima", () => {
    expect(derivadosDePrevia({ ...BASE, quitan_total: 9 }).pideConfirmar).toBe(false);
    expect(derivadosDePrevia({ ...BASE, quitan_total: 10 }).pideConfirmar).toBe(true);
    expect(derivadosDePrevia({ ...BASE, fijan_total: 200 }).pideConfirmarMasiva).toBe(false);
    expect(derivadosDePrevia({ ...BASE, fijan_total: 201 }).pideConfirmarMasiva).toBe(true);
  });

  it("omitidos suma conflictos, desconocidos y filas sin referencia", () => {
    const d = derivadosDePrevia({ ...BASE, conflictos_total: 2, desconocidos_total: 3, sin_referencia_total: 4 });
    expect(d.omitidos).toBe(9);
  });

  it("hay errores en cuanto se cuenta uno", () => {
    expect(derivadosDePrevia({ ...BASE, errores_total: 1 }).hayErrores).toBe(true);
    expect(derivadosDePrevia(BASE).hayErrores).toBe(false);
  });
});
