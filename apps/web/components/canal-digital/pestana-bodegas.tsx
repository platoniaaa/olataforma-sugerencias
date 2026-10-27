"use client";

// Bodegas: los parametros de la bodega elegida (tipos de venta, cortes, bodegas del ERP...) y, para admin, el alta de
// bodegas nuevas. Se guarda completo o no se guarda: el servidor valida todo antes de tocar nada.
import { useId, useState, type ReactNode } from "react";
import { Plus, RefreshCw, RotateCcw, Save, X } from "lucide-react";
import {
  canalDigitalApi,
  type BodegaCD,
  type BodegasCanalDigital,
  type CambiosBodegaCD,
} from "@/lib/canal-digital";

const BOTON_PRIMARIO =
  "inline-flex items-center gap-1.5 rounded-md bg-brand px-3 py-1.5 text-[13px] font-medium text-white hover:bg-brand-700 disabled:opacity-50";
const BOTON_SECUNDARIO =
  "inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-[13px] text-slate-700 hover:bg-slate-50 disabled:opacity-50";
const CAJA = "w-full rounded border border-slate-300 px-2 py-1 text-[12.5px] disabled:bg-slate-50";
const CAJA_NUMERO =
  "w-24 rounded border border-slate-300 px-2 py-1 text-right text-[12.5px] tabular-nums disabled:bg-slate-50";

const CAMPOS_NUMERICOS = ["r_semanas", "nuevo_meses", "corte_a_pct", "corte_b_pct", "gestion_dias"] as const;
type CampoNumerico = (typeof CAMPOS_NUMERICOS)[number];
const CAMPOS_LISTA = ["tipos_venta", "bodegas_stock", "bodegas_aparte", "bodegas_informativas"] as const;
type CampoLista = (typeof CAMPOS_LISTA)[number];

/** Lo que hay en pantalla: los numeros como texto (con coma decimal) hasta que se guardan. */
interface Borrador extends Record<CampoNumerico, string>, Record<CampoLista, string[]> {
  nombre: string;
  activa: boolean;
}

const comoTexto = (n: number) => String(n).replace(".", ",");

/** "2,5" -> 2.5. Lo que no es un numero (vacio, letras) da null; el rango lo juzga el servidor. */
const aNumero = (v: string): number | null => {
  const t = v.trim().replace(",", ".");
  return /^-?(\d+\.?\d*|\.\d+)$/.test(t) ? Number(t) : null;
};

const aBorrador = (b: BodegaCD): Borrador => ({
  nombre: b.nombre,
  activa: b.activa,
  tipos_venta: [...b.tipos_venta],
  bodegas_stock: [...b.bodegas_stock],
  bodegas_aparte: [...b.bodegas_aparte],
  bodegas_informativas: [...b.bodegas_informativas],
  r_semanas: comoTexto(b.r_semanas),
  nuevo_meses: comoTexto(b.nuevo_meses),
  corte_a_pct: comoTexto(b.corte_a_pct),
  corte_b_pct: comoTexto(b.corte_b_pct),
  gestion_dias: comoTexto(b.gestion_dias),
});

/** Mismos elementos, sin importar el orden: quitar un chip y volver a ponerlo no es un cambio. */
const mismaLista = (a: string[], b: string[]) => {
  const orden = (l: string[]) => [...l].sort().join("\u0000");
  return a.length === b.length && orden(a) === orden(b);
};

/** Solo lo que cambio respecto de lo guardado: es lo unico que viaja en el guardado. */
function cambiosDe(original: BodegaCD, b: Borrador): CambiosBodegaCD {
  const out: CambiosBodegaCD = {};
  if (b.nombre.trim() !== original.nombre) out.nombre = b.nombre.trim();
  if (b.activa !== original.activa) out.activa = b.activa;
  for (const c of CAMPOS_LISTA) if (!mismaLista(b[c], original[c])) out[c] = b[c];
  for (const c of CAMPOS_NUMERICOS) {
    const n = aNumero(b[c]);
    if (n !== null && n !== original[c]) out[c] = n;
  }
  return out;
}

