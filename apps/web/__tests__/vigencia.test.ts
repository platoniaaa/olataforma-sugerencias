/**
 * La logica pura de la vigencia (lib/vigencia.ts): fechas sin husos, atajos, validacion,
 * la etiqueta del chip y lo que se manda al guardar.
 *
 * Lo que mas importa: las fechas de calendario ("2026-11-30") NUNCA pasan por
 * `new Date("2026-11-30")` ni `toISOString()`, que las leen como UTC y en Chile corren un
 * dia. Un Hasta corrido un dia es un precio de promocion que dura un dia de mas o de menos.
 */
import { describe, expect, it } from "vitest";

import { formatoCLP } from "@/lib/formato";
import {
  armarPeriodoParaEnviar, atajo, compararVencimiento, decisionRige, diasEntre, esFechaIso, estadoDe,
  etiquetaVigencia, finDeMes, hayErrores, hoyLocal, partesFecha, resumenVigencia, sumarDias, validarPeriodo,
} from "@/lib/vigencia";

const HOY = "2026-10-20";

describe("hoyLocal", () => {
  it("es el dia del calendario local aunque ya sea mañana en UTC", () => {
    // 23:30 del 20-10 en la hora de esta maquina: en UTC puede ya ser el 21.
    expect(hoyLocal(new Date(2026, 9, 20, 23, 30))).toBe("2026-10-20");
    expect(hoyLocal(new Date(2026, 9, 20, 0, 5))).toBe("2026-10-20");
    expect(hoyLocal(new Date(2026, 11, 31, 23, 59))).toBe("2026-12-31");
  });
});

describe("fechas sobre partes", () => {
  it("sumarDias cruza mes, año y bisiesto", () => {
    expect(sumarDias("2026-10-20", 30)).toBe("2026-11-19");
    expect(sumarDias("2026-12-20", 30)).toBe("2027-01-19");
    expect(sumarDias("2028-02-28", 1)).toBe("2028-02-29");
    expect(sumarDias("2027-02-28", 1)).toBe("2027-03-01");
    expect(sumarDias("2026-10-31", 1)).toBe("2026-11-01");
    expect(sumarDias("2026-11-01", -1)).toBe("2026-10-31");
    expect(sumarDias("2026-10-20", 0)).toBe("2026-10-20");
  });

  it("un 30-11 sigue siendo 30-11 (no se corre un dia por el huso)", () => {
    expect(sumarDias("2026-11-30", 0)).toBe("2026-11-30");
    expect(sumarDias("2026-11-30", 1)).toBe("2026-12-01");
  });

  it("diasEntre cuenta dias de calendario, con signo", () => {
    expect(diasEntre("2026-10-20", "2026-10-23")).toBe(3);
    expect(diasEntre("2026-10-23", "2026-10-20")).toBe(-3);
    expect(diasEntre("2026-10-20", "2026-10-20")).toBe(0);
    expect(diasEntre("2026-12-30", "2027-01-02")).toBe(3);
  });

  it("finDeMes: el ultimo dia del mes; si ya es el ultimo, el del mes siguiente", () => {
    expect(finDeMes("2026-10-20")).toBe("2026-10-31");
    expect(finDeMes("2026-10-31")).toBe("2026-11-30");
    expect(finDeMes("2026-12-05")).toBe("2026-12-31");
    expect(finDeMes("2026-12-31")).toBe("2027-01-31");
    expect(finDeMes("2028-02-10")).toBe("2028-02-29");
    expect(finDeMes("2028-02-29")).toBe("2028-03-31");
    expect(finDeMes("2027-02-10")).toBe("2027-02-28");
  });

  it("solo acepta fechas de calendario reales aaaa-mm-dd", () => {
    expect(esFechaIso("2028-02-29")).toBe(true);
    for (const mala of ["2027-02-29", "2026-02-30", "2026-04-31", "2026-13-01", "2026-00-10", "2026-10-00",
      "2026-1-5", "30-11-2026", "", "2026-10-20T00:00:00Z"]) {
      expect(esFechaIso(mala)).toBe(false);
    }
    expect(partesFecha("2026-11-30")).toEqual({ anio: 2026, mes: 11, dia: 30 });
  });
});

