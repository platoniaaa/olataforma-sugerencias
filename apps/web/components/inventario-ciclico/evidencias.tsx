"use client";

// Evidencias de un producto: subir foto/PDF y abrirlas. El endpoint exige token,
// por eso cada archivo se baja como blob antes de mostrarlo.
import { useRef, useState } from "react";
import { Camera, FileText, Loader2, Trash2 } from "lucide-react";
import { inventarioApi, type ItemInventario } from "@/lib/inventario-ciclico";
import { getEmail } from "@/lib/auth";

interface Props {
  item: ItemInventario;
  puedeSubir: boolean;
  esAdmin: boolean;
  onCambio: (item: ItemInventario) => void;
}

export function Evidencias({ item, puedeSubir, esAdmin, onCambio }: Props) {
  const input = useRef<HTMLInputElement>(null);
  const [subiendo, setSubiendo] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const email = getEmail();

  const subir = async (archivos: FileList | null) => {
    if (!archivos?.length) return;
    setSubiendo(true);
    setError(null);
    try {
      let ultimo = item;
      for (const a of Array.from(archivos)) ultimo = await inventarioApi.subirEvidencia(item.id, a);
      onCambio(ultimo);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo subir");
    } finally {
      setSubiendo(false);
      if (input.current) input.current.value = "";
    }
  };

  const abrir = async (id: string) => {
    // La ventana se abre antes del await: si no, el navegador del celular la bloquea.
    const win = window.open("", "_blank");
    try {
      const url = await inventarioApi.urlEvidencia(id);
      if (win) win.location.href = url;
      else window.location.href = url;
    } catch (e) {
      win?.close();
      setError(e instanceof Error ? e.message : "No se pudo abrir");
    }
  };

  const borrar = async (id: string) => {
    if (!confirm("¿Borrar esta evidencia?")) return;
    try {
      await inventarioApi.borrarEvidencia(id);
      onCambio({ ...item, evidencias: item.evidencias.filter((e) => e.id !== id) });
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo borrar");
    }
  };

  return (
    <div className="space-y-1.5">
      {item.evidencias.length > 0 && (
        <ul className="flex flex-wrap gap-1.5">
          {item.evidencias.map((ev, n) => (
            <li key={ev.id} className="flex items-center rounded-sm border border-ink-200 bg-paper-100">
              <button
                type="button"
                onClick={() => abrir(ev.id)}
                className="flex items-center gap-1 px-2 py-1 text-[12px] text-ink-700 hover:text-brand"
                title={ev.nombre}
              >
                {ev.content_type === "application/pdf" ? <FileText size={13} /> : <Camera size={13} />}
                Evidencia {n + 1}
              </button>
              {puedeSubir && (esAdmin || ev.subido_por === email) && (
                <button
                  type="button"
                  onClick={() => borrar(ev.id)}
                  className="border-l border-ink-200 px-1.5 py-1 text-ink-400 hover:text-red-600"
                  aria-label="Borrar evidencia"
                >
                  <Trash2 size={12} />
                </button>
              )}
            </li>
          ))}
        </ul>
      )}
      {puedeSubir && (
        <>
          <input
            ref={input}
            type="file"
            accept="image/*,application/pdf"
            multiple
            className="hidden"
            onChange={(e) => subir(e.target.files)}
          />
          <button
            type="button"
            onClick={() => input.current?.click()}
            disabled={subiendo}
            className={`inline-flex items-center gap-1.5 rounded-sm border px-2.5 py-1.5 text-[12.5px] font-medium transition-colors disabled:opacity-60 ${
              item.requiere_evidencia && item.evidencias.length === 0
                ? "border-amber-300 bg-amber-50 text-amber-800 hover:bg-amber-100"
                : "border-ink-200 bg-white text-ink-700 hover:bg-paper-100"
            }`}
          >
            {subiendo ? <Loader2 size={14} className="animate-spin" /> : <Camera size={14} />}
            {subiendo ? "Subiendo…" : "Tomar foto / adjuntar"}
          </button>
        </>
      )}
      {error && <p className="text-[12px] text-red-700">{error}</p>}
    </div>
  );
}
