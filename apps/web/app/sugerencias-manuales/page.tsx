"use client";

import { useCallback, useEffect, useState } from "react";
import { Boxes, Repeat, Trash2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import { formatoFecha, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { Recurrente, SugerenciaManual } from "@/lib/types";

type Tab = "unicas" | "recurrentes";

export default function SugerenciasManualesPage() {
  const [tab, setTab] = useState<Tab>("unicas");
  const [unicas, setUnicas] = useState<SugerenciaManual[] | null>(null);
  const [recurrentes, setRecurrentes] = useState<Recurrente[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const [u, r] = await Promise.all([
        api.sugerenciasManuales({ soloUnicas: true }),
        api.recurrentes(),
      ]);
      setUnicas(u);
      setRecurrentes(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const eliminarUnica = async (id: string) => {
    if (!confirm("¿Eliminar esta sugerencia? Se quita de la compra.")) return;
    await api.eliminarSugerenciaManual(id);
    cargar();
  };

  const eliminarRecurrente = async (id: string) => {
    if (
      !confirm(
        "¿Eliminar esta recurrencia? Su ajuste vigente dejará de sumar a la compra."
      )
    )
      return;
    await api.eliminarRecurrente(id);
    cargar();
  };

  const tabs: { id: Tab; icon: React.ReactNode; label: string; count: number | null }[] = [
    {
      id: "unicas",
      icon: <Boxes size={15} />,
      label: "Únicas",
      count: unicas?.length ?? null,
    },
    {
      id: "recurrentes",
      icon: <Repeat size={15} />,
      label: "Recurrentes",
      count: recurrentes?.length ?? null,
    },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">
          Sugerencias manuales
        </h1>
        <p className="text-[13px] text-slate-500">
          Ajustes del equipo que se suman al sugerido del BI. Se crean desde el botón
          “Sugerencia manual” en el dashboard.
        </p>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${
              tab === t.id
                ? "border-brand text-brand"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.icon} {t.label}
            {t.count !== null && (
              <span className="rounded bg-slate-100 px-1.5 py-px text-[10px] text-slate-600">
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          {error}
        </div>
      )}

      {tab === "unicas" && (
        <SeccionUnicas
          items={unicas}
          onEliminar={eliminarUnica}
        />
      )}

      {tab === "recurrentes" && (
        <SeccionRecurrentes
          items={recurrentes}
          onEliminar={eliminarRecurrente}
        />
      )}
    </div>
  );
}

function SeccionUnicas({
  items,
  onEliminar,
}: {
  items: SugerenciaManual[] | null;
  onEliminar: (id: string) => void;
}) {
  if (items === null) return <p className="text-slate-500">Cargando…</p>;
  if (items.length === 0)
    return (
      <Card>
        <CardContent className="text-[13px] text-slate-500">
          No hay sugerencias únicas vigentes. Para crear una, andá al dashboard, hacé
          click en “Sugerencia manual” y <b>no</b> marqués “Repetir periódicamente”.
        </CardContent>
      </Card>
    );
  return (
    <div className="space-y-2">
      {items.map((s) => (
        <Card key={s.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">{s.producto}</span>
                <span className="text-[13px] text-slate-500">·</span>
                <span className="text-[13px] text-slate-600">{s.sucursal_id}</span>
                <Badge className="bg-emerald-50 text-emerald-700">
                  +{formatoNumero(s.unidades)} u
                </Badge>
              </div>
              <p className="mt-1 text-[12px] text-slate-500">
                {s.creado_por && <>{s.creado_por} · </>}
                {formatoFechaHora(s.creado_en)}
                {s.motivo && <> · {s.motivo}</>}
              </p>
            </div>
            <button
              onClick={() => onEliminar(s.id)}
              className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
              aria-label="Eliminar sugerencia"
            >
              <Trash2 size={16} />
            </button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function SeccionRecurrentes({
  items,
  onEliminar,
}: {
  items: Recurrente[] | null;
  onEliminar: (id: string) => void;
}) {
  if (items === null) return <p className="text-slate-500">Cargando…</p>;
  if (items.length === 0)
    return (
      <Card>
        <CardContent className="text-[13px] text-slate-500">
          No hay recurrencias activas. Se crean desde el dashboard, marcando “Repetir
          periódicamente” en el modal de sugerencia manual.
        </CardContent>
      </Card>
    );
  return (
    <div className="space-y-2">
      {items.map((r) => (
        <Card key={r.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">{r.resumen}</span>
                <Badge className="bg-brand-50 text-brand">
                  {r.dias_inventario
                    ? `+${r.dias_inventario} días`
                    : `+${formatoNumero(r.unidades)} u`}
                </Badge>
                <Badge className="bg-slate-100 text-slate-600">
                  cada {r.cada_dias} días
                </Badge>
                <Badge className="bg-slate-100 text-slate-500">
                  {r.modo === "individual" ? "Individual" : "Por grupo"}
                </Badge>
              </div>
              <p className="mt-1 text-[12px] text-slate-500">
                Próxima: <b>{formatoFecha(r.proxima_ejecucion)}</b>
                {r.fecha_fin && <> · termina {formatoFecha(r.fecha_fin)}</>}
                {r.ultima_ejecucion && <> · última {formatoFecha(r.ultima_ejecucion)}</>}
                {r.motivo && <> · {r.motivo}</>}
              </p>
            </div>
            <button
              onClick={() => onEliminar(r.id)}
              className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
              aria-label="Eliminar recurrencia"
            >
              <Trash2 size={16} />
            </button>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