describe("estadoDe", () => {
  it("sin fechas no hay estado", () => {
    expect(estadoDe({ desde: "", hasta: "" }, HOY)).toBeNull();
  });

  it("el Hasta es inclusivo: el mismo dia todavia rige y al siguiente vence", () => {
    expect(estadoDe({ desde: "", hasta: HOY }, HOY)).toBe("vigente");
    expect(estadoDe({ desde: "", hasta: "2026-10-19" }, HOY)).toBe("vencida");
  });

  it("el Desde tambien: el mismo dia ya rige y antes esta programada", () => {
    expect(estadoDe({ desde: HOY, hasta: "" }, HOY)).toBe("vigente");
    expect(estadoDe({ desde: "2026-10-21", hasta: "" }, HOY)).toBe("programada");
  });

  it("un periodo al reves nunca rige", () => {
    expect(estadoDe({ desde: "2026-11-05", hasta: "2026-11-01" }, HOY)).toBe("vencida");
  });

  it("decisionRige: programada y vencida no rigen; el resto si", () => {
    expect(decisionRige({ vigencia: "programada" })).toBe(false);
    expect(decisionRige({ vigencia: "vencida" })).toBe(false);
    expect(decisionRige({ vigencia: "vigente" })).toBe(true);
    expect(decisionRige({ vigencia: null })).toBe(true);
    expect(decisionRige({})).toBe(true);
  });
});

describe("atajo", () => {
  it("30, 60 y 90 dias desde hoy", () => {
    expect(atajo("30", "", HOY)).toBe("2026-11-19");
    expect(atajo("60", "", HOY)).toBe("2026-12-19");
    expect(atajo("90", "", HOY)).toBe("2027-01-18");
  });

  it("si el Desde es futuro, se cuenta desde el Desde", () => {
    expect(atajo("30", "2026-11-05", HOY)).toBe("2026-12-05");
    expect(atajo("mes", "2026-11-05", HOY)).toBe("2026-11-30");
  });

  it("un Desde pasado o de hoy se ignora: se cuenta desde hoy", () => {
    expect(atajo("30", "2026-10-01", HOY)).toBe("2026-11-19");
    expect(atajo("30", HOY, HOY)).toBe("2026-11-19");
  });

  it("fin de mes y sin vencimiento", () => {
    expect(atajo("mes", "", HOY)).toBe("2026-10-31");
    expect(atajo("mes", "", "2026-10-31")).toBe("2026-11-30");
    expect(atajo("sin", "2026-11-05", HOY)).toBe("");
  });
});

