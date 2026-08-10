/**
 * La celda de "Meses con venta".
 *
 * Antes decia "3/6/12", que en el caso mas comun —un repuesto que se vende todos
 * los meses— sale identico al encabezado de la columna: el comprador no puede
 * saber si lee el titulo o el dato.
 */
import "@testing-library/jest-dom/vitest";
import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { FrecuenciaVenta, lecturaFrecuencia } from "@/components/frecuencia-venta";

describe("lecturaFrecuencia", () => {
  it("avisa cuando se vendia y dejo de venderse", () => {
    // Lo que los tres numeros crudos escondian: 12m alto, 3m en cero.
    expect(lecturaFrecuencia(0, 8)).toEqual({
      texto: "sin venta hace 3 meses",
      alerta: true,
    });
  });

  it("no confunde 'esporadico' con 'dejo de venderse'", () => {
    // 2 de 12 con cero en los ultimos 3 es su ritmo normal, no una caida.
    expect(lecturaFrecuencia(0, 2)?.alerta).toBeFalsy();
  });

  it("marca el que se mueve todos los meses", () => {
    expect(lecturaFrecuencia(3, 12)?.texto).toBe("se vende casi todos los meses");
  });

  it("marca el esporadico", () => {
    expect(lecturaFrecuencia(1, 2)?.texto).toBe("esporádico");
  });

  it("no dice nada del caso intermedio", () => {
    expect(lecturaFrecuencia(2, 7)).toBeNull();
  });

  it("un repuesto sin ventas no cuenta como caida", () => {
    expect(lecturaFrecuencia(0, 0)).toBeNull();
  });
});

describe("FrecuenciaVenta", () => {
  it("muestra el denominador, que es lo que faltaba", () => {
    render(<FrecuenciaVenta meses3={3} meses6={6} meses12={12} />);
    expect(screen.getByText("12")).toBeInTheDocument();
    expect(screen.getByText("/12")).toBeInTheDocument();
  });

  it("el valor ya no se puede confundir con el encabezado", () => {
    const { container } = render(<FrecuenciaVenta meses3={3} meses6={6} meses12={12} />);
    expect(container.textContent).not.toContain("3/6/12");
  });

  it("los tres numeros siguen disponibles en el tooltip", () => {
    const { container } = render(<FrecuenciaVenta meses3={1} meses6={4} meses12={9} />);
    expect(container.querySelector("[title]")?.getAttribute("title")).toBe(
      "Meses con venta: 1 de los últimos 3, 4 de 6, 9 de 12"
    );
  });

  it("sin dato local pero con venta en otra sucursal, lo dice", () => {
    render(
      <FrecuenciaVenta
        meses3={null}
        meses6={null}
        meses12={null}
        otraSucursal={{ nombre_sucursal: "CURICO", meses_con_venta_12m: 7 }}
      />
    );
    expect(screen.getByText(/CURICO 7\/12/)).toBeInTheDocument();
  });

  it("sin dato en ninguna parte, un guion", () => {
    render(<FrecuenciaVenta meses3={null} meses6={null} meses12={null} />);
    expect(screen.getByText("—")).toBeInTheDocument();
  });
});
