/**
 * El recorrido guiado de la lista de precios.
 *
 * Lo que se prueba aca no es el texto -ese cambia- sino el contrato de la
 * navegacion: que se pueda salir en cualquier paso, que los extremos no ofrezcan
 * un paso que no existe, y que la primera visita se abra sola una sola vez. Sin
 * lo ultimo el recorrido tapa la pantalla cada manana, que es exactamente lo que
 * hace que la gente deje de leerlo.
 *
 * Y lo que lo hace un recorrido y no un modal: que destaque el elemento real de
 * la pantalla, que abra la ficha de un producto en los pasos que hablan de ella
 * (y la cierre al salir), y que cuando el elemento no esta -sin permiso, lista
 * vacia- lo diga en vez de apuntar al vacio.
 */
import "@testing-library/jest-dom/vitest";
import { act, fireEvent, render, screen } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { TutorialPrecios } from "@/components/tutorial-precios";

const TOTAL_PASOS = 15;
const PASO_FICHA = 6;      // "La ficha: el precio y su porqué"
const PASO_RECALCULAR = 10;

beforeEach(() => {
  localStorage.clear();
});

afterEach(() => {
  vi.useRealTimers();
});

/** Lo abre desde el boton, partiendo de un navegador que ya lo vio. */
function abrirDesdeElBoton(props: Parameters<typeof TutorialPrecios>[0] = {}) {
  localStorage.setItem("precios_tutorial_visto", "1");
  const r = render(<TutorialPrecios {...props} />);
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Tutorial/i }));
  return r;
}

function irAlPaso(n: number) {
  fireEvent.click(screen.getByRole("button", { name: new RegExp(`^Ir al paso ${n}:`) }));
}

/** Deja pasar el tiempo en que el recorrido insiste buscando un elemento
 *  que no esta (la ficha y la tabla se pintan despues de pedir los datos). */
function darPorPerdidoElElemento() {
  act(() => {
    vi.advanceTimersByTime(2500);
  });
}