describe("validarPeriodo", () => {
  const valida = (p: { desde?: string; hasta?: string }, op = {}) =>
    validarPeriodo({ desde: p.desde ?? "", hasta: p.hasta ?? "" }, HOY, op);

  it("un periodo sano no tiene errores", () => {
    const e = valida({ desde: "2026-11-05", hasta: "2026-11-30" }, { desdeTocado: true, hastaTocado: true });
    expect(e).toEqual({ desde: null, hasta: null, aviso: null });
    expect(hayErrores(e)).toBe(false);
    expect(hayErrores(valida({}))).toBe(false);
  });

  it("Hasta antes del Desde: el error va en el Hasta y dice el Desde", () => {
    const e = valida({ desde: "2026-11-05", hasta: "2026-11-01" }, { hastaTocado: true });
    expect(e.hasta).toBe("El Hasta no puede ser antes del Desde (05-11-2026).");
    expect(e.desde).toBeNull();
    expect(hayErrores(e)).toBe(true);
  });

  it("un Hasta pasado que la persona toco es un error, con el camino para arreglarlo", () => {
    const e = valida({ hasta: "2026-10-12" }, { hastaTocado: true });
    expect(e.hasta).toContain("Ese Hasta ya pasó (12-10-2026)");
    expect(e.hasta).toContain("Pon un Hasta de hoy en adelante o déjalo vacío");
    expect(e.desde).toBeNull();
  });

  it("un Hasta vencido que vino del servidor y nadie toco NO es un error", () => {
    expect(hayErrores(valida({ hasta: "2026-10-12" }))).toBe(false);
    expect(hayErrores(valida({ hasta: "2026-10-12" }, { congelar: true }))).toBe(false);
  });

  it("pero si cambia la decision con el periodo vencido, hay que renovarlo en el mismo guardado", () => {
    // La API lo rechaza igual (422): mejor decirlo junto al campo que despues del clic.
    const e = valida({ hasta: "2026-10-12" }, { decisionCambiada: true });
    expect(e.hasta).toContain("Ese Hasta ya pasó");
  });

  it("hoy como Hasta esta bien: es el ultimo dia que rige", () => {
    expect(hayErrores(valida({ hasta: HOY }, { hastaTocado: true }))).toBe(false);
  });

  it("congelar toma el precio de hoy: no admite un Desde futuro (usa precio fijo)", () => {
    const e = valida({ desde: "2026-11-05" }, { congelar: true, desdeTocado: true });
    expect(e.desde).toContain("Congelar toma el precio de hoy");
    expect(e.desde).toContain("usa precio fijo");
    // Con un Desde de hoy o pasado si se puede.
    expect(hayErrores(valida({ desde: HOY }, { congelar: true, desdeTocado: true }))).toBe(false);
    expect(hayErrores(valida({ desde: "2026-11-05" }, { congelar: false, desdeTocado: true }))).toBe(false);
  });

  it("una fecha mal formada no es una fecha", () => {
    const e = valida({ hasta: "2026-02-30" }, { hastaTocado: true });
    expect(e.hasta).toBe("Escribe una fecha válida, por ejemplo 30-11-2026.");
  });

  it("a mas de tres años de hoy la API la rechaza; aca tambien, solo si la toco", () => {
    const e = valida({ hasta: "2030-01-01" }, { hastaTocado: true });
    expect(e.hasta).toBe("La fecha está a más de 3 años de hoy.");
    expect(hayErrores(valida({ hasta: "2030-01-01" }))).toBe(false);
    expect(valida({ desde: "2022-01-01" }, { desdeTocado: true }).desde).toBe("La fecha está a más de 3 años de hoy.");
    expect(hayErrores(valida({ hasta: "2029-10-20" }, { hastaTocado: true }))).toBe(false);
  });

  it("a mas de un año avisa, sin bloquear", () => {
    const e = valida({ hasta: "2027-10-22" }, { hastaTocado: true });
    expect(e.aviso).toBe("¿Seguro? Es dentro de más de un año.");
    expect(hayErrores(e)).toBe(false);
    // 366 dias exactos todavia no avisa.
    expect(valida({ hasta: "2027-10-21" }, { hastaTocado: true }).aviso).toBeNull();
  });

  it("el año a medio escribir (0002) no grita mientras se teclea, pero al guardar si", () => {
    expect(hayErrores(valida({ hasta: "0002-10-20" }, { hastaTocado: true }))).toBe(false);
    expect(valida({ hasta: "0002-10-20" }, { hastaTocado: true, estricto: true }).hasta)
      .toBe("Escribe una fecha válida, por ejemplo 30-11-2026.");
  });
});

