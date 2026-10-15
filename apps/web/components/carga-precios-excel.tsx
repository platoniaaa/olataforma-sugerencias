"use client";

// Editar la lista de precios en Excel: se baja el archivo, se edita y se vuelve a
// cargar. Antes de guardar se ve que cambia, producto por producto.
//
// El archivo que se sube es el que se bajo aca: trae una columna "Referencia" con los
// valores que tenia cada producto al bajarlo. Con ella el servidor sabe QUE cambio la
// persona (y no confunde con edicion lo que el motor recalculo de noche), a que
// producto pertenece cada fila y si otra persona edito el producto mientras tanto.
import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, Download, FileSpreadsheet, Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { api } from "@/lib/api-client";
import { formatoNumero } from "@/lib/formato";
import type { CargaPreciosError, CargaPreciosResultado, CargaPreciosVistaPrevia } from "@/lib/types";

/** Las siete columnas que se pueden editar y que hace cada una al cargarla. */
export const COLUMNAS_EDITABLES = [
  { columna: "Tipo", hace: "Escribe el tipo a mano en ese producto.", vacia: "Vuelve a seguir al rubro." },
  { columna: "Procedencia", hace: "Escribe la procedencia a mano (Nacional o Importado).", vacia: "Vuelve a la regla de compras." },
  { columna: "Factor", hace: "Le da al producto un factor propio (margen fijo).", vacia: "Lo quita: vuelve al factor de la política." },
  { columna: "Precio final", hace: "Lo deja como precio fijo.", vacia: "Quita el precio fijo." },
  { columna: "Obs", hace: "Cambia la observación.", vacia: "La borra." },
  { columna: "Congelar", hace: "Sí congela el precio de hoy; No lo descongela.", vacia: "Cuenta como No." },
  { columna: "No es producto", hace: "Sí lo saca del cálculo (servicios, mano de obra).", vacia: "Cuenta como No." },
] as const;

/** Como se llama cada decision que una carga puede quitar. */
const DECISION: Record<string, string> = {
  tipo: "tipo a mano",
  procedencia: "procedencia a mano",
  factor: "factor propio",
  precio_fijo: "precio fijo",
  obs: "observación",
  congelar: "congelado",
  no_producto: "«no es producto»",
};

/** Las decisiones que una carga puede PONER en bloque, en singular y plural. */
const FIJAN: Record<string, [string, string]> = {
  precio_fijo: ["precio fijo", "precios fijos"],
  factor: ["factor propio", "factores propios"],
};

type Fase = "inicio" | "leyendo" | "previa" | "cargando" | "listo";

// Nombre con que el cliente marca la carga cuya respuesta se perdio (ver api-client).
// Se compara por nombre y no se importa: asi el componente no depende de ese modulo.
const CARGA_SIN_CONFIRMAR = "CargaSinConfirmar";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Se llama cuando la carga terminó, para que la lista se refresque. */
  onCargado?: () => void;
}

const pesos = (n: number | null) => (n == null ? "sin precio" : `$${formatoNumero(n)}`);

/** "1 producto", "2 productos". */
const cantidad = (n: number, uno: string, varios: string) => `${formatoNumero(n)} ${n === 1 ? uno : varios}`;

function textoFijan(clave: string, n: number): string {
  const [uno, varios] = FIJAN[clave] ?? [clave, clave];
  return cantidad(n, uno, varios);
}

/** "1 sube, 0 bajan, ...": el verbo concuerda con la cantidad. */
function efectoTexto(e: CargaPreciosVistaPrevia["efecto"]): string {
  const v = (n: number, uno: string, varios: string) => (n === 1 ? uno : varios);
  return (
    `Precios: ${formatoNumero(e.suben)} ${v(e.suben, "sube", "suben")}, ` +
    `${formatoNumero(e.bajan)} ${v(e.bajan, "baja", "bajan")}, ` +
    `${formatoNumero(e.con_precio_nuevo)} ${v(e.con_precio_nuevo, "pasa", "pasan")} de sin precio a tener uno y ` +
    `${formatoNumero(e.sin_cambio_de_precio)} no ${v(e.sin_cambio_de_precio, "cambia", "cambian")} de precio.`
  );
}

