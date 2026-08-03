"use client";

/**
 * Carro del vendedor de sucursal. Reemplaza el correo al comprador.
 *
 * Poka-yoke, o sea: que el error no pueda ocurrir, no avisarlo después.
 *
 * - El código NO se escribe. Se busca en la lista de precios de Curifor y se
 *   elige de la lista. Un código inventado deja de ser posible.
 * - La sucursal tampoco se escribe: sale del usuario.
 * - Agregar dos veces el mismo producto SUMA la cantidad y marca la fila, en vez
 *   de dejar dos líneas iguales que el comprador tiene que interpretar.
 * - La cantidad no puede ser 0 ni negativa: el `−` se apaga en 1.
 * - Se confirma antes de enviar, con el total a la vista.
 * - Si hay carro armado y se intenta cerrar la pestaña, el navegador avisa.
 *
 * El que ya tiene la lista en un Excel la pega y se arma sola: si hubiera que
 * buscar producto por producto sería más trabajo que el correo, y volvería al
 * correo.
 */

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  AlertTriangle,
  ArrowLeft,
  Check,
  ClipboardPaste,
  Loader2,
  Minus,
  Plus,
  Search,
  Send,
  ShoppingCart,
  Trash2,
  X,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { api } from "@/lib/api-client";
import { getSucursales } from "@/lib/auth";
import { formatoCLP, formatoNumero } from "@/lib/formato";
import type { LineaCarroRequerimiento, MisSucursales, ProductoBuscado } from "@/lib/types";

/** Una línea pegada que además trae cantidad y si existe en la lista de precios. */
type Pegado = ProductoBuscado & {
  cantidad: number | null;
  encontrado: boolean;
  texto_original: string | null;
};

