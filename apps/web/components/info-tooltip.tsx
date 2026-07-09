"use client";

import { useRef, useState } from "react";
import { createPortal } from "react-dom";
import { Info } from "lucide-react";

/**
 * Icono de info (ⓘ) que muestra un texto al pasar el mouse. El tooltip se
 * renderiza en un portal a <body> con posición fija, para que no lo recorte el
 * overflow del contenedor (modales, listas con scroll, etc.). Mismo estilo que
 * el de los encabezados de la tabla del sugerido.
 */
export function InfoTooltip({ texto, size = 13 }: { texto: string; size?: number }) {
  const iconRef = useRef<HTMLSpanElement>(null);
  const [tip, setTip] = useState<{ x: number; y: number } | null>(null);

  const mostrar = () => {
    const r = iconRef.current?.getBoundingClientRect();
    if (r) setTip({ x: r.left + r.width / 2, y: r.bottom + 6 });
  };

  return (
    <>
      <span
        ref={iconRef}
        onMouseEnter={mostrar}
        onMouseLeave={() => setTip(null)}
        onFocus={mostrar}
        onBlur={() => setTip(null)}
        onClick={(e) => e.stopPropagation()}
        tabIndex={0}
        role="button"
        aria-label={texto}
        className="inline-flex shrink-0 cursor-help text-ink-400 transition-colors hover:text-accent-600 focus:text-accent-600 focus:outline-none"
      >
        <Info size={size} />
      </span>
      {tip &&
        typeof document !== "undefined" &&
        createPortal(
          <div
            className="pointer-events-none fixed z-[200] max-w-[280px] -translate-x-1/2 rounded-md border border-ink-200 bg-white px-3 py-2 text-[12px] font-normal normal-case leading-snug tracking-normal text-ink-700 shadow-lift"
            style={{ left: tip.x, top: tip.y }}
          >
            {texto}
          </div>,
          document.body
        )}
    </>
  );
}
