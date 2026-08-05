// Utilidades de formato chileno (es-CL).

/** Formatea un numero como peso chileno: $1.234.567 (sin decimales). */
export function formatoCLP(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  return new Intl.NumberFormat("es-CL", {
    style: "currency",
    currency: "CLP",
    maximumFractionDigits: 0,
  }).format(valor);
}

/** Version corta para KPIs grandes: $1.234 mill / $1,2 mill / $987 mil. */
export function formatoCLPCorto(valor: number | null | undefined): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  const abs = Math.abs(valor);
  if (abs >= 1_000_000_000) return `$${formatoNumero(valor / 1_000_000_000, 1)} mil mill`;
  if (abs >= 1_000_000) return `$${formatoNumero(valor / 1_000_000, 1)} mill`;
  if (abs >= 1_000) return `$${formatoNumero(valor / 1_000, 0)} mil`;
  return formatoCLP(valor);
}

/** Numero con separador de miles chileno (punto). */
export function formatoNumero(
  valor: number | null | undefined,
  decimales = 0
): string {
  if (valor === null || valor === undefined || Number.isNaN(valor)) return "—";
  return new Intl.NumberFormat("es-CL", {
    minimumFractionDigits: decimales,
    maximumFractionDigits: decimales,
  }).format(valor);
}

/** Fecha en formato chileno dd-mm-aaaa. */
export function formatoFecha(iso: string | null | undefined): string {
  if (!iso) return "—";
  // Una fecha SIN hora ("2026-05-02") la interpreta JS como medianoche UTC, y al
  // mostrarla en hora de Chile (UTC-4) retrocede al dia anterior. Una fecha de OC
  // corrida un dia no es un detalle cosmetico: es un dato equivocado.
  const soloFecha = /^\d{4}-\d{2}-\d{2}$/.exec(iso.trim());
  if (soloFecha) {
    const [a, m, d] = iso.trim().split("-");
    return `${d}-${m}-${a}`;
  }
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const dd = String(d.getDate()).padStart(2, "0");
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  return `${dd}-${mm}-${d.getFullYear()}`;
}

/** Fecha + hora chilena dd-mm-aaaa HH:MM. */
export function formatoFechaHora(iso: string | null | undefined): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  const hh = String(d.getHours()).padStart(2, "0");
  const min = String(d.getMinutes()).padStart(2, "0");
  return `${formatoFecha(iso)} ${hh}:${min}`;
}
