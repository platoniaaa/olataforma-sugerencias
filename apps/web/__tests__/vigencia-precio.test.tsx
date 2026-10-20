/**
 * La sección «Vigencia» de la ficha: Desde, Hasta (incluido), atajos y línea resumen.
 *
 * Es controlada (no habla con la API), así que se prueba con un arnés que guarda las fechas
 * como lo hace la ficha. Lo que importa cuidar: cada campo alcanzable por su etiqueta, el error
 * junto al campo que lo causa (aria-invalid + aria-describedby, no solo color), los atajos
 * cuentan desde hoy -o desde el Desde si es futuro-, y sin permiso o sin decisión todo queda
 * deshabilitado y dice por qué.
 */
import "@testing-library/jest-dom/vitest";
import { useState } from "react";
import { fireEvent, render, screen, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { VigenciaPrecio } from "@/components/vigencia-precio";
import { validarPeriodo, type ErroresPeriodo, type Periodo, type ResumenVigencia } from "@/lib/vigencia";

const HOY = "2026-10-20";
const SIN_ERRORES: ErroresPeriodo = { desde: null, hasta: null, aviso: null };

function Arnes({ inicial = { desde: "", hasta: "" }, habilitado = true, motivoBloqueo = null, errores, resumen = null }: {
  inicial?: Periodo; habilitado?: boolean; motivoBloqueo?: string | null;
  errores?: ErroresPeriodo; resumen?: ResumenVigencia | null;
}) {
  const [p, setP] = useState(inicial);
  return (
    <VigenciaPrecio
      desde={p.desde} hasta={p.hasta} hoy={HOY}
      onCambiar={(campo, valor) => setP((a) => ({ ...a, [campo]: valor }))}
      habilitado={habilitado} motivoBloqueo={motivoBloqueo}
      errores={errores ?? validarPeriodo(p, HOY, { desdeTocado: true, hastaTocado: true })}
      resumen={resumen}
    />
  );
}

const desde = () => screen.getByLabelText("Desde") as HTMLInputElement;
const hasta = () => screen.getByLabelText("Hasta (incluido)") as HTMLInputElement;
const atajoBtn = (nombre: string) => screen.getByRole("button", { name: nombre });

describe("VigenciaPrecio: los campos", () => {
  it("«Desde» y «Hasta (incluido)» se alcanzan por su etiqueta y son selectores de fecha", () => {
    render(<Arnes />);

    expect(desde()).toHaveAttribute("type", "date");
    expect(hasta()).toHaveAttribute("type", "date");
    expect(screen.getByRole("group", { name: /Vigencia/ })).toBeInTheDocument();
  });

  it("explica para qué sirve y deja la ayuda de cada campo enlazada, no dentro de la etiqueta", () => {
    render(<Arnes />);

    expect(screen.getByText(/Vale para el precio fijo, el margen fijo o el congelado/)).toBeInTheDocument();
    expect(screen.getByText("Vacío: desde que guardes")).toBeInTheDocument();
    expect(screen.getByText(/Último día en que rige/)).toBeInTheDocument();
    // La etiqueta es corta: el nombre del campo no arrastra el texto de ayuda.
    expect(desde()).toHaveAccessibleName("Desde");
    expect(hasta()).toHaveAccessibleName("Hasta (incluido)");
    expect(desde()).toHaveAccessibleDescription("Vacío: desde que guardes");
  });

  it("escribir una fecha avisa el cambio con el campo que se tocó", () => {
    const onCambiar = vi.fn();
    render(
      <VigenciaPrecio desde="" hasta="" hoy={HOY} onCambiar={onCambiar} habilitado
                      errores={SIN_ERRORES} resumen={null} />,
    );

    fireEvent.change(hasta(), { target: { value: "2026-11-30" } });
    fireEvent.change(desde(), { target: { value: "2026-11-05" } });

    expect(onCambiar).toHaveBeenNthCalledWith(1, "hasta", "2026-11-30");
    expect(onCambiar).toHaveBeenNthCalledWith(2, "desde", "2026-11-05");
  });

  it("trae las fechas que le pasan", () => {
    render(<Arnes inicial={{ desde: "2026-11-05", hasta: "2026-11-30" }} />);

    expect(desde().value).toBe("2026-11-05");
    expect(hasta().value).toBe("2026-11-30");
  });
});

describe("VigenciaPrecio: los atajos", () => {
  it("«30 días» escribe hoy + 30 y queda marcado (aria-pressed)", () => {
    render(<Arnes />);
    expect(atajoBtn("30 días")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(atajoBtn("30 días"));

    expect(hasta().value).toBe("2026-11-19");
    expect(atajoBtn("30 días")).toHaveAttribute("aria-pressed", "true");
    expect(atajoBtn("60 días")).toHaveAttribute("aria-pressed", "false");
  });

  it("60 y 90 días, y fin de mes", () => {
    render(<Arnes />);

    fireEvent.click(atajoBtn("60 días"));
    expect(hasta().value).toBe("2026-12-19");
    fireEvent.click(atajoBtn("90 días"));
    expect(hasta().value).toBe("2027-01-18");
    fireEvent.click(atajoBtn("Fin de mes"));
    expect(hasta().value).toBe("2026-10-31");
  });

  it("con un Desde futuro cuentan desde el Desde", () => {
    render(<Arnes inicial={{ desde: "2026-11-05", hasta: "" }} />);

    fireEvent.click(atajoBtn("30 días"));
    expect(hasta().value).toBe("2026-12-05");
    fireEvent.click(atajoBtn("Fin de mes"));
    expect(hasta().value).toBe("2026-11-30");
  });

  it("«Sin vencimiento» vacía el Hasta; está marcado cuando no hay Hasta", () => {
    render(<Arnes />);
    expect(atajoBtn("Sin vencimiento")).toHaveAttribute("aria-pressed", "true");

    fireEvent.click(atajoBtn("90 días"));
    expect(atajoBtn("Sin vencimiento")).toHaveAttribute("aria-pressed", "false");

    fireEvent.click(atajoBtn("Sin vencimiento"));
    expect(hasta().value).toBe("");
    expect(atajoBtn("Sin vencimiento")).toHaveAttribute("aria-pressed", "true");
  });

  it("lo marcado se deduce de la fecha: escribirla a mano también marca el atajo", () => {
    render(<Arnes />);

    fireEvent.change(hasta(), { target: { value: "2026-11-19" } });
    expect(atajoBtn("30 días")).toHaveAttribute("aria-pressed", "true");

    fireEvent.change(hasta(), { target: { value: "2026-11-20" } });
    expect(atajoBtn("30 días")).toHaveAttribute("aria-pressed", "false");
  });

  it("cada atajo dice en su title la fecha que daría", () => {
    render(<Arnes />);

    expect(atajoBtn("30 días")).toHaveAttribute("title", "Hasta el 19-11-2026");
    expect(atajoBtn("Fin de mes")).toHaveAttribute("title", "Hasta el 31-10-2026");
    expect(atajoBtn("Sin vencimiento")).toHaveAttribute("title", "Sin fecha de término");
  });

  it("anuncia el Hasta que quedó, porque el foco no se mueve", () => {
    const { container } = render(<Arnes />);

    fireEvent.click(atajoBtn("30 días"));

    const viva = container.querySelector('span.sr-only[aria-live="polite"]');
    expect(viva).toHaveTextContent("Hasta: 19-11-2026");
  });

  it("son botones simples: no envían ningún formulario", () => {
    const alEnviar = vi.fn((e: { preventDefault: () => void }) => e.preventDefault());
    render(<form onSubmit={alEnviar}><Arnes /></form>);

    for (const nombre of ["30 días", "60 días", "90 días", "Fin de mes", "Sin vencimiento"]) {
      expect(atajoBtn(nombre)).toHaveAttribute("type", "button");
      fireEvent.click(atajoBtn(nombre));
    }
    expect(alEnviar).not.toHaveBeenCalled();
  });
});

describe("VigenciaPrecio: los errores", () => {
  it("un Hasta antes del Desde marca solo el Hasta, con el mensaje enlazado y un ícono", () => {
    render(<Arnes inicial={{ desde: "2026-11-05", hasta: "2026-11-01" }} />);

    expect(hasta()).toHaveAttribute("aria-invalid", "true");
    expect(desde()).not.toHaveAttribute("aria-invalid");
    const mensaje = "El Hasta no puede ser antes del Desde (05-11-2026).";
    expect(hasta()).toHaveAccessibleDescription(expect.stringContaining(mensaje));
    // Palabras junto al campo, no solo el borde rojo.
    const texto = screen.getByText(mensaje);
    expect(texto.closest("p")?.querySelector("svg")).not.toBeNull();
  });

  it("un error en el Desde marca solo el Desde", () => {
    render(<Arnes errores={{ desde: "Escribe una fecha válida, por ejemplo 30-11-2026.", hasta: null, aviso: null }} />);

    expect(desde()).toHaveAttribute("aria-invalid", "true");
    expect(hasta()).not.toHaveAttribute("aria-invalid");
    expect(desde()).toHaveAccessibleDescription(expect.stringContaining("Escribe una fecha válida"));
  });

  it("sin errores ningún campo está marcado como inválido", () => {
    render(<Arnes inicial={{ desde: "2026-11-05", hasta: "2026-11-30" }} />);

    expect(desde()).not.toHaveAttribute("aria-invalid");
    expect(hasta()).not.toHaveAttribute("aria-invalid");
  });

  it("un Hasta vencido que vino del servidor y nadie tocó no es un error", () => {
    render(<Arnes inicial={{ desde: "", hasta: "2026-10-12" }} errores={SIN_ERRORES} />);

    expect(hasta().value).toBe("2026-10-12");
    expect(hasta()).not.toHaveAttribute("aria-invalid");
  });

  it("un aviso (fecha muy lejana) no bloquea ni marca el campo como inválido", () => {
    render(<Arnes inicial={{ desde: "", hasta: "2027-12-01" }} errores={{ desde: null, hasta: null, aviso: "¿Seguro? Es dentro de más de un año." }} />);

    expect(screen.getByText("¿Seguro? Es dentro de más de un año.")).toBeInTheDocument();
    expect(hasta()).not.toHaveAttribute("aria-invalid");
    expect(hasta()).toHaveAccessibleDescription(expect.stringContaining("Es dentro de más de un año"));
  });
});

describe("VigenciaPrecio: deshabilitada", () => {
  it("sin decisión a la que ponerle fecha: todo deshabilitado y dice por qué", () => {
    const motivo = "Primero fija un precio, un margen o congela el precio: las fechas valen para eso.";
    render(<Arnes habilitado={false} motivoBloqueo={motivo} />);

    expect(desde()).toBeDisabled();
    expect(hasta()).toBeDisabled();
    for (const nombre of ["30 días", "60 días", "90 días", "Fin de mes", "Sin vencimiento"]) {
      expect(atajoBtn(nombre)).toBeDisabled();
    }
    expect(screen.getByText(motivo)).toBeInTheDocument();
    expect(screen.getByRole("group", { name: /Vigencia/ })).toHaveAccessibleDescription(expect.stringContaining(motivo));
  });

  it("habilitada no muestra ese mensaje", () => {
    render(<Arnes motivoBloqueo="Primero fija un precio, un margen o congela el precio: las fechas valen para eso." />);

    expect(desde()).toBeEnabled();
    expect(hasta()).toBeEnabled();
    expect(atajoBtn("30 días")).toBeEnabled();
    expect(screen.queryByText(/Primero fija un precio/)).not.toBeInTheDocument();
  });

  it("sin permiso se ven las fechas pero no se pueden tocar", () => {
    render(<Arnes inicial={{ desde: "", hasta: "2026-11-30" }} habilitado={false} />);

    expect(hasta().value).toBe("2026-11-30");
    expect(hasta()).toBeDisabled();
    expect(atajoBtn("30 días")).toBeDisabled();
  });
});

describe("VigenciaPrecio: la línea resumen", () => {
  it("muestra lo que le pasan, en una región que se anuncia sola", () => {
    const resumen: ResumenVigencia = {
      texto: "Rige hoy y hasta el 30-11-2026 incluido. El 01-12-2026 vuelve a la regla.",
      vencimiento: "Al vencer pasaría de $12.990 a $11.000 (−15 %).", fuerte: false,
    };
    render(<Arnes resumen={resumen} />);

    const linea = screen.getByText(/Rige hoy y hasta el 30-11-2026 incluido/).closest("p") as HTMLElement;
    expect(linea).toHaveAttribute("aria-live", "polite");
    expect(within(linea).getByText("Al vencer pasaría de $12.990 a $11.000 (−15 %).")).toBeInTheDocument();
  });

  it("un salto grande se destaca con ícono y negrita, además de la palabra", () => {
    const resumen: ResumenVigencia = {
      texto: "Rige hoy y hasta el 30-11-2026 incluido. El 01-12-2026 vuelve a la regla.",
      vencimiento: "Al vencer el precio baja de $12.990 a $10.450 (−20 %).", fuerte: true,
    };
    render(<Arnes resumen={resumen} />);

    const destacado = screen.getByText(/Al vencer el precio baja de/);
    expect(destacado.className).toContain("font-semibold");
    expect(destacado.querySelector("svg")).not.toBeNull();
  });

  it("sin resumen no dibuja la línea", () => {
    const { container } = render(<Arnes resumen={null} />);

    expect(container.querySelector("p[aria-live]")).toBeNull();
  });
});
