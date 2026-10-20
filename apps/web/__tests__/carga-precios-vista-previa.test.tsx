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

import { VistaPrevia, derivadosDePrevia } from "@/components/carga-precios/vista-previa";
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