describe("etiquetaVigencia", () => {
  const fijo = { precio_fijo: 12990, margen_fijo: null, congelar: false };

  it("fijo que vence lejos: «Fijo hasta 30-11», sin año, tono neutro", () => {
    const e = etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_hasta: "2026-11-30", vigencia_dias: 41 }, HOY);
    expect(e?.texto).toBe("Fijo hasta 30-11");
    expect(e?.tono).toBe("lejos");
    expect(e?.icono).toBe("calendario-reloj");
    // La fecha larga del title no se corre un dia.
    expect(e?.titulo).toBe("Precio fijo hasta el 30-11-2026 incluido. El 01-12-2026 vuelve a la regla.");
  });

  it("entre 2 y 7 dias suma los dias, y es «pronto»", () => {
    const e = etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_hasta: "2026-10-23", vigencia_dias: 3 }, HOY);
    expect(e?.texto).toBe("Fijo hasta 23-10 (3 días)");
    expect(e?.tono).toBe("pronto");
    expect(e?.icono).toBe("reloj-arena");
    expect(etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_hasta: "2026-10-27", vigencia_dias: 7 }, HOY)?.tono)
      .toBe("pronto");
    expect(etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_hasta: "2026-10-28", vigencia_dias: 8 }, HOY)?.tono)
      .toBe("lejos");
  });

  it("mañana y hoy se dicen con palabras", () => {
    expect(etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_hasta: "2026-10-21", vigencia_dias: 1 }, HOY)?.texto)
      .toBe("Fijo hasta mañana");
    expect(etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_hasta: HOY, vigencia_dias: 0 }, HOY)?.texto)
      .toBe("Fijo hasta hoy");
  });

  it("sin vigencia_dias del servidor los calcula con hoy", () => {
    expect(etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_hasta: "2026-10-23" }, HOY)?.texto)
      .toBe("Fijo hasta 23-10 (3 días)");
  });

  it("programada: «Programado desde 05-11»", () => {
    const e = etiquetaVigencia({ ...fijo, vigencia: "programada", vigente_desde: "2026-11-05", vigente_hasta: "2026-11-30" }, HOY);
    expect(e?.texto).toBe("Programado desde 05-11");
    expect(e?.tono).toBe("programado");
    expect(e?.icono).toBe("calendario-rango");
    expect(e?.titulo).toContain("desde el 05-11-2026 hasta el 30-11-2026");
    expect(e?.titulo).toContain("sigue la regla");
  });

  it("vencida: «Vencido 12-10»", () => {
    const e = etiquetaVigencia({ ...fijo, vigencia: "vencida", vigente_hasta: "2026-10-12", vigencia_dias: 8 }, HOY);
    expect(e?.texto).toBe("Vencido 12-10");
    expect(e?.tono).toBe("vencido");
    expect(e?.icono).toBe("calendario-x");
    expect(e?.titulo).toBe("Precio fijo vencido el 12-10-2026: el producto volvió a la regla.");
  });

  it("de otro año muestra el año", () => {
    expect(etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_hasta: "2027-01-15", vigencia_dias: 87 }, HOY)?.texto)
      .toBe("Fijo hasta 15-01-2027");
    expect(etiquetaVigencia({ ...fijo, vigencia: "vencida", vigente_hasta: "2025-12-31" }, HOY)?.texto)
      .toBe("Vencido 31-12-2025");
  });

  it("el sustantivo sale de la decision: precio fijo > congelado > margen", () => {
    const base = { vigencia: "vigente" as const, vigente_hasta: "2026-11-30", vigencia_dias: 41 };
    expect(etiquetaVigencia({ ...base, precio_fijo: 100, congelar: true, margen_fijo: 30 }, HOY)?.texto).toBe("Fijo hasta 30-11");
    expect(etiquetaVigencia({ ...base, precio_fijo: null, congelar: true, margen_fijo: 30 }, HOY)?.texto).toBe("Congelado hasta 30-11");
    expect(etiquetaVigencia({ ...base, precio_fijo: null, congelar: false, margen_fijo: 30 }, HOY)?.texto).toBe("Margen hasta 30-11");
    expect(etiquetaVigencia({ ...base, precio_fijo: null, congelar: false, margen_fijo: 30 }, HOY)?.titulo)
      .toContain("Margen fijo hasta el 30-11-2026");
  });

  it("sin periodo, o vigente sin Hasta, no hay nada que mostrar", () => {
    expect(etiquetaVigencia({ ...fijo, vigencia: null }, HOY)).toBeNull();
    expect(etiquetaVigencia({ ...fijo }, HOY)).toBeNull();
    expect(etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_desde: "2026-10-01", vigente_hasta: null }, HOY)).toBeNull();
  });

  it("nunca imprime undefined, null ni NaN", () => {
    const casos = [
      etiquetaVigencia({ ...fijo, vigencia: "vigente", vigente_hasta: "2026-10-23" }, HOY),
      etiquetaVigencia({ ...fijo, vigencia: "programada", vigente_desde: "2026-11-05" }, HOY),
      etiquetaVigencia({ ...fijo, vigencia: "vencida", vigente_hasta: null }, HOY),
    ];
    for (const e of casos) {
      expect(e).not.toBeNull();
      expect(`${e?.texto} ${e?.titulo}`).not.toMatch(/undefined|null|NaN/);
    }
  });
});

describe("armarPeriodoParaEnviar", () => {
  const vacio = { desde: "", hasta: "" };

  it("sin tocar las fechas no manda nada (una API sin vigencia rechazaria el guardado)", () => {
    expect(armarPeriodoParaEnviar(vacio, vacio, true)).toEqual({});
    const p = { desde: "2026-11-05", hasta: "2026-11-30" };
    expect(armarPeriodoParaEnviar(p, p, true)).toEqual({});
  });

  it("manda solo el extremo que cambio", () => {
    expect(armarPeriodoParaEnviar({ desde: "", hasta: "2026-11-30" }, vacio, true)).toEqual({ vigente_hasta: "2026-11-30" });
    expect(armarPeriodoParaEnviar({ desde: "2026-11-05", hasta: "2026-11-30" }, { desde: "", hasta: "2026-11-30" }, true))
      .toEqual({ vigente_desde: "2026-11-05" });
  });

  it("vaciar un extremo que tenia valor lo manda como null (quita ese lado)", () => {
    const p = { desde: "2026-11-05", hasta: "2026-11-30" };
    expect(armarPeriodoParaEnviar({ desde: "2026-11-05", hasta: "" }, p, true)).toEqual({ vigente_hasta: null });
    expect(armarPeriodoParaEnviar(vacio, p, true)).toEqual({ vigente_desde: null, vigente_hasta: null });
  });

  it("si no queda ninguna decision, las fechas se mandan vacias, pero solo si habia algo guardado", () => {
    const p = { desde: "2026-11-05", hasta: "2026-11-30" };
    expect(armarPeriodoParaEnviar(p, p, false)).toEqual({ vigente_desde: null, vigente_hasta: null });
    expect(armarPeriodoParaEnviar({ desde: "", hasta: "2026-12-01" }, { desde: "", hasta: "2026-11-30" }, false))
      .toEqual({ vigente_desde: null, vigente_hasta: null });
    expect(armarPeriodoParaEnviar(vacio, vacio, false)).toEqual({});
    // Fechas escritas sobre un producto que nunca tuvo periodo, y sin decision: no hay nada que borrar.
    expect(armarPeriodoParaEnviar({ desde: "", hasta: "2026-11-30" }, vacio, false)).toEqual({});
  });
});

