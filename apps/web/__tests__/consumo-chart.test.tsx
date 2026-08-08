/**
 * Un repuesto sin ninguna venta caia igual a la serie nacional y dibujaba doce
 * barras de altura cero: un recuadro en blanco con los meses abajo. El comprador
 * lo lee como "no cargo la vista", no como "este repuesto no se vende". Pasó en
 * produccion con `13  BG5X2K351DANL` (requerimiento #2, Linderos, 07-08-2026).
 *
 * Encima el subtitulo prometia "se muestra la venta nacional" cuando la nacional
 * tambien era cero.
 */
import "@testing-library/jest-dom/vitest";
import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { ConsumoChart } from "@/components/consumo-chart";

const MESES = [
  "202508", "202509", "202510", "202511", "202512", "202601",
  "202602", "202603", "202604", "202605", "202606", "202607",
];

const serie = (suc: number[], nac: number[]) =>
  MESES.map((periodo, i) => ({ periodo, sucursal: suc[i], nacional: nac[i] }));

const ceros = () => new Array(12).fill(0);

describe("ConsumoChart", () => {
  it("sin ventas en ninguna parte lo dice con palabras, no con un grafico vacio", () => {
    const { container } = render(
      <ConsumoChart datos={serie(ceros(), ceros())} nombreSucursal="Linderos" />
    );

    expect(
      screen.getByText(/Sin ventas en los últimos 12 meses/i)
    ).toBeInTheDocument();
    // Nada de barras: doce ceros no son un grafico.
    expect(container.querySelector("svg")).toBeNull();
    // Y no puede prometer una serie nacional que tampoco existe.
    expect(screen.queryByText(/Se muestra la venta nacional/i)).toBeNull();
  });

  it("sin venta local pero con venta nacional si cae a la serie nacional", () => {
    const nac = ceros();
    nac[3] = 12;
    const { container } = render(
      <ConsumoChart datos={serie(ceros(), nac)} nombreSucursal="Linderos" />
    );

    expect(screen.getByText(/Se muestra la venta nacional/i)).toBeInTheDocument();
    expect(container.querySelector("svg")).not.toBeNull();
    expect(screen.getByText(/toda la empresa/i)).toBeInTheDocument();
  });

  it("con venta local grafica la sucursal y no la nacional", () => {
    const suc = ceros();
    suc[5] = 4;
    const nac = ceros();
    nac[5] = 40;
    render(<ConsumoChart datos={serie(suc, nac)} nombreSucursal="Linderos" />);

    expect(screen.getByText(/Consumo mensual · Linderos/i)).toBeInTheDocument();
    expect(screen.queryByText(/Se muestra la venta nacional/i)).toBeNull();
  });

  it("sin historico cargado avisa que no hay datos, que no es lo mismo que cero", () => {
    render(<ConsumoChart datos={[]} nombreSucursal="Linderos" />);
    expect(
      screen.getByText(/No hay histórico de ventas cargado/i)
    ).toBeInTheDocument();
  });
});
