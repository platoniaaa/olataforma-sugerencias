/**
 * La ficha del producto (lista de precios): prueba de caracterizacion.
 *
 * La ficha vivia dentro de app/precios/page.tsx y no tenia ni una prueba. Estas
 * pruebas congelan lo que hace HOY -antes de moverla a components/ficha-precio.tsx
 * y de agregarle el periodo (Desde / Hasta)- para que la extraccion no cambie nada
 * sin que alguien se entere:
 *
 * 1. Muestra el precio final, su estado y la cuenta que lo dio.
 * 2. Guardar manda los siete campos, tal como estan en el formulario.
 * 3. «Volver a la regla» y «Sacar de la lista» piden confirmacion y llaman a su endpoint.
 * 4. Un error del servidor se ve en la ficha, no se pierde.
 * 5. Sin permiso se puede mirar pero no tocar.
 *
 * Y la vigencia (Desde / Hasta del precio fijo, el margen fijo y el congelado): el chip, la
 * explicacion cuando la decision NO rige, lo que viaja al guardar (las fechas solo si
 * cambiaron), los errores junto al campo y el desglose del stock por bodega.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ModalProducto, explicacionMargen } from "@/components/ficha-precio";
import { formatoCLP } from "@/lib/formato";
import type { PrecioDetalle } from "@/lib/types";

const mocks = vi.hoisted(() => ({
  detalle: vi.fn(),
  guardar: vi.fn(),
  quitar: vi.fn(),
  sacar: vi.fn(),
}));

vi.mock("@/lib/api-client", () => ({
  api: {
    precioDetalle: mocks.detalle,
    guardarPrecioOverride: mocks.guardar,
    quitarPrecioOverride: mocks.quitar,
    eliminarPrecioProducto: mocks.sacar,
  },
}));

const CODIGO = "71 2720142";

/** Un producto que sigue la regla: ninguna decision a mano. */
const SIN_DECISION: PrecioDetalle = {
  producto: CODIGO, glosa: "AMORTIGUADOR DELANTERO", rubro: "71",
  tipo: "Liviano", tipo_origen: "rubro",
  procedencia_maestro: "Nacional", procedencia_final: "Nacional", procedencia_origen: "compras",
  factor: 1.8, costo: 10000, precio_erp: 17000, stock: 5, stock_transito: 2,
  ult_recep_importado: null, ult_pe_nacional: "2026-09-15", ultima_venta: "2026-10-01",
  precio_sugerido: null, precio_calculado: 18000, precio_final: 18000,
  estado: "OK", cambios_pendientes: 0, origen: "maestro",
  desviacion_pesos: 1000, desviacion_pct: 5.9,
  precio_fijo: null, margen_fijo: null, congelar: false, congelado_precio: null,
  no_producto: false, obs: null, tipo_manual: null, procedencia_manual: null,
  editado_por: null, editado_en: null, actualizado_en: "2026-10-20T08:00:00Z",
  cambios: [], envios: [],
};

/** El mismo producto con las siete decisiones puestas. */
const CON_DECISION: PrecioDetalle = {
  ...SIN_DECISION,
  tipo: "Sugerido", tipo_origen: "manual", tipo_manual: "Sugerido",
  procedencia_final: "Importado", procedencia_origen: "manual", procedencia_manual: "Importado",
  precio_fijo: 15000, margen_fijo: 40, congelar: true, congelado_precio: 14000,
  no_producto: false, obs: "Promocion de octubre",
  precio_final: 15000, estado: "FIJO",
  editado_por: "compras@curifor.cl", editado_en: "2026-10-10T15:30:00Z",
};

let confirmar: ReturnType<typeof vi.fn>;