describe("resumenVigencia", () => {
  const precio = (n: number) => formatoCLP(n);
  const fijo = { tipo: "fijo" as const, precio: 12990 };
  const entrada = (periodo: { desde?: string; hasta?: string }, extra = {}) => ({
    periodo: { desde: periodo.desde ?? "", hasta: periodo.hasta ?? "" },
    guardado: { desde: "", hasta: "" },
    hoy: HOY, decision: fijo, precioRegla: 10450 as number | null,
    ...extra,
  });

  it("sin ninguna decision y sin fechas no dice nada; con fechas avisa que se borran", () => {
    expect(resumenVigencia(entrada({}, { decision: null }))).toBeNull();
    const r = resumenVigencia(entrada({ hasta: "2026-11-30" }, { decision: null }));
    expect(r?.texto).toContain("Al guardar se borran las fechas");
  });

  it("sin fechas: rige desde que se guarda, sin vencimiento", () => {
    expect(resumenVigencia(entrada({}))?.texto).toBe("Rige desde que guardes, sin vencimiento.");
  });

  it("solo Hasta: rige hoy y el dia siguiente vuelve a la regla", () => {
    const r = resumenVigencia(entrada({ hasta: "2026-11-30" }, { guardado: { desde: "", hasta: "2026-11-30" } }));
    expect(r?.texto).toBe("Rige hoy y hasta el 30-11-2026 incluido. El 01-12-2026 vuelve a la regla.");
  });

  it("si lo que se ve no es lo guardado, lo dice: «Al guardar: …»", () => {
    const r = resumenVigencia(entrada({ hasta: "2026-11-30" }));
    expect(r?.texto).toBe("Al guardar: rige hoy y hasta el 30-11-2026 incluido. El 01-12-2026 vuelve a la regla.");
  });

  it("Desde pasado y Hasta: dice desde cuando rige", () => {
    const r = resumenVigencia(entrada({ desde: "2026-10-01", hasta: "2026-11-30" }, { guardado: { desde: "2026-10-01", hasta: "2026-11-30" } }));
    expect(r?.texto).toBe("Rige desde el 01-10-2026 hasta el 30-11-2026 incluido. El 01-12-2026 vuelve a la regla.");
  });

  it("Desde futuro: hoy sigue la regla y desde el Desde rige la decision", () => {
    const r = resumenVigencia(entrada({ desde: "2026-11-05", hasta: "2026-11-30" }, { guardado: { desde: "2026-11-05", hasta: "2026-11-30" } }));
    expect(r?.texto).toBe(
      `Hoy el producto sigue la regla (${precio(10450)}). Desde el 05-11-2026 rige el precio fijo de ${precio(12990)} hasta el 30-11-2026.`,
    );
    expect(r?.vencimiento).toBeNull();
  });

  it("Desde futuro sin Hasta: sin vencimiento", () => {
    const r = resumenVigencia(entrada({ desde: "2026-11-05" }, { guardado: { desde: "2026-11-05", hasta: "" } }));
    expect(r?.texto).toContain("Desde el 05-11-2026 rige el precio fijo");
    expect(r?.texto).toContain("sin vencimiento");
  });

  it("vencido: dice que sigue la regla y como renovar", () => {
    const r = resumenVigencia(entrada({ hasta: "2026-10-12" }, { guardado: { desde: "", hasta: "2026-10-12" } }));
    expect(r?.texto).toBe(
      `Venció el 12-10-2026 y hoy sigue la regla (${precio(10450)}). Para aplicar de nuevo el precio fijo de ${precio(12990)} `
      + "elige un nuevo Hasta y guarda; o usa «Volver a la regla» para borrar la decisión.",
    );
  });

  it("sin el precio de la regla no pone parentesis ni cifras inventadas", () => {
    const r = resumenVigencia(entrada({ desde: "2026-11-05" }, { guardado: { desde: "2026-11-05", hasta: "" }, precioRegla: null }));
    expect(r?.texto).toContain("Hoy el producto sigue la regla.");
    expect(r?.texto).not.toMatch(/undefined|null|NaN/);
  });

  it("al vencer: de cuanto a cuanto pasa, con el %; desde 20 % se destaca con la palabra «baja»", () => {
    const r = resumenVigencia(entrada({ hasta: "2026-11-30" }, { guardado: { desde: "", hasta: "2026-11-30" } }));
    // 10.450 / 12.990 = -19,55 %, que redondea a -20 %.
    expect(r?.vencimiento).toBe(`Al vencer el precio baja de ${precio(12990)} a ${precio(10450)} (−20 %).`);
    expect(r?.fuerte).toBe(true);
  });

  it("un salto menor a 20 % no se destaca", () => {
    const r = resumenVigencia(entrada({ hasta: "2026-11-30" }, { guardado: { desde: "", hasta: "2026-11-30" }, precioRegla: 11000 }));
    expect(r?.vencimiento).toBe(`Al vencer pasaría de ${precio(12990)} a ${precio(11000)} (−15 %).`);
    expect(r?.fuerte).toBe(false);
  });

  it("si sube, dice «sube»", () => {
    const r = resumenVigencia(entrada({ hasta: "2026-11-30" }, { guardado: { desde: "", hasta: "2026-11-30" }, precioRegla: 18000 }));
    expect(r?.vencimiento).toBe(`Al vencer el precio sube de ${precio(12990)} a ${precio(18000)} (+39 %).`);
    expect(r?.fuerte).toBe(true);
  });

  it("si la regla da lo mismo, dice que no cambia", () => {
    const r = resumenVigencia(entrada({ hasta: "2026-11-30" }, { guardado: { desde: "", hasta: "2026-11-30" }, precioRegla: 12990 }));
    expect(r?.vencimiento).toBe("Al vencer el precio no cambia.");
  });

  it("sin Hasta no hay vencimiento que anunciar", () => {
    expect(resumenVigencia(entrada({ desde: "2026-10-01" }, { guardado: { desde: "2026-10-01", hasta: "" } }))?.vencimiento).toBeNull();
  });

  it("congelado y margen se nombran distinto", () => {
    const c = resumenVigencia(entrada({ desde: "2026-10-01", hasta: "" }, {
      guardado: { desde: "2026-10-01", hasta: "" }, decision: { tipo: "congelado", precio: 14000 },
    }));
    expect(c?.texto).toBeTruthy();
    const v = resumenVigencia(entrada({ hasta: "2026-10-12" }, {
      guardado: { desde: "", hasta: "2026-10-12" }, decision: { tipo: "congelado", precio: 14000 },
    }));
    expect(v?.texto).toContain(`el precio congelado de ${precio(14000)}`);
    const m = resumenVigencia(entrada({ hasta: "2026-10-12" }, {
      guardado: { desde: "", hasta: "2026-10-12" }, decision: { tipo: "margen", precio: null, margen: 35 },
    }));
    expect(m?.texto).toContain("el margen fijo de 35,0 %");
  });
});

describe("compararVencimiento", () => {
  /** AG Grid invierte el resultado cuando el orden es descendente. */
  const ordenar = (v: (string | null)[], descendente: boolean) =>
    [...v].sort((a, b) => compararVencimiento(a, b, descendente) * (descendente ? -1 : 1));

  it("ascendente: la fecha más próxima primero, los vacíos al final", () => {
    expect(ordenar(["2026-12-01", null, "2026-10-12", ""], false)).toEqual(["2026-10-12", "2026-12-01", null, ""]);
  });

  it("descendente: los vacíos TAMBIÉN al final", () => {
    expect(ordenar(["2026-12-01", null, "2026-10-12", ""], true)).toEqual(["2026-12-01", "2026-10-12", null, ""]);
  });

  it("dos vacíos o dos fechas iguales empatan", () => {
    expect(compararVencimiento(null, "", false)).toBe(0);
    expect(compararVencimiento("2026-11-30", "2026-11-30", true)).toBe(0);
  });
});
