/**
 * El recorrido guiado de la lista de precios.
 *
 * Lo que se prueba aca no es el texto -ese cambia- sino el contrato de la
 * navegacion: que se pueda salir en cualquier paso, que los extremos no ofrezcan
 * un paso que no existe, y que la primera visita se abra sola una sola vez. Sin
 * lo ultimo el recorrido tapa la pantalla cada manana, que es exactamente lo que
 * hace que la gente deje de leerlo.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { beforeEach, describe, expect, it } from "vitest";

import { TutorialPrecios } from "@/components/tutorial-precios";

const TOTAL_PASOS = 13;

beforeEach(() => {
  localStorage.clear();
});

/** Lo abre desde el boton, partiendo de un navegador que ya lo vio. */
function abrirDesdeElBoton() {
  localStorage.setItem("precios_tutorial_visto", "1");
  render(<TutorialPrecios />);
  expect(screen.queryByRole("dialog")).toBeNull();
  fireEvent.click(screen.getByRole("button", { name: /Tutorial/i }));
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
    expect(screen.getByText("Cómo se calcula un precio")).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Siguiente/i }));
    expect(screen.getByText(`Paso 3 de ${TOTAL_PASOS}`)).toBeInTheDocument();

    fireEvent.click(screen.getByRole("button", { name: /Anterior/i }));
    expect(screen.getByText(`Paso 2 de ${TOTAL_PASOS}`)).toBeInTheDocument();
    expect(screen.getByText("Cómo se calcula un precio")).toBeInTheDocument();
  });

  it("en el primer paso no deja retroceder y ofrece seguir", () => {
    abrirDesdeElBoton();

    expect(screen.getByRole("button", { name: /Anterior/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /Siguiente/i })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Listo" })).toBeNull();
  });

  it("en el ultimo paso no ofrece seguir y cierra con Listo", () => {
    abrirDesdeElBoton();

    fireEvent.click(screen.getByRole("button", { name: new RegExp(`Ir al paso ${TOTAL_PASOS}:`) }));
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

  it("la tecla Escape tambien lo cierra", () => {
    abrirDesdeElBoton();

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
  });
});