describe("Tutorial de la lista de precios", () => {
  it("se abre solo la primera vez y despues ya no", () => {
    const { unmount } = render(<TutorialPrecios />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    unmount();

    // Segunda entrada a la pantalla: la barra tiene el boton, pero nada tapa la lista.
    render(<TutorialPrecios />);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(screen.getByRole("button", { name: /Tutorial/i })).toBeInTheDocument();
  });

  it("el boton lo vuelve a abrir en el primer paso", () => {
    abrirDesdeElBoton();

    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText(`Paso 1 de ${TOTAL_PASOS}`)).toBeInTheDocument();
    expect(screen.getByText("Qué es esta pantalla")).toBeInTheDocument();
  });

  it("avanza y retrocede entre pasos", () => {
    abrirDesdeElBoton();

    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    expect(screen.getByText(`Paso 2 de ${TOTAL_PASOS}`)).toBeInTheDocument();
    expect(screen.getByText("Los números de arriba")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    expect(screen.getByText(`Paso 3 de ${TOTAL_PASOS}`)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Anterior/i }));
    expect(screen.getByText(`Paso 2 de ${TOTAL_PASOS}`)).toBeInTheDocument();
    expect(screen.getByText("Los números de arriba")).toBeInTheDocument();
  });

  it("las flechas del teclado tambien navegan", () => {
    abrirDesdeElBoton();

    fireEvent.keyDown(document, { key: "ArrowRight" });
    expect(screen.getByText(`Paso 2 de ${TOTAL_PASOS}`)).toBeInTheDocument();

    fireEvent.keyDown(document, { key: "ArrowLeft" });
    expect(screen.getByText(`Paso 1 de ${TOTAL_PASOS}`)).toBeInTheDocument();

    // En el primer paso no hay adonde retroceder.
    fireEvent.keyDown(document, { key: "ArrowLeft" });
    expect(screen.getByText(`Paso 1 de ${TOTAL_PASOS}`)).toBeInTheDocument();
  });

  it("en el primer paso no deja retroceder y ofrece seguir", () => {
    abrirDesdeElBoton();

    expect(screen.getByRole("button", { name: /Anterior/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Siguiente/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Listo" })).toBeNull();
  });

  it("en el ultimo paso no ofrece seguir y cierra con Listo", () => {
    abrirDesdeElBoton();

    irAlPaso(TOTAL_PASOS);
    expect(screen.getByText(`Paso ${TOTAL_PASOS} de ${TOTAL_PASOS}`)).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Siguiente/i })).toBeNull();
    expect(screen.getByRole("button", { name: /Anterior/i })).toBeEnabled();

    fireEvent.click(screen.getByRole("button", { name: "Listo" }));
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("se puede cerrar a la mitad y vuelve a empezar desde el principio", () => {
    abrirDesdeElBoton();

    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    expect(screen.getByText(`Paso 3 de ${TOTAL_PASOS}`)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(screen.queryByRole("dialog")).toBeNull();

    fireEvent.click(screen.getByRole("button", { name: /Tutorial/i }));
    expect(screen.getByText(`Paso 1 de ${TOTAL_PASOS}`)).toBeInTheDocument();
  });

  it("la tecla Escape lo cierra sin llegarle a la ficha", () => {
    abrirDesdeElBoton();
    // La ficha escucha Escape en document (fase de burbuja). Si el recorrido no
    // corta la propagacion, una sola tecla cierra los dos.
    const otro = vi.fn();
    document.addEventListener("keydown", otro);

    fireEvent.keyDown(document.body, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(otro).not.toHaveBeenCalled();

    document.removeEventListener("keydown", otro);
  });

  it("destaca el elemento real de la pantalla en cada paso", () => {
    const kpis = document.createElement("div");
    kpis.setAttribute("data-tour", "kpis");
    kpis.getBoundingClientRect = () =>
      ({ top: 200, left: 100, width: 500, height: 60, right: 600, bottom: 260, x: 100, y: 200, toJSON: () => ({}) }) as DOMRect;
    document.body.appendChild(kpis);
    try {
      abrirDesdeElBoton();
      irAlPaso(2);

      // El recorte envuelve al elemento con 8 px de aire por lado.
      const recorte = screen.getByTestId("recorrido-recorte");
      expect(recorte).toHaveAttribute("x", "92");
      expect(recorte).toHaveAttribute("y", "192");
      expect(recorte).toHaveAttribute("width", "516");
      expect(recorte).toHaveAttribute("height", "76");
    } finally {
      kpis.remove();
    }
  });

  it("en los pasos de la ficha la abre, no la reabre entre ellos, y la cierra al salir", () => {
    const abrirFicha = vi.fn(() => true);
    const cerrarFicha = vi.fn();
    abrirDesdeElBoton({ acciones: { abrirFicha, cerrarFicha } });

    irAlPaso(PASO_FICHA);
    expect(abrirFicha).toHaveBeenCalledTimes(1);
    expect(cerrarFicha).not.toHaveBeenCalled();

    // Los tres pasos siguientes tambien son de la ficha: la misma queda abierta.
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    expect(abrirFicha).toHaveBeenCalledTimes(1);

    // Volver a la tabla la cierra.
    irAlPaso(PASO_FICHA - 1);
    expect(cerrarFicha).toHaveBeenCalledTimes(1);

    // Entrar de nuevo la vuelve a abrir, y cerrar el recorrido ahi la cierra.
    irAlPaso(PASO_FICHA);
    expect(abrirFicha).toHaveBeenCalledTimes(2);
    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(cerrarFicha).toHaveBeenCalledTimes(2);
  });

  it("si no hay producto para la ficha lo dice, y no intenta cerrar nada", () => {
    vi.useFakeTimers();
    const cerrarFicha = vi.fn();
    abrirDesdeElBoton({ acciones: { abrirFicha: () => false, cerrarFicha } });

    irAlPaso(PASO_FICHA);
    darPorPerdidoElElemento();
    expect(screen.getByText(/No hay productos en la lista para abrir una ficha/)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: "Cerrar" }));
    expect(cerrarFicha).not.toHaveBeenCalled();
  });

  it("cuando el boton no esta en pantalla explica por que, en vez de apuntar al vacio", () => {
    vi.useFakeTimers();
    abrirDesdeElBoton();

    irAlPaso(PASO_RECALCULAR);
    expect(screen.getByText("Recalcular")).toBeInTheDocument();
    darPorPerdidoElElemento();
    expect(screen.getByText(/puede ver la lista pero no editarla/)).toBeInTheDocument();
    expect(screen.queryByTestId("recorrido-recorte")).toBeNull();
  });
});
