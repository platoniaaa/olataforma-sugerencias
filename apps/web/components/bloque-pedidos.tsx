"use client";

// Cierre del loop: dejar registrado que esta linea del sugerido ya se pidio.
// Sin esto, al dia siguiente el mismo producto vuelve a aparecer como si nadie
// hubiera hecho nada y no hay forma de saber cuanto de lo sugerido se compro.
import { useCallback, useEffect, useState } from "react";
import { Check, ClipboardCheck, Trash2 } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { getSoloLectura } from "@/lib/auth";
import { formatoFecha, formatoNumero } from "@/lib/formato";
import type { LineaPedida } from "@/lib/types";

export function BloquePedidos({
  producto,
  sucursalId,
  sugerido,
  proveedor,
}: {
  producto: string;
  sucursalId: string;
  sugerido: number;
  proveedor?: string | null;
}) {
  const [items, setItems] = useState<LineaPedida[]>([]);
  const [abierto, setAbierto] = useState(false);
  const [unidades, setUnidades] = useState(String(Math.round(sugerido) || ""));
  const [noc, setNoc] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [soloLectura, setSoloLectura] = useState(false);

  useEffect(() => setSoloLectura(getSoloLectura()), []);

  const cargar = useCallback(async () => {
    try {
      const r = await api.pedidos(producto, sucursalId);
      setItems(r.items);
    } catch {
      setItems([]);
    }
  }, [producto, sucursalId]);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const guardar = async () => {
    setGuardando(true);
    setError(null);
    try {
      await api.marcarPedido({
        producto,
        sucursal_id: sucursalId,
        unidades: Number(unidades) || 0,
        n_oc: noc.trim() || null,
        proveedor: proveedor ?? null,
      });
      setAbierto(false);
      setNoc("");
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo registrar");
    } finally {
      setGuardando(false);
    }
  };

  const borrar = async (id: string) => {
    await api.eliminarPedido(id);
    await cargar();
  };

  const pendientes = items.filter((i) => !i.recibido);
  const totalPendiente = pendientes.reduce((s, i) => s + i.unidades, 0);

  if (soloLectura && items.length === 0) return null;

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <ClipboardCheck size={17} /> Pedidos registrados
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        {items.length === 0 ? (
          <p className="text-[13px] text-slate-500">
            Nadie marcó esta línea como pedida todavía.
          </p>
        ) : (
          <>
            {totalPendiente > 0 && (
              <p className="text-[13px] text-slate-700">
                <span className="tabular font-semibold">{formatoNumero(totalPendiente)}</span>{" "}
                unidades pedidas y aún sin recibir.
              </p>
            )}
            <ul className="divide-y divide-slate-100 text-[13px]">
              {items.map((p) => (
                <li key={p.id} className="flex items-center justify-between gap-2 py-1.5">
                  <span>
                    <span className="tabular font-medium">{formatoNumero(p.unidades)}</span> u
                    {p.n_oc && <span className="text-slate-500"> · OC {p.n_oc}</span>}
                    <span className="text-slate-400"> · {formatoFecha(p.creado_en)}</span>
                    {p.recibido && (
                      <span className="ml-2 inline-flex items-center gap-1 rounded bg-emerald-50 px-1.5 py-0.5 text-[11px] font-semibold text-emerald-700">
                        <Check size={11} /> recibido
                      </span>
                    )}
                  </span>
                  {!soloLectura && (
                    <button
                      onClick={() => borrar(p.id)}
                      title="Eliminar"
                      className="rounded p-1 text-slate-400 hover:bg-red-50 hover:text-red-600"
                    >
                      <Trash2 size={13} />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </>
        )}

        {!soloLectura &&
          (abierto ? (
            <div className="space-y-2 rounded-md bg-slate-50 p-3">
              <div className="flex flex-wrap gap-2">
                <label className="flex-1">
                  <span className="mb-1 block text-[12px] text-slate-600">Unidades</span>
                  <input
                    type="number"
                    value={unidades}
                    onChange={(e) => setUnidades(e.target.value)}
                    className="w-full rounded-md border border-slate-300 px-2 py-1 text-[13px]"
                  />
                </label>
                <label className="flex-1">
                  <span className="mb-1 block text-[12px] text-slate-600">N° de OC (opcional)</span>
                  <input
                    value={noc}
                    onChange={(e) => setNoc(e.target.value)}
                    placeholder="0000005758"
                    className="w-full rounded-md border border-slate-300 px-2 py-1 text-[13px]"
                  />
                </label>
              </div>
              {error && <p className="text-[12px] text-red-700">{error}</p>}
              <div className="flex justify-end gap-2">
                <button
                  onClick={() => setAbierto(false)}
                  className="rounded-md border border-slate-200 px-3 py-1 text-[12px] hover:bg-white"
                >
                  Cancelar
                </button>
                <button
                  onClick={guardar}
                  disabled={guardando || !Number(unidades)}
                  className="rounded-md bg-brand px-3 py-1 text-[12px] font-medium text-white hover:bg-brand-700 disabled:opacity-50"
                >
                  {guardando ? "Guardando…" : "Registrar"}
                </button>
              </div>
            </div>
          ) : (
            <Button onClick={() => setAbierto(true)} className="w-full">
              <ClipboardCheck size={15} /> Marcar como pedido
            </Button>
          ))}
      </CardContent>
    </Card>
  );
}