/** Lo que una carga dejo sin cargar, solo lo que no es cero. */
function textoOmitidos(o: CargaPreciosResultado["omitidos"]): string {
  const partes: string[] = [];
  if (o.conflictos) partes.push(`${formatoNumero(o.conflictos)} con conflicto`);
  if (o.desconocidos) {
    partes.push(`${formatoNumero(o.desconocidos)} que no ${o.desconocidos === 1 ? "está" : "están"} en la lista`);
  }
  if (o.sin_referencia) partes.push(`${formatoNumero(o.sin_referencia)} sin referencia`);
  return partes.join(", ");
}

function ListaErrores({ items, total, tono }: { items: CargaPreciosError[]; total: number; tono: "rojo" | "ambar" }) {
  const clase = tono === "rojo" ? "text-rose-800" : "text-amber-800";
  return (
    <ul className={`mt-1 max-h-40 space-y-0.5 overflow-y-auto text-[12px] ${clase}`}>
      {items.map((e, i) => (
        <li key={`${e.fila}-${i}`}>
          <span className="font-medium">Fila {e.fila}</span> · <span className="font-mono">{e.producto}</span>: {e.mensaje}
        </li>
      ))}
      {total > items.length && <li>… y {formatoNumero(total - items.length)} más.</li>}
    </ul>
  );
}

function ListaCodigos({ codigos, total }: { codigos: string[]; total: number }) {
  return (
    <p className="mt-1 max-h-24 overflow-y-auto font-mono text-[12px]">
      {codigos.join(", ")}
      {total > codigos.length && ` … y ${formatoNumero(total - codigos.length)} más.`}
    </p>
  );
}

