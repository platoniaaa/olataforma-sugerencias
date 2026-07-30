"use client";

import { Boxes, DollarSign, Package, Truck } from "lucide-react";
import { formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type { SugeridoKpis } from "@/lib/types";

interface Props {
  kpis: SugeridoKpis | null;
  cargando: boolean;
}

function KpiCard({
  icon,
  label,
  valor,
  index,
  acento,
  nota,
}: {
  icon: React.ReactNode;
  label: string;
  valor: string;
  index: string;
  acento?: boolean;
  /** Renglón chico bajo la cifra (ej: cuánto viene de sugerencias manuales). */
  nota?: string | null;
}) {
  return (
    <div className="group relative overflow-hidden border border-ink-200 bg-white p-5 transition-colors hover:border-ink-300">
      {/* indice arriba-izq tipo "01." */}
      <span className="absolute left-5 top-4 font-mono text-[10px] text-ink-400">
        {index}
      </span>
      {/* icono arriba-derecha, decorativo */}
      <span className="absolute right-4 top-4 text-ink-300 transition-colors group-hover:text-ink-500">
        {icon}
      </span>
      <p className="kicker mt-6">{label}</p>
      <p
        className={`figure mt-2 text-[34px] leading-none ${
          acento ? "text-accent-700" : "text-ink-900"
        }`}
      >
        {valor}
      </p>
      {/* Desglose opcional: se reserva el alto igual cuando no hay nota, para que
          las cuatro tarjetas queden parejas. */}
      <p className="mt-1.5 h-4 text-[11px] leading-4 text-ink-500">{nota ?? ""}</p>
      {/* linea inferior tipo "subrayado tecnico" */}
      <span
        className={`absolute bottom-0 left-0 h-px transition-all ${
          acento ? "w-12 bg-accent-700" : "w-8 bg-ink-300 group-hover:w-16"
        }`}
      />
    </div>
  );
}

export function KpiCards({ kpis, cargando }: Props) {
  const v = (s: string) => (cargando || !kpis ? "—" : s);
  // Los totales ya incluyen las sugerencias manuales y lo que agrega la regla
  // InStock; el paréntesis dice cuánto viene de cada una. Solo aparece si hay algo
  // que mostrar, y si conviven las dos se muestran juntas.
  const uManual = kpis?.total_sugerido_manual ?? 0;
  const clpManual = kpis?.valor_manual_clp ?? 0;
  const uInstock = kpis?.total_sugerido_instock ?? 0;
  const clpInstock = kpis?.valor_instock_clp ?? 0;
  const nota = (mostrar: boolean, texto: string) =>
    cargando || !kpis || !mostrar ? null : texto;
  const desglose = (manual: number, instock: number, fmt: (n: number) => string) =>
    [
      manual > 0 ? `${fmt(manual)} manuales` : null,
      instock > 0 ? `${fmt(instock)} InStock` : null,
    ]
      .filter(Boolean)
      .join(" · ");
  return (
    <div className="grid grid-cols-2 gap-px bg-ink-200 lg:grid-cols-4">
      <KpiCard
        index="01"
        icon={<Boxes size={16} />}
        label="Total Sugerido"
        valor={v(formatoNumero(kpis?.total_sugerido))}
        nota={nota(
          uManual > 0 || uInstock > 0,
          `(${desglose(uManual, uInstock, (n) => formatoNumero(n))})`
        )}
      />
      <KpiCard
        index="02"
        icon={<DollarSign size={16} />}
        label="Valor Total"
        valor={v(formatoCLPCorto(kpis?.valor_total_clp))}
        nota={nota(
          clpManual > 0 || clpInstock > 0,
          `(${desglose(clpManual, clpInstock, (n) => formatoCLPCorto(n))})`
        )}
        acento
      />
      <KpiCard
        index="03"
        icon={<Package size={16} />}
        label="Productos a Comprar"
        valor={v(formatoNumero(kpis?.n_productos))}
      />
      <KpiCard
        index="04"
        icon={<Truck size={16} />}
        label="Proveedores a Contactar"
        valor={v(formatoNumero(kpis?.n_proveedores))}
      />
    </div>
  );
}
