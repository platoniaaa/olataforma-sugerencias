"use client";

/**
 * El comprador resuelve un requerimiento de sucursal.
 *
 * Trae el MISMO contexto que la pantalla de pegar lista (frecuencia de venta,
 * stock acá y nacional, clase ABC, lo que el modelo ya sugiere): no hay dos
 * formas de mirar un requerimiento según por dónde entró.
 *
 * El archivo del portal es OPCIONAL. Hay requerimientos que se resuelven con
 * stock del CD o con un traslado y no se compran a nadie; obligar a bajar un CSV
 * para poder cerrar el requerimiento sería inventarle un paso.
 */

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { AlertTriangle, ArrowLeft, Check, Download, Loader2, X } from "lucide-react";
import { Button } from "@/components/ui/button";
import { EstadoRequerimientoBadge } from "@/components/estado-requerimiento";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { LineaGuardada, Requerimiento } from "@/lib/types";

/** Frecuencia 3/6/12 en una celda, que es como se lee de un vistazo. */
function Frecuencia({ linea }: { linea: LineaGuardada }) {
  const a = linea.analisis;
  if (!a || a.meses_con_venta_12m === null) {
    const otra = a?.frecuencia_otra_sucursal;
    return otra ? (
      <span className="text-[11.5px] text-amber-800">
        acá nunca · {otra.nombre_sucursal} {otra.meses_con_venta_12m}/12
      </span>
    ) : (
      <span className="text-ink-300">—</span>
    );
  }
  const m12 = a.meses_con_venta_12m ?? 0;
  const color = m12 >= 9 ? "text-emerald-700" : m12 >= 4 ? "text-ink-900" : "text-ink-400";
  return (
    <span className={`tabular ${color}`}>
      {a.meses_con_venta_3m}/{a.meses_con_venta_6m}/<strong>{m12}</strong>
    </span>
  );
}

