/**
 * Cada cuanto se mueve un repuesto, en una celda.
 *
 * Antes decia "3/6/12": los meses con venta de los ultimos 3, 6 y 12. El problema
 * es que en el caso MAS COMUN —un repuesto que se vende todos los meses— el valor
 * sale exactamente "3/6/12", que es identico al encabezado de la columna. El
 * comprador no puede saber si esta leyendo el titulo o el dato. Y sin denominador
 * tampoco se sabe si "3" es mucho o poco.
 *
 * Ahora se muestra el de 12 meses CON su denominador (12/12), que es la lectura
 * que sirve, y los de 3 y 6 pasan al tooltip. A cambio se gana lo que los tres
 * numeros crudos escondian: que un repuesto con 8/12 pero cero ventas en los
 * ultimos tres meses dejo de venderse. Eso hay que verlo, y antes habia que
 * deducirlo comparando el primer numero con el tercero.
 */

const TOPE_SIEMPRE = 11; // 11 o 12 de 12: se mueve todos los meses
const TOPE_ESPORADICO = 3; // 3 o menos: casi no se mueve

export type FrecuenciaProps = {
  meses3: number | null | undefined;
  meses6: number | null | undefined;
  meses12: number | null | undefined;
  /** Cuando no se vende aca pero si en otra parte, se dice donde. */
  otraSucursal?: { nombre_sucursal: string; meses_con_venta_12m: number } | null;
};

/** Que decir del patron, si es que hay algo que decir. */
export function lecturaFrecuencia(
  meses3: number | null | undefined,
  meses12: number | null | undefined
): { texto: string; alerta: boolean } | null {
  const m12 = meses12 ?? 0;
  // Lo primero que hay que ver: se vendia y paro. El 12m sigue alto y engaña.
  if (m12 >= 4 && (meses3 ?? 0) === 0) {
    return { texto: "sin venta hace 3 meses", alerta: true };
  }
  if (m12 >= TOPE_SIEMPRE) return { texto: "se vende casi todos los meses", alerta: false };
  if (m12 > 0 && m12 <= TOPE_ESPORADICO) return { texto: "esporádico", alerta: false };
  return null;
}

export function FrecuenciaVenta({ meses3, meses6, meses12, otraSucursal }: FrecuenciaProps) {
  if (meses12 == null) {
    return otraSucursal ? (
      <span className="text-[11.5px] text-amber-800">
        acá nunca · {otraSucursal.nombre_sucursal} {otraSucursal.meses_con_venta_12m}/12
      </span>
    ) : (
      <span className="text-ink-300">—</span>
    );
  }

  const lectura = lecturaFrecuencia(meses3, meses12);
  // El color acompaña, no informa por si solo: al lado va siempre el numero, y
  // cuando hay algo que advertir va tambien la palabra.
  const color = lectura?.alerta
    ? "text-amber-800"
    : meses12 >= TOPE_SIEMPRE
      ? "text-emerald-700"
      : meses12 <= TOPE_ESPORADICO
        ? "text-ink-400"
        : "text-ink-900";

  return (
    <span
      className="inline-flex flex-col leading-tight"
      title={`Meses con venta: ${meses3 ?? "—"} de los últimos 3, ${meses6 ?? "—"} de 6, ${meses12} de 12`}
    >
      <span className={`tabular ${color}`}>
        <strong>{meses12}</strong>
        <span className="text-ink-400">/12</span>
      </span>
      {lectura && (
        <span className={`text-[10.5px] ${lectura.alerta ? "text-amber-700" : "text-ink-400"}`}>
          {lectura.texto}
        </span>
      )}
    </span>
  );
}