beforeEach(() => {
  mocks.detalle.mockReset().mockResolvedValue(SIN_DECISION);
  mocks.guardar.mockReset().mockResolvedValue({});
  mocks.quitar.mockReset().mockResolvedValue({});
  mocks.sacar.mockReset().mockResolvedValue({ eliminados: 1, overrides_conservados: 0 });
  confirmar = vi.fn().mockReturnValue(true);
  vi.stubGlobal("confirm", confirmar);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

async function abrir(
  detalle: PrecioDetalle = SIN_DECISION,
  extra: Partial<{ puedeEditar: boolean; onCerrar: () => void; onGuardado: () => Promise<void>; hoy: string }> = {},
) {
  mocks.detalle.mockResolvedValue(detalle);
  const props = {
    onCerrar: vi.fn(),
    onGuardado: vi.fn().mockResolvedValue(undefined),
    ...extra,
  };
  const vista = render(
    <ModalProducto
      producto={CODIGO}
      puedeEditar={extra.puedeEditar ?? true}
      tipos={["Liviano", "Pesado", "Sugerido"]}
      onCerrar={props.onCerrar}
      onGuardado={props.onGuardado}
      hoy={extra.hoy}
    />,
  );
  // La ficha pide el detalle al abrirse: hasta que llega solo dice «Cargando…».
  await screen.findByText("Precio final");
  return { ...vista, ...props };
}

const precioFijo = () => screen.getByPlaceholderText(/^Precio fijo/) as HTMLInputElement;
const margenFijo = () => screen.getByPlaceholderText(/^Margen fijo/) as HTMLInputElement;
const observacion = () => screen.getByPlaceholderText(/Por qué este precio/) as HTMLTextAreaElement;
const congelar = () => screen.getByRole("checkbox", { name: /Congelar el precio actual/ }) as HTMLInputElement;
const noProducto = () => screen.getByRole("checkbox", { name: /No es un producto/ }) as HTMLInputElement;
const tipoManual = () => screen.getAllByRole("combobox")[0] as HTMLSelectElement;
const procedenciaManual = () => screen.getAllByRole("combobox")[1] as HTMLSelectElement;
const boton = (nombre: RegExp | string) => screen.getByRole("button", { name: nombre });

describe("Ficha: lo que muestra", () => {
  it("pide el detalle del producto y muestra el codigo y la glosa", async () => {
    await abrir();

    expect(mocks.detalle).toHaveBeenCalledWith(CODIGO);
    expect(screen.getByRole("dialog", { name: CODIGO })).toBeInTheDocument();
    expect(screen.getByText("AMORTIGUADOR DELANTERO")).toBeInTheDocument();
  });

  it("mientras llega el detalle dice «Cargando…» y no muestra el formulario", () => {
    mocks.detalle.mockReturnValue(new Promise(() => {}));
    render(
      <ModalProducto producto={CODIGO} puedeEditar tipos={[]} onCerrar={vi.fn()} onGuardado={vi.fn()} />,
    );

    expect(screen.getByText("Cargando…")).toBeInTheDocument();
    expect(screen.queryByText("Precio final")).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Guardar" })).not.toBeInTheDocument();
  });

  it("el precio final va primero, con su estado y la cuenta que lo dio", async () => {
    const { container } = await abrir();

    const cabecera = container.querySelector('[data-tour="ficha-precio"]') as HTMLElement;
    expect(cabecera).not.toBeNull();
    const dentro = within(cabecera);
    expect(dentro.getByText("Precio final")).toBeInTheDocument();
    expect(dentro.getByText(formatoCLP(18000))).toBeInTheDocument();
    expect(dentro.getByText("OK")).toBeInTheDocument();
    // La cuenta: costo x factor = precio calculado.
    expect(dentro.getByText(`${formatoCLP(10000)} × 1,80 = ${formatoCLP(18000)}`)).toBeInTheDocument();
    expect(dentro.getByText("Precio en el ERP hoy")).toBeInTheDocument();
    expect(dentro.getByText(formatoCLP(17000))).toBeInTheDocument();
    expect(dentro.getByText("+5,9% vs. el nuevo")).toBeInTheDocument();
  });

  it("un precio fijo lo dice: estado FIJO y «Precio fijo puesto a mano»", async () => {
    const { container } = await abrir(CON_DECISION);

    const cabecera = within(container.querySelector('[data-tour="ficha-precio"]') as HTMLElement);
    expect(cabecera.getByText(formatoCLP(15000))).toBeInTheDocument();
    expect(cabecera.getByText("FIJO")).toBeInTheDocument();
    expect(cabecera.getByText("Precio fijo puesto a mano")).toBeInTheDocument();
  });

  it("deja las tres paradas del recorrido guiado del tutorial", async () => {
    const { container } = await abrir();

    for (const parada of ["ficha-precio", "ficha-origen", "ficha-decision"]) {
      expect(container.querySelector(`[data-tour="${parada}"]`)).not.toBeNull();
    }
  });

  it("«De dónde sale»: cada dato con su origen, y el margen fijo en el factor", async () => {
    const { container } = await abrir(CON_DECISION);

    const origen = within(container.querySelector('[data-tour="ficha-origen"]') as HTMLElement);
    // Lo decidido a mano se rotula «manual»; lo que pone la regla, con su origen.
    expect(origen.getByText("Sugerido").nextSibling?.textContent).toBe("manual");
    expect(origen.getByText("Importado").nextSibling?.textContent).toBe("manual");
    expect(origen.getByText("margen 40,0 %")).toBeInTheDocument();
    expect(origen.getByText("71")).toBeInTheDocument();
    expect(origen.getByText(formatoCLP(10000))).toBeInTheDocument();
    expect(origen.getByText("5 / 2")).toBeInTheDocument();
    expect(origen.getByText("01-10-2026")).toBeInTheDocument();
  });

  it("el origen de lo que sigue a la regla no se rotula como manual", async () => {
    const { container } = await abrir();

    const origen = within(container.querySelector('[data-tour="ficha-origen"]') as HTMLElement);
    const etiqueta = origen.getByText("rubro");
    expect(etiqueta.className).toContain("bg-ink-100");
    expect(etiqueta.className).not.toContain("bg-brand-50");
    expect(origen.queryByText("manual")).not.toBeInTheDocument();
  });

  it("los cambios detectados van plegados y avisan los que nadie ha revisado", async () => {
    await abrir({
      ...SIN_DECISION,
      cambios: [
        { campo: "costo", antes: "9000", despues: "10000", visto: false, detectado_en: "2026-10-18T12:00:00Z" },
        { campo: "factor", antes: "1.7", despues: "1.8", visto: true, detectado_en: "2026-10-01T12:00:00Z" },
      ],
    });

    const resumen = screen.getByText(/Cambios detectados \(2\)/);
    expect(resumen.closest("details")).not.toHaveAttribute("open");
    expect(within(resumen).getByText("sin revisar")).toBeInTheDocument();
    expect(screen.getByText(/costo/, { selector: "b" })).toBeInTheDocument();
  });

  it("sin cambios detectados no muestra el historial", async () => {
    await abrir();

    expect(screen.queryByText(/Cambios detectados/)).not.toBeInTheDocument();
  });

  it("dice cuando fue el ultimo envio al ERP y quien lo hizo", async () => {
    await abrir({
      ...SIN_DECISION,
      envios: [{ precio: 16500, costo: 9500, lote_id: "L1", enviado_en: "2026-10-12T12:00:00Z", enviado_por: "ana" }],
    });

    expect(screen.getByText(`Último envío al ERP: ${formatoCLP(16500)} el 12-10-2026 por ana`)).toBeInTheDocument();
  });
});

describe("Ficha: guardar", () => {
  it("manda los siete campos tal como estan en el formulario", async () => {
    const { onGuardado } = await abrir();

    fireEvent.change(precioFijo(), { target: { value: "15000" } });
    fireEvent.change(margenFijo(), { target: { value: "35.5" } });
    fireEvent.click(congelar());
    fireEvent.change(tipoManual(), { target: { value: "Sugerido" } });
    fireEvent.change(procedenciaManual(), { target: { value: "Importado" } });
    fireEvent.click(noProducto());
    fireEvent.change(observacion(), { target: { value: "Promocion de octubre" } });
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(mocks.guardar).toHaveBeenCalledTimes(1);
    expect(mocks.guardar).toHaveBeenCalledWith(CODIGO, {
      precio_fijo: 15000,
      margen_fijo: 35.5,
      congelar: true,
      tipo_manual: "Sugerido",
      procedencia_manual: "Importado",
      no_producto: true,
      obs: "Promocion de octubre",
    });
  });

  it("lo vacio viaja como null (sigue la regla) y los casilleros apagados como false", async () => {
    const { onGuardado } = await abrir();

    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(mocks.guardar).toHaveBeenCalledWith(CODIGO, {
      precio_fijo: null,
      margen_fijo: null,
      congelar: false,
      tipo_manual: null,
      procedencia_manual: null,
      no_producto: false,
      obs: null,
    });
  });

  it("al abrir, el formulario trae lo ya decidido, y guardar sin tocar lo reenvia igual", async () => {
    const { onGuardado } = await abrir(CON_DECISION);

    expect(precioFijo().value).toBe("15000");
    expect(margenFijo().value).toBe("40");
    expect(congelar().checked).toBe(true);
    expect(tipoManual().value).toBe("Sugerido");
    expect(procedenciaManual().value).toBe("Importado");
    expect(noProducto().checked).toBe(false);
    expect(observacion().value).toBe("Promocion de octubre");

    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(mocks.guardar).toHaveBeenCalledWith(CODIGO, {
      precio_fijo: 15000,
      margen_fijo: 40,
      congelar: true,
      tipo_manual: "Sugerido",
      procedencia_manual: "Importado",
      no_producto: false,
      obs: "Promocion de octubre",
    });
  });

  it("borrar el precio fijo lo manda como null", async () => {
    const { onGuardado } = await abrir(CON_DECISION);

    fireEvent.change(precioFijo(), { target: { value: "" } });
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(mocks.guardar.mock.calls[0][1].precio_fijo).toBeNull();
  });

  it("despues de guardar vuelve a pedir el detalle y avisa a la lista", async () => {
    const { onGuardado, onCerrar } = await abrir();
    expect(mocks.detalle).toHaveBeenCalledTimes(1);

    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(mocks.detalle).toHaveBeenCalledTimes(2);
    // Guardar no cierra la ficha: se queda para ver el resultado.
    expect(onCerrar).not.toHaveBeenCalled();
    expect(screen.getByRole("button", { name: "Guardar" })).toBeEnabled();
  });

  it("el error del servidor se muestra en la ficha y no avisa a la lista", async () => {
    mocks.guardar.mockRejectedValue(new Error("El precio fijo no puede ser negativo"));
    const { onGuardado } = await abrir();

    fireEvent.click(boton("Guardar"));

    expect(await screen.findByText("El precio fijo no puede ser negativo")).toBeInTheDocument();
    expect(onGuardado).not.toHaveBeenCalled();
    // Y se puede volver a intentar.
    expect(screen.getByRole("button", { name: "Guardar" })).toBeEnabled();
  });

  it("si lo que falla no trae mensaje, dice «No se pudo guardar.»", async () => {
    mocks.guardar.mockRejectedValue("cayo");
    await abrir();

    fireEvent.click(boton("Guardar"));

    expect(await screen.findByText("No se pudo guardar.")).toBeInTheDocument();
  });

  it("un error anterior se borra al volver a guardar", async () => {
    mocks.guardar.mockRejectedValueOnce(new Error("Sin conexion"));
    const { onGuardado } = await abrir();

    fireEvent.click(boton("Guardar"));
    expect(await screen.findByText("Sin conexion")).toBeInTheDocument();

    fireEvent.click(boton("Guardar"));
    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(screen.queryByText("Sin conexion")).not.toBeInTheDocument();
  });
});

describe("Ficha: volver a la regla", () => {
  it("el boton solo aparece si hay alguna decision a mano", async () => {
    const { unmount } = await abrir(SIN_DECISION);
    expect(screen.queryByRole("button", { name: "Volver a la regla" })).not.toBeInTheDocument();
    unmount();

    await abrir(CON_DECISION);
    expect(screen.getByRole("button", { name: "Volver a la regla" })).toBeInTheDocument();
  });

  it("basta una observacion para que aparezca", async () => {
    await abrir({ ...SIN_DECISION, obs: "revisar con el proveedor" });

    expect(screen.getByRole("button", { name: "Volver a la regla" })).toBeInTheDocument();
  });

  it("pide confirmacion con el codigo y, si se acepta, quita la decision y refresca", async () => {
    const { onGuardado } = await abrir(CON_DECISION);

    fireEvent.click(boton("Volver a la regla"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(confirmar).toHaveBeenCalledWith(expect.stringContaining(CODIGO));
    expect(mocks.quitar).toHaveBeenCalledWith(CODIGO);
    // Vuelve a pedir el detalle: la ficha muestra lo que quedo.
    expect(mocks.detalle).toHaveBeenCalledTimes(2);
    expect(mocks.guardar).not.toHaveBeenCalled();
  });

  it("si no se confirma, no toca nada", async () => {
    confirmar.mockReturnValue(false);
    const { onGuardado } = await abrir(CON_DECISION);

    fireEvent.click(boton("Volver a la regla"));

    expect(confirmar).toHaveBeenCalledTimes(1);
    expect(mocks.quitar).not.toHaveBeenCalled();
    expect(onGuardado).not.toHaveBeenCalled();
  });

  it("si el servidor falla, lo dice", async () => {
    mocks.quitar.mockRejectedValue(new Error("No se pudo volver a la regla (503)"));
    const { onGuardado } = await abrir(CON_DECISION);

    fireEvent.click(boton("Volver a la regla"));

    expect(await screen.findByText("No se pudo volver a la regla (503)")).toBeInTheDocument();
    expect(onGuardado).not.toHaveBeenCalled();
  });
});

describe("Ficha: sacar de la lista", () => {
  it("avisa que NO lo da de baja en el ERP y, si se acepta, lo saca, refresca y cierra", async () => {
    const { onGuardado, onCerrar } = await abrir();

    fireEvent.click(boton("Sacar de la lista"));

    await waitFor(() => expect(onCerrar).toHaveBeenCalledTimes(1));
    const texto = confirmar.mock.calls[0][0] as string;
    expect(texto).toContain(CODIGO);
    expect(texto).toContain("NO lo da de baja en el ERP");
    expect(mocks.sacar).toHaveBeenCalledWith(CODIGO);
    expect(onGuardado).toHaveBeenCalledTimes(1);
  });

  it("si no se confirma, el producto sigue en la lista", async () => {
    confirmar.mockReturnValue(false);
    const { onGuardado, onCerrar } = await abrir();

    fireEvent.click(boton("Sacar de la lista"));

    expect(mocks.sacar).not.toHaveBeenCalled();
    expect(onGuardado).not.toHaveBeenCalled();
    expect(onCerrar).not.toHaveBeenCalled();
  });

  it("si el servidor falla, lo dice, no cierra y no deja la ficha bloqueada", async () => {
    mocks.sacar.mockRejectedValue(new Error("No se pudo sacar de la lista"));
    const { onCerrar } = await abrir();

    fireEvent.click(boton("Sacar de la lista"));

    expect(await screen.findByText("No se pudo sacar de la lista")).toBeInTheDocument();
    expect(onCerrar).not.toHaveBeenCalled();
  });
});

describe("Ficha: sin permiso para editar", () => {
  it("se puede mirar pero no tocar: avisa y no hay botones de accion", async () => {
    await abrir(CON_DECISION, { puedeEditar: false });

    expect(screen.getByText("Tu usuario puede ver la lista pero no editarla.")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Guardar" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Volver a la regla" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Sacar de la lista" })).not.toBeInTheDocument();
    for (const campo of [precioFijo(), margenFijo(), congelar(), noProducto(), observacion(), tipoManual(), procedenciaManual()]) {
      expect(campo).toBeDisabled();
    }
    // Lo decidido sigue a la vista.
    expect(precioFijo().value).toBe("15000");
  });

  it("con permiso no muestra el aviso y los campos se pueden editar", async () => {
    await abrir();

    expect(screen.queryByText(/puede ver la lista pero no editarla/)).not.toBeInTheDocument();
    expect(precioFijo()).toBeEnabled();
    expect(observacion()).toBeEnabled();
  });
});

describe("Ficha: el selector de tipo", () => {
  it("ofrece «(según regla)» y los tipos que le pasa la lista", async () => {
    await abrir();

    const opciones = within(tipoManual()).getAllByRole("option").map((o) => o.textContent);
    expect(opciones).toEqual(["(según regla)", "Liviano", "Pesado", "Sugerido"]);
  });

  it("la procedencia ofrece Nacional e Importado", async () => {
    await abrir();

    const opciones = within(procedenciaManual()).getAllByRole("option").map((o) => o.textContent);
    expect(opciones).toEqual(["(según regla)", "Nacional", "Importado"]);
  });
});

describe("explicacionMargen: lo que se lee bajo el campo", () => {
  it("vacio: explica que el precio sigue al costo", () => {
    expect(explicacionMargen("", 10000)).toBe("Sobre la venta. El precio sigue al costo; sin stock queda en $0.");
    expect(explicacionMargen("   ", 10000)).toBe("Sobre la venta. El precio sigue al costo; sin stock queda en $0.");
  });

  it("con costo: dice el factor y el precio que resulta hoy", () => {
    expect(explicacionMargen("35", 10000)).toBe(
      `Factor 1,54 → ${formatoCLP(15385)} con el costo de hoy. Sin stock queda en $0.`,
    );
  });

  it("acepta la coma decimal", () => {
    expect(explicacionMargen("35,5", 10000)).toBe(explicacionMargen("35.5", 10000));
  });

  it("sin costo cargado dice solo el factor", () => {
    expect(explicacionMargen("35", null)).toBe("Factor 1,54. Sin stock queda en $0.");
    expect(explicacionMargen("35", 0)).toBe("Factor 1,54. Sin stock queda en $0.");
  });

  it("fuera de 0 a 100 avisa en vez de calcular", () => {
    for (const malo of ["0", "-5", "100", "150", "abc"]) {
      expect(explicacionMargen(malo, 10000)).toBe("El margen tiene que estar entre 0 y 100.");
    }
  });

  it("la ficha la muestra bajo el campo mientras se escribe", async () => {
    await abrir();
    expect(screen.getByText("Sobre la venta. El precio sigue al costo; sin stock queda en $0.")).toBeInTheDocument();

    fireEvent.change(margenFijo(), { target: { value: "50" } });

    expect(screen.getByText(`Factor 2,00 → ${formatoCLP(20000)} con el costo de hoy. Sin stock queda en $0.`)).toBeInTheDocument();
  });
});

// ------------------------------------------------------------------ vigencia

const HOY = "2026-10-20";

/** Precio fijo que rige hasta el 30-11. La regla daria $18.000. */
const FIJO_VIGENTE: PrecioDetalle = {
  ...SIN_DECISION,
  precio_fijo: 15000, precio_final: 15000, estado: "FIJO",
  vigente_desde: null, vigente_hasta: "2026-11-30", vigencia: "vigente", vigencia_dias: 41, precio_regla: 18000,
  editado_por: "compras@curifor.cl", editado_en: "2026-10-10T15:30:00Z",
};

/** Precio fijo guardado que empieza el 05-11: hoy el producto sigue la regla. */
const FIJO_PROGRAMADO: PrecioDetalle = {
  ...SIN_DECISION,
  precio_fijo: 15000, margen_fijo: null,
  vigente_desde: "2026-11-05", vigente_hasta: "2026-11-30", vigencia: "programada", vigencia_dias: 16,
};

/** Precio fijo que venció el 12-10: sigue guardado, pero el precio ya es el de la regla. */
const FIJO_VENCIDO: PrecioDetalle = {
  ...SIN_DECISION,
  precio_fijo: 15000,
  vigente_desde: null, vigente_hasta: "2026-10-12", vigencia: "vencida", vigencia_dias: 8,
};

const hastaCampo = () => screen.getByLabelText("Hasta (incluido)") as HTMLInputElement;
const desdeCampo = () => screen.getByLabelText("Desde") as HTMLInputElement;
const enviado = () => mocks.guardar.mock.calls[0][1] as Record<string, unknown>;

describe("Ficha: el chip y la explicacion segun la vigencia", () => {
  it("un precio fijo que rige muestra el chip y hasta cuando", async () => {
    const { container } = await abrir(FIJO_VIGENTE, { hoy: HOY });

    const cabecera = within(container.querySelector('[data-tour="ficha-precio"]') as HTMLElement);
    expect(cabecera.getByText("FIJO")).toBeInTheDocument();
    expect(cabecera.getByTestId("chip-vigencia")).toHaveTextContent("Fijo hasta 30-11");
    expect(cabecera.getByText("Precio fijo puesto a mano · hasta el 30-11")).toBeInTheDocument();
  });

  it("sin periodo no hay chip y la explicacion es la de siempre", async () => {
    const { container } = await abrir(CON_DECISION, { hoy: HOY });

    const cabecera = container.querySelector('[data-tour="ficha-precio"]') as HTMLElement;
    expect(within(cabecera).queryByTestId("chip-vigencia")).not.toBeInTheDocument();
    expect(within(cabecera).getByText("Precio fijo puesto a mano")).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Renovar" })).not.toBeInTheDocument();
  });

  it("programado: NO dice «Precio fijo puesto a mano»: explica la regla y cuando empieza", async () => {
    const { container } = await abrir(FIJO_PROGRAMADO, { hoy: HOY });

    const cabecera = within(container.querySelector('[data-tour="ficha-precio"]') as HTMLElement);
    expect(cabecera.queryByText(/Precio fijo puesto a mano/)).not.toBeInTheDocument();
    expect(cabecera.getByText(
      `Hoy sigue la regla: ${formatoCLP(10000)} × 1,80 = ${formatoCLP(18000)}. El precio fijo de ${formatoCLP(15000)} empieza el 05-11.`,
    )).toBeInTheDocument();
    // El estado es el de lo que rige hoy, no FIJO.
    expect(cabecera.getByText("OK")).toBeInTheDocument();
    expect(cabecera.getByText(formatoCLP(18000))).toBeInTheDocument();
    expect(cabecera.getByTestId("chip-vigencia")).toHaveTextContent("Programado desde 05-11");
  });

  it("vencido: dice que volvio a la regla y que la decision sigue guardada", async () => {
    const { container } = await abrir(FIJO_VENCIDO, { hoy: HOY });

    const cabecera = within(container.querySelector('[data-tour="ficha-precio"]') as HTMLElement);
    expect(cabecera.queryByText(/Precio fijo puesto a mano/)).not.toBeInTheDocument();
    expect(cabecera.getByText(
      `Venció el 12-10: volvió a la regla (${formatoCLP(10000)} × 1,80 = ${formatoCLP(18000)}). El precio fijo de ${formatoCLP(15000)} sigue guardado.`,
    )).toBeInTheDocument();
    expect(cabecera.getByTestId("chip-vigencia")).toHaveTextContent("Vencido 12-10");
  });

  it("el margen fijo solo se rotula en el factor si rige hoy", async () => {
    const margen = { ...SIN_DECISION, margen_fijo: 40, vigente_desde: null, vigente_hasta: "2026-11-30", vigencia_dias: 41 };
    const { container, unmount } = await abrir({ ...margen, vigencia: "vigente" }, { hoy: HOY });
    expect(within(container.querySelector('[data-tour="ficha-origen"]') as HTMLElement).getByText("margen 40,0 %")).toBeInTheDocument();
    unmount();

    const otra = await abrir({ ...margen, vigencia: "vencida", vigente_hasta: "2026-10-12" }, { hoy: HOY });
    expect(within(otra.container.querySelector('[data-tour="ficha-origen"]') as HTMLElement).queryByText(/margen 40/)).not.toBeInTheDocument();
  });

  it("vencido: «Renovar» lleva el foco al Hasta y «Volver a la regla» sigue ahi", async () => {
    await abrir(FIJO_VENCIDO, { hoy: HOY });

    expect(screen.getByRole("button", { name: "Volver a la regla" })).toBeInTheDocument();
    fireEvent.click(boton("Renovar"));

    expect(hastaCampo()).toHaveFocus();
    expect(mocks.guardar).not.toHaveBeenCalled();
  });

  it("«Renovar» solo aparece si esta vencido", async () => {
    for (const detalle of [FIJO_VIGENTE, FIJO_PROGRAMADO, SIN_DECISION]) {
      const { unmount } = await abrir(detalle, { hoy: HOY });
      expect(screen.queryByRole("button", { name: "Renovar" })).not.toBeInTheDocument();
      unmount();
    }
  });
});

describe("Ficha: la seccion Vigencia", () => {
  it("esta dentro de la decision, con las fechas que trae el producto", async () => {
    const { container } = await abrir(FIJO_PROGRAMADO, { hoy: HOY });

    const decision = container.querySelector('[data-tour="ficha-decision"]') as HTMLElement;
    expect(within(decision).getByRole("group", { name: /Vigencia/ })).toBeInTheDocument();
    expect(desdeCampo().value).toBe("2026-11-05");
    expect(hastaCampo().value).toBe("2026-11-30");
  });

  it("sin ninguna decision esta deshabilitada y dice por que; al fijar un precio se habilita", async () => {
    await abrir(SIN_DECISION, { hoy: HOY });

    expect(desdeCampo()).toBeDisabled();
    expect(screen.getByText(/Primero fija un precio, un margen o congela el precio/)).toBeInTheDocument();

    fireEvent.change(precioFijo(), { target: { value: "15000" } });

    expect(desdeCampo()).toBeEnabled();
    expect(hastaCampo()).toBeEnabled();
    expect(screen.queryByText(/Primero fija un precio/)).not.toBeInTheDocument();
  });

  it("congelar tambien habilita las fechas, y el margen", async () => {
    const { unmount } = await abrir(SIN_DECISION, { hoy: HOY });
    fireEvent.click(congelar());
    expect(hastaCampo()).toBeEnabled();
    unmount();

    await abrir(SIN_DECISION, { hoy: HOY });
    fireEvent.change(margenFijo(), { target: { value: "35" } });
    expect(hastaCampo()).toBeEnabled();
  });

  it("sin permiso se ven las fechas pero no se tocan", async () => {
    await abrir(FIJO_VIGENTE, { puedeEditar: false, hoy: HOY });

    expect(hastaCampo().value).toBe("2026-11-30");
    expect(hastaCampo()).toBeDisabled();
    expect(desdeCampo()).toBeDisabled();
    expect(screen.getByRole("button", { name: "30 días" })).toBeDisabled();
    // Y el chip sigue a la vista.
    expect(screen.getAllByTestId("chip-vigencia").length).toBeGreaterThan(0);
  });

  it("los atajos cuentan desde el «hoy» del servidor, no desde el reloj del navegador", async () => {
    await abrir(SIN_DECISION, { hoy: "2026-03-10" });
    fireEvent.change(precioFijo(), { target: { value: "15000" } });

    fireEvent.click(boton("30 días"));

    expect(hastaCampo().value).toBe("2026-04-09");
  });

  it("la linea viva explica al vencer a que precio vuelve, usando el precio de la regla", async () => {
    // 15.000 -> 12.000 es -20 %: se destaca con la palabra «baja».
    await abrir({ ...FIJO_VIGENTE, precio_regla: 12000 }, { hoy: HOY });

    expect(screen.getByText(/Rige hoy y hasta el 30-11-2026 incluido\. El 01-12-2026 vuelve a la regla\./)).toBeInTheDocument();
    expect(screen.getByText(`Al vencer el precio baja de ${formatoCLP(15000)} a ${formatoCLP(12000)} (−20 %).`)).toBeInTheDocument();
  });

  it("si la regla da mas, dice «sube»", async () => {
    await abrir(FIJO_VIGENTE, { hoy: HOY });

    expect(screen.getByText(`Al vencer el precio sube de ${formatoCLP(15000)} a ${formatoCLP(18000)} (+20 %).`)).toBeInTheDocument();
  });

  it("cambiar las fechas antepone «Al guardar:» a la linea", async () => {
    await abrir(FIJO_VIGENTE, { hoy: HOY });

    fireEvent.change(hastaCampo(), { target: { value: "2026-12-15" } });

    expect(screen.getByText(/^Al guardar: rige hoy y hasta el 15-12-2026 incluido/)).toBeInTheDocument();
  });

  it("al desmarcar todas las decisiones avisa que se borran las fechas", async () => {
    await abrir(FIJO_VIGENTE, { hoy: HOY });

    fireEvent.change(precioFijo(), { target: { value: "" } });

    expect(screen.getByText(/Al guardar se borran las fechas/)).toBeInTheDocument();
    expect(hastaCampo()).toBeDisabled();
  });
});

describe("Ficha: guardar con vigencia", () => {
  it("sin tocar las fechas NO las manda (una API sin vigencia las rechazaria)", async () => {
    const { onGuardado } = await abrir(FIJO_VIGENTE, { hoy: HOY });

    fireEvent.change(observacion(), { target: { value: "revisado" } });
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(enviado()).toEqual({
      precio_fijo: 15000, margen_fijo: null, congelar: false,
      tipo_manual: null, procedencia_manual: null, no_producto: false, obs: "revisado",
    });
    expect(enviado()).not.toHaveProperty("vigente_desde");
    expect(enviado()).not.toHaveProperty("vigente_hasta");
  });

  it("un producto sin periodo tampoco las manda", async () => {
    const { onGuardado } = await abrir(SIN_DECISION, { hoy: HOY });

    fireEvent.change(precioFijo(), { target: { value: "15000" } });
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(Object.keys(enviado()).sort()).toEqual(
      ["congelar", "margen_fijo", "no_producto", "obs", "precio_fijo", "procedencia_manual", "tipo_manual"],
    );
  });

  it("con un Hasta nuevo manda solo el Hasta", async () => {
    const { onGuardado } = await abrir(SIN_DECISION, { hoy: HOY });

    fireEvent.change(precioFijo(), { target: { value: "15000" } });
    fireEvent.change(hastaCampo(), { target: { value: "2026-11-30" } });
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(enviado().precio_fijo).toBe(15000);
    expect(enviado().vigente_hasta).toBe("2026-11-30");
    expect(enviado()).not.toHaveProperty("vigente_desde");
  });

  it("con Desde y Hasta manda los dos", async () => {
    const { onGuardado } = await abrir(SIN_DECISION, { hoy: HOY });

    fireEvent.change(precioFijo(), { target: { value: "15000" } });
    fireEvent.change(desdeCampo(), { target: { value: "2026-11-05" } });
    fireEvent.change(hastaCampo(), { target: { value: "2026-11-30" } });
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(enviado().vigente_desde).toBe("2026-11-05");
    expect(enviado().vigente_hasta).toBe("2026-11-30");
  });

  it("«Sin vencimiento» manda el Hasta como null (quita ese lado)", async () => {
    const { onGuardado } = await abrir(FIJO_VIGENTE, { hoy: HOY });

    fireEvent.click(boton("Sin vencimiento"));
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(enviado().vigente_hasta).toBeNull();
    expect(enviado()).not.toHaveProperty("vigente_desde");
  });

  it("renovar un vencido: un Hasta nuevo en el mismo guardado", async () => {
    const { onGuardado } = await abrir(FIJO_VENCIDO, { hoy: HOY });

    fireEvent.click(boton("60 días"));
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(enviado().vigente_hasta).toBe("2026-12-19");
    expect(enviado().precio_fijo).toBe(15000);
  });

  it("vaciar precio fijo, margen y congelar manda las dos fechas en null", async () => {
    const conDesde = { ...FIJO_VIGENTE, vigente_desde: "2026-10-01" };
    const { onGuardado } = await abrir(conDesde, { hoy: HOY });

    fireEvent.change(precioFijo(), { target: { value: "" } });
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(enviado().precio_fijo).toBeNull();
    expect(enviado().vigente_desde).toBeNull();
    expect(enviado().vigente_hasta).toBeNull();
  });

  it("un vencido sin tocar se puede seguir editando (la observacion) sin renovar", async () => {
    const { onGuardado } = await abrir(FIJO_VENCIDO, { hoy: HOY });

    fireEvent.change(observacion(), { target: { value: "ya no aplica" } });
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(enviado().obs).toBe("ya no aplica");
    expect(enviado()).not.toHaveProperty("vigente_hasta");
  });
});

describe("Ficha: si el detalle no carga", () => {
  it("dice el error con un boton Reintentar en vez de quedarse en Cargando", async () => {
    mocks.detalle.mockRejectedValueOnce(new Error("El servidor no responde."));
    render(
      <ModalProducto producto={CODIGO} puedeEditar tipos={["Liviano"]} onCerrar={vi.fn()}
                     onGuardado={vi.fn().mockResolvedValue(undefined)} hoy={HOY} />,
    );

    const aviso = await screen.findByRole("alert");
    expect(aviso).toHaveTextContent("El servidor no responde.");
    expect(screen.queryByText("Cargando…")).not.toBeInTheDocument();

    mocks.detalle.mockResolvedValue(SIN_DECISION);
    fireEvent.click(screen.getByRole("button", { name: "Reintentar" }));

    expect(await screen.findByText("Precio final")).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });
});

describe("Ficha: errores de la vigencia", () => {
  it("Hasta antes del Desde: no llama a la API, dice el error junto al campo y enfoca el Hasta", async () => {
    const { onGuardado } = await abrir(SIN_DECISION, { hoy: HOY });
    fireEvent.change(precioFijo(), { target: { value: "15000" } });
    fireEvent.change(desdeCampo(), { target: { value: "2026-11-05" } });
    fireEvent.change(hastaCampo(), { target: { value: "2026-11-01" } });

    // El error se ve apenas se escribe, antes de guardar.
    expect(screen.getByText("El Hasta no puede ser antes del Desde (05-11-2026).")).toBeInTheDocument();
    expect(hastaCampo()).toHaveAttribute("aria-invalid", "true");
    expect(desdeCampo()).not.toHaveAttribute("aria-invalid");

    fireEvent.click(boton("Guardar"));

    expect(mocks.guardar).not.toHaveBeenCalled();
    expect(onGuardado).not.toHaveBeenCalled();
    expect(hastaCampo()).toHaveFocus();
  });

  it("un Hasta que ya paso, escrito por la persona, no se guarda", async () => {
    await abrir(SIN_DECISION, { hoy: HOY });
    fireEvent.change(precioFijo(), { target: { value: "15000" } });
    fireEvent.change(hastaCampo(), { target: { value: "2026-10-12" } });

    expect(screen.getByText(/Ese Hasta ya pasó \(12-10-2026\)/)).toBeInTheDocument();
    fireEvent.click(boton("Guardar"));

    expect(mocks.guardar).not.toHaveBeenCalled();
    expect(hastaCampo()).toHaveFocus();
  });

  it("un Hasta vencido que vino del servidor y nadie toco NO es un error", async () => {
    await abrir(FIJO_VENCIDO, { hoy: HOY });

    expect(hastaCampo()).not.toHaveAttribute("aria-invalid");
    expect(screen.queryByText(/Ese Hasta ya pasó/)).not.toBeInTheDocument();
    // Lo que si dice es que ya vencio y como seguir.
    expect(screen.getByText(/Venció el 12-10-2026 y hoy sigue la regla/)).toBeInTheDocument();
  });

  it("tocar el Desde de un vencido y devolverlo a lo guardado no cuenta como cambio", async () => {
    // La API compara contra lo guardado: si el valor vuelve a ser el mismo, no rechaza.
    await abrir(FIJO_VENCIDO, { hoy: HOY });

    fireEvent.change(desdeCampo(), { target: { value: "2026-10-01" } });
    fireEvent.change(desdeCampo(), { target: { value: "" } });

    expect(screen.queryByText(/Ese Hasta ya pasó/)).not.toBeInTheDocument();
    expect(hastaCampo()).not.toHaveAttribute("aria-invalid");
  });

  it("cambiar el precio de un vencido sin renovar el Hasta se rechaza antes de ir al servidor", async () => {
    await abrir(FIJO_VENCIDO, { hoy: HOY });

    fireEvent.change(precioFijo(), { target: { value: "14000" } });
    fireEvent.click(boton("Guardar"));

    expect(mocks.guardar).not.toHaveBeenCalled();
    expect(hastaCampo()).toHaveFocus();
    expect(hastaCampo()).toHaveAttribute("aria-invalid", "true");
  });

  it("congelar con un Desde futuro: el error esta en el Desde y manda a usar precio fijo", async () => {
    await abrir(SIN_DECISION, { hoy: HOY });
    fireEvent.click(congelar());
    fireEvent.change(desdeCampo(), { target: { value: "2026-11-05" } });

    expect(screen.getByText(/Congelar toma el precio de hoy/)).toBeInTheDocument();
    expect(desdeCampo()).toHaveAttribute("aria-invalid", "true");
    fireEvent.click(boton("Guardar"));

    expect(mocks.guardar).not.toHaveBeenCalled();
    expect(desdeCampo()).toHaveFocus();
  });

  it("corregido el error, guarda", async () => {
    const { onGuardado } = await abrir(SIN_DECISION, { hoy: HOY });
    fireEvent.change(precioFijo(), { target: { value: "15000" } });
    fireEvent.change(hastaCampo(), { target: { value: "2026-10-12" } });
    fireEvent.click(boton("Guardar"));
    expect(mocks.guardar).not.toHaveBeenCalled();

    fireEvent.change(hastaCampo(), { target: { value: "2026-11-30" } });
    fireEvent.click(boton("Guardar"));

    await waitFor(() => expect(onGuardado).toHaveBeenCalledTimes(1));
    expect(enviado().vigente_hasta).toBe("2026-11-30");
  });

  it("un rechazo del servidor se anuncia como alerta, con su mensaje", async () => {
    mocks.guardar.mockRejectedValue(new Error("El periodo ya terminó (Hasta 12-10-2026): pon un Hasta de hoy en adelante o déjalo sin vencimiento."));
    await abrir(FIJO_VIGENTE, { hoy: HOY });

    fireEvent.click(boton("Guardar"));

    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent("El periodo ya terminó (Hasta 12-10-2026)");
  });
});

describe("Ficha: rotulos de precio fijo y margen fijo", () => {
  it("tienen rotulo visible y accesible, no solo placeholder", async () => {
    await abrir(SIN_DECISION, { hoy: HOY });

    expect(screen.getByLabelText("Precio fijo ($)")).toBe(precioFijo());
    expect(screen.getByLabelText("Margen fijo (% sobre la venta)")).toBe(margenFijo());
    // La ayuda va enlazada, no dentro de la etiqueta: el nombre del campo es solo su rotulo.
    expect(precioFijo()).toHaveAccessibleDescription("Gana a todo, incluso sin stock.");
    expect(margenFijo()).toHaveAccessibleDescription(/Sobre la venta/);
  });
});

describe("Ficha: stock por bodega", () => {
  const BODEGAS = [
    { bodega: "BODEGA CENTRAL", stock: 30, cuenta: true },
    { bodega: "PE X REGULARIZAR", stock: 4, cuenta: true },
    { bodega: "BODEGA DAÑADOS", stock: 5, cuenta: false },
  ];

  it("lo que no cuenta va tachado Y rotulado, y el desglose se abre solo", async () => {
    await abrir({ ...SIN_DECISION, stock_bodegas: BODEGAS }, { hoy: HOY });

    const resumen = screen.getByText(/Stock por bodega \(3\)/);
    expect(resumen.closest("details")).toHaveAttribute("open");
    expect(within(resumen).getByText("1 no cuenta")).toBeInTheDocument();
    const danados = screen.getByText("BODEGA DAÑADOS");
    expect(danados.className).toContain("line-through");
    expect(danados.nextSibling?.textContent).toBe("no cuenta");
    // Las que cuentan, sin tachar.
    expect(screen.getByText("BODEGA CENTRAL").className).not.toContain("line-through");
    expect(screen.getAllByText("no cuenta")).toHaveLength(1);
  });

  it("si todas cuentan queda plegado y sin aviso", async () => {
    await abrir({ ...SIN_DECISION, stock_bodegas: BODEGAS.slice(0, 2) }, { hoy: HOY });

    const resumen = screen.getByText(/Stock por bodega \(2\)/);
    expect(resumen.closest("details")).not.toHaveAttribute("open");
    expect(screen.queryByText(/no cuenta/)).not.toBeInTheDocument();
  });

  it("varias que no cuentan: lo dice en plural", async () => {
    await abrir({ ...SIN_DECISION, stock_bodegas: [BODEGAS[0], { bodega: "BODEGA SCRAP", stock: 2, cuenta: false }, BODEGAS[2]] }, { hoy: HOY });

    expect(screen.getByText("2 no cuentan")).toBeInTheDocument();
  });

  it("sin desglose (una API anterior o sin stock) no dibuja nada", async () => {
    await abrir(SIN_DECISION, { hoy: HOY });
    expect(screen.queryByText(/Stock por bodega/)).not.toBeInTheDocument();
  });
});
