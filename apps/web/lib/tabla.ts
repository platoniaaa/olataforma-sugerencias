import type React from "react";

/**
 * Click en cualquier parte de la fila que navegue al detalle, sin romper lo que
 * un <a> da gratis.
 *
 * La fila entera tiene que ser clickeable —con solo el "#1" enlazado, la bandeja
 * parecia una lista muerta y nadie llegaba al detalle, que es donde se gestiona
 * la compra—. Pero un onClick pelado se lleva por delante tres cosas:
 *
 * - Ctrl/Cmd+click y el click de rueda para abrir en pestana nueva. El comprador
 *   que triajea abre varios requerimientos a la vez; eso hay que conservarlo, y
 *   por eso el "#id" sigue siendo un <a> de verdad.
 * - Arrastrar para copiar texto de la fila: al soltar disparaba la navegacion en
 *   medio de la seleccion.
 * - El click sobre algo interactivo dentro de la fila.
 */
export function filaNavegable(ir: () => void) {
  return (e: React.MouseEvent<HTMLTableRowElement>) => {
    // Con modificador se deja pasar: el navegador ya sabe que hacer con el <a>.
    if (e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || e.button !== 0) return;
    // Si el click salio de un enlace o un control, es de ellos.
    if ((e.target as HTMLElement).closest("a,button,input,select,textarea,label")) return;
    // Si el usuario estaba seleccionando texto, no navegar.
    if ((window.getSelection()?.toString() ?? "").length > 0) return;
    ir();
  };
}
