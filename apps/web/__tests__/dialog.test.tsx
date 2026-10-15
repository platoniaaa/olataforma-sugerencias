/**
 * El fondo oscuro del dialogo lo cierra, pero la barra de desplazamiento del fondo no
 * es "el fondo": tocarla para bajar no puede cerrar el dialogo y perder lo que hay en
 * pantalla (ej. la vista previa de una carga de precios).
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Dialog } from "@/components/ui/dialog";

function abrir() {
  const onClose = vi.fn();
  render(<Dialog open onClose={onClose} title="Prueba"><p>contenido</p></Dialog>);
  const fondo = screen.getByRole("dialog");
  return { onClose, fondo };
}

/** jsdom no calcula medidas: se simula un fondo de 1000 x 600 con barra vertical de 15 px. */
function conBarra(fondo: HTMLElement) {
  Object.defineProperty(fondo, "offsetWidth", { configurable: true, value: 1000 });
  Object.defineProperty(fondo, "clientWidth", { configurable: true, value: 985 });
  Object.defineProperty(fondo, "offsetHeight", { configurable: true, value: 600 });
  Object.defineProperty(fondo, "clientHeight", { configurable: true, value: 600 });
  fondo.getBoundingClientRect = () => ({ left: 0, top: 0, right: 1000, bottom: 600, width: 1000, height: 600, x: 0, y: 0, toJSON: () => ({}) });
}

describe("cerrar con el fondo", () => {
  it("un clic en el fondo cierra", () => {
    const { onClose, fondo } = abrir();

    fireEvent.mouseDown(fondo, { clientX: 20, clientY: 20 });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("un clic dentro del panel no cierra", () => {
    const { onClose } = abrir();

    fireEvent.mouseDown(screen.getByText("contenido"));

    expect(onClose).not.toHaveBeenCalled();
  });

  it("un clic en la barra de desplazamiento no cierra", () => {
    const { onClose, fondo } = abrir();
    conBarra(fondo);

    fireEvent.mouseDown(fondo, { clientX: 992, clientY: 200 });

    expect(onClose).not.toHaveBeenCalled();
  });

  it("con barra, un clic en el fondo (a la izquierda de la barra) sigue cerrando", () => {
    const { onClose, fondo } = abrir();
    conBarra(fondo);

    fireEvent.mouseDown(fondo, { clientX: 20, clientY: 200 });

    expect(onClose).toHaveBeenCalledTimes(1);
  });

  it("Escape cierra", () => {
    const { onClose } = abrir();

    fireEvent.keyDown(document, { key: "Escape" });

    expect(onClose).toHaveBeenCalledTimes(1);
  });
});
