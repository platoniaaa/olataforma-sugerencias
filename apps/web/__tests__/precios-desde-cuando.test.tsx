/**
 * "Solo diferencias" tiene que decir DESDE CUANDO son esas diferencias.
 *
 * El boton mostraba un numero suelto -2.041- y nada mas. Quien lo ve por primera
 * vez no tiene como saber si son las de hoy, las de la semana o las de siempre,
 * y la respuesta importa: son las acumuladas desde la ultima vez que alguien
 * bajo ese mismo archivo. Sin la fecha, el numero obliga a preguntar.
 */
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ResumenDiferencias } from "@/components/resumen-diferencias";

describe("Desde cuando son las diferencias", () => {
  it("dice la fecha de la ultima descarga", () => {
    render(<ResumenDiferencias pendientes={2041} ultimoEnvio="2026-10-02T17:11:00Z" />);

    const texto = screen.getByTestId("desde-cuando").textContent ?? "";
    expect(texto).toMatch(/2\.041/);
    expect(texto).toMatch(/02-10-2026/);
    // Dicho en lo que la persona hizo, no en jerga del sistema.
    expect(texto).toMatch(/desde la última descarga/i);
  });

  it("cuando nunca se descargo, lo dice en vez de mostrar una fecha vacia", () => {
    render(<ResumenDiferencias pendientes={39471} ultimoEnvio={null} />);

    const texto = screen.getByTestId("desde-cuando").textContent ?? "";
    expect(texto).toMatch(/39\.471/);
    expect(texto).toMatch(/nunca se ha descargado/i);
    expect(texto).not.toMatch(/undefined|null|NaN/);
  });

  it("sin nada pendiente no muestra un numero en cero: avisa que esta al dia", () => {
    render(<ResumenDiferencias pendientes={0} ultimoEnvio="2026-10-02T17:11:00Z" />);

    const texto = screen.getByTestId("desde-cuando").textContent ?? "";
    expect(texto).toMatch(/al día/i);
    expect(texto).toMatch(/02-10-2026/);
  });
});
