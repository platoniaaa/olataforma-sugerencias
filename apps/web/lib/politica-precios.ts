// Lo que la pantalla de política de precios calcula sin ir al servidor: validar un
// tipo nuevo y armar el cambio que se manda a guardar. Vive aparte de la página
// para poder probarlo (y porque una página de Next no puede exportar otra cosa).
import type { CambioPolitica, PoliticaFactor, PoliticaRubro } from "./types";

// Los mismos alias que `politica_precio_service._ALIAS`: "Baterias" es "Bateria".
// Sin esto, un tipo nuevo "Baterias" pasaría la validación y el servidor lo
// guardaría encima del que ya existe.
const ALIAS: Record<string, string> = {
  baterias: "bateria",
  neumaticos: "neumatico",
  lubricantes: "lubricante",
};

export function tipoCanonico(tipo: string): string {
  const t = tipo.trim().toLowerCase();
  return ALIAS[t] ?? t;
}

/** Un número escrito con coma o con punto: "1,88" y "1.88" son lo mismo. */
export function leerNumero(texto: string): number {
  const t = texto.trim().replace(",", ".");
  return t === "" ? Number.NaN : Number(t);
}

/** Un factor de 1 o menos vende bajo el costo; el servidor tampoco lo acepta. */
export function factorValido(factor: number | null | undefined): factor is number {
  return typeof factor === "number" && factor > 1 && factor <= 10;
}

export interface TipoNuevoForm {
  nombre: string;
  nacional: string;
  importado: string;
  descuento: string;
}

export const TIPO_NUEVO_VACIO: TipoNuevoForm = { nombre: "", nacional: "", importado: "", descuento: "" };

/** Qué está mal en el formulario de tipo nuevo, o null si se puede agregar. */
export function errorTipoNuevo(form: TipoNuevoForm, tiposExistentes: string[]): string | null {
  const nombre = form.nombre.trim();
  if (!nombre) return "Escribe un nombre para el tipo.";
  if (nombre.length > 40) return "El nombre puede tener hasta 40 caracteres.";
  // "Sugerido" no lleva factor: toma la lista del proveedor.
  const existentes = new Set([...tiposExistentes, "Sugerido"].map(tipoCanonico));
  if (existentes.has(tipoCanonico(nombre))) {
    return `Ya existe el tipo "${nombre}". Usa otro nombre, o cambia el factor de ese tipo en la tabla.`;
  }
  const factores: [string, string][] = [["nacional", form.nacional], ["importado", form.importado]];
  for (const [cual, valor] of factores) {
    if (!factorValido(leerNumero(valor))) {
      return `El factor ${cual} tiene que ser mayor que 1 y hasta 10: con 1 o menos se vende bajo el costo.`;
    }
  }
  const descuento = leerNumero(form.descuento);
  if (!(descuento >= 0 && descuento <= 100)) return "El descuento va de 0 a 100.";
  return null;
}

/** Las dos filas de factores de un tipo nuevo, una por procedencia. */
export function filasTipoNuevo(form: TipoNuevoForm): PoliticaFactor[] {
  const tipo = form.nombre.trim();
  const descuento = leerNumero(form.descuento);
  return [
    { tipo, procedencia: "Nacional", factor: leerNumero(form.nacional), descuento_max: descuento, margen_post: null },
    { tipo, procedencia: "Importado", factor: leerNumero(form.importado), descuento_max: descuento, margen_post: null },
  ];
}

/**
 * Lo que cambió respecto de lo cargado. Solo eso viaja: el servidor guarda fila
 * por fila, y mandar las 60 filas de rubros para cambiar una dejaba en Auditoría
 * a quien guardó como autor de las 60.
 *
 * Las filas de factor inválidas (vacías o de 1 o menos) no se mandan: la página
 * las muestra como error y no deja guardar.
 */
export function cambioPolitica(
  factores: PoliticaFactor[],
  originalFactores: PoliticaFactor[],
  rubros: PoliticaRubro[],
  originalRubros: PoliticaRubro[],
  seguirAlRubro: string[],
): CambioPolitica {
  const fs = factores
    .filter((f) => factorValido(f.factor))
    .filter((f) => {
      const o = originalFactores.find((x) => x.tipo === f.tipo && x.procedencia === f.procedencia);
      return !o || o.factor !== f.factor || (o.descuento_max ?? null) !== (f.descuento_max ?? null);
    })
    .map(({ tipo, procedencia, factor, descuento_max, margen_post }) => ({
      tipo, procedencia, factor, descuento_max, margen_post,
    }));
  const rs = rubros
    .filter((r) => {
      const o = originalRubros.find((x) => x.rubro === r.rubro);
      return !o || (o.tipo ?? null) !== (r.tipo ?? null)
        || (o.procedencia_forzada ?? null) !== (r.procedencia_forzada ?? null);
    })
    .map(({ rubro, tipo, procedencia_forzada }) => ({ rubro, tipo, procedencia_forzada }));
  // "Que sigan al rubro" solo tiene sentido para un rubro que cambia en este guardado.
  const cambiados = new Set(rs.map((r) => r.rubro));
  return { factores: fs, rubros: rs, seguir_al_rubro: seguirAlRubro.filter((r) => cambiados.has(r)) };
}
