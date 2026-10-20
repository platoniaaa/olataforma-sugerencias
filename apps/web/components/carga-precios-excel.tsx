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
import type { CargaPreciosResultado, CargaPreciosVistaPrevia } from "@/lib/types";
import { VistaPrevia, cantidad, derivadosDePrevia } from "@/components/carga-precios/vista-previa";

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

export function CargaPreciosExcel({ open, onClose, onCargado }: Props) {
  const [fase, setFase] = useState<Fase>("inicio");
  const [archivo, setArchivo] = useState<File | null>(null);
  const [previa, setPrevia] = useState<CargaPreciosVistaPrevia | null>(null);
  const [resultado, setResultado] = useState<CargaPreciosResultado | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Un aviso por operacion: con uno solo, el reintento de la descarga aparecia junto a "Leyendo
  // el archivo" y parecia que fallaba la lectura, y cada una borraba el aviso de la otra.
  const [avisoDescarga, setAvisoDescarga] = useState<string | null>(null);
  const [avisoLectura, setAvisoLectura] = useState<string | null>(null);
  const [descargando, setDescargando] = useState(false);
  const [confirmaQuitas, setConfirmaQuitas] = useState(false);
  const [confirmaMasiva, setConfirmaMasiva] = useState(false);
  const entrada = useRef<HTMLInputElement>(null);
  const botonElegir = useRef<HTMLButtonElement>(null);
  const botonDescargar = useRef<HTMLButtonElement>(null);
  const panelResultado = useRef<HTMLDivElement>(null);
  const alerta = useRef<HTMLParagraphElement>(null);
  const panelPrevia = useRef<HTMLElement>(null);
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
  // Terminada la lectura, la vista previa y el boton Cargar quedan abajo, fuera de pantalla: el
  // unico cambio visible era que desaparecia "Leyendo el archivo", y parecia que no pasaba nada.
  const enfocarPrevia = useRef(false);

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
    setAvisoDescarga(null);
    setAvisoLectura(null);
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

  // Al terminar de leer, el foco va a la vista previa (y el navegador la lleva a la vista).
  useEffect(() => {
    if (fase === "previa" && previa && enfocarPrevia.current) {
      enfocarPrevia.current = false;
      panelPrevia.current?.focus();
    }
  }, [fase, previa]);

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
        (i, t) => { if (id === descarga.current) setAvisoDescarga(`Descarga: el servidor no responde. Reintentando (${i} de ${t})…`); },
      );
      if (id === descarga.current) {
        setAvisoDescarga(`Archivo descargado: ${cantidad(n, "producto", "productos")}. Ábrelo con Excel, edita y vuelve aquí.`);
      }
    } catch (e) {
      if (id === descarga.current) {
        setAvisoDescarga(null);
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
    setAvisoLectura(null);
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
        (i, t) => { if (id === lectura.current) setAvisoLectura(`Lectura: el servidor no responde. Reintentando (${i} de ${t})…`); },
        control.signal,
      );
      if (id !== lectura.current) return;
      setAvisoLectura(null);
      enfocarPrevia.current = true;
      setPrevia(p);
      setFase("previa");
    } catch (e) {
      if (id !== lectura.current) return;
      setAvisoLectura(null);
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
  const { hayErrores, pideConfirmar, pideConfirmarMasiva } = derivadosDePrevia(previa);
  const puedeCargar = fase === "previa" && previa !== null && previa.a_cambiar > 0 && !hayErrores
    && (!pideConfirmar || confirmaQuitas) && (!pideConfirmarMasiva || confirmaMasiva);
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
              {avisoDescarga && (
                <p role="status" className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700">{avisoDescarga}</p>
              )}
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
              {avisoLectura && (
                <p role="status" className="rounded-md border border-slate-200 bg-slate-50 px-3 py-2 text-slate-700">{avisoLectura}</p>
              )}
            </section>

            {previa && (
              <VistaPrevia
                previa={previa}
                panelRef={panelPrevia}
                cargando={cargando}
                puedeCargar={puedeCargar}
                confirmaQuitas={confirmaQuitas}
                confirmaMasiva={confirmaMasiva}
                onConfirmaQuitas={setConfirmaQuitas}
                onConfirmaMasiva={setConfirmaMasiva}
                // El boton desaparece con la seccion: el foco pasa a "Elegir archivo".
                onDescartar={() => { void elegir(null); setTimeout(() => botonElegir.current?.focus(), 0); }}
                onCargar={() => void cargar()}
              />
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