export default function RevisarRequerimientoPage() {
  const params = useParams<{ id: string }>();
  const id = Number(params?.id);

  const [req, setReq] = useState<Requerimiento | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [cerrando, setCerrando] = useState<"procesado" | "rechazado" | null>(null);

  /** Cantidades editadas en pantalla (por id de línea). */
  const [cantidades, setCantidades] = useState<Record<number, number>>({});
  const [nota, setNota] = useState("");

  useEffect(() => {
    if (!id) return;
    api
      .requerimiento(id)
      .then((r) => {
        setReq(r);
        setNota(r.nota_comprador ?? "");
        setCantidades(
          Object.fromEntries(
            r.lineas.map((l) => [l.id, l.cantidad_aprobada ?? l.cantidad_pedida])
          )
        );
      })
      .catch((e) => setError(e instanceof Error ? e.message : "No se pudo cargar"));
  }, [id]);

  const cerrado = req?.estado === "procesado" || req?.estado === "rechazado";

  /** Lo que de verdad se compra: cantidad > 0. Es lo que va al archivo del portal. */
  const aComprar = useMemo(
    () =>
      (req?.lineas ?? [])
        .filter((l) => (cantidades[l.id] ?? l.cantidad_pedida) > 0)
        .map((l) => ({ producto: l.producto, cantidad: cantidades[l.id] ?? l.cantidad_pedida })),
    [req, cantidades]
  );

  const total = useMemo(
    () =>
      (req?.lineas ?? []).reduce(
        (s, l) => s + (cantidades[l.id] ?? l.cantidad_pedida) * (l.precio_lista ?? 0),
        0
      ),
    [req, cantidades]
  );

  const guardar = async (estado?: "procesado" | "rechazado") => {
    if (!req) return;
    setGuardando(true);
    setError(null);
    setAviso(null);
    try {
      const r = await api.actualizarRequerimiento(req.id, {
        estado,
        nota_comprador: nota.trim() || null,
        cantidades: req.lineas.map((l) => ({
          linea_id: l.id,
          cantidad: cantidades[l.id] ?? l.cantidad_pedida,
        })),
      });
      setReq({ ...r, lineas: req.lineas.map((l, i) => ({ ...r.lineas[i], analisis: l.analisis })) });
      setAviso(estado ? "Requerimiento cerrado." : "Cambios guardados.");
      setCerrando(null);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
      setCerrando(null);
    } finally {
      setGuardando(false);
    }
  };

  const bajarArchivo = async (proveedor: "FORD" | "GILDEMEISTER") => {
    if (!req) return;
    setError(null);
    try {
      const fuera = await api.archivoPortal(proveedor, req.sucursal_id, aComprar);
      setAviso(
        fuera > 0
          ? `Archivo descargado. ${fuera} ${fuera === 1 ? "línea quedó fuera" : "líneas quedaron fuera"}: sin equivalencia en el portal o sin cantidad.`
          : "Archivo descargado con todas las líneas."
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo generar el archivo");
    }
  };

  if (error && !req) {
    return (
      <div className="rounded-sm border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
        {error}
      </div>
    );
  }
  if (!req) {
    return (
      <div className="flex items-center gap-2 px-4 py-10 text-[13.5px] text-ink-400">
        <Loader2 size={15} className="animate-spin" /> Cargando…
      </div>
    );
  }

  return (
    <div className="space-y-5 pb-24">
      <div>
        <Link
          href="/requerimientos"
          className="inline-flex items-center gap-1 text-[13px] text-ink-500 hover:text-accent-700"
        >
          <ArrowLeft size={14} /> Requerimientos
        </Link>
        <div className="mt-3 flex flex-wrap items-center gap-3">
          <h1 className="display text-[30px] leading-tight">Requerimiento #{req.id}</h1>
          <EstadoRequerimientoBadge estado={req.estado} />
        </div>
        <p className="mt-1 text-[13.5px] text-ink-500">
          <strong className="text-ink-700">{req.nombre_sucursal}</strong> ·{" "}
          {req.creado_por_nombre ?? req.creado_por} · {formatoFechaHora(req.creado_en)}
        </p>
      </div>

      {req.nota && (
        <div className="rounded-sm border border-ink-200 bg-paper-50 px-4 py-3 text-[13px]">
          <p className="text-[11.5px] uppercase tracking-wide text-ink-400">
            Nota del vendedor
          </p>
          <p className="mt-1 text-ink-700">{req.nota}</p>
        </div>
      )}

      {aviso && (
        <div className="rounded-sm border border-emerald-200 bg-emerald-50 px-4 py-3 text-[13px] text-emerald-800">
          {aviso}
        </div>
      )}
      {error && (
        <div className="rounded-sm border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
          {error}
        </div>
      )}

      {/* La tabla de decisión: mismo contexto que la pantalla de pegar lista. */}
      <div className="overflow-x-auto rounded-sm border border-ink-200 bg-white shadow-card">
        <table className="w-full min-w-[1040px] text-[13px]">
          <thead>
            <tr className="border-b border-ink-200 bg-paper-50 text-left text-[11.5px] uppercase tracking-wide text-ink-500">
              <th className="px-3 py-2">Código</th>
              <th className="px-3 py-2">Descripción</th>
              <th className="px-3 py-2">ABC</th>
              <th className="px-3 py-2" title="Meses con venta de los últimos 3 / 6 / 12">
                Frecuencia
              </th>
              <th className="px-3 py-2 text-right">Stock suc.</th>
              <th className="px-3 py-2 text-right">Stock CD</th>
              <th className="px-3 py-2 text-right">Ya sugerido</th>
              <th className="px-3 py-2 text-right">Pidió</th>
              <th className="px-3 py-2 text-center">Se compra</th>
              <th className="px-3 py-2 text-right">Subtotal</th>
            </tr>
          </thead>
          <tbody>
            {req.lineas.map((l) => {
              const a = l.analisis;
              const cantidad = cantidades[l.id] ?? l.cantidad_pedida;
              return (
                <tr
                  key={l.id}
                  className={`border-b border-ink-100 ${cantidad === 0 ? "opacity-45" : ""}`}
                >
                  <td className="px-3 py-2 font-mono font-medium">{l.producto}</td>
                  <td className="max-w-[260px] truncate px-3 py-2 text-ink-600">
                    {l.descripcion ?? "—"}
                    {l.comentario && (
                      <span className="block text-[12px] text-ink-400">{l.comentario}</span>
                    )}
                  </td>
                  <td className="px-3 py-2">
                    {a?.clasificacion_abc ?? <span className="text-ink-300">—</span>}
                  </td>
                  <td className="px-3 py-2">
                    <Frecuencia linea={l} />
                  </td>
                  <td className="px-3 py-2 text-right tabular">
                    {formatoNumero(a?.stock_sucursal ?? 0)}
                  </td>
                  <td className="px-3 py-2 text-right tabular text-ink-500">
                    {formatoNumero(a?.stock_cd ?? 0)}
                  </td>
                  <td className="px-3 py-2 text-right tabular text-ink-500">
                    {a?.total_sugerido_suc ? formatoNumero(a.total_sugerido_suc) : "—"}
                  </td>
                  <td className="px-3 py-2 text-right tabular font-medium">
                    {formatoNumero(l.cantidad_pedida)}
                  </td>
                  <td className="px-3 py-2">
                    <input
                      type="number"
                      min={0}
                      disabled={cerrado}
                      value={cantidad}
                      onChange={(e) =>
                        setCantidades((prev) => ({
                          ...prev,
                          [l.id]: Math.max(0, Number(e.target.value) || 0),
                        }))
                      }
                      className="mx-auto block h-8 w-20 rounded-sm border border-ink-200 bg-paper-50 text-center tabular text-[13px] disabled:opacity-60 focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none"
                    />
                  </td>
                  <td className="px-3 py-2 text-right tabular">
                    {formatoCLP(cantidad * (l.precio_lista ?? 0))}
                  </td>
                </tr>
              );
            })}
          </tbody>
          <tfoot>
            <tr className="bg-paper-50 text-[13px] font-medium">
              <td className="px-3 py-2" colSpan={9}>
                {aComprar.length} de {req.lineas.length} líneas se compran
              </td>
              <td className="px-3 py-2 text-right tabular">{formatoCLP(total)}</td>
            </tr>
          </tfoot>
        </table>
      </div>

      {/* Archivo del portal: opcional. */}
      <div className="rounded-sm border border-ink-200 bg-white p-4 shadow-card">
        <p className="text-[13px] font-medium">Archivo para el portal (opcional)</p>
        <p className="mt-1 text-[12.5px] text-ink-500">
          Sale con las cantidades de la columna <strong>Se compra</strong> y los códigos ya
          convertidos al formato de cada portal. Si el requerimiento se resuelve con stock
          del CD o con un traslado, no lo necesitas.
        </p>
        <div className="mt-3 flex flex-wrap gap-2">
          <Button
            variant="outline"
            onClick={() => bajarArchivo("FORD")}
            disabled={aComprar.length === 0}
          >
            <Download size={15} /> Ford
          </Button>
          <Button
            variant="outline"
            onClick={() => bajarArchivo("GILDEMEISTER")}
            disabled={aComprar.length === 0}
          >
            <Download size={15} /> Gildemeister
          </Button>
        </div>
      </div>

      {/* Respuesta al vendedor + cierre. */}
      <div className="rounded-sm border border-ink-200 bg-white p-4 shadow-card">
        <label className="block">
          <span className="mb-1 block text-[12px] font-medium text-ink-600">
            Respuesta al vendedor
            {cerrando === "rechazado" && (
              <span className="ml-1 text-red-700">· obligatoria para rechazar</span>
            )}
          </span>
          <textarea
            value={nota}
            onChange={(e) => setNota(e.target.value)}
            rows={2}
            disabled={cerrado}
            placeholder="Ej: los 3 filtros salen del CD, el resto se pidió a Ford."
            className="w-full rounded-sm border border-ink-200 bg-paper-50 p-3 text-[13.5px] placeholder:text-ink-300 disabled:opacity-60 focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none"
          />
        </label>
      </div>

      {cerrado ? (
        <div className="flex items-start gap-2 rounded-sm border border-ink-200 bg-paper-50 px-4 py-3 text-[13px] text-ink-600">
          <Check size={15} className="mt-0.5 shrink-0 text-emerald-600" />
          <span>
            Este requerimiento ya está cerrado ({req.estado === "procesado" ? "comprado" : "rechazado"})
            {req.revisado_en && ` el ${formatoFechaHora(req.revisado_en)}`}. Queda como
            registro de lo que se decidió y no se modifica.
          </span>
        </div>
      ) : (
        <div className="fixed bottom-0 left-0 right-0 z-20 border-t border-ink-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-[1600px] flex-wrap items-center gap-3 px-4 py-3">
            <span className="text-[13px] text-ink-500">
              A comprar: <strong className="text-ink-900">{aComprar.length}</strong> líneas ·{" "}
              <strong className="text-ink-900">{formatoCLP(total)}</strong>
            </span>
            <div className="ml-auto flex flex-wrap gap-2">
              <Button variant="outline" onClick={() => guardar()} disabled={guardando}>
                {guardando ? <Loader2 size={15} className="animate-spin" /> : null}
                Guardar sin cerrar
              </Button>
              <Button
                variant="outline"
                onClick={() => setCerrando("rechazado")}
                disabled={guardando}
                className="border-red-200 text-red-700 hover:border-red-300 hover:bg-red-50"
              >
                <X size={15} /> Rechazar
              </Button>
              <Button onClick={() => setCerrando("procesado")} disabled={guardando}>
                <Check size={15} /> Marcar como comprado
              </Button>
            </div>
          </div>
        </div>
      )}

      {/* Cerrar es irreversible: se pregunta. */}
      {cerrando && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-[440px] rounded-sm border border-ink-200 bg-white p-5 shadow-2xl">
            <h3 className="display text-[19px]">
              {cerrando === "procesado"
                ? "¿Marcar como comprado?"
                : "¿Rechazar el requerimiento?"}
            </h3>
            <p className="mt-2 text-[13.5px] text-ink-600">
              {cerrando === "procesado" ? (
                <>
                  Se cierra con <strong>{aComprar.length}</strong> líneas por{" "}
                  <strong>{formatoCLP(total)}</strong>. El vendedor va a ver qué le
                  aprobaste de cada una.
                </>
              ) : (
                <>
                  El vendedor va a ver el rechazo y tu respuesta. Sin motivo no se puede
                  rechazar: tendría que preguntarte por correo, que es lo que estamos
                  sacando.
                </>
              )}
            </p>
            {cerrando === "rechazado" && !nota.trim() && (
              <div className="mt-3 flex items-start gap-2 rounded-sm border border-amber-200 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
                <AlertTriangle size={14} className="mt-0.5 shrink-0" />
                <span>Escribe la respuesta al vendedor antes de rechazar.</span>
              </div>
            )}
            <p className="mt-3 text-[12.5px] text-ink-400">
              Después de cerrarlo no se puede modificar.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setCerrando(null)} disabled={guardando}>
                Volver
              </Button>
              <Button
                onClick={() => guardar(cerrando)}
                disabled={guardando || (cerrando === "rechazado" && !nota.trim())}
              >
                {guardando ? <Loader2 size={15} className="animate-spin" /> : null}
                {cerrando === "procesado" ? "Sí, comprado" : "Sí, rechazar"}
              </Button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
