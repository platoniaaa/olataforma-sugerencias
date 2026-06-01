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
}: {
  icon: React.ReactNode;
  label: string;
  valor: string;
  index: string;
  acento?: boolean;
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
  return (
    <div className="grid grid-cols-2 gap-px bg-ink-200 lg:grid-cols-4">
      <KpiCard
        index="01"
        icon={<Boxes size={16} />}
        label="Total Sugerido"
        valor={v(formatoNumero(kpis?.total_sugerido))}
      />
      <KpiCard
        index="02"
        icon={<DollarSign size={16} />}
        label="Valor Total"
        valor={v(formatoCLPCorto(kpis?.valor_total_clp))}
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
