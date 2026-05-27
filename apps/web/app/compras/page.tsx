"use client";

import { useEffect, useState } from "react";
import { ChevronDown, Download, ShoppingCart, Truck } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Badge, colorABC } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoCLPCorto, formatoNumero } from "@/lib/formato";
import type { CarroProveedor, CarrosResponse } from "@/lib/types";

export default function ComprasPage() {
  const [data, setData] = useState<CarrosResponse | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [abierto, setAbierto] = useState<string | null>(null);
  const [exportando, setExportando] = useState<string | null>(null);

  useEffect(() => {
    (async () => {
      try {
        setData(await api.carros({ solo_pedir: true }));
      } catch (e) {
        setError(
          e instanceof Error
            ? `${e.message}. ¿Está corriendo el backend?`
            : "Error al cargar"
        );
      } finally {
        setCargando(false);
      }
    })();
  }, []);

  const exportar = async (proveedor?: string) => {
    setExportando(proveedor ?? "__all__");
    try {
      await api.exportOrden({ solo_pedir: true }, proveedor);
    } catch (e) {
      alert(e instanceof Error ? e.message : "No se pudo exportar");
    } finally {
      setExportando(null);
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="flex items-center gap-2 text-xl font-semibold tracking-tight text-slate-900">
            <ShoppingCart size={20} className="text-brand" /> Carros de compra
          </h1>
          <p className="text-[13px] text-slate-500">
            El sugerido agrupado por proveedor, listo para ordenar. La cantidad es la
            compra neta (descontando lo que se cubre con traslado desde el CD) más los
            ajustes manuales vigentes.
          </p>
        </div>
        {data && data.carros.length > 0 && (
          <Button onClick={() => exportar()} disabled={exportando !== null}>
            <Download size={15} />
            {exportando === "__all__" ? "Generando…" : "Exportar todas las órdenes"}
          </Button>
        )}
      </div>

      {/* KPIs */}
      {data && (
        <div className="grid grid-cols-3 gap-3">
          <Card className="px-4 py-3.5">
            <p className="text-[12px] font-medium uppercase tracking-wide text-slate-500">
              Proveedores
            </p>
            <p className="tabular text-xl font-semibold text-slate-900">
              {formatoNumero(data.total_proveedores)}
            </p>
          </Card>
          <Card className="px-4 py-3.5">
            <p className="text-[12px] font-medium uppercase tracking-wide text-slate-500">
              Unidades a comprar
            </p>
            <p className="tabular text-xl font-semibold text-slate-900">
              {formatoNumero(data.total_unidades)}
            </p>
          </Card>
          <Card className="px-4 py-3.5">
            <p className="text-[12px] font-medium uppercase tracking-wide text-slate-500">
              Valor total
            </p>
            <p className="tabular text-xl font-semibold text-emerald-700">
              {formatoCLP(data.total_clp)}
            </p>
          </Card>
        </div>
      )}

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          {error}
        </div>
      )}
      {cargando && <p className="text-slate-500">Cargando carros…</p>}
      {data && data.carros.length === 0 && !cargando && (
        <p className="text-slate-400">No hay nada que comprar con los filtros actuales.</p>
      )}

      {/* Carros por proveedor */}
      <div className="space-y-2">
        {data?.carros.map((carro) => (
          <CarroCard
            key={carro.proveedor}
            carro={carro}
            abierto={abierto === carro.proveedor}
            onToggle={() =>
              setAbierto(abierto === carro.proveedor ? null : carro.proveedor)
            }
            onExport={() => exportar(carro.proveedor)}
            exportando={exportando === carro.proveedor}
          />
        ))}
      </div>
    </div>
  );
}

function CarroCard({
  carro,
  abierto,
  onToggle,
  onExport,
  exportando,
}: {
  carro: CarroProveedor;
  abierto: boolean;
  onToggle: () => void;
  onExport: () => void;
  exportando: boolean;
}) {
  return (
    <Card>
      <div className="flex flex-wrap items-center gap-3 px-4 py-3">
        <button onClick={onToggle} className="flex flex-1 items-center gap-3 text-left">
          <ChevronDown
            size={18}
            className={`shrink-0 text-slate-400 transition-transform ${abierto ? "rotate-180" : ""}`}
          />
          <div className="flex h-9 w-9 items-center justify-center rounded-lg bg-brand-50">
            <Truck size={18} className="text-brand" />
          </div>
          <div className="min-w-0">
            <p className="truncate font-semibold text-slate-900">{carro.proveedor}</p>
            <p className="text-[12px] text-slate-500">
              {formatoNumero(carro.n_productos)} productos ·{" "}
              {formatoNumero(carro.total_unidades)} unidades
            </p>
          </div>
        </button>
        <div className="text-right">
          <p className="tabular text-lg font-semibold text-emerald-700">
            {formatoCLPCorto(carro.total_clp)}
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={onExport} disabled={exportando}>
          <Download size={14} />
          {exportando ? "…" : "Orden"}
        </Button>
      </div>

      {abierto && (
        <CardContent className="border-t border-slate-100 pt-3">
          <div className="overflow-x-auto">
            <table className="w-full text-[13px]">
              <thead>
                <tr className="border-b border-slate-100 text-left text-slate-500">
                  <th className="py-1.5 pr-3 font-medium">Producto</th>
                  <th className="py-1.5 pr-3 font-medium">Descripción</th>
                  <th className="py-1.5 pr-3 font-medium">ABC</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Cantidad</th>
                  <th className="py-1.5 pr-3 text-right font-medium">Costo</th>
                  <th className="py-1.5 text-right font-medium">Subtotal</th>
                </tr>
              </thead>
              <tbody>
                {carro.lineas.map((l) => (
                  <tr key={l.producto} className="border-b border-slate-50">
                    <td className="py-1.5 pr-3 font-medium text-slate-800">{l.producto}</td>
                    <td className="py-1.5 pr-3 text-slate-600">{l.descripcion ?? "—"}</td>
                    <td className="py-1.5 pr-3">
                      <Badge className={colorABC(l.clasificacion_abc)}>
                        {l.clasificacion_abc ?? "—"}
                      </Badge>
                    </td>
                    <td className="tabular py-1.5 pr-3 text-right font-semibold">
                      {formatoNumero(l.cantidad)}
                    </td>
                    <td className="tabular py-1.5 pr-3 text-right text-slate-600">
                      {formatoCLP(l.costo_unitario)}
                    </td>
                    <td className="tabular py-1.5 text-right font-medium text-slate-900">
                      {formatoCLP(l.subtotal_clp)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      )}
    </Card>
  );
}
