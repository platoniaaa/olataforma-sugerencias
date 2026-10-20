"use client";

// Elegir como se carga la lista de precios: con el Excel corto (una plantilla de cinco columnas,
// para tocar pocos productos) o con el Excel completo (el archivo que se baja para editar).
//
// Son dos radios nativos: el teclado (flechas) y los lectores de pantalla ya los entienden. La
// opcion elegida se ve por tres senales y no solo por el color: el borde azul, el titulo en
// negrita y la marca de verificacion. El modo se recuerda en el navegador de cada persona.
import { Check } from "lucide-react";
import { useId } from "react";
import type { ModoCarga } from "@/lib/types";

/** Donde se recuerda el ultimo modo elegido (solo en este navegador). */
export const CLAVE_MODO_CARGA = "precios_carga_modo";

/** El modo que se uso la ultima vez. Sin nada guardado, con un valor raro o sin acceso al
 *  almacenamiento (ventana privada, datos bloqueados), el corto: es lo que se usa para tocar
 *  pocos productos, y no hace falta bajar nada para empezar. */
export function modoGuardado(): ModoCarga {
  try {
    return window.localStorage.getItem(CLAVE_MODO_CARGA) === "completo" ? "completo" : "corto";
  } catch {
    return "corto";
  }
}

/** Recuerda el modo para la proxima vez. Si el navegador no deja, simplemente no se recuerda. */
export function guardarModo(modo: ModoCarga): void {
  try {
    window.localStorage.setItem(CLAVE_MODO_CARGA, modo);
  } catch {
    // Sin almacenamiento: se vuelve a elegir la proxima vez.
  }
}

const OPCIONES: { modo: ModoCarga; titulo: string; descripcion: string }[] = [
  {
    modo: "corto",
    titulo: "Excel corto",
    descripcion: "Solo los productos que pongo. Código, precio fijo y fechas; no baja la lista.",
  },
  {
    modo: "completo",
    titulo: "Excel completo para editar",
    descripcion: "Bajo toda la lista (unos 40 mil productos), edito lo que quiera y la subo.",
  },
];

export function SelectorModo({ modo, onCambiar, deshabilitado }: {
  modo: ModoCarga;
  onCambiar: (modo: ModoCarga) => void;
  /** Mientras se lee un archivo o se guarda, el modo no se puede cambiar. */
  deshabilitado: boolean;
}) {
  const id = useId();
  return (
    <fieldset className="min-w-0">
      <legend className="sr-only">¿Cómo quieres cargar?</legend>
      <div className="grid gap-2 sm:grid-cols-2">
        {OPCIONES.map((o) => {
          const elegido = modo === o.modo;
          const idInput = `${id}-${o.modo}`;
          return (
            <div key={o.modo} className="relative">
              <input
                id={idInput}
                type="radio"
                name={`${id}-modo`}
                value={o.modo}
                checked={elegido}
                disabled={deshabilitado}
                onChange={() => onCambiar(o.modo)}
                aria-labelledby={`${idInput}-titulo`}
                aria-describedby={`${idInput}-descripcion`}
                className="peer sr-only"
              />
              <label
                htmlFor={idInput}
                className="flex min-h-[44px] cursor-pointer items-start gap-2.5 rounded-md border border-slate-200 bg-white p-3 text-left transition-colors hover:border-slate-300 peer-checked:border-brand peer-checked:bg-brand-50 peer-focus-visible:ring-2 peer-focus-visible:ring-accent-700/40 peer-focus-visible:ring-offset-1 peer-disabled:cursor-not-allowed peer-disabled:opacity-60"
              >
                <span
                  aria-hidden="true"
                  className={`mt-0.5 flex h-4 w-4 shrink-0 items-center justify-center rounded-full border ${
                    elegido ? "border-brand bg-brand text-white" : "border-slate-300 bg-white"
                  }`}
                >
                  {elegido && <Check size={11} strokeWidth={3} />}
                </span>
                <span className="min-w-0">
                  <span
                    id={`${idInput}-titulo`}
                    className={`block text-[13px] ${elegido ? "font-semibold text-slate-900" : "font-medium text-slate-800"}`}
                  >
                    {o.titulo}
                  </span>
                  <span id={`${idInput}-descripcion`} className="mt-0.5 block text-[12px] text-slate-600">
                    {o.descripcion}
                  </span>
                </span>
              </label>
            </div>
          );
        })}
      </div>
    </fieldset>
  );
}
