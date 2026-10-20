"use client";

// Editar la lista de precios en Excel, con DOS modos que la persona elige:
//
// - Excel corto: se baja una plantilla vacia (Codigo, Precio fijo, Desde, Hasta, Obs), se llena
//   con los pocos productos que se quieren tocar y se sube. Se aplica TAL CUAL, solo a esos codigos.
// - Excel completo: se baja la lista entera, se edita (once columnas se pueden tocar) y se sube.
//
// El archivo completo trae una columna "Referencia" con los valores que tenia cada producto al
// bajarlo. Con ella el servidor sabe QUE cambio la persona (y no confunde con edicion lo que el
// motor recalculo de noche), a que producto pertenece cada fila y si otra persona edito el
// producto mientras tanto. El corto no la necesita: no compara contra una descarga.
//
// Los dos modos comparten el paso de subir el archivo y la vista previa "Qué cambia", antes de
// guardar. El modo se declara al servidor (si el archivo no es de ese modo, da un error claro en
// vez de cargarlo como otra cosa), se recuerda en el navegador y, al cambiarlo, se descarta lo que
// habia a medias.
import { useEffect, useRef, useState } from "react";
import { AlertCircle, CheckCircle2, FileSpreadsheet, Loader2, Upload } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";
import { api } from "@/lib/api-client";
import { formatoNumero } from "@/lib/formato";
import type { CargaPreciosResultado, CargaPreciosVistaPrevia, ModoCarga } from "@/lib/types";
import { PasosCompleto } from "@/components/carga-precios/pasos-completo";
import { PasosCorto } from "@/components/carga-precios/pasos-corto";
import { SelectorModo, guardarModo, modoGuardado } from "@/components/carga-precios/selector-modo";
import { VistaPrevia, cantidad, derivadosDePrevia } from "@/components/carga-precios/vista-previa";

// Las columnas del archivo completo (las once que se editan y las trece de solo lectura) viven con
// sus pasos; se exportan desde aca porque es lo que el resto del codigo y las pruebas importan.
export { COLUMNAS_EDITABLES, COLUMNAS_SOLO_LECTURA } from "@/components/carga-precios/pasos-completo";

type Fase = "inicio" | "leyendo" | "previa" | "cargando" | "listo";

// Nombre con que el cliente marca la carga cuya respuesta se perdio (ver api-client).
// Se compara por nombre y no se importa: asi el componente no depende de ese modulo.
const CARGA_SIN_CONFIRMAR = "CargaSinConfirmar";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Se llama cuando la carga terminó, para que la lista se refresque. */
  onCargado?: () => void;
  /** Cuantos productos tiene la lista: con eso, el Excel corto dice cuantos quedan como estan. */
  totalProductos?: number;
  /** La fecha de hoy en Chile (la del servidor), para decir que empieza mas adelante. */
  hoy?: string;
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

/** "Listo: 12 productos actualizados, 9 cambiaron de precio. 3 empiezan más adelante y se aplican
 *  ese día. Los precios nuevos salen en el próximo «Solo diferencias»." */
function textoListo(r: CargaPreciosResultado, programados: number): string {
  const empiezan = programados > 0
    ? ` ${programados === 1 ? "1 empieza más adelante y se aplica ese día." : `${formatoNumero(programados)} empiezan más adelante y se aplican ese día.`}`
    : "";
  const base = `Listo: ${cantidad(r.aplicados, "producto actualizado", "productos actualizados")}`;
  if (r.precios_distintos > 0) {
    const cambiaron = r.precios_distintos === 1 ? "1 cambió" : `${formatoNumero(r.precios_distintos)} cambiaron`;
    return `${base}, ${cambiaron} de precio.${empiezan} Los precios nuevos salen en el próximo "Solo diferencias".`;
  }
  return `${base}. Ningún precio cambió.${empiezan}`;
}

