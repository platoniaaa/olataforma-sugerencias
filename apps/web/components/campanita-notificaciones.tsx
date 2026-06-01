"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { Bell } from "lucide-react";
import { api } from "@/lib/api-client";
import type { Notificacion } from "@/lib/types";

function tiempoRelativo(iso: string): string {
  const d = new Date(iso);
  const segs = Math.max(0, (Date.now() - d.getTime()) / 1000);
  if (segs < 60) return "ahora";
  const mins = Math.floor(segs / 60);
  if (mins < 60) return `${mins} min`;
  const hs = Math.floor(mins / 60);
  if (hs < 24) return `${hs} h`;
  return `${Math.floor(hs / 24)} d`;
}

export function CampanitaNotificaciones() {
  const [items, setItems] = useState<Notificacion[]>([]);
  const [noLeidas, setNoLeidas] = useState(0);
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const cargar = async () => {
    try {
      const r = await api.notificaciones(false, 20);
      setItems(r.items);
      setNoLeidas(r.no_leidas);
    } catch {
      // sin red / sin sesion: no quebrar el header
    }
  };

  useEffect(() => {
    cargar();
    const t = setInterval(cargar, 60_000); // refresca cada 60s
    return () => clearInterval(t);
  }, []);

  // Cerrar al click fuera.
  useEffect(() => {
    if (!open) return;
    const onClick = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onClick);
    return () => document.removeEventListener("mousedown", onClick);
  }, [open]);

  const marcarTodas = async () => {
    if (!noLeidas) return;
    try {
      await api.marcarLeidas();
      await cargar();
    } catch {
      /* ignore */
    }
  };

  return (
    <div className="relative" ref={ref}>
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative flex items-center rounded-md p-1.5 text-slate-500 hover:bg-slate-100 hover:text-slate-900"
        title="Notificaciones"
      >
        <Bell size={17} />
        {noLeidas > 0 && (
          <span className="absolute -right-0.5 -top-0.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-red-600 px-1 text-[10px] font-bold text-white">
            {noLeidas > 9 ? "9+" : noLeidas}
          </span>
        )}
      </button>

      {open && (
        <div className="absolute right-0 top-full z-40 mt-1 w-80 overflow-hidden rounded-lg border border-slate-200 bg-white shadow-lg">
          <div className="flex items-center justify-between border-b border-slate-100 px-3 py-2">
            <span className="text-[13px] font-semibold text-slate-700">Notificaciones</span>
            <button
              onClick={marcarTodas}
              disabled={noLeidas === 0}
              className="text-[11px] text-brand disabled:text-slate-300"
            >
              Marcar todas como leidas
            </button>
          </div>
          <div className="max-h-96 overflow-y-auto">
            {items.length === 0 ? (
              <p className="px-3 py-6 text-center text-[12px] text-slate-400">
                Sin notificaciones todavia.
              </p>
            ) : (
              items.map((n) => (
                <div
                  key={n.id}
                  className={`border-b border-slate-50 px-3 py-2 last:border-b-0 ${
                    n.leida ? "bg-white" : "bg-brand-50/50"
                  }`}
                >
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0 flex-1">
                      <p className="text-[12px] font-semibold text-slate-800">
                        {n.titulo}
                      </p>
                      {n.mensaje && (
                        <p className="mt-0.5 text-[11px] text-slate-500">{n.mensaje}</p>
                      )}
                    </div>
                    <span className="shrink-0 text-[10px] text-slate-400">
                      {tiempoRelativo(n.creado_en)}
                    </span>
                  </div>
                </div>
              ))
            )}
          </div>
          <Link
            href="/auditoria"
            onClick={() => setOpen(false)}
            className="block border-t border-slate-100 px-3 py-2 text-center text-[12px] text-brand hover:bg-slate-50"
          >
            Ver toda la auditoria
          </Link>
        </div>
      )}
    </div>
  );
}