export default function NuevoRequerimientoPage() {
  const router = useRouter();

  const [permisos, setPermisos] = useState<MisSucursales | null>(null);
  const [sucursal, setSucursal] = useState<string>(() => getSucursales()[0] ?? "");

  const [q, setQ] = useState("");
  const [resultados, setResultados] = useState<ProductoBuscado[]>([]);
  const [buscando, setBuscando] = useState(false);

  const [carro, setCarro] = useState<LineaCarroRequerimiento[]>([]);
  const [resaltada, setResaltada] = useState<string | null>(null);
  const [nota, setNota] = useState("");

  const [pegarAbierto, setPegarAbierto] = useState(false);
  const [textoPegado, setTextoPegado] = useState("");
  const [noEncontrados, setNoEncontrados] = useState<string[]>([]);

  const [confirmando, setConfirmando] = useState(false);
  const [enviando, setEnviando] = useState(false);
  const [enviado, setEnviado] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);

  const buscadorRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    api
      .misSucursales()
      .then((p) => {
        setPermisos(p);
        if (!sucursal && p.sucursales.length === 1) setSucursal(p.sucursales[0]);
      })
      .catch(() => {});
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Buscador con espera: no se dispara una consulta por tecla.
  useEffect(() => {
    if (q.trim().length < 2) {
      setResultados([]);
      return;
    }
    const t = setTimeout(async () => {
      setBuscando(true);
      try {
        setResultados(await api.buscarProductos(q.trim(), sucursal || null));
      } catch {
        setResultados([]);
      } finally {
        setBuscando(false);
      }
    }, 250);
    return () => clearTimeout(t);
  }, [q, sucursal]);

  // Cerrar la pestaña con el carro armado pierde el trabajo: el navegador avisa.
  useEffect(() => {
    if (!carro.length || enviado) return;
    const aviso = (e: BeforeUnloadEvent) => {
      e.preventDefault();
      e.returnValue = "";
    };
    window.addEventListener("beforeunload", aviso);
    return () => window.removeEventListener("beforeunload", aviso);
  }, [carro.length, enviado]);

  const agregar = useCallback((p: ProductoBuscado, cantidad = 1) => {
    setCarro((prev) => {
      const i = prev.findIndex((l) => l.producto === p.producto);
      if (i >= 0) {
        // Repetido: se suma. Dos líneas iguales serían un problema del comprador.
        const copia = [...prev];
        copia[i] = { ...copia[i], cantidad: copia[i].cantidad + cantidad };
        return copia;
      }
      return [
        ...prev,
        {
          producto: p.producto,
          descripcion: p.descripcion,
          precio: p.precio,
          stock_sucursal: p.stock_sucursal,
          stock_nacional: p.stock_nacional,
          cantidad,
          comentario: null,
        },
      ];
    });
    setResaltada(p.producto);
    setTimeout(() => setResaltada(null), 1200);
  }, []);

  const cambiarCantidad = (producto: string, cantidad: number) =>
    setCarro((prev) =>
      prev.map((l) => (l.producto === producto ? { ...l, cantidad: Math.max(1, cantidad) } : l))
    );

  const quitar = (producto: string) =>
    setCarro((prev) => prev.filter((l) => l.producto !== producto));

  const pegar = async () => {
    if (!textoPegado.trim()) return;
    setError(null);
    try {
      const filas = (await api.pegarLista(textoPegado, sucursal || null)) as Pegado[];
      const encontrados = filas.filter((f) => f.encontrado);
      setNoEncontrados(filas.filter((f) => !f.encontrado).map((f) => f.producto));
      encontrados.forEach((f) => agregar(f, f.cantidad && f.cantidad > 0 ? f.cantidad : 1));
      setTextoPegado("");
      if (!filas.some((f) => !f.encontrado)) setPegarAbierto(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo leer la lista");
    }
  };

  const total = useMemo(
    () => carro.reduce((s, l) => s + l.cantidad * (l.precio ?? 0), 0),
    [carro]
  );

  const enviar = async () => {
    setEnviando(true);
    setError(null);
    try {
      const r = await api.crearRequerimiento({
        sucursal_id: sucursal || null,
        nota: nota.trim() || null,
        lineas: carro.map((l) => ({
          producto: l.producto,
          cantidad: l.cantidad,
          comentario: l.comentario,
        })),
      });
      setEnviado(r.id);
      setCarro([]);
      setNota("");
      setConfirmando(false);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo enviar el requerimiento");
      setConfirmando(false);
    } finally {
      setEnviando(false);
    }
  };

  // ------------------------------------------------------------------ enviado
  if (enviado !== null) {
    return (
      <div className="mx-auto max-w-[720px] space-y-4 py-10">
        <div className="rounded-sm border border-emerald-200 bg-emerald-50 p-6 text-center">
          <div className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-emerald-600 text-white">
            <Check size={24} />
          </div>
          <h1 className="display text-[24px] text-emerald-900">Requerimiento enviado</h1>
          <p className="mt-1 text-[13.5px] text-emerald-800">
            Quedó con el número <strong>#{enviado}</strong>. El comprador ya lo tiene en su
            bandeja; cuando lo abra vas a verlo marcado como revisado.
          </p>
          <div className="mt-5 flex justify-center gap-2">
            <Button onClick={() => router.push("/mis-requerimientos")}>
              Ver mis requerimientos
            </Button>
            <Button variant="outline" onClick={() => setEnviado(null)}>
              Hacer otro
            </Button>
          </div>
        </div>
      </div>
    );
  }

  const sinSucursal = permisos !== null && !sucursal && !permisos.puede_elegir;

  return (
    <div className="space-y-5 pb-24">
      <div>
        <Link
          href="/mis-requerimientos"
          className="inline-flex items-center gap-1 text-[13px] text-ink-500 hover:text-accent-700"
        >
          <ArrowLeft size={14} /> Mis requerimientos
        </Link>
        <p className="kicker mt-3">Sucursal</p>
        <h1 className="display text-[30px] leading-tight">Nuevo requerimiento</h1>
        <p className="mt-1 text-[13.5px] text-ink-500">
          Busca los repuestos que necesitas, arma la lista y envíala. El comprador la
          recibe al tiro, sin correo de por medio.
        </p>
      </div>

      {/* Sucursal: se muestra, no se escribe. */}
      <div className="flex flex-wrap items-center gap-3 rounded-sm border border-ink-200 bg-white px-4 py-3 shadow-card">
        <span className="text-[12px] font-medium text-ink-600">Pides para</span>
        {permisos?.puede_elegir ? (
          <select
            value={sucursal}
            onChange={(e) => setSucursal(e.target.value)}
            className="h-9 rounded-sm border border-ink-200 bg-paper-50 px-3 text-[13.5px]"
          >
            <option value="">Elige tu sucursal…</option>
            {(permisos?.sucursales ?? []).map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        ) : (
          <span className="rounded-sm bg-brand px-2.5 py-1 text-[13px] font-medium text-paper">
            {sucursal || "—"}
          </span>
        )}
        {sinSucursal && (
          <span className="text-[12.5px] text-red-700">
            Tu usuario no tiene sucursal asignada. Pídele a un administrador que te la
            configure.
          </span>
        )}
      </div>

      {/* Buscador: la única forma de meter un producto al carro. */}
      <div className="rounded-sm border border-ink-200 bg-white p-4 shadow-card">
        <label className="block">
          <span className="mb-1 block text-[12px] font-medium text-ink-600">
            Busca el repuesto por código o por nombre
          </span>
          <div className="relative">
            <Search
              size={16}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-ink-400"
            />
            <input
              ref={buscadorRef}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Ej: SZ6Z3B437B, filtro de aceite, 2723982…"
              className="h-11 w-full rounded-sm border border-ink-200 bg-paper-50 pl-9 pr-9 text-[14px] focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none"
            />
            {buscando && (
              <Loader2
                size={16}
                className="absolute right-3 top-1/2 -translate-y-1/2 animate-spin text-ink-400"
              />
            )}
            {!buscando && q && (
              <button
                onClick={() => setQ("")}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-ink-400 hover:text-ink-700"
                aria-label="Limpiar búsqueda"
              >
                <X size={16} />
              </button>
            )}
          </div>
        </label>

        {q.trim().length >= 2 && !buscando && resultados.length === 0 && (
          <p className="mt-3 rounded-sm bg-amber-50 px-3 py-2 text-[13px] text-amber-800">
            No hay ningún repuesto con eso en la lista de precios de Curifor. Revisa el
            código o búscalo por el nombre.
          </p>
        )}

        {resultados.length > 0 && (
          <ul className="mt-3 max-h-[320px] divide-y divide-ink-100 overflow-y-auto rounded-sm border border-ink-100">
            {resultados.map((p) => {
              const yaEsta = carro.some((l) => l.producto === p.producto);
              return (
                <li
                  key={p.producto}
                  className="flex items-center gap-3 px-3 py-2 hover:bg-paper-50"
                >
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center gap-2">
                      <span className="font-mono text-[13px] font-medium text-ink-900">
                        {p.producto}
                      </span>
                      {yaEsta && (
                        <span className="rounded-sm bg-emerald-50 px-1.5 py-0.5 text-[11px] font-medium text-emerald-700">
                          ya está en tu lista
                        </span>
                      )}
                    </div>
                    <p className="truncate text-[12.5px] text-ink-500">
                      {p.descripcion ?? "—"}
                    </p>
                  </div>
                  <div className="hidden shrink-0 text-right text-[12px] text-ink-500 sm:block">
                    <div className="tabular">{formatoCLP(p.precio)}</div>
                    <div className="text-[11.5px]">
                      stock acá: {formatoNumero(p.stock_sucursal ?? 0)}
                    </div>
                  </div>
                  <Button size="sm" onClick={() => agregar(p)} className="shrink-0">
                    <Plus size={14} /> Agregar
                  </Button>
                </li>
              );
            })}
          </ul>
        )}

        {/* Pegar la lista: para el que ya la tiene armada. */}
        <div className="mt-3 border-t border-ink-100 pt-3">
          <button
            onClick={() => setPegarAbierto((v) => !v)}
            className="inline-flex items-center gap-1.5 text-[13px] text-ink-500 hover:text-accent-700"
          >
            <ClipboardPaste size={14} />
            {pegarAbierto ? "Cerrar" : "¿Ya tienes la lista? Pégala acá"}
          </button>
          {pegarAbierto && (
            <div className="mt-2">
              <textarea
                value={textoPegado}
                onChange={(e) => setTextoPegado(e.target.value)}
                rows={5}
                spellCheck={false}
                placeholder={"Pega código y cantidad, como venga:\n19 SZ6Z3B437B\t4\n70 2723982\t2"}
                className="w-full rounded-sm border border-ink-200 bg-paper-50 p-3 font-mono text-[13px] leading-relaxed placeholder:text-ink-300 focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none"
              />
              <div className="mt-2 flex items-center gap-2">
                <Button size="sm" onClick={pegar} disabled={!textoPegado.trim()}>
                  Agregar a mi lista
                </Button>
                <span className="text-[12px] text-ink-400">
                  Da igual el separador y si trae encabezado.
                </span>
              </div>
              {noEncontrados.length > 0 && (
                <div className="mt-2 rounded-sm border border-red-200 bg-red-50 px-3 py-2 text-[12.5px] text-red-800">
                  <p className="font-medium">
                    Estos códigos no existen en la lista de precios y no se agregaron:
                  </p>
                  <p className="mt-1 font-mono">{noEncontrados.join(" · ")}</p>
                </div>
              )}
            </div>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded-sm border border-red-200 bg-red-50 px-4 py-3 text-[13px] text-red-800">
          {error}
        </div>
      )}

      {/* El carro */}
      <div className="rounded-sm border border-ink-200 bg-white shadow-card">
        <div className="flex items-center gap-2 border-b border-ink-200 px-4 py-3">
          <ShoppingCart size={16} className="text-ink-500" />
          <h2 className="text-[14px] font-semibold">
            Mi lista {carro.length > 0 && <span className="text-ink-400">({carro.length})</span>}
          </h2>
          {carro.length > 0 && (
            <button
              onClick={() => setCarro([])}
              className="ml-auto inline-flex items-center gap-1 text-[12.5px] text-ink-400 hover:text-red-700"
            >
              <Trash2 size={13} /> Vaciar
            </button>
          )}
        </div>

        {carro.length === 0 ? (
          <p className="px-4 py-10 text-center text-[13.5px] text-ink-400">
            Todavía no agregas nada. Busca arriba el repuesto que necesitas.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full min-w-[720px] text-[13px]">
              <thead>
                <tr className="border-b border-ink-200 bg-paper-50 text-left text-[11.5px] uppercase tracking-wide text-ink-500">
                  <th className="px-3 py-2">Código</th>
                  <th className="px-3 py-2">Descripción</th>
                  <th className="px-3 py-2 text-right">Stock acá</th>
                  <th className="px-3 py-2 text-center">Cantidad</th>
                  <th className="px-3 py-2 text-right">Subtotal</th>
                  <th className="w-10 px-3 py-2"></th>
                </tr>
              </thead>
              <tbody>
                {carro.map((l) => (
                  <tr
                    key={l.producto}
                    className={`border-b border-ink-100 transition-colors ${
                      resaltada === l.producto ? "bg-emerald-50" : ""
                    }`}
                  >
                    <td className="px-3 py-2 font-mono font-medium">{l.producto}</td>
                    <td className="max-w-[320px] truncate px-3 py-2 text-ink-600">
                      {l.descripcion ?? "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular text-ink-500">
                      {formatoNumero(l.stock_sucursal ?? 0)}
                    </td>
                    <td className="px-3 py-2">
                      <div className="mx-auto flex w-[124px] items-center justify-center gap-1">
                        <button
                          onClick={() => cambiarCantidad(l.producto, l.cantidad - 1)}
                          disabled={l.cantidad <= 1}
                          className="flex h-7 w-7 items-center justify-center rounded-sm border border-ink-200 text-ink-600 hover:bg-ink-100 disabled:opacity-30"
                          aria-label="Quitar uno"
                        >
                          <Minus size={13} />
                        </button>
                        <input
                          type="number"
                          min={1}
                          value={l.cantidad}
                          onChange={(e) =>
                            cambiarCantidad(l.producto, Number(e.target.value) || 1)
                          }
                          className="h-7 w-14 rounded-sm border border-ink-200 bg-paper-50 text-center tabular text-[13px] focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none"
                        />
                        <button
                          onClick={() => cambiarCantidad(l.producto, l.cantidad + 1)}
                          className="flex h-7 w-7 items-center justify-center rounded-sm border border-ink-200 text-ink-600 hover:bg-ink-100"
                          aria-label="Agregar uno"
                        >
                          <Plus size={13} />
                        </button>
                      </div>
                    </td>
                    <td className="px-3 py-2 text-right tabular">
                      {formatoCLP(l.cantidad * (l.precio ?? 0))}
                    </td>
                    <td className="px-3 py-2">
                      <button
                        onClick={() => quitar(l.producto)}
                        className="text-ink-300 transition-colors hover:text-red-700"
                        aria-label={`Quitar ${l.producto}`}
                      >
                        <Trash2 size={15} />
                      </button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>

      {carro.length > 0 && (
        <div className="rounded-sm border border-ink-200 bg-white p-4 shadow-card">
          <label className="block">
            <span className="mb-1 block text-[12px] font-medium text-ink-600">
              ¿Algo que el comprador deba saber? (opcional)
            </span>
            <textarea
              value={nota}
              onChange={(e) => setNota(e.target.value)}
              rows={2}
              placeholder="Ej: es para una mantención del jueves, el cliente ya lo pagó."
              className="w-full rounded-sm border border-ink-200 bg-paper-50 p-3 text-[13.5px] placeholder:text-ink-300 focus-visible:border-accent-700 focus-visible:bg-white focus-visible:outline-none"
            />
          </label>
        </div>
      )}

      {/* Barra fija: el total y el envío siempre a la vista. */}
      {carro.length > 0 && (
        <div className="fixed bottom-0 left-0 right-0 z-20 border-t border-ink-200 bg-white/95 backdrop-blur">
          <div className="mx-auto flex max-w-[1600px] items-center gap-4 px-4 py-3">
            <div className="text-[13px] text-ink-500">
              <strong className="text-ink-900">{carro.length}</strong>{" "}
              {carro.length === 1 ? "repuesto" : "repuestos"} ·{" "}
              <strong className="text-ink-900">
                {formatoNumero(carro.reduce((s, l) => s + l.cantidad, 0))}
              </strong>{" "}
              unidades
            </div>
            <div className="ml-auto text-[13px] text-ink-500">
              Total aprox.{" "}
              <strong className="text-[15px] text-ink-900">{formatoCLP(total)}</strong>
            </div>
            <Button onClick={() => setConfirmando(true)} disabled={!sucursal || enviando}>
              <Send size={15} /> Enviar requerimiento
            </Button>
          </div>
        </div>
      )}

      {/* Confirmación: enviar es irreversible para la sucursal, así que se pregunta. */}
      {confirmando && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink-900/50 p-4 backdrop-blur-sm">
          <div className="w-full max-w-[440px] rounded-sm border border-ink-200 bg-white p-5 shadow-2xl">
            <h3 className="display text-[19px]">¿Enviar el requerimiento?</h3>
            <p className="mt-2 text-[13.5px] text-ink-600">
              Vas a pedir <strong>{carro.length}</strong>{" "}
              {carro.length === 1 ? "repuesto" : "repuestos"} para{" "}
              <strong>{sucursal}</strong>, por unos <strong>{formatoCLP(total)}</strong>.
            </p>
            <p className="mt-2 text-[12.5px] text-ink-400">
              Una vez enviado no lo puedes editar. Si te falta algo, haces otro.
            </p>
            <div className="mt-5 flex justify-end gap-2">
              <Button variant="outline" onClick={() => setConfirmando(false)} disabled={enviando}>
                Volver
              </Button>
              <Button onClick={enviar} disabled={enviando}>
                {enviando ? <Loader2 size={15} className="animate-spin" /> : <Send size={15} />}
                {enviando ? "Enviando…" : "Sí, enviar"}
              </Button>
            </div>
          </div>
        </div>
      )}

      {sinSucursal && (
        <div className="flex items-start gap-2 rounded-sm border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-900">
          <AlertTriangle size={15} className="mt-0.5 shrink-0" />
          <span>
            Sin sucursal asignada no puedes enviar requerimientos: el comprador no sabría
            para dónde es.
          </span>
        </div>
      )}
    </div>
  );
}
