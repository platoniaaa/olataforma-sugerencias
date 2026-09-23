"use client";

/**
 * Recorrido guiado de la lista de precios.
 *
 * El modulo reemplazo un Excel y un .exe que Abastecimiento manejaba de memoria:
 * la regla de precios es la misma de siempre, pero ya no esta a la vista en
 * ninguna celda. Sin este recorrido, el orden de prioridades (precio fijo gana a
 * congelado, congelado gana a la regla, sin stock manda antes que "no es
 * producto") hay que adivinarlo mirando resultados.
 *
 * Antes era un modal con trece pantallas de texto y la gente lo cerraba sin
 * leerlo: describia botones que no estaba viendo. Ahora el recorrido pasa por la
 * pantalla de verdad: oscurece todo menos el elemento del que habla (los
 * elementos se marcan con `data-tour`) y, en los pasos de la ficha, abre la
 * ficha de un producto real. Lo que no esta en pantalla -un boton que el usuario
 * no tiene permiso de ver, una lista vacia- se dice, en vez de apuntar al vacio.
 *
 * El texto describe la pantalla, no las tablas: quien lo lee es un analista de
 * repuestos, no quien la programo.
 */

import { useCallback, useEffect, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import {
  Bell, Calculator, CheckCircle2, ChevronLeft, ChevronRight, Columns3, Compass, Download,
  FileText, Filter, Gauge, GraduationCap, Pencil, Plus, RefreshCw, Sigma, Table2, Tag, X,
} from "lucide-react";
import { Button } from "@/components/ui/button";

// Se recuerda que ya se vio para que el recorrido se abra SOLO la primera vez.
// No esconde nada: el boton Tutorial queda siempre arriba. Lo que evita es que
// la pantalla arranque tapada cada manana.
const LS_VISTO = "precios_tutorial_visto";

// Aire entre el elemento destacado y el borde del recorte.
const MARGEN = 8;
// Separacion entre el recorte y el cuadro con el texto.
const SEPARACION = 14;
// Alto de la barra superior fija de la plataforma: lo que hay que dejar libre
// al desplazar un elemento hacia arriba para que no quede escondido debajo.
const BARRA_SUPERIOR = 88;
const RADIO = 10;

/** Lo que el recorrido necesita que la pantalla haga por el: abrir y cerrar la
 *  ficha de un producto real para los pasos que hablan de ella. */
export interface AccionesTutorial {
  /** Abre la ficha de un producto de la lista. Devuelve false si no hay ninguno. */
  abrirFicha?: () => boolean;
  cerrarFicha?: () => void;
}

type Lado = "abajo" | "arriba" | "derecha" | "izquierda";

interface Paso {
  titulo: string;
  icono: ReactNode;
  /** Valor del `data-tour` del elemento que se destaca. Sin destino, el paso va centrado. */
  destino?: string;
  /** El paso habla de la ficha: hay que abrirla antes de mostrarlo. */
  ficha?: boolean;
  /** Tope de alto del recorte. La tabla mide toda la pantalla; con destacar el
   *  encabezado y las primeras filas alcanza y queda lugar para el texto. */
  alto?: number;
  /** De que lado del elemento conviene poner el texto. Si no cabe, se prueba el resto. */
  lado?: Lado;
  /** Que decir cuando el elemento no esta en pantalla (permiso, lista vacia). */
  siFalta?: string;
  cuerpo: ReactNode;
}

function Nota({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-sm border-l-2 border-accent-700 bg-accent-50 px-3 py-2 text-[13px] text-ink-700">
      {children}
    </p>
  );
}

const SIN_PERMISO =
  "Este botón no aparece en tu pantalla porque tu usuario puede ver la lista pero no editarla. Si te corresponde editar, se pide y listo.";
const SIN_FICHA = "No hay productos en la lista para abrir una ficha de ejemplo. Cuando tenga datos, este paso la abre solo.";

const PASOS: Paso[] = [
  {
    titulo: "Qué es esta pantalla",
    icono: <Tag size={16} />,
    destino: "titulo",
    cuerpo: (
      <>
        <p>
          Esta es la lista de precios que se sube al ERP. Es la misma que antes vivía en el
          Excel y se armaba con el programa de un PC de la oficina.
        </p>
        <p>
          Ahora vive acá, al lado del stock, del costo y de las compras que la plataforma
          recibe todos los días, y se recalcula <b>sola, cada mañana</b>, cuando el motor
          termina de publicar. No hay que apretar nada para tener los datos del día.
        </p>
        <p className="text-ink-500">
          El recorrido va marcando en la pantalla cada cosa de la que habla. Avanza con{" "}
          <b>Siguiente</b> o con las flechas del teclado; ciérralo cuando quieras.
        </p>
      </>
    ),
  },
  {
    titulo: "Los números de arriba",
    icono: <Gauge size={16} />,
    destino: "kpis",
    cuerpo: (
      <ul className="list-disc space-y-1.5 pl-5">
        <li><b>Productos</b>: cuántos hay hoy en la lista.</li>
        <li>
          <b>Con cambios sin revisar</b>: diferencias que encontró el último recálculo y que
          nadie ha mirado. Hazle clic y la lista se filtra a esos.
        </li>
        <li>
          <b>Último recálculo</b>: cuándo se recalculó por última vez y, debajo, cuándo fue el
          último envío al ERP.
        </li>
      </ul>
    ),
  },
  {
    titulo: "Buscar y filtrar",
    icono: <Filter size={16} />,
    destino: "filtros",
    cuerpo: (
      <>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>El buscador encuentra por <b>código o glosa</b>, en los 39 mil productos.</li>
          <li>Los filtros son por <b>rubro</b>, <b>tipo</b>, <b>procedencia</b> y <b>estado</b>.</li>
          <li>
            <b>Con stock</b> deja solo lo que hay en bodega; <b>Creados aquí</b>, lo que se
            agregó desde la plataforma.
          </li>
        </ul>
        <p>
          Se combinan entre sí y con los números de arriba. Cuando hay alguno puesto aparece{" "}
          <b>Limpiar</b>, que deja la lista completa de nuevo.
        </p>
      </>
    ),
  },
  {
    titulo: "Elegir qué columnas ver",
    icono: <Columns3 size={16} />,
    destino: "columnas",
    cuerpo: (
      <>
        <p>
          <b>Columnas</b> abre la lista de todo lo que se puede mostrar. Hay bastante más de lo
          que se ve por defecto: el precio calculado, la desviación contra lo que tiene hoy el
          ERP, las fechas de las últimas compras, la observación, quién editó y cuándo.
        </p>
        <p>
          Tu elección se guarda <b>en este navegador</b>; <b>Restaurar por defecto</b> la deja
          como venía.
        </p>
      </>
    ),
  },
  {
    titulo: "La tabla",
    icono: <Table2 size={16} />,
    destino: "tabla",
    alto: 300,
    cuerpo: (
      <>
        <p>
          Una fila por producto. El <b>Estado</b> dice de un vistazo qué pasa con el precio:{" "}
          <b>OK</b> sigue la regla, <b>FIJO</b> lo puso una persona, <b>SIN STOCK</b> sale en
          $0 y <b>SIN REVISION</b>, en rojo, es el que hay que mirar antes de mandar la lista.
        </p>
        <p>
          <b>Clic en una fila</b> abre la ficha del producto, que es lo que viene ahora. Con el
          botón derecho aparece <b>Sacar de la lista</b>.
        </p>
      </>
    ),
  },
  {
    titulo: "La ficha: el precio y su porqué",
    icono: <FileText size={16} />,
    destino: "ficha-precio",
    ficha: true,
    lado: "abajo",
    siFalta: SIN_FICHA,
    cuerpo: (
      <>
        <p>
          Se abrió la ficha de un producto real. Arriba está el resultado: el <b>precio final</b>{" "}
          con su estado, la fórmula con la que se llegó a él en una línea, y al lado el{" "}
          <b>precio que tiene hoy el ERP</b> con la diferencia entre ambos.
        </p>
        <p>Si un precio te extraña, la respuesta está acá: se lee de corrido.</p>
      </>
    ),
  },
  {
    titulo: "Cómo se calcula un precio",
    icono: <Calculator size={16} />,
    destino: "ficha-origen",
    ficha: true,
    lado: "izquierda",
    siFalta: SIN_FICHA,
    cuerpo: (
      <>
        <p>Se prueba en este orden y gana el primero que aplica:</p>
        <ol className="list-decimal space-y-1 pl-5">
          <li><b>Precio fijo</b> puesto a mano: ese es el precio, pase lo que pase.</li>
          <li><b>Precio congelado</b>: el que tenía cuando lo congelaste.</li>
          <li><b>Sin stock y nada en tránsito</b>: precio 0, porque el ERP no lo ofrece.</li>
          <li><b>No es un producto</b> (servicios, mano de obra, cargos): sin precio.</li>
          <li><b>Tipo Sugerido</b>: se usa la lista del proveedor.</li>
          <li><b>El resto</b>: <b>costo × factor</b>.</li>
        </ol>
        <p>
          Este bloque muestra cada pieza: rubro, tipo, factor, costo, stock y tránsito, y las
          últimas compras. El factor sale del par <b>Tipo</b> y <b>Procedencia</b>; el tipo lo
          pone el rubro, salvo que lo escribas a mano o que la glosa empiece con NEU, que es
          neumático y se clasifica solo.
        </p>
        <Nota>
          El 3 va antes que el 4: un servicio sin stock sale en 0, no sin precio. Es tal cual
          lo hacía el programa antiguo.
        </Nota>
      </>
    ),
  },
  {
    titulo: "De dónde sale la procedencia",
    icono: <Compass size={16} />,
    destino: "ficha-origen",
    ficha: true,
    lado: "izquierda",
    siFalta: SIN_FICHA,
    cuerpo: (
      <>
        <p>
          Al lado de cada dato dice quién lo decidió. Para la procedencia, el primero que aplica
          gana:
        </p>
        <ol className="list-decimal space-y-1 pl-5">
          <li>La que hayas <b>escrito a mano</b> en esta ficha.</li>
          <li>La <b>procedencia fija del rubro</b>, si tiene una.</li>
          <li>La <b>última compra</b>: recepción importada, Importado; P/E nacional, Nacional.</li>
          <li>Lo que diga el <b>maestro</b> del ERP.</li>
          <li>Si nada de eso alcanza, queda en <b>SIN REVISION</b>.</li>
        </ol>
        <Nota>
          Sin procedencia no hay factor, y sin factor no hay precio. Por eso SIN REVISION sale
          en rojo: hay que resolverlo antes de mandar la lista al ERP.
        </Nota>
      </>
    ),
  },
  {
    titulo: "Decidir sobre un precio",
    icono: <Pencil size={16} />,
    destino: "ficha-decision",
    ficha: true,
    lado: "derecha",
    siFalta: SIN_FICHA,
    cuerpo: (
      <>
        <ul className="list-disc space-y-1.5 pl-5">
          <li><b>Precio fijo</b>: ese es el precio. Gana a todo, incluso sin stock.</li>
          <li><b>Congelar</b>: deja el precio de hoy aunque después cambie el costo.</li>
          <li><b>Tipo o Procedencia a mano</b>: para cuando la regla se equivoca.</li>
          <li><b>No es un producto</b>: servicios, mano de obra y cargos, sin precio.</li>
          <li><b>Observación</b>: para dejar dicho por qué.</li>
        </ul>
        <p><b>Volver a la regla</b> borra todo eso de una y el producto se vuelve a calcular solo.</p>
        <Nota>
          Lo que decides acá <b>no lo pisa nunca el recálculo</b>: se guarda aparte, a
          propósito. Si no ves los controles, tu usuario puede mirar pero no editar.
        </Nota>
      </>
    ),
  },
  {
    titulo: "Recalcular",
    icono: <RefreshCw size={16} />,
    destino: "recalcular",
    siFalta: `${SIN_PERMISO} El motor recalcula igual cada mañana, con o sin este botón.`,
    cuerpo: (
      <>
        <p>
          Hace a mano lo mismo que el motor hace cada mañana: relee stock, tránsito, costo y
          compras, y vuelve a aplicar la regla a los 39 mil productos.
        </p>
        <p>
          Casi nunca hace falta. Sirve cuando alguien cambió la política de factores o los
          rubros y quiere ver el efecto ahora. Demora unos minutos y <b>no manda nada al ERP</b>.
        </p>
      </>
    ),
  },
  {
    titulo: "Crear un producto",
    icono: <Plus size={16} />,
    destino: "nuevo",
    siFalta: SIN_PERMISO,
    cuerpo: (
      <>
        <p>
          <b>Nuevo producto</b> sirve para lo que todavía no está en el ERP. El código se
          escribe como allá, con el rubro adelante (por ejemplo{" "}
          <span className="font-mono">71 2720142</span>).
        </p>
        <p>
          Puedes dejarle glosa, tipo, procedencia, costo, stock y un precio fijo. Lo que no
          llenes lo resuelve la regla. Queda en la lista como los demás y sale en el próximo
          envío al ERP.
        </p>
      </>
    ),
  },
  {
    titulo: "Marcar los cambios revisados",
    icono: <Bell size={16} />,
    destino: "revisados",
    siFalta:
      "El botón aparece solo cuando hay cambios pendientes de revisar, y solo para quien edita la lista. Ahora mismo no hay nada pendiente o tu usuario no edita.",
    cuerpo: (
      <>
        <p>
          Cuando terminaste de mirar los cambios pendientes, aprieta <b>Marcar revisados</b> y
          el contador de arriba vuelve a cero.
        </p>
        <p>
          Con un filtro puesto marca <b>solo los que estás viendo</b>, y el botón te lo avisa.
          Así puedes ir cerrando por rubro sin dar por revisado lo que no miraste.
        </p>
      </>
    ),
  },
  {
    titulo: "Exportar al ERP",
    icono: <Download size={16} />,
    destino: "exportar",
    cuerpo: (
      <>
        <ul className="list-disc space-y-1.5 pl-5">
          <li><b>Exportar completa</b>: baja toda la lista.</li>
          <li>
            <b>Solo diferencias</b>: baja únicamente lo que cambió desde el último envío. Es lo
            normal del día a día; el número al lado dice cuántos van.
          </li>
        </ul>
        <p>
          El archivo trae tres columnas, <b>código</b>, <b>precio</b> y <b>costo</b>, las mismas
          que aceptaba el programa antiguo.
        </p>
        <Nota>
          Las dos exportaciones quedan registradas como envío: si bajas la lista completa, el
          contador de diferencias parte de cero desde ahí.
        </Nota>
      </>
    ),
  },
  {
    titulo: "La política",
    icono: <Sigma size={16} />,
    destino: "politica",
    cuerpo: (
      <>
        <p>
          <b>Política</b> lleva a la pantalla con los factores por tipo y procedencia, el
          margen que deja cada uno, y el tipo y la procedencia fija de cada rubro. Es donde se
          ve de dónde salió el factor que estás viendo en un producto.
        </p>
        <p>
          La puede editar cualquiera del equipo de precios, igual que un precio fijo. Ojo con
          una diferencia: cambiar un factor o un rubro <b>recalcula la lista entera</b> al
          guardar, así que mueve miles de precios de una.
        </p>
        <Nota>
          Por eso cada cambio queda en <b>Auditoría</b> con tu nombre, la fecha y el valor
          anterior. Si un día los precios amanecen distintos, ahí está la respuesta.
        </Nota>
      </>
    ),
  },
  {
    titulo: "Eso es todo",
    icono: <CheckCircle2 size={16} />,
    cuerpo: (
      <>
        <p>
          Puedes mirar y probar sin miedo: acá no se rompe nada. Cada cambio queda guardado con
          tu nombre y la fecha, y <b>Volver a la regla</b> deshace cualquier decisión sobre un
          producto.
        </p>
        <p>
          Lo único que sale de la plataforma es el archivo que exportas tú. Mientras no lo
          subas al ERP, nada de lo que hagas acá le cambia el precio a nadie.
        </p>
        <p className="text-ink-500">
          Este recorrido queda en el botón <b>Tutorial</b>, arriba. Ábrelo las veces que
          necesites.
        </p>
      </>
    ),
  },
];

interface Recuadro {
  top: number;
  left: number;
  width: number;
  height: number;
}

/** Busca el elemento del paso, lo trae a la vista y sigue su posicion mientras
 *  el paso este activo. `buscado` dice que la busqueda termino: con `recuadro`
 *  nulo despues de eso, el elemento no esta en pantalla. */
function useDestino(destino: string | undefined, activo: boolean, alto?: number) {
  const [recuadro, setRecuadro] = useState<Recuadro | null>(null);
  const [buscado, setBuscado] = useState(false);

  useEffect(() => {
    setRecuadro(null);
    setBuscado(false);
    if (!activo || !destino) {
      setBuscado(true);
      return;
    }
    let el: HTMLElement | null = null;
    let cancelado = false;
    let intentos = 0;
    let observador: ResizeObserver | null = null;

    const medir = () => {
      if (!el || cancelado) return;
      const r = el.getBoundingClientRect();
      setRecuadro({
        top: r.top,
        left: r.left,
        width: r.width,
        height: alto ? Math.min(r.height, alto) : r.height,
      });
    };

    const buscar = () => {
      if (cancelado) return;
      el = document.querySelector<HTMLElement>(`[data-tour="${destino}"]`);
      const r = el?.getBoundingClientRect();
      // La ficha y la tabla se pintan despues de pedir los datos: se insiste un
      // par de segundos antes de darlo por ausente. Un elemento sin tamano es
      // uno que no se ve.
      if (!el || !r || (r.width === 0 && r.height === 0)) {
        el = null;
        if (intentos++ < 20) setTimeout(buscar, 100);
        else setBuscado(true);
        return;
      }
      const visible = alto ? Math.min(r.height, alto) : r.height;
      const cabe = r.top >= BARRA_SUPERIOR && r.top + visible <= window.innerHeight - 16;
      if (!cabe) {
        // Con tope de alto se alinea arriba (lo que importa es el comienzo);
        // sin tope, al centro.
        const objetivo = alto
          ? window.scrollY + r.top - BARRA_SUPERIOR
          : window.scrollY + r.top - (window.innerHeight - visible) / 2;
        try {
          window.scrollTo({ top: Math.max(0, objetivo) });
        } catch {
          /* sin scroll programatico (pruebas) */
        }
      }
      medir();
      setBuscado(true);
      if (typeof ResizeObserver !== "undefined") {
        observador = new ResizeObserver(medir);
        observador.observe(el);
      }
      window.addEventListener("resize", medir);
      window.addEventListener("scroll", medir, true);
    };

    buscar();
    return () => {
      cancelado = true;
      observador?.disconnect();
      window.removeEventListener("resize", medir);
      window.removeEventListener("scroll", medir, true);
    };
  }, [destino, activo, alto]);

  return { recuadro, buscado };
}

/** Recorte redondeado como trazo SVG, para dibujarlo como agujero (evenodd). */
function trazoRecorte(r: Recuadro) {
  const x = r.left - MARGEN;
  const y = r.top - MARGEN;
  const w = r.width + MARGEN * 2;
  const h = r.height + MARGEN * 2;
  const rad = Math.min(RADIO, w / 2, h / 2);
  return (
    `M${x + rad} ${y}h${w - rad * 2}a${rad} ${rad} 0 0 1 ${rad} ${rad}v${h - rad * 2}` +
    `a${rad} ${rad} 0 0 1 -${rad} ${rad}h-${w - rad * 2}a${rad} ${rad} 0 0 1 -${rad} -${rad}` +
    `v-${h - rad * 2}a${rad} ${rad} 0 0 1 ${rad} -${rad}z`
  );
}

/** Donde poner el cuadro respecto del recorte: se prueba el lado pedido y,
 *  si no cabe, el resto en orden; como ultimo recurso se superpone, siempre
 *  dentro de la pantalla. */
function ubicarCuadro(
  r: Recuadro | null, ancho: number, altoCuadro: number, lado: Lado | undefined,
  vw: number, vh: number,
) {
  const clampX = (x: number) => Math.max(16, Math.min(x, vw - ancho - 16));
  const clampY = (y: number) => Math.max(16, Math.min(y, vh - altoCuadro - 16));
  if (!r) return { top: clampY((vh - altoCuadro) / 2), left: clampX((vw - ancho) / 2) };

  const arriba = r.top - MARGEN - SEPARACION;
  const abajo = r.top + r.height + MARGEN + SEPARACION;
  const izquierda = r.left - MARGEN - SEPARACION;
  const derecha = r.left + r.width + MARGEN + SEPARACION;

  const candidatos: Record<Lado, { cabe: boolean; top: number; left: number }> = {
    abajo: { cabe: abajo + altoCuadro <= vh - 16, top: abajo, left: clampX(r.left - MARGEN) },
    arriba: { cabe: arriba - altoCuadro >= 16, top: arriba - altoCuadro, left: clampX(r.left - MARGEN) },
    derecha: { cabe: derecha + ancho <= vw - 16, top: clampY(r.top - MARGEN), left: derecha },
    izquierda: { cabe: izquierda - ancho >= 16, top: clampY(r.top - MARGEN), left: izquierda - ancho },
  };
  const orden: Lado[] = ["abajo", "derecha", "izquierda", "arriba"];
  for (const l of lado ? [lado, ...orden.filter((o) => o !== lado)] : orden) {
    if (candidatos[l].cabe) return { top: candidatos[l].top, left: candidatos[l].left };
  }
  return { top: clampY(abajo), left: clampX(r.left - MARGEN) };
}

/** Boton "Tutorial" de la barra superior de /precios y el recorrido que abre. */
export function TutorialPrecios({ acciones }: { acciones?: AccionesTutorial } = {}) {
  const [abierto, setAbierto] = useState(false);
  const [paso, setPaso] = useState(0);
  // Las acciones cambian de identidad en cada render de la pagina (cierran
  // sobre las filas); se leen por ref para no reiniciar nada por eso.
  const accionesRef = useRef(acciones);
  accionesRef.current = acciones;
  // Si la ficha la abrio el recorrido, el recorrido la cierra al salir de esos
  // pasos o al terminar. Una ficha que abrio la persona no se toca.
  const fichaPorTour = useRef(false);

  useEffect(() => {
    // En el servidor no hay localStorage, por eso la primera apertura se decide
    // aca y no en el estado inicial.
    if (localStorage.getItem(LS_VISTO) !== "1") setAbierto(true);
  }, []);

  const actual = PASOS[paso];
  const esUltimo = paso === PASOS.length - 1;

  const soltarFicha = useCallback(() => {
    if (!fichaPorTour.current) return;
    accionesRef.current?.cerrarFicha?.();
    fichaPorTour.current = false;
  }, []);

  const irA = useCallback((i: number) => {
    const siguiente = PASOS[i];
    if (!siguiente) return;
    if (siguiente.ficha) {
      if (!fichaPorTour.current) fichaPorTour.current = accionesRef.current?.abrirFicha?.() ?? false;
    } else {
      soltarFicha();
    }
    setPaso(i);
  }, [soltarFicha]);

  const cerrar = useCallback(() => {
    soltarFicha();
    localStorage.setItem(LS_VISTO, "1");
    setAbierto(false);
  }, [soltarFicha]);

  function abrir() {
    setPaso(0);
    setAbierto(true);
  }

  // Teclado: Escape cierra, las flechas navegan. Va en captura y corta la
  // propagacion del Escape: la ficha tambien lo escucha y se cerraria a la vez.
  useEffect(() => {
    if (!abierto) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.stopPropagation();
        cerrar();
      } else if (e.key === "ArrowRight" && !esUltimo) {
        irA(paso + 1);
      } else if (e.key === "ArrowLeft" && paso > 0) {
        irA(paso - 1);
      }
    };
    document.addEventListener("keydown", onKey, true);
    return () => document.removeEventListener("keydown", onKey, true);
  }, [abierto, paso, esUltimo, cerrar, irA]);

  const { recuadro, buscado } = useDestino(actual.destino, abierto, actual.alto);

  // El tamano de la ventana, para el oscurecido y para reubicar el cuadro.
  const [vista, setVista] = useState({ w: 0, h: 0 });
  useEffect(() => {
    if (!abierto) return;
    const medir = () => setVista({ w: window.innerWidth, h: window.innerHeight });
    medir();
    window.addEventListener("resize", medir);
    return () => window.removeEventListener("resize", medir);
  }, [abierto]);

  // El cuadro se mide una vez pintado y recien ahi se ubica: hasta entonces va
  // invisible, para que no se lo vea saltar de un lado a otro.
  const cuadroRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);
  useLayoutEffect(() => {
    if (!abierto || !buscado) return;
    const caja = cuadroRef.current;
    if (!caja) return;
    setPos(ubicarCuadro(recuadro, caja.offsetWidth, caja.offsetHeight, actual.lado,
      window.innerWidth, window.innerHeight));
  }, [abierto, buscado, recuadro, paso, actual.lado, vista]);

  // El foco parte en "Siguiente" para que el teclado sirva desde el primer paso.
  const siguienteRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    if (abierto) siguienteRef.current?.focus();
  }, [abierto, paso]);

  const falta = buscado && actual.destino !== undefined && recuadro === null;

  const recorrido = abierto && typeof document !== "undefined" ? createPortal(
    <div className="fixed inset-0 z-[60]" data-testid="recorrido-precios">
      {/* Oscurece toda la pantalla salvo el recorte del elemento. El rectangulo
          transparente sobre el agujero bloquea los clics: en el paso de
          exportar, un clic que pasara registraria un envio de verdad. */}
      <svg className="absolute inset-0 h-full w-full" aria-hidden="true">
        <path
          fill="rgba(15, 23, 42, 0.58)"
          fillRule="evenodd"
          d={`M0 0H${vista.w}V${vista.h}H0Z` + (recuadro ? trazoRecorte(recuadro) : "")}
        />
        {recuadro && (
          <>
            <rect
              x={recuadro.left - MARGEN} y={recuadro.top - MARGEN}
              width={recuadro.width + MARGEN * 2} height={recuadro.height + MARGEN * 2}
              rx={RADIO} fill="transparent"
              data-testid="recorrido-recorte"
            />
            <rect
              x={recuadro.left - MARGEN} y={recuadro.top - MARGEN}
              width={recuadro.width + MARGEN * 2} height={recuadro.height + MARGEN * 2}
              rx={RADIO} fill="none" strokeWidth={2}
              className="pointer-events-none stroke-brand"
            />
          </>
        )}
      </svg>

      <div
        ref={cuadroRef}
        role="dialog"
        aria-modal="true"
        aria-label={`Recorrido de la lista de precios, paso ${paso + 1} de ${PASOS.length}: ${actual.titulo}`}
        className="absolute flex max-h-[min(72vh,600px)] w-[min(420px,calc(100vw-32px))] flex-col rounded-xl border border-ink-200 bg-white shadow-2xl"
        style={pos ? { top: pos.top, left: pos.left } : { top: 16, left: 16, visibility: "hidden" }}
      >
        <div className="flex items-start justify-between gap-3 border-b border-ink-100 px-4 pb-3 pt-3">
          <div className="min-w-0">
            <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
              Paso {paso + 1} de {PASOS.length}
            </p>
            <h3 className="mt-0.5 flex items-center gap-2 font-display text-[15px] font-medium text-ink-900">
              <span className="text-brand">{actual.icono}</span>
              {actual.titulo}
            </h3>
          </div>
          <button
            onClick={cerrar}
            aria-label="Cerrar"
            className="rounded-md p-1 text-ink-400 hover:bg-ink-100 hover:text-ink-700"
          >
            <X size={18} />
          </button>
        </div>

        <div className="flex items-center gap-1 px-4 pt-3">
          {PASOS.map((p, i) => (
            <button
              key={`${i}-${p.titulo}`}
              onClick={() => irA(i)}
              aria-label={`Ir al paso ${i + 1}: ${p.titulo}`}
              aria-current={i === paso ? "step" : undefined}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                i === paso ? "bg-brand" : i < paso ? "bg-brand-200" : "bg-ink-200 hover:bg-ink-300"
              }`}
            />
          ))}
        </div>

        <div className="min-h-0 flex-1 space-y-2.5 overflow-y-auto px-4 py-3 text-[13.5px] leading-relaxed text-ink-600">
          {falta && actual.siFalta && (
            <p className="rounded-sm border-l-2 border-amber-500 bg-amber-50 px-3 py-2 text-[13px] text-amber-900">
              {actual.siFalta}
            </p>
          )}
          {actual.cuerpo}
        </div>

        <div className="flex items-center justify-end gap-2 border-t border-ink-100 px-4 py-3">
          <Button variant="outline" size="sm" disabled={paso === 0} onClick={() => irA(paso - 1)}>
            <ChevronLeft size={15} /> Anterior
          </Button>
          {esUltimo ? (
            <Button ref={siguienteRef} size="sm" onClick={cerrar}>Listo</Button>
          ) : (
            <Button ref={siguienteRef} size="sm" onClick={() => irA(paso + 1)}>
              Siguiente <ChevronRight size={15} />
            </Button>
          )}
        </div>
      </div>
    </div>,
    document.body,
  ) : null;

  return (
    <>
      <Button variant="outline" size="sm" onClick={abrir}>
        <GraduationCap size={15} /> Tutorial
      </Button>
      {recorrido}
    </>
  );
}
