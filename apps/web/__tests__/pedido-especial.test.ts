/**
 * Las cuentas del recuadro "Hoy se compran N en total" del modal de sugerencia
 * manual. Son las del servidor (sugerido_service._faltante_para_objetivo y
 * _objetivo_dias): los mismos números de apps/api/tests/test_pedido_especial.py.
 * Si se separan, la pantalla promete un número y se guarda otro.
 */
import { describe, expect, it } from "vitest";

import { calcular, fechaEnDias, textoResultado } from "@/lib/pedido-especial";
import type { ContextoSugerencia } from "@/lib/types";

// 5 en stock, 2 en camino, el sistema pide 3, se venden 0,8 al día.
const ctx = (extra: Partial<ContextoSugerencia> = {}): ContextoSugerencia => ({
  stock: 5,
  transito: 2,
  sugerido_sistema: 3,
  demanda_diaria: 0.8,
  en_sugerido: true,
  bodegas: [],
  vigentes: [],
  reglas: [],
  ...extra,
});

describe("calcular", () => {
  it("una sola vez suma lo tuyo a lo del sistema", () => {
    const r = calcular("una", ctx(), 7);
    expect(r).toMatchObject({ total: 10, tuyas: 7, quedas: 17, nadaQuePedir: false });
    expect(r?.diasVenta).toBeCloseTo(21.25);
  });

  it("nunca menos de N pide solo lo que falta (12 - 10 = 2)", () => {
    expect(calcular("min", ctx(), 12)).toMatchObject({ total: 5, tuyas: 2, quedas: 12 });
  });

  it("si ya alcanza, la regla no pide nada hoy", () => {
    expect(calcular("min", ctx(), 8)).toMatchObject({ tuyas: 0, total: 3, nadaQuePedir: true });
  });

  it("días de venta: 30 × 0,8 = 24, menos 10 = 14", () => {
    expect(calcular("dias", ctx(), 30)).toMatchObject({ tuyas: 14, total: 17, quedas: 24 });
  });

  it("sin venta registrada los días no se pueden pasar a unidades", () => {
    expect(calcular("dias", ctx({ demanda_diaria: null }), 30)).toMatchObject({
      sinDemanda: true,
      tuyas: 0,
    });
    // "nunca menos de" sí funciona sin venta.
    expect(calcular("min", ctx({ demanda_diaria: null }), 12)).toMatchObject({
      tuyas: 2,
      diasVenta: null,
    });
  });

  it("un número vacío, cero o negativo no calcula", () => {
    expect(calcular("una", ctx(), NaN)).toBeNull();
    expect(calcular("una", ctx(), 0)).toBeNull();
    expect(calcular("min", ctx(), -3)).toBeNull();
  });
});

describe("textoResultado", () => {
  it("una sola vez", () => {
    expect(textoResultado("una", ctx(), 7)).toEqual({
      titulo: "Hoy se compran 10 en total",
      detalle: "3 que pide el sistema + 7 tuyas. Quedas con 17, unos 21 días de venta.",
    });
  });

  it("nunca menos de", () => {
    expect(textoResultado("min", ctx(), 12)?.detalle).toBe(
      "3 que pide el sistema + 2 para no bajar de 12. Quedas con 12, unos 15 días de venta."
    );
  });

  it("días de venta", () => {
    expect(textoResultado("dias", ctx(), 30)?.detalle).toBe(
      "3 que pide el sistema + 14 para cubrir 30 días. Quedas con 24, unos 30 días de venta."
    );
  });

  it("cuando ya alcanza lo dice en vez de mostrar cero", () => {
    expect(textoResultado("min", ctx(), 8)?.titulo).toBe("Hoy no hace falta pedir");
  });

  it("si el sistema no pide nada no lo suma", () => {
    expect(textoResultado("una", ctx({ sugerido_sistema: 0 }), 7)?.detalle).toBe(
      "7 tuyas; el sistema no pide nada hoy. Quedas con 14, unos 18 días de venta."
    );
  });

  it("sin venta registrada no inventa días", () => {
    expect(textoResultado("una", ctx({ demanda_diaria: null }), 7)?.detalle).toBe(
      "3 que pide el sistema + 7 tuyas. Quedas con 17."
    );
    expect(textoResultado("dias", ctx({ demanda_diaria: null }), 30)?.titulo).toBe(
      "No se puede calcular"
    );
  });
});

describe("fechaEnDias", () => {
  it("cuenta en hora local: a las 23:30 en Chile sigue siendo hoy", () => {
    expect(fechaEnDias(7, new Date(2026, 9, 8, 23, 30))).toBe("2026-10-15");
    expect(fechaEnDias(0, new Date(2026, 9, 8, 23, 30))).toBe("2026-10-08");
  });

  it("cruza el fin de mes", () => {
    expect(fechaEnDias(7, new Date(2026, 9, 28, 10, 0))).toBe("2026-11-04");
  });
});