export function CargaPreciosExcel({ open, onClose, onCargado, totalProductos, hoy }: Props) {
  const [modo, setModo] = useState<ModoCarga>(modoGuardado);
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
  // El boton de bajar el archivo (la lista o la plantilla: en pantalla hay uno solo).
  const botonDescargar = useRef<HTMLButtonElement>(null);
  const panelResultado = useRef<HTMLDivElement>(null);
  const alerta = useRef<HTMLParagraphElement>(null);
  const panelPrevia = useRef<HTMLElement>(null);
  // Cada lectura y cada descarga lleva un numero. Si cuando termina ya no es el
  // vigente -se eligio otro archivo, se cambio de modo o se cerro el dialogo-, su respuesta se
  // descarta: sin esto, una lectura lenta que llegaba tarde dejaba el nombre de un archivo y la
  // tabla de otro, y "Cargar" subia uno distinto del que se habia mirado.
  const lectura = useRef(0);
  const descarga = useRef(0);
  // Cuantas descargas siguen en curso. Cerrar el dialogo (o cambiar de modo) no cancela la
  // peticion: si el boton se rehabilitara, se podia lanzar otra descarga de 11 MB encima.
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
  // cargarlo despues de que la lista ya cambio. El modo elegido NO se borra: es una preferencia.
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

  /** Baja un archivo (la lista para editar o la plantilla) con su aviso propio. `pedir` hace la
   *  descarga y devuelve lo que se le dice a la persona al terminar. */
  async function bajar(
    pedir: (alReintentar: (intento: number, total: number) => void) => Promise<string>,
    errorPorDefecto: string,
  ) {
    const id = ++descarga.current;
    enVuelo.current += 1;
    setDescargando(true);
    setError(null);
    try {
      const aviso = await pedir((i, t) => {
        if (id === descarga.current) setAvisoDescarga(`Descarga: el servidor no responde. Reintentando (${i} de ${t})…`);
      });
      if (id === descarga.current) setAvisoDescarga(aviso);
    } catch (e) {
      if (id === descarga.current) {
        setAvisoDescarga(null);
        const activo = typeof document !== "undefined" ? document.activeElement : null;
        enfocarError.current = activo === botonDescargar.current || activo === document.body;
        setError(e instanceof Error ? e.message : errorPorDefecto);
      }
    } finally {
      enVuelo.current -= 1;
      setDescargando(enVuelo.current > 0);
    }
  }

  function descargarLista() {
    return bajar(
      async (alReintentar) => {
        const n = await api.exportarPrecios({ soloDiferencias: false, formato: "editable" }, alReintentar);
        return `Archivo descargado: ${cantidad(n, "producto", "productos")}. Ábrelo con Excel, edita y vuelve aquí.`;
      },
      "No se pudo descargar el archivo.",
    );
  }

  function descargarPlantilla() {
    return bajar(
      async (alReintentar) => {
        const nombre = await api.descargarPlantillaCarga("xlsx", alReintentar);
        return `Plantilla descargada (${nombre}). Ábrela con Excel, llena tus productos y vuelve aquí.`;
      },
      "No se pudo descargar la plantilla.",
    );
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
        modo,
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
      const r = await api.cargarPrecios(archivo, { confirmarQuitas: confirmaQuitas, confirmarMasiva: confirmaMasiva, modo });
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

  /** Cambiar de modo es empezar de nuevo, como "Descartar": el archivo y la vista previa eran de
   *  otro modo. Una descarga en curso no se puede cancelar y sigue (el boton espera), pero su
   *  aviso ya no corresponde a este modo, asi que se descarta. */
  function cambiarModo(nuevo: ModoCarga) {
    if (nuevo === modo) return;
    void elegir(null);
    descarga.current += 1;
    setAvisoDescarga(null);
    setModo(nuevo);
    guardarModo(nuevo);
  }

  const leyendo = fase === "leyendo";
  const cargando = fase === "cargando";
  const { hayErrores, pideConfirmar, pideConfirmarMasiva } = derivadosDePrevia(previa);
  const puedeCargar = fase === "previa" && previa !== null && previa.a_cambiar > 0 && !hayErrores
    && (!pideConfirmar || confirmaQuitas) && (!pideConfirmarMasiva || confirmaMasiva);
  const omitidosCarga = resultado
    ? resultado.omitidos.conflictos + resultado.omitidos.desconocidos + resultado.omitidos.sin_referencia
    : 0;
  // Los que la vista previa dijo que empiezan mas adelante (el resultado no lo repite), sin
  // contar mas de los que se cargaron.
  const programados = resultado ? Math.min(previa?.programados_total ?? 0, resultado.aplicados) : 0;
  const bloqueaDescarga = descargando || leyendo || cargando;

  return (
    <Dialog
      open={open}
      // Mientras se guarda no se cierra: la respuesta es lo unico que dice si quedo cargado.
      onClose={() => { if (!cargando) onClose(); }}
      title="Editar la lista con Excel"
      description="Elige cómo cargar. Antes de guardar ves qué cambia."
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
                    : textoListo(resultado, programados)}
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
              <Button size="sm" className="[@media(pointer:coarse)]:h-11" onClick={onClose}>Cerrar</Button>
            </div>
          </div>
        ) : (
          <>
            <SelectorModo modo={modo} onCambiar={cambiarModo} deshabilitado={leyendo || cargando} />

            {modo === "corto" ? (
              <PasosCorto
                descargando={descargando}
                deshabilitado={bloqueaDescarga}
                aviso={avisoDescarga}
                onDescargar={() => void descargarPlantilla()}
                botonRef={botonDescargar}
              />
            ) : (
              <PasosCompleto
                descargando={descargando}
                deshabilitado={bloqueaDescarga}
                aviso={avisoDescarga}
                onDescargar={() => void descargarLista()}
                botonRef={botonDescargar}
              />
            )}

            <section className="space-y-2">
              <h3 className="text-[13px] font-semibold text-slate-900">3. Súbelo</h3>
              <p>Antes de guardar verás qué cambia en cada producto.</p>
              <input
                ref={entrada}
                type="file"
                accept=".csv,.xlsx,.xlsm"
                className="sr-only"
                tabIndex={-1}
                aria-label={modo === "corto" ? "Archivo con tus productos" : "Archivo editado"}
                disabled={cargando}
                onChange={(e) => {
                  void elegir(e.target.files?.[0] ?? null);
                  e.target.value = "";
                }}
              />
              <div className="flex flex-wrap items-center gap-2">
                <Button ref={botonElegir} variant="outline" size="sm" className="[@media(pointer:coarse)]:h-11" onClick={() => entrada.current?.click()} disabled={cargando}>
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
                totalProductos={totalProductos}
                hoy={hoy}
              />
            )}
          </>
        )}
      </div>
    </Dialog>
  );
}