/** Las bodegas del ERP se comparan sin signos ni espacios ni mayusculas, como en el calculo. */
const clave = (t: string) => t.replace(/[^0-9A-Za-z]/g, "").toUpperCase();

function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-3 text-[13px] font-semibold text-slate-900">{titulo}</h2>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

/** Una lista de textos como chips que se quitan con la X y se agregan escribiendo (Enter o coma) o con una sugerencia. */
function EditorChips({ etiqueta, ayuda, agregarEtiqueta, valores, onCambio, deshabilitado, sugerencias = [], obligatorio = false, porClave = false }: {
  etiqueta: string;
  ayuda: string;
  agregarEtiqueta: string;
  valores: string[];
  onCambio: (v: string[]) => void;
  deshabilitado: boolean;
  sugerencias?: string[];
  obligatorio?: boolean;
  porClave?: boolean;
}) {
  const id = useId();
  const [texto, setTexto] = useState("");
  const igual = (a: string, b: string) => (porClave ? clave(a) === clave(b) : a === b);

  function agregar(crudo: string) {
    let lista = valores;
    for (const t of crudo.split(",").map((x) => x.trim()).filter(Boolean)) {
      if (!lista.some((v) => igual(v, t))) lista = [...lista, t];
    }
    if (lista !== valores) onCambio(lista);
    setTexto("");
  }

  const faltan = sugerencias.filter((s) => !valores.some((v) => igual(v, s)));

  return (
    <div role="group" aria-labelledby={`${id}-t`} className="space-y-1.5">
      <div id={`${id}-t`} className="text-[12.5px] font-medium text-slate-800">
        {etiqueta}
      </div>
      <p id={`${id}-a`} className="text-[12px] text-slate-500">
        {ayuda}
      </p>
      {valores.length > 0 ? (
        <ul className="flex flex-wrap gap-1.5">
          {valores.map((v) => (
            <li
              key={v}
              className={`inline-flex items-center gap-1 rounded-full border border-slate-300 bg-slate-50 py-0.5 text-[12px] text-slate-800 ${
                deshabilitado ? "px-2.5" : "pl-2.5 pr-1"
              }`}
            >
              {v}
              {!deshabilitado && (
                <button
                  type="button"
                  aria-label={`Quitar ${v}`}
                  onClick={() => onCambio(valores.filter((x) => x !== v))}
                  className="rounded-full p-0.5 text-slate-500 hover:bg-slate-200 hover:text-slate-800"
                >
                  <X size={12} aria-hidden="true" />
                </button>
              )}
            </li>
          ))}
        </ul>
      ) : (
        <p className={`text-[12px] ${obligatorio ? "text-red-700" : "text-slate-500"}`}>
          {obligatorio ? "Debe quedar al menos uno." : "Ninguna."}
        </p>
      )}
      {!deshabilitado && (
        <div className="flex flex-wrap items-center gap-2">
          <input
            aria-label={agregarEtiqueta}
            aria-describedby={`${id}-a`}
            className={`${CAJA} max-w-xs`}
            placeholder="Escribe y presiona Enter"
            value={texto}
            onChange={(e) => setTexto(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter" || e.key === ",") {
                e.preventDefault();
                agregar(texto);
              }
            }}
          />
          <button type="button" onClick={() => agregar(texto)} disabled={!texto.trim()} className={BOTON_SECUNDARIO}>
            <Plus size={14} aria-hidden="true" /> Agregar
          </button>
        </div>
      )}
      {!deshabilitado && faltan.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5 text-[12px] text-slate-500">
          <span>Sugeridos:</span>
          {faltan.map((s) => (
            <button
              key={s}
              type="button"
              onClick={() => agregar(s)}
              className="inline-flex items-center gap-1 rounded-full border border-dashed border-slate-300 px-2 py-0.5 text-slate-700 hover:bg-slate-50"
            >
              <Plus size={11} aria-hidden="true" />
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function CampoNumero({ etiqueta, ayuda, valor, onCambio, deshabilitado, aria }: {
  etiqueta: string;
  ayuda: string;
  valor: string;
  onCambio: (v: string) => void;
  deshabilitado: boolean;
  aria?: string;
}) {
  const id = useId();
  const malo = aNumero(valor) === null;
  return (
    <div className="space-y-1">
      {aria ? (
        <div className="text-[12.5px] font-medium text-slate-800">{etiqueta}</div>
      ) : (
        <label htmlFor={id} className="block text-[12.5px] font-medium text-slate-800">
          {etiqueta}
        </label>
      )}
      <input
        id={id}
        aria-label={aria}
        aria-invalid={malo}
        aria-describedby={`${id}-a`}
        inputMode="decimal"
        className={CAJA_NUMERO}
        disabled={deshabilitado}
        value={valor}
        onChange={(e) => onCambio(e.target.value)}
      />
      {malo && <span className="ml-2 text-[12px] text-red-700">Escribe un número.</span>}
      <p id={`${id}-a`} className="text-[12px] text-slate-500">
        {ayuda}
      </p>
    </div>
  );
}

function FormularioBodega({ bodega, tiposSugeridos, puedeEditar, onGuardada }: {
  bodega: BodegaCD;
  tiposSugeridos: string[];
  puedeEditar: boolean;
  onGuardada: (b: BodegaCD) => void;
}) {
  const [original, setOriginal] = useState(bodega);
  const [b, setB] = useState<Borrador>(() => aBorrador(bodega));
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  const [ok, setOk] = useState<string | null>(null);
  const [avisos, setAvisos] = useState<string[]>([]);
  const idNombre = useId();
  const idActiva = useId();

  const cambios = cambiosDe(original, b);
  const hayCambios = Object.keys(cambios).length > 0;
  const incompleto =
    CAMPOS_NUMERICOS.some((c) => aNumero(b[c]) === null) || b.nombre.trim() === "" ||
    b.tipos_venta.length === 0 || b.bodegas_stock.length === 0;
  const deshabilitado = !puedeEditar;

  function poner<K extends keyof Borrador>(campo: K, valor: Borrador[K]) {
    setOk(null);
    setB((x) => ({ ...x, [campo]: valor }));
  }

  async function guardar() {
    setGuardando(true);
    setError(null);
    setOk(null);
    setAvisos([]);
    try {
      const { cambios: cambiados, avisos: avisosServidor, ...guardada } = await canalDigitalApi.guardarBodega(
        original.bodega,
        cambios
      );
      setOriginal(guardada);
      setB(aBorrador(guardada));
      setOk(
        cambiados.length > 0
          ? "Parámetros guardados. El resumen y los sugeridos de esta bodega se recalcularon."
          : "Esos valores ya estaban guardados: no cambió nada."
      );
      setAvisos(avisosServidor);
      onGuardada(guardada);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="space-y-4">
      <p className="rounded-md bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
        Al guardar, el resumen y los sugeridos de esta bodega se recalculan al tiro. Si cambias los tipos de venta, el
        cambio vale desde la próxima carga de líneas del ERP: la venta que ya está guardada no se vuelve a filtrar.
      </p>
      <Seccion titulo={`Bodega ${original.bodega}`}>
        <div className="space-y-1">
          <label htmlFor={idNombre} className="block text-[12.5px] font-medium text-slate-800">
            Nombre de la bodega
          </label>
          <input
            id={idNombre}
            className={`${CAJA} max-w-sm`}
            disabled={deshabilitado}
            value={b.nombre}
            onChange={(e) => poner("nombre", e.target.value)}
          />
        </div>
        <div className="flex items-start gap-2">
          <input
            id={idActiva}
            type="checkbox"
            className="mt-0.5"
            disabled={deshabilitado}
            checked={b.activa}
            onChange={(e) => poner("activa", e.target.checked)}
          />
          <label htmlFor={idActiva} className="text-[12.5px] text-slate-800">
            <span className="font-medium">Bodega activa</span>
            <span className="block text-[12px] text-slate-500">
              Una bodega desactivada se puede seguir consultando; la pantalla avisa que está desactivada.
            </span>
          </label>
        </div>
      </Seccion>

      <Seccion titulo="Qué cuenta como venta del canal">
        <EditorChips
          etiqueta="Tipos de venta que cuentan como venta del canal"
          ayuda="Las líneas del ERP con alguno de estos tipos suman a la venta de la bodega. Escríbelo igual que viene en el ERP."
          agregarEtiqueta="Agregar tipo de venta"
          valores={b.tipos_venta}
          onCambio={(v) => poner("tipos_venta", v)}
          deshabilitado={deshabilitado}
          sugerencias={tiposSugeridos}
          obligatorio
        />
      </Seccion>

      <Seccion titulo="Cómo se calcula la reposición">
        <div className="grid gap-4 sm:grid-cols-2">
          <CampoNumero
            etiqueta="Semanas entre revisiones"
            ayuda="Cada cuántas semanas se revisa y se repone esta bodega. De 0 a 8."
            valor={b.r_semanas}
            onCambio={(v) => poner("r_semanas", v)}
            deshabilitado={deshabilitado}
          />
          <CampoNumero
            etiqueta="Días de gestión que se suman al plazo"
            ayuda="Días internos que se suman al plazo de entrega del proveedor. De 0 a 30."
            valor={b.gestion_dias}
            onCambio={(v) => poner("gestion_dias", v)}
            deshabilitado={deshabilitado}
          />
          <CampoNumero
            etiqueta="Meses para considerar nuevo un producto"
            ayuda="Un producto con su primera venta hace menos meses que esto es NUEVO y todavía no entra a los clusters. De 1 a 12."
            valor={b.nuevo_meses}
            onCambio={(v) => poner("nuevo_meses", v)}
            deshabilitado={deshabilitado}
          />
        </div>
        <div role="group" aria-labelledby={`${idNombre}-cortes`} className="space-y-1">
          <div id={`${idNombre}-cortes`} className="text-[12.5px] font-medium text-slate-800">
            Corte A / Corte B del Pareto (%)
          </div>
          <p className="text-[12px] text-slate-500">
            Un producto es A mientras lo vendido antes que él (acumulado) no llegue al corte A, y B hasta el corte B; el
            resto es C. El corte A debe ser menor que el B, y el B no puede pasar de 100.
          </p>
          <div className="flex flex-wrap gap-4">
            <CampoNumero
              etiqueta="Corte A"
              aria="Corte A del Pareto (%)"
              ayuda="Por ejemplo, 80."
              valor={b.corte_a_pct}
              onCambio={(v) => poner("corte_a_pct", v)}
              deshabilitado={deshabilitado}
            />
            <CampoNumero
              etiqueta="Corte B"
              aria="Corte B del Pareto (%)"
              ayuda="Por ejemplo, 95."
              valor={b.corte_b_pct}
              onCambio={(v) => poner("corte_b_pct", v)}
              deshabilitado={deshabilitado}
            />
          </div>
        </div>
        <p className="text-[12px] text-slate-500">
          Ventana de venta: {original.ventana_meses} meses, fija. Los topes de frecuencia (A de 8 a 12 meses con venta, B de 5
          a 7, C de 1 a 4) están pensados para 12 meses, por eso no se cambia.
        </p>
      </Seccion>

      <Seccion titulo="Qué stock se mira">
        <p className="text-[12px] text-slate-500">
          Escribe los nombres tal como vienen del ERP. Una bodega va en una sola de las tres listas.
        </p>
        <EditorChips
          etiqueta="Bodegas cuyo stock cuenta como disponible"
          ayuda="Su stock se suma al disponible del producto."
          agregarEtiqueta="Agregar bodega que suma al disponible"
          valores={b.bodegas_stock}
          onCambio={(v) => poner("bodegas_stock", v)}
          deshabilitado={deshabilitado}
          obligatorio
          porClave
        />
        <EditorChips
          etiqueta="Bodegas que se muestran aparte (no suman)"
          ayuda="Su stock se ve en la tabla de productos, pero no se suma al disponible."
          agregarEtiqueta="Agregar bodega que se muestra aparte"
          valores={b.bodegas_aparte}
          onCambio={(v) => poner("bodegas_aparte", v)}
          deshabilitado={deshabilitado}
          porClave
        />
        <EditorChips
          etiqueta="Bodegas solo informativas"
          ayuda="Se muestran como dato de referencia y no entran al cálculo."
          agregarEtiqueta="Agregar bodega informativa"
          valores={b.bodegas_informativas}
          onCambio={(v) => poner("bodegas_informativas", v)}
          deshabilitado={deshabilitado}
          porClave
        />
      </Seccion>

      {/* Los mensajes van junto a los botones: el formulario es largo y el motivo de un rechazo tiene que verse donde se guardo. */}
      {(error || ok || avisos.length > 0) && (
        <div className="space-y-2">
          {error && (
            <pre role="alert" className="whitespace-pre-wrap rounded-md bg-red-50 px-3 py-2 text-[12.5px] text-red-700">
              {error}
            </pre>
          )}
          {ok && (
            <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-[12.5px] text-emerald-800">
              {ok}
            </p>
          )}
          {avisos.map((a) => (
            <p key={a} className="rounded-md bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
              {a}
            </p>
          ))}
        </div>
      )}

      {puedeEditar ? (
        <div className="flex gap-2">
          <button type="button" onClick={guardar} disabled={!hayCambios || incompleto || guardando} className={BOTON_PRIMARIO}>
            <Save size={14} /> {guardando ? "Guardando…" : "Guardar parámetros"}
          </button>
          <button
            type="button"
            onClick={() => {
              setB(aBorrador(original));
              setError(null);
            }}
            disabled={!hayCambios}
            className={BOTON_SECUNDARIO}
          >
            <RotateCcw size={14} /> Descartar cambios
          </button>
        </div>
      ) : (
        <p className="text-[12px] text-slate-500">
          Tu usuario es de solo lectura: puedes ver los parámetros pero no cambiarlos.
        </p>
      )}
    </div>
  );
}

/** Alta de una bodega: codigo y nombre. Nace con los parametros de siembra y la politica provisoria. */
function FormularioNueva({ onCreada, onCancelar }: { onCreada: (b: BodegaCD) => void; onCancelar: () => void }) {
  const [codigo, setCodigo] = useState("");
  const [nombre, setNombre] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [creando, setCreando] = useState(false);
  const idCodigo = useId();
  const idNombre = useId();

  async function crear() {
    setCreando(true);
    setError(null);
    try {
      onCreada(await canalDigitalApi.crearBodega(codigo.trim(), nombre));
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo crear la bodega");
      setCreando(false);
    }
  }

  return (
    <section aria-label="Agregar bodega" className="space-y-3 rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="text-[13px] font-semibold text-slate-900">Agregar bodega</h2>
      <p className="text-[12px] text-slate-500">
        Nace con los parámetros estándar y la política provisoria; después los ajustas aquí. No se puede borrar: si ya no
        se usa, se desactiva.
      </p>
      {error && (
        <pre role="alert" className="whitespace-pre-wrap rounded-md bg-red-50 px-3 py-2 text-[12.5px] text-red-700">
          {error}
        </pre>
      )}
      <div className="flex flex-wrap gap-4">
        <div className="space-y-1">
          <label htmlFor={idCodigo} className="block text-[12.5px] font-medium text-slate-800">
            Código de la bodega
          </label>
          <input
            id={idCodigo}
            className={`${CAJA} w-32 font-mono uppercase`}
            maxLength={12}
            value={codigo}
            onChange={(e) => setCodigo(e.target.value)}
          />
          <p className="text-[12px] text-slate-500">De 1 a 12 letras o números, sin espacios.</p>
        </div>
        <div className="min-w-[14rem] flex-1 space-y-1">
          <label htmlFor={idNombre} className="block text-[12.5px] font-medium text-slate-800">
            Nombre de la nueva bodega
          </label>
          <input id={idNombre} className={`${CAJA} max-w-sm`} value={nombre} onChange={(e) => setNombre(e.target.value)} />
          <p className="text-[12px] text-slate-500">Si lo dejas vacío, se llama «Canal digital» y el código.</p>
        </div>
      </div>
      <div className="flex gap-2">
        <button type="button" onClick={crear} disabled={!codigo.trim() || creando} className={BOTON_PRIMARIO}>
          <Plus size={14} /> {creando ? "Creando…" : "Crear bodega"}
        </button>
        <button type="button" onClick={onCancelar} disabled={creando} className={BOTON_SECUNDARIO}>
          Cancelar
        </button>
      </div>
    </section>
  );
}

interface Props {
  /** La bodega elegida arriba en la pagina: es la que se edita. */
  bodega: string;
  /** Null mientras se carga la lista. */
  datos: BodegasCanalDigital | null;
  error: string | null;
  puedeEditar: boolean;
  esAdmin: boolean;
  onReintentar: () => void;
  onGuardada: (b: BodegaCD) => void;
  /** La pagina agrega la bodega a su lista y pasa a verla. */
  onCreada: (b: BodegaCD) => void;
}

export function PestanaBodegas({ bodega, datos, error, puedeEditar, esAdmin, onReintentar, onGuardada, onCreada }: Props) {
  const [agregando, setAgregando] = useState(false);
  const [creada, setCreada] = useState<string | null>(null);
  const actual = datos?.bodegas.find((x) => x.bodega === bodega) ?? null;

  return (
    <div className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12.5px] text-slate-500">
          Los parámetros de la bodega {bodega}: qué se considera venta del canal, cómo se clasifica y qué stock se mira.
        </p>
        {esAdmin && !agregando && (
          <button
            type="button"
            onClick={() => {
              setAgregando(true);
              setCreada(null);
            }}
            className={BOTON_SECUNDARIO}
          >
            <Plus size={14} /> Agregar bodega
          </button>
        )}
      </div>

      {creada && (
        <p role="status" className="rounded-md bg-emerald-50 px-3 py-2 text-[12.5px] text-emerald-800">
          Bodega {creada} creada. Estás viendo sus parámetros: ajústalos y guarda.
        </p>
      )}

      {esAdmin && agregando && (
        <FormularioNueva
          onCancelar={() => setAgregando(false)}
          onCreada={(b) => {
            setAgregando(false);
            setCreada(b.bodega);
            onCreada(b);
          }}
        />
      )}

      {error && (
        <div className="space-y-2">
          <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">
            {error}
          </p>
          <button type="button" onClick={onReintentar} className={BOTON_SECUNDARIO}>
            <RefreshCw size={14} /> Reintentar
          </button>
        </div>
      )}

      {!error && !datos && (
        <p role="status" className="text-[13px] text-slate-500">
          Cargando bodegas…
        </p>
      )}

      {datos && !actual && !error && (
        <p className="rounded-md bg-amber-50 px-3 py-2 text-[13px] text-amber-900">
          No se encontró la bodega {bodega} entre las bodegas del canal.
        </p>
      )}

      {actual && (
        <FormularioBodega
          key={actual.bodega}
          bodega={actual}
          tiposSugeridos={datos?.tipos_venta_sugeridos ?? []}
          puedeEditar={puedeEditar}
          onGuardada={onGuardada}
        />
      )}
    </div>
  );
}
