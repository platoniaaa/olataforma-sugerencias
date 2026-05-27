"use client";

import { useCallback, useEffect, useState } from "react";
import { Repeat, Trash2 } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import { formatoFecha, formatoNumero } from "@/lib/formato";
import type { Recurrente } from "@/lib/types";

export default function RecurrentesPage() {
  const [items, setItems] = useState<Recurrente[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    try {
      setItems(await api.recurrentes());
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const eliminar = async (id: string) => {
    if (!confirm("¿Eliminar esta recurrencia? Su ajuste vigente dejará de sumar a la compra.")) return;
    await api.eliminarRecurrente(id);
    cargar();
  };

  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
          <Repeat size={20} className="text-brand" /> Sugerencias recurrentes
        </h1>
        <p className="text-[13px] text-slate-500">
          Reglas que agregan una sugerencia manual cada cierto tiempo. Cada repetición
          reemplaza a la anterior (no se acumulan). Se crean desde el botón “Agregar
          sugerencia manual”, marcando “Repetir periódicamente”.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          {error}
        </div>
      )}

      {items === null && !error && <p className="text-slate-500">Cargando…</p>}

      {items && items.length === 0 && (
        <Card>
          <CardContent className="text-[13px] text-slate-500">
            No hay recurrencias activas. Crea una desde “Agregar sugerencia manual” →
            “Repetir periódicamente”.
          </CardContent>
        </Card>
      )}

      <div className="space-y-2">
        {items?.map((r) => (
          <Card key={r.id}>
            <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
              <div className="min-w-0">
                <div className="flex flex-wrap items-center gap-2">
                  <span className="font-semibold text-slate-900">{r.resumen}</span>
                  <Badge className="bg-brand-50 text-brand">
                    +{formatoNumero(r.unidades)} u
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
                onClick={() => eliminar(r.id)}
                className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                aria-label="Eliminar recurrencia"
              >
                <Trash2 size={16} />
              </button>
            </CardContent>
          </Card>
        ))}
      </div>
    </div>
  );
}
