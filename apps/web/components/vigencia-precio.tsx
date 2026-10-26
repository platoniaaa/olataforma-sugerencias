"use client";

// La sección «Vigencia» de la ficha de un precio: desde y hasta cuándo rigen el precio fijo,
// el margen fijo o el congelado. Antes del Desde y después del Hasta el producto sigue la
// regla; la decisión queda guardada para renovarla.
//
// Es controlada y no habla con la API: recibe las fechas, los errores y la línea resumen ya
// calculados (lib/vigencia.ts) y avisa lo que la persona cambia. Así la ficha valida con las
// mismas cuentas al guardar.
import { useId, useState, type ReactNode } from "react";
import { AlertCircle, Check, TriangleAlert } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input, Label } from "@/components/ui/input";
import { formatoFecha } from "@/lib/formato";
import { ATAJOS, atajo, type AtajoId, type ErroresPeriodo, type ResumenVigencia } from "@/lib/vigencia";

const CLASE_FECHA = "[@media(pointer:coarse)]:h-11 aria-[invalid=true]:border-rose-500 aria-[invalid=true]:ring-rose-500/20 disabled:cursor-not-allowed disabled:bg-ink-50 disabled:text-ink-400";

export function VigenciaPrecio({ desde, hasta, onCambiar, hoy, habilitado, motivoBloqueo, errores, resumen }: {
  /** Aaaa-mm-dd o vacío. */
  desde: string;
  hasta: string;
  onCambiar: (campo: "desde" | "hasta", valor: string) => void;
  /** La fecha de hoy en Chile: desde ella cuentan los atajos. */
  hoy: string;
  /** Sin permiso, o sin ninguna decisión a la que ponerle fecha, todo queda deshabilitado. */
  habilitado: boolean;
  /** Por qué está deshabilitado; se muestra solo en ese caso. */
  motivoBloqueo?: string | null;
  errores: ErroresPeriodo;
  resumen: ResumenVigencia | null;
}) {
  const id = useId();
  const ids = {
    ayuda: `${id}-ayuda`, motivo: `${id}-motivo`,
    desde: `${id}-desde`, desdeAyuda: `${id}-desde-ayuda`, desdeError: `${id}-desde-error`,
    hasta: `${id}-hasta`, hastaAyuda: `${id}-hasta-ayuda`, hastaError: `${id}-hasta-error`, hastaAviso: `${id}-hasta-aviso`,
    resumen: `${id}-resumen`,
  };
  // Lo que se lee en voz alta al aplicar un atajo: el input cambia de valor sin que el foco se mueva.
  const [anuncio, setAnuncio] = useState("");

  const describe = (...partes: (string | false | null | undefined)[]) => partes.filter(Boolean).join(" ") || undefined;
  const bloqueado = !habilitado;

  function aplicar(cual: AtajoId) {
    const valor = atajo(cual, desde, hoy);
    onCambiar("hasta", valor);
    setAnuncio(valor ? `Hasta: ${formatoFecha(valor)}` : "Sin vencimiento");
  }

  return (
    <fieldset
      disabled={bloqueado}
      aria-describedby={describe(ids.ayuda, bloqueado && motivoBloqueo && ids.motivo)}
      className="min-w-0 space-y-2 rounded-md border border-ink-100 p-3"
    >
      <legend className="px-1 text-[12px] font-semibold text-ink-700">Vigencia (opcional)</legend>
      <p id={ids.ayuda} className="text-[11px] text-ink-500">
        Vale para el precio fijo, el margen fijo o el congelado. Antes del Desde y después del Hasta
        el producto sigue la regla.
      </p>
      {bloqueado && motivoBloqueo && (
        <p id={ids.motivo} className="rounded-md bg-ink-50 px-2 py-1.5 text-[12px] text-ink-600">{motivoBloqueo}</p>
      )}

      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <div>
          <Label htmlFor={ids.desde}>Desde</Label>
          <Input
            id={ids.desde} name="vigente_desde" type="date" value={desde} className={CLASE_FECHA}
            onChange={(e) => onCambiar("desde", e.target.value)}
            aria-invalid={errores.desde ? true : undefined}
            aria-describedby={describe(ids.desdeAyuda, errores.desde && ids.desdeError)}
          />
          <p id={ids.desdeAyuda} className="mt-0.5 text-[11px] text-ink-500">Vacío: desde que guardes</p>
          {errores.desde && <ErrorCampo id={ids.desdeError}>{errores.desde}</ErrorCampo>}
        </div>
        <div>
          <Label htmlFor={ids.hasta}>Hasta (incluido)</Label>
          <Input
            id={ids.hasta} name="vigente_hasta" type="date" value={hasta} className={CLASE_FECHA}
            onChange={(e) => onCambiar("hasta", e.target.value)}
            aria-invalid={errores.hasta ? true : undefined}
            aria-describedby={describe(ids.hastaAyuda, errores.hasta && ids.hastaError, errores.aviso && ids.hastaAviso)}
          />
          <p id={ids.hastaAyuda} className="mt-0.5 text-[11px] text-ink-500">
            Último día en que rige. Vacío: sin vencimiento
          </p>
          {errores.hasta && <ErrorCampo id={ids.hastaError}>{errores.hasta}</ErrorCampo>}
          {errores.aviso && !errores.hasta && (
            <p id={ids.hastaAviso} className="mt-1 flex items-start gap-1 text-[11px] text-amber-800">
              <TriangleAlert size={12} className="mt-px shrink-0" aria-hidden="true" /> {errores.aviso}
            </p>
          )}
        </div>
      </div>

      <div role="group" aria-label="Atajos para el Hasta" className="flex flex-wrap gap-1.5">
        {ATAJOS.map((a) => {
          const valor = atajo(a.id, desde, hoy);
          const activo = hasta === valor;
          return (
            <Button
              key={a.id} type="button" variant="outline" size="sm"
              aria-pressed={activo}
              title={valor ? `Hasta el ${formatoFecha(valor)}` : "Sin fecha de término"}
              className="[@media(pointer:coarse)]:h-11 aria-pressed:border-brand aria-pressed:bg-brand-50 aria-pressed:text-brand"
              onClick={() => aplicar(a.id)}
            >
              {activo && <Check size={13} aria-hidden="true" />} {a.etiqueta}
            </Button>
          );
        })}
      </div>
      <span className="sr-only" aria-live="polite">{anuncio}</span>

      {resumen && (
        <p id={ids.resumen} aria-live="polite" className="text-[12px] leading-relaxed text-ink-600">
          {resumen.texto}{" "}
          {resumen.vencimiento && (
            <span className={`mt-0.5 flex items-start gap-1 ${resumen.fuerte ? "font-semibold text-amber-800" : ""}`}>
              {resumen.fuerte && <TriangleAlert size={13} className="mt-px shrink-0" aria-hidden="true" />}
              {resumen.vencimiento}
            </span>
          )}
        </p>
      )}
    </fieldset>
  );
}

/** El error va pegado al campo, con ícono y palabras: nunca solo el borde rojo. */
function ErrorCampo({ id, children }: { id: string; children: ReactNode }) {
  return (
    <p id={id} className="mt-1 flex items-start gap-1 text-[12px] font-medium text-rose-700">
      <AlertCircle size={13} className="mt-px shrink-0" aria-hidden="true" /> <span>{children}</span>
    </p>
  );
}
