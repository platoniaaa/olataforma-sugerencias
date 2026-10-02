"use client";

/**
 * La linea que dice DESDE CUANDO son las diferencias pendientes.
 *
 * El boton "Solo diferencias" mostraba un numero suelto y nada mas. Quien lo ve
 * por primera vez no tiene como saber si esos 2.041 son de hoy, de la semana o
 * de siempre; y la respuesta no es una fecha cualquiera, es "desde la ultima vez
 * que alguien bajo este mismo archivo", que es justo lo que no se veia en
 * ninguna parte de la pantalla.
 *
 * Se dice en terminos de lo que la persona hizo -una descarga- y no del sistema
 * -un envio registrado-, que es la palabra que usamos entre nosotros y que a
 * quien recibe el modulo no le dice nada.
 */

import { Clock } from "lucide-react";
import { formatoFechaHora, formatoNumero } from "@/lib/formato";

export function ResumenDiferencias({
  pendientes,
  ultimoEnvio,
}: {
  pendientes: number;
  ultimoEnvio: string | null;
}) {
  const cuando = ultimoEnvio ? formatoFechaHora(ultimoEnvio) : null;

  const texto = !cuando ? (
    <>
      <b>{formatoNumero(pendientes)}</b> productos esperando: la lista{" "}
      <b>nunca se ha descargado</b>, así que salen todos.
    </>
  ) : pendientes === 0 ? (
    <>Todo al día: no hay cambios desde la última descarga, del {cuando}.</>
  ) : (
    <>
      <b>{formatoNumero(pendientes)}</b> productos cambiaron desde la última descarga, del{" "}
      <b>{cuando}</b>.
    </>
  );

  return (
    <p
      data-testid="desde-cuando"
      className="flex items-center gap-1.5 text-[12px] text-ink-500"
    >
      <Clock size={13} className="shrink-0 text-ink-400" />
      {texto}
    </p>
  );
}
