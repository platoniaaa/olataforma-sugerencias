/**
 * Margen en % SOBRE LA VENTA <-> factor sobre el costo.
 *
 * Sobre la venta y no sobre el costo (decisión del 07-10-2026): es el margen
 * como lo mira contabilidad. 35 % es factor 1,5385; el factor 1,78 de la
 * política equivale a 43,8 %. Misma cuenta que `precios_service.factor_desde_margen`.
 */
export function factorDesdeMargen(margen: number | null | undefined): number | null {
  if (margen == null || !Number.isFinite(margen) || margen <= 0 || margen >= 100) return null;
  return Math.round((1 / (1 - margen / 100)) * 10000) / 10000;
}

export function margenDesdeFactor(factor: number | null | undefined): number | null {
  if (factor == null || !Number.isFinite(factor) || factor <= 0) return null;
  return Math.round((1 - 1 / factor) * 1000) / 10;
}
