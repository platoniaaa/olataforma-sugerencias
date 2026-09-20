/**
 * Clic derecho sobre una fila de la lista de precios.
 *
 * AG Grid Community no trae menu contextual (es de la version paga), asi que se
 * dibuja uno propio. Lo que importa cuidar:
 *
 * 1. "Sacar de la lista" aparece SOLO si el usuario puede editar. Ofrecerlo y que
 *    el backend responda 403 seria un boton que miente.
 * 2. El menu se cierra con Escape y con un clic afuera: uno que queda colgado
 *    sobre otra fila es la forma mas facil de borrar el producto equivocado.
 * 3. La accion recibe LA fila sobre la que se hizo clic derecho, no la ultima
 *    seleccionada.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { TablaPrecios } from "@/components/tabla-precios";
import type { PrecioRow } from "@/lib/types";

function fila(producto: string): PrecioRow {
  return {
    producto, glosa: "AMORTIGUADOR", rubro: "17", tipo: "Liviano",
    procedencia_final: "Nacional", factor: 1.78, costo: 1000, stock: 3,
    precio_erp: 1800, precio_final: 1780, estado: "OK", cambios_pendientes: 0,
  } as unknown as PrecioRow;
}

const COLS = ["producto", "glosa", "estado"];

async function abrirMenuSobre(producto: string) {
  const celda = await screen.findByText(producto);
  fireEvent.contextMenu(celda, { clientX: 100, clientY: 100 });
  return screen.findByRole("menu");
}

describe("menu contextual de la fila", () => {
  it("con permiso de edicion ofrece abrir la ficha y sacar de la lista", async () => {
    const onEliminar = vi.fn();
    render(<TablaPrecios rows={[fila("17 A"), fila("17 B")]} columnasVisibles={COLS}
                         onFila={vi.fn()} onEliminar={onEliminar} />);

    const menu = await abrirMenuSobre("17 B");

    expect(menu).toHaveTextContent("17 B");
    expect(screen.getByRole("menuitem", { name: /Abrir ficha/ })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("menuitem", { name: /Sacar de la lista/ }));
    expect(onEliminar).toHaveBeenCalledTimes(1);
    expect(onEliminar.mock.calls[0][0].producto).toBe("17 B");
    // Se cierra solo despues de elegir.
    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
  });

  it("sin permiso de edicion no ofrece sacar de la lista", async () => {
    render(<TablaPrecios rows={[fila("17 A")]} columnasVisibles={COLS} onFila={vi.fn()} />);

    await abrirMenuSobre("17 A");

    expect(screen.getByRole("menuitem", { name: /Abrir ficha/ })).toBeInTheDocument();
    expect(screen.queryByRole("menuitem", { name: /Sacar de la lista/ })).toBeNull();
  });

  it("Escape lo cierra sin hacer nada", async () => {
    const onEliminar = vi.fn();
    render(<TablaPrecios rows={[fila("17 A")]} columnasVisibles={COLS}
                         onFila={vi.fn()} onEliminar={onEliminar} />);
    await abrirMenuSobre("17 A");

    fireEvent.keyDown(window, { key: "Escape" });

    await waitFor(() => expect(screen.queryByRole("menu")).toBeNull());
    expect(onEliminar).not.toHaveBeenCalled();
  });

  it("abrir ficha abre la fila correcta", async () => {
    const onFila = vi.fn();
    render(<TablaPrecios rows={[fila("17 A"), fila("17 B")]} columnasVisibles={COLS}
                         onFila={onFila} />);
    await abrirMenuSobre("17 A");

    fireEvent.click(screen.getByRole("menuitem", { name: /Abrir ficha/ }));

    expect(onFila).toHaveBeenCalledTimes(1);
    expect(onFila.mock.calls[0][0].producto).toBe("17 A");
  });
});