export function CargaPreciosExcel({ open, onClose, onCargado }: Props) {
  const [fase, setFase] = useState<Fase>("inicio");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<CargaPreciosVistaPrevia | null>(null);
  const [resultado, setResultado] = useState<CargaPreciosResultado | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [descargando, setDescargando] = useState(false);
  const [confirmaQuitas, setConfirmaQuitas] = useState(false);
  const [confirmaMasiva, setConfirmaMasiva] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);
  const botonElegir = useRef<HTMLButtonElement>(null);
  const botonDescargar = useRef<HTMLButtonElement>(null);
  const panelResultado = useRef<HTMLDivElement>(null);
  const alerta = useRef<HTMLParagraphElement>(null);
  // Cada lectura y cada descarga lleva un numero. Si cuando termina ya no es el
  // vigente -se eligio otro archivo, o se cerro el dialogo-, su respuesta se descarta:
  // sin esto, una lectura lenta que llegaba tarde dejaba el nombre de un archivo y la
  // tabla de otro, y "Cargar" subia uno distinto del que se habia mirado.
  const lectura = useRef(0);
  const descarga = useRef(0);
  // Cuantas descargas siguen en curso. Cerrar el dialogo no cancela la peticion: si el
  // boton se rehabilitara al reabrir, se podia lanzar otra descarga de 11 MB encima.
  const enVuelo = useRef(0);
  // La lectura vigente se puede cancelar: sin esto una lectura descartada seguia
  // reintentando y re-subiendo el archivo (hasta 30 MB) a un servidor de 512 MB.
  const cancelaLectura = useRef<AbortController | null>(null);
  // El foco va al error solo si viene de lo que la persona acaba de hacer; un error
  // de otra operacion no le quita la casilla o el boton donde esta.
  const enfocarError = useRef(false);

  // Al cerrarse el dialogo se empieza de cero: un archivo viejo en pantalla invita a
  // cargarlo despues de que la lista ya cambio.
  useEffect(() => {
    if (open) return;
    lectura.current += 1;
    descarga.current += 1;
    cancelaLectura.current?.abort();
    cancelaLectura.current = null;
    setFase("inicio");
    setArchivo(null);
    setPrevia(null);
    setResultado(null);
    setError(null);
    setAviso(null);
    setConfirmaQuitas(false);
    setConfirmaMasiva(false);
  }, [open]);

  // Un error que queda arriba del dialogo mientras el boton esta abajo parece "no paso
  // nada": se lleva a la vista.
  useEffect(() => {
    if (error && enfocarError.current) alerta.current?.focus();
    enfocarError.current = false;
  }, [error]);

  // Salir sin pasar por "cerrar" (la pagina se desmonta) tambien corta la lectura.
  useEffect(() => () => cancelaLectura.current?.abort(), []);

  // Al terminar, el foco va al resultado: el boton que lo tenia desaparece.
  useEffect(() => {
    if (fase === "listo") panelResultado.current?.focus();
  }, [fase]);

  async function descargar() {
    const id = ++descarga.current;
    enVuelo.current += 1;
    setDescargando(true);
    setError(null);
    try {
      const n = await api.exportarPrecios(
        { soloDiferencias: false, formato: "editable" },
        (i, t) => { if (id === descarga.current) setAviso(`El servidor no responde. Reintentando (${i} de ${t})…`); },
      );
      if (id === descarga.current) {
        setAviso(`Archivo descargado: ${cantidad(n, "producto", "productos")}. Ábrelo con Excel, edita y vuelve aquí.`);
      }
    } catch (e) {
      if (id === descarga.current) {
        setAviso(null);
        const activo = typeof document !== "undefined" ? document.activeElement : null;
        enfocarError.current = activo === botonDescargar.current || activo === document.body;
        setError(e instanceof Error ? e.message : "No se pudo descargar el archivo.");
      }
    } finally {
      enVuelo.current -= 1;
      setDescargando(enVuelo.current > 0);
    }
  }

  async function elegir(f: File | null) {
    const id = ++lectura.current;
    cancelaLectura.current?.abort();
    cancelaLectura.current = null;
    setPrevia(null);
    setResultado(null);
    setError(null);
    setAviso(null);
    setConfirmaQuitas(false);
    setConfirmaMasiva(false);
    setArchivo(f);
    if (!f) {
      setFase("inicio");
      return;
    }
    setFase("leyendo");
    const control = new AbortController();
    cancelaLectura.current = control;
    try {
      const p = await api.vistaPreviaCargaPrecios(
        f,
        (i, t) => { if (id === lectura.current) setAviso(`El servidor no responde. Reintentando (${i} de ${t})…`); },
        control.signal,
      );
      if (id !== lectura.current) return;
      setAviso(null);
      setPrevia(p);
      setFase("previa");
    } catch (e) {
      if (id !== lectura.current) return;
      setAviso(null);
      enfocarError.current = true;
      setError(e instanceof Error ? e.message : "No se pudo leer el archivo.");
      setFase("inicio");
    }
  }

  async function cargar() {
    if (!archivo || !previa) return;
    setFase("cargando");
    setError(null);
    try {
      const r = await api.cargarPrecios(archivo, { confirmarQuitas: confirmaQuitas, confirmarMasiva: confirmaMasiva });
      setResultado(r);
      setFase("listo");
      onCargado?.();
    } catch (e) {
      // Si la respuesta se perdio, la carga pudo quedar hecha: la lista de atras se
      // refresca igual, o seguiria mostrando los precios de antes.
      if (e instanceof Error && e.name === CARGA_SIN_CONFIRMAR) onCargado?.();
      enfocarError.current = true;
      setError(e instanceof Error ? e.message : "No se pudo cargar el archivo.");
      // El archivo sigue siendo el mismo: se puede volver a mirar y reintentar.
      setFase("previa");
    }
  }

  const leyendo = fase === "leyendo";
  const cargando = fase === "cargando";
  const hayErrores = (previa?.errores_total ?? 0) > 0;
  const quitan = previa?.quitan_total ?? 0;
  const pideConfirmar = previa !== null && quitan >= previa.umbral_quitas;
  const fijan = previa?.fijan_total ?? 0;
  const pideConfirmarMasiva = previa !== null && fijan > previa.umbral_masiva;
  const puedeCargar = fase === "previa" && previa !== null && previa.a_cambiar > 0 && !hayErrores
    && (!pideConfirmar || confirmaQuitas) && (!pideConfirmarMasiva || confirmaMasiva);
  const omitidos = previa
    ? previa.conflictos_total + previa.desconocidos_total + previa.sin_referencia_total
    : 0;
  const omitidosCarga = resultado
    ? resultado.omitidos.conflictos + resultado.omitidos.desconocidos + resultado.omitidos.sin_referencia
    : 0;

  return (
    <Dialog
      open={open}
      // Mientras se guarda no se cierra: la respuesta es lo unico que dice si quedo cargado.
      onClose={() => { if (!cargando) onClose(); }}
      title="Editar la lista con Excel"
      description="Baja el archivo, edítalo y vuelve a cargarlo. Antes de guardar ves qué cambia."
      className="max-w-4xl"
    >
      <div className="space-y-5 text-[13px] text-slate-700">
        {error && fase !== "listo" && (
          <p ref={alerta} tabIndex={-1} role="alert" className="flex items-start gap-2 rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-rose-800 outline-none">
            <AlertCircle size={16} className="mt-0.5 shrink-0" /> {error}
          </p>
        )}
        {aviso && fase !== "listo" && (
          <p role="status" className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700">{aviso}</p>
        )}

        {fase === "listo" && resultado ? (
          <div ref={panelResultado} tabIndex={-1} role="status" className="space-y-3 outline-none">
            {resultado.aplicados === 0 && omitidosCarga > 0 ? (
              <p className="flex items-start gap-2 rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
                <AlertCircle size={16} className="mt-0.5 shrink-0" />
                <span>No se cargó nada: todos los cambios del archivo se omitieron (detalle abajo).</span>
              </p>
            ) : (
              <p className="flex items-start gap-2 rounded-md border border-emerald-200 bg-emerald-50 px-3 py-2 text-emerald-800">
                <CheckCircle2 size={16} className="mt-0.5 shrink-0" />
                <span>
                  {resultado.aplicados === 0
                    ? "No había nada que cargar: la lista ya estaba como dice el archivo."
                    : `Listo: ${cantidad(resultado.aplicados, "producto actualizado", "productos actualizados")}` +
                      (resultado.precios_distintos > 0
                        ? `, ${resultado.precios_distintos === 1 ? "1 cambió" : `${formatoNumero(resultado.precios_distintos)} cambiaron`} de precio. Los precios nuevos salen en el próximo "Solo diferencias".`
                        : ". Ningún precio cambió.")}
                </span>
              </p>
            )}
            {omitidosCarga > 0 && (
              <p className="text-slate-600">
                No se cargaron: {textoOmitidos(resultado.omitidos)}.
                {resultado.omitidos.conflictos > 0 && " Descarga el archivo de nuevo y repite esos cambios."}
              </p>
            )}
            <div className="flex justify-end">
              <Button size="sm" onClick={onClose}>Cerrar</Button>
            </div>
          </div>
        ) : (
          <>
            <section className="space-y-2">
              <h3 className="text-[13px] font-semibold text-slate-900">1. Descarga la lista</h3>
              <p>Baja un archivo con todos los productos y sus precios de hoy.</p>
              <Button ref={botonDescargar} variant="outline" size="sm" onClick={() => void descargar()} disabled={descargando || leyendo || cargando}>
                {descargando ? <Loader2 size={15} className="animate-spin" /> : <Download size={15} />}
                Descargar para editar
              </Button>
            </section>

            <section className="space-y-2">
              <h3 className="text-[13px] font-semibold text-slate-900">2. Edítala en Excel</h3>
              <p>Cambia solo las columnas de esta tabla:</p>
              <div className="overflow-x-auto rounded-md border border-slate-200">
                <table className="w-full text-[12px]">
                  <thead className="bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
                    <tr>
                      <th className="px-3 py-1.5">Columna</th>
                      <th className="px-3 py-1.5">Al cargarla</th>
                      <th className="px-3 py-1.5">Si la dejas vacía</th>
                    </tr>
                  </thead>
                  <tbody>
                    {COLUMNAS_EDITABLES.map((c) => (
                      <tr key={c.columna} className="border-t border-slate-100">
                        <td className="px-3 py-1.5 font-medium text-slate-900">{c.columna}</td>
                        <td className="px-3 py-1.5">{c.hace}</td>
                        <td className="px-3 py-1.5 text-slate-500">{c.vacia}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              <ul className="list-disc space-y-0.5 pl-5 text-[12px] text-slate-600">
                <li>No toques la última columna, <b>Referencia</b>, ni ordenes columnas sueltas: con ella la plataforma sabe qué cambiaste.</li>
                <li>Guarda el archivo en el formato que quieras: CSV o libro de Excel (.xlsx). Los dos sirven.</li>
                <li>Solo se carga lo que cambies. Lo demás (costo, stock, precio ERP, estado, descuento) viene del ERP y se recalcula cada día.</li>
                <li>Un producto no puede tener precio fijo y factor propio a la vez: cambia uno, o deja vacía la celda del otro.</li>
                <li>Un factor para todo un rubro conviene cambiarlo en <b>Política</b>: es un solo cambio y alcanza a los productos nuevos.</li>
              </ul>
            </section>

            <section className="space-y-2">
              <h3 className="text-[13px] font-semibold text-slate-900">3. Súbelo</h3>
              <p>Antes de guardar verás qué cambia en cada producto.</p>
              <input
                ref={entrada}
                type="file"
                accept=".csv,.xlsx,.xlsm"
                className="sr-only"
                tabIndex={-1}
                aria-label="Archivo editado"
                disabled={cargando}
                onChange={(e) => {
                  void elegir(e.target.files?.[0] ?? null);
                  e.target.value = "";
                }}
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button ref={botonElegir} variant="outline" size="sm" onClick={() => entrada.current?.click()} disabled={cargando}>
                  <Upload size={15} /> Elegir archivo
                </Button>
                {archivo && (
                  <span className="flex items-center gap-1 text-slate-600">
                    <FileSpreadsheet size={14} /> {archivo.name}
                  </span>
                )}
                {leyendo && (
                  <span role="status" className="flex items-center gap-1 text-slate-500">
                    <Loader2 size={14} className="animate-spin" /> Leyendo el archivo… puede tardar unos segundos.
                  </span>
                )}
              </div>
            </section>

            {previa && (
              <section className="space-y-3" aria-label="Qué cambia">
                <h3 className="text-[13px] font-semibold text-slate-900">Qué cambia</h3>
                <div className="flex flex-wrap gap-2 text-[12px]">
                  <span className="rounded-md bg-slate-100 px-2 py-1">{cantidad(previa.filas, "fila leída", "filas leídas")}</span>
                  <span className="rounded-md bg-slate-100 px-2 py-1">{formatoNumero(previa.sin_cambios)} sin cambios</span>
                  {hayErrores ? (
                    <span className="rounded-md bg-slate-100 px-2 py-1">
                      {cantidad(previa.a_cambiar, "producto con cambios válido", "productos con cambios válidos")}
                    </span>
                  ) : (
                    <span className="rounded-md bg-brand-50 px-2 py-1 font-medium text-brand">
                      {previa.a_cambiar === 1 ? "1 producto se cargará" : `${formatoNumero(previa.a_cambiar)} productos se cargarán`}
                    </span>
                  )}
                  {omitidos > 0 && (
                    <span className="rounded-md bg-amber-50 px-2 py-1 text-amber-800">
                      {omitidos === 1 ? "1 se omite" : `${formatoNumero(omitidos)} se omiten`}
                    </span>
                  )}
                </div>

                {hayErrores && (
                  <div role="alert" className="rounded-md border border-rose-200 bg-rose-50 px-3 py-2 text-rose-800">
                    <p className="font-medium">
                      El archivo tiene {formatoNumero(previa.errores_total)} error(es). No se carga nada hasta corregirlos:
                      arréglalos en Excel y vuelve a subirlo.
                    </p>
                    <ListaErrores items={previa.errores} total={previa.errores_total} tono="rojo" />
                  </div>
                )}

                {quitan > 0 && !hayErrores && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
                    <p className="font-medium">
                      Esta carga quita {cantidad(quitan, "decisión", "decisiones")}:{" "}
                      {Object.entries(previa.quitan).map(([k, n]) => `${formatoNumero(n)} ${DECISION[k] ?? k}`).join(", ")}.
                    </p>
                    {previa.quitan_ejemplos.length > 0 && (
                      <p className="mt-0.5 text-[12px]">
                        Por ejemplo:{" "}
                        {previa.quitan_ejemplos.slice(0, 5).map((e) => `${e.producto} (${e.campo.toLowerCase()})`).join(", ")}
                        {quitan > Math.min(5, previa.quitan_ejemplos.length) && "…"}
                      </p>
                    )}
                    <p className="mt-0.5 text-[12px]">
                      Una celda vacía quita la decisión del producto. Si no dejaste esas celdas vacías a propósito, puede
                      que el Excel tenga celdas con error (#N/D, #REF!), que se leen como vacías.
                    </p>
                    {pideConfirmar && (
                      <label className="mt-2 flex items-start gap-2 text-[13px]">
                        <input
                          type="checkbox"
                          className="mt-0.5"
                          checked={confirmaQuitas}
                          disabled={cargando}
                          onChange={(e) => setConfirmaQuitas(e.target.checked)}
                        />
                        <span>Entiendo que se quitan {formatoNumero(quitan)} decisiones y quiero cargarlas.</span>
                      </label>
                    )}
                  </div>
                )}

                {pideConfirmarMasiva && !hayErrores && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
                    <p className="font-medium">
                      Esta carga deja {formatoNumero(fijan)} precios fijos o factores propios nuevos:{" "}
                      {Object.entries(previa.fijan).map(([k, n]) => textoFijan(k, n)).join(", ")}.
                    </p>
                    <p className="mt-0.5 text-[12px]">
                      Son muchos para una edición a mano. Si ordenaste una sola columna del Excel (por ejemplo Precio final
                      o Factor), cada valor quedó en la fila de otro producto: descarga el archivo de nuevo y edítalo sin
                      ordenar columnas sueltas.
                    </p>
                    <label className="mt-2 flex items-start gap-2 text-[13px]">
                      <input
                        type="checkbox"
                        className="mt-0.5"
                        checked={confirmaMasiva}
                        disabled={cargando}
                        onChange={(e) => setConfirmaMasiva(e.target.checked)}
                      />
                      <span>Entiendo que se fijan {formatoNumero(fijan)} valores y quiero cargarlos.</span>
                    </label>
                  </div>
                )}

                {previa.conflictos_total > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
                    <p className="font-medium">
                      {previa.conflictos_total === 1
                        ? "1 producto no se cargará: cambió en la plataforma"
                        : `${formatoNumero(previa.conflictos_total)} productos no se cargarán: cambiaron en la plataforma`}{" "}
                      después de que bajaste el archivo.
                    </p>
                    <ListaErrores items={previa.conflictos} total={previa.conflictos_total} tono="ambar" />
                    <p className="mt-1 text-[12px]">Descarga el archivo de nuevo y repite el cambio en esos productos.</p>
                  </div>
                )}

                {previa.desconocidos_total > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
                    <p className="font-medium">
                      {previa.desconocidos_total === 1
                        ? "1 código no está en la lista y se ignora."
                        : `${formatoNumero(previa.desconocidos_total)} códigos no están en la lista y se ignoran.`}
                    </p>
                    <ListaCodigos codigos={previa.desconocidos} total={previa.desconocidos_total} />
                  </div>
                )}

                {previa.sin_referencia_total > 0 && (
                  <div className="rounded-md border border-amber-200 bg-amber-50 px-3 py-2 text-amber-900">
                    <p className="font-medium">
                      {previa.sin_referencia_total === 1
                        ? "1 fila no trae Referencia y se ignora (¿fila agregada a mano?)."
                        : `${formatoNumero(previa.sin_referencia_total)} filas no traen Referencia y se ignoran (¿filas agregadas a mano?).`}
                    </p>
                    <ListaCodigos codigos={previa.sin_referencia} total={previa.sin_referencia_total} />
                  </div>
                )}

                {previa.a_cambiar > 0 && !hayErrores && (
                  <>
                    <p className="text-slate-700">{efectoTexto(previa.efecto)}</p>
                    <div className="max-h-72 overflow-auto rounded-md border border-slate-200">
                      <table className="w-full text-[12px]">
                        <thead className="sticky top-0 bg-slate-50 text-left text-[11px] uppercase tracking-wide text-slate-500">
                          <tr>
                            <th className="px-3 py-1.5">Producto</th>
                            <th className="px-3 py-1.5">Qué cambia</th>
                            <th className="px-3 py-1.5 text-right">Precio</th>
                          </tr>
                        </thead>
                        <tbody>
                          {previa.cambios.map((c) => (
                            <tr key={c.producto} className="border-t border-slate-100 align-top">
                              <td className="px-3 py-1.5">
                                <span className="font-mono">{c.producto}</span>
                                {c.glosa && <span className="block text-slate-500">{c.glosa}</span>}
                              </td>
                              <td className="px-3 py-1.5">
                                {c.campos.map((f) => (
                                  <span key={f.campo} className="block">
                                    <span className="font-medium">{f.campo}:</span> {f.antes} → {f.despues}
                                  </span>
                                ))}
                              </td>
                              <td className="whitespace-nowrap px-3 py-1.5 text-right tabular-nums">
                                {c.precio_antes === c.precio_despues ? "no cambia" : `${pesos(c.precio_antes)} → ${pesos(c.precio_despues)}`}
                              </td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                      {previa.cambios_total > previa.cambios.length && (
                        <p className="border-t border-slate-100 px-3 py-1.5 text-[12px] text-slate-500">
                          … y {cantidad(previa.cambios_total - previa.cambios.length, "producto más", "productos más")} con cambios.
                        </p>
                      )}
                    </div>
                  </>
                )}

                {previa.a_cambiar === 0 && !hayErrores && (
                  <p className="text-slate-600">
                    {omitidos > 0
                      ? "No hay nada que cargar: los cambios del archivo se omiten (detalle arriba)."
                      : "El archivo no trae ningún cambio que cargar."}
                  </p>
                )}

                <div className="flex flex-wrap items-center justify-end gap-2 pt-1">
                  <Button
                    variant="outline"
                    size="sm"
                    // El boton desaparece con la seccion: el foco pasa a "Elegir archivo".
                    onClick={() => { void elegir(null); setTimeout(() => botonElegir.current?.focus(), 0); }}
                    disabled={cargando}
                  >
                    Descartar
                  </Button>
                  <Button size="sm" onClick={() => void cargar()} disabled={!puedeCargar}>
                    {cargando ? <Loader2 size={15} className="animate-spin" /> : <Upload size={15} />}
                    {cargando ? "Cargando…" : `Cargar ${cantidad(previa.a_cambiar, "producto", "productos")}`}
                  </Button>
                </div>
                {cargando && (
                  <p role="status" className="text-right text-[12px] text-slate-500">
                    Guardando y recalculando solo los productos editados. No cierres esta ventana.
                  </p>
                )}
              </section>
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
