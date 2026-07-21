"use client";

// Documentos: enlaces directos a archivos que viven en SharePoint (ventas
// historicas, planillas de stock, etc.). La plataforma NO almacena los archivos:
// el clic abre SharePoint y los permisos de la biblioteca siguen mandando.
import { useEffect, useMemo, useState } from "react";
import {
  ExternalLink,
  EyeOff,
  FolderOpen,
  Pencil,
  Plus,
  RefreshCw,
  Trash2,
  X,
} from "lucide-react";
import { api } from "@/lib/api-client";
import { getEsAdmin } from "@/lib/auth";
import type { Documento } from "@/lib/types";

const FORM_VACIO = { titulo: "", url: "", descripcion: "", categoria: "" };

export default function DocumentosPage() {
  const esAdmin = getEsAdmin();
  const [items, setItems] = useState<Documento[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Formulario (crear o editar). editando=null -> crear.
  const [mostrarForm, setMostrarForm] = useState(false);
  const [editando, setEditando] = useState<Documento | null>(null);
  const [form, setForm] = useState(FORM_VACIO);
  const [guardando, setGuardando] = useState(false);
  const [errorForm, setErrorForm] = useState<string | null>(null);

  const cargar = async () => {
    setCargando(true);
    setError(null);
    try {
      setItems(await api.documentos(esAdmin));
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    } finally {
      setCargando(false);
    }
  };

  useEffect(() => {
    cargar();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const categorias = useMemo(() => {
    const orden: string[] = [];
    const por: Record<string, Documento[]> = {};
    for (const d of items) {
      if (!por[d.categoria]) {
        por[d.categoria] = [];
        orden.push(d.categoria);
      }
      por[d.categoria].push(d);
    }
    return orden.map((c) => ({ nombre: c, docs: por[c] }));
  }, [items]);

  const abrirCrear = () => {
    setEditando(null);
    setForm(FORM_VACIO);
    setErrorForm(null);
    setMostrarForm(true);
  };

  const abrirEditar = (d: Documento) => {
    setEditando(d);
    setForm({
      titulo: d.titulo,
      url: d.url,
      descripcion: d.descripcion ?? "",
      categoria: d.categoria,
    });
    setErrorForm(null);
    setMostrarForm(true);
  };

  const guardar = async () => {
    setGuardando(true);
    setErrorForm(null);
    try {
      const payload = {
        titulo: form.titulo.trim(),
        url: form.url.trim(),
        descripcion: form.descripcion.trim() || null,
        categoria: form.categoria.trim() || "General",
      };
      if (editando) {
        await api.editarDocumento(editando.id, payload);
      } else {
        await api.crearDocumento(payload);
      }
      setMostrarForm(false);
      await cargar();
    } catch (e) {
      setErrorForm(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  };

  const eliminar = async (d: Documento) => {
    if (!window.confirm(`¿Eliminar el enlace "${d.titulo}"?`)) return;
    try {
      await api.eliminarDocumento(d.id);
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo eliminar");
    }
  };

  const alternarActivo = async (d: Documento) => {
    try {
      await api.editarDocumento(d.id, { activo: !d.activo });
      await cargar();
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo actualizar");
    }
  };

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-baseline justify-between gap-3">
        <div>
          <h1 className="text-xl font-semibold tracking-tight text-slate-900">
            Documentos
          </h1>
          <p className="text-[13px] text-slate-500">
            Archivos compartidos en SharePoint: se abren con tu cuenta corporativa.
          </p>
        </div>
        <div className="flex items-center gap-2">
          {esAdmin && (
            <button
              onClick={abrirCrear}
              className="inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700"
            >
              <Plus size={14} /> Nuevo enlace
            </button>
          )}
          <button
            onClick={cargar}
            className="inline-flex items-center gap-1.5 rounded-md border border-slate-200 bg-white px-3 py-1.5 text-[13px] hover:bg-slate-50"
          >
            <RefreshCw size={14} /> Actualizar
          </button>
        </div>
      </div>

      {error && (
        <p className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">{error}</p>
      )}

      {mostrarForm && esAdmin && (
        <div className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
          <div className="mb-3 flex items-center justify-between">
            <h2 className="text-[14px] font-semibold text-slate-900">
              {editando ? "Editar enlace" : "Nuevo enlace"}
            </h2>
            <button
              onClick={() => setMostrarForm(false)}
              className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
              aria-label="Cerrar"
            >
              <X size={16} />
            </button>
          </div>
          <div className="grid gap-3 md:grid-cols-2">
            <label className="block">
              <span className="mb-1 block text-[12px] font-medium text-slate-600">Título *</span>
              <input
                value={form.titulo}
                onChange={(e) => setForm({ ...form, titulo: e.target.value })}
                placeholder="Ventas 2024"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px] focus:border-brand focus:outline-none"
              />
            </label>
            <label className="block">
              <span className="mb-1 block text-[12px] font-medium text-slate-600">Categoría</span>
              <input
                value={form.categoria}
                onChange={(e) => setForm({ ...form, categoria: e.target.value })}
                placeholder="Ventas históricas"
                list="categorias-existentes"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px] focus:border-brand focus:outline-none"
              />
              <datalist id="categorias-existentes">
                {categorias.map((c) => (
                  <option key={c.nombre} value={c.nombre} />
                ))}
              </datalist>
            </label>
            <label className="block md:col-span-2">
              <span className="mb-1 block text-[12px] font-medium text-slate-600">
                URL de SharePoint *
              </span>
              <input
                value={form.url}
                onChange={(e) => setForm({ ...form, url: e.target.value })}
                placeholder="https://curifor.sharepoint.com/..."
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 font-mono text-[12px] focus:border-brand focus:outline-none"
              />
            </label>
            <label className="block md:col-span-2">
              <span className="mb-1 block text-[12px] font-medium text-slate-600">Descripción</span>
              <input
                value={form.descripcion}
                onChange={(e) => setForm({ ...form, descripcion: e.target.value })}
                placeholder="Ventas transaccionales Curifor + Frontera del año completo"
                className="w-full rounded-md border border-slate-300 px-3 py-1.5 text-[13px] focus:border-brand focus:outline-none"
              />
            </label>
          </div>
          {errorForm && (
            <p className="mt-2 rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">
              {errorForm}
            </p>
          )}
          <div className="mt-3 flex justify-end gap-2">
            <button
              onClick={() => setMostrarForm(false)}
              className="rounded-md border border-slate-200 px-3 py-1.5 text-[13px] hover:bg-slate-50"
            >
              Cancelar
            </button>
            <button
              onClick={guardar}
              disabled={guardando || !form.titulo.trim() || !form.url.trim()}
              className="rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
            >
              {guardando ? "Guardando…" : editando ? "Guardar cambios" : "Crear enlace"}
            </button>
          </div>
        </div>
      )}

      {cargando ? (
        <p className="text-[13px] text-slate-400">Cargando…</p>
      ) : categorias.length === 0 ? (
        <div className="rounded-xl border border-dashed border-slate-300 bg-white px-4 py-10 text-center">
          <FolderOpen className="mx-auto mb-2 text-slate-300" size={28} />
          <p className="text-[13px] text-slate-500">
            Aún no hay documentos publicados.
            {esAdmin && " Usa “Nuevo enlace” para agregar el primero."}
          </p>
        </div>
      ) : (
        categorias.map(({ nombre, docs }) => (
          <section key={nombre}>
            <h2 className="mb-2 text-[12px] font-semibold uppercase tracking-wide text-slate-500">
              {nombre}
            </h2>
            <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
              <ul className="divide-y divide-slate-100">
                {docs.map((d) => (
                  <li
                    key={d.id}
                    className={`flex items-center gap-3 px-4 py-3 ${d.activo ? "" : "opacity-50"}`}
                  >
                    <a
                      href={d.url}
                      target="_blank"
                      rel="noopener noreferrer"
                      onClick={() => api.registrarAperturaDocumento(d.id)}
                      className="group flex min-w-0 flex-1 items-center gap-3"
                    >
                      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-md bg-brand-50 text-brand">
                        <ExternalLink size={15} />
                      </span>
                      <span className="min-w-0">
                        <span className="block truncate text-[14px] font-medium text-slate-900 group-hover:text-brand group-hover:underline">
                          {d.titulo}
                          {!d.activo && (
                            <span className="ml-2 rounded bg-slate-100 px-1.5 py-0.5 text-[10px] font-semibold uppercase text-slate-500">
                              oculto
                            </span>
                          )}
                        </span>
                        {d.descripcion && (
                          <span className="block truncate text-[12px] text-slate-500">
                            {d.descripcion}
                          </span>
                        )}
                      </span>
                    </a>
                    {esAdmin && (
                      <span className="flex shrink-0 items-center gap-1">
                        <button
                          onClick={() => alternarActivo(d)}
                          title={d.activo ? "Ocultar a los usuarios" : "Volver a publicar"}
                          className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                        >
                          <EyeOff size={14} />
                        </button>
                        <button
                          onClick={() => abrirEditar(d)}
                          title="Editar"
                          className="rounded p-1.5 text-slate-400 hover:bg-slate-100 hover:text-slate-600"
                        >
                          <Pencil size={14} />
                        </button>
                        <button
                          onClick={() => eliminar(d)}
                          title="Eliminar"
                          className="rounded p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                        >
                          <Trash2 size={14} />
                        </button>
                      </span>
                    )}
                  </li>
                ))}
              </ul>
            </div>
          </section>
        ))
      )}
    </div>
  );
}
