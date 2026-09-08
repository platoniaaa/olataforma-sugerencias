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
 * El texto describe la pantalla, no las tablas: quien lo lee es un analista de
 * repuestos, no quien la programo.
 */

import { useEffect, useState, type ReactNode } from "react";
import {
  Bell, Calculator, CheckCircle2, ChevronLeft, ChevronRight, Columns3, Compass,
  Download, FileText, Filter, Gauge, GraduationCap, Pencil, Plus, Sigma, Tag,
} from "lucide-react";
import { Button } from "@/components/ui/button";
import { Dialog } from "@/components/ui/dialog";

// Se recuerda que ya se vio para que el recorrido se abra SOLO la primera vez.
// No esconde nada: el boton Tutorial queda siempre arriba. Lo que evita es que
// la pantalla arranque tapada cada manana.
const LS_VISTO = "precios_tutorial_visto";

interface Paso {
  titulo: string;
  icono: ReactNode;
  cuerpo: ReactNode;
}

function Nota({ children }: { children: ReactNode }) {
  return (
    <p className="rounded-sm border-l-2 border-accent-700 bg-accent-50 px-3 py-2 text-[13px] text-ink-700">
      {children}
    </p>
  );
}

const PASOS: Paso[] = [
  {
    titulo: "Qué es esta pantalla",
    icono: <Tag size={16} />,
    cuerpo: (
      <>
        <p>
          Esta es la lista de precios que se sube al ERP. Es la misma que antes vivía en el
          Excel y que se armaba con el programa que corría en un PC de la oficina.
        </p>
        <p>
          Ahora vive acá, al lado del stock, del costo y de las compras que la plataforma
          recibe todos los días. Ya no hay que juntar planillas: los datos llegan solos y tú
          decides sobre los precios.
        </p>
        <p>
          Para que la lista tome los datos del día se aprieta <b>Recalcular</b>, a la derecha de
          los filtros. Vuelve a pasar la regla por toda la lista y deja anotado, producto por
          producto, todo lo que cambió.
        </p>
      </>
    ),
  },
  {
    titulo: "Cómo se calcula un precio",
    icono: <Calculator size={16} />,
    cuerpo: (
      <>
        <p>Se va probando en este orden y gana el primero que aplica:</p>
        <ol className="list-decimal space-y-1.5 pl-5">
          <li><b>Precio fijo</b> puesto a mano: ese es el precio, pase lo que pase.</li>
          <li><b>Precio congelado</b>: el que tenía cuando lo congelaste.</li>
          <li><b>Sin stock y nada en tránsito</b>: precio 0, porque el ERP no lo ofrece.</li>
          <li><b>No es un producto</b> (servicios, mano de obra, cargos): queda sin precio.</li>
          <li><b>Tipo Sugerido</b>: se usa la lista del proveedor.</li>
          <li><b>El resto</b>: <b>costo × factor</b>.</li>
        </ol>
        <p>
          El factor sale del par <b>Tipo</b> y <b>Procedencia</b>. El tipo lo pone el rubro,
          salvo que lo escribas a mano o que la glosa empiece con NEU: eso es neumático y se
          clasifica solo.
        </p>
        <Nota>
          Fíjate en el orden: el 3 va antes que el 4. Un servicio sin stock sale en 0, no sin
          precio. Es tal cual lo hacía el programa antiguo.
        </Nota>
      </>
    ),
  },
  {
    titulo: "De dónde sale la procedencia",
    icono: <Compass size={16} />,
    cuerpo: (
      <>
        <p>Mismo juego, el primero que aplica gana:</p>
        <ol className="list-decimal space-y-1.5 pl-5">
          <li>La que hayas <b>escrito a mano</b> en la ficha del producto.</li>
          <li>La <b>procedencia fija del rubro</b>, si el rubro tiene una.</li>
          <li>
            La <b>última compra</b>: si lo más reciente es una recepción importada queda
            Importado; si es un P/E nacional, queda Nacional.
          </li>
          <li>Lo que diga el <b>maestro</b> del ERP.</li>
          <li>Si nada de eso alcanza, queda en <b>SIN REVISION</b>.</li>
        </ol>
        <Nota>
          Un producto en SIN REVISION no tiene factor, y sin factor no hay precio. Por eso
          salen marcados en rojo: son los que hay que mirar antes de mandar la lista al ERP.
        </Nota>
      </>
    ),
  },
  {
    titulo: "Los números de arriba",
    icono: <Gauge size={16} />,
    cuerpo: (
      <>
        <ul className="list-disc space-y-1.5 pl-5">
          <li><b>Productos</b>: cuántos hay hoy en la lista.</li>
          <li>
            <b>Con cambios sin revisar</b>: diferencias que encontró el último recálculo y que
            nadie ha mirado todavía. Hazle clic y la lista se filtra a esos.
          </li>
          <li>
            <b>Pendientes de envío</b>: lo que cambió desde la última vez que se mandó al ERP.
          </li>
          <li>
            <b>Sin revisión</b>: los que no tienen precio calculable. También se puede hacer
            clic para verlos.
          </li>
          <li>
            <b>Último recálculo</b>: cuándo se recalculó por última vez y, abajo, cuándo fue el
            último envío.
          </li>
        </ul>
        <p>
          Si los números se ven viejos, aprieta <b>Recalcular</b>: vuelve a leer el stock y el
          costo del día y deja los contadores al día.
        </p>
      </>
    ),
  },
  {
    titulo: "Buscar y filtrar",
    icono: <Filter size={16} />,
    cuerpo: (
      <>
        <ul className="list-disc space-y-1.5 pl-5">
          <li>El buscador de arriba encuentra por <b>código o glosa</b>.</li>
          <li>Los filtros son por <b>rubro</b>, <b>tipo</b>, <b>procedencia</b> y <b>estado</b>.</li>
          <li><b>Con stock</b> deja solo lo que hay en bodega.</li>
          <li>
            <b>Creados aquí</b> muestra los productos que se agregaron desde la plataforma; el
            resto vino del ERP.
          </li>
        </ul>
        <p>
          Los filtros se combinan entre sí y con los números de arriba. Cuando hay alguno
          puesto aparece <b>Limpiar</b>, que deja la lista completa de nuevo.
        </p>
      </>
    ),
  },
  {
    titulo: "Elegir qué columnas ver",
    icono: <Columns3 size={16} />,
    cuerpo: (
      <>
        <p>
          El botón <b>Columnas</b>, arriba, abre la lista de todo lo que se puede mostrar. Hay
          bastante más de lo que se ve por defecto: el precio calculado, la desviación contra
          lo que tiene hoy el ERP, las fechas de las últimas compras, la observación, quién
          editó y cuándo.
        </p>
        <p>
          Tu elección se guarda <b>en este navegador</b>. Si entras desde otro computador
          vuelve a la de siempre, y <b>Restaurar por defecto</b> la deja como venía.
        </p>
      </>
    ),
  },
  {
    titulo: "La ficha de un producto",
    icono: <FileText size={16} />,
    cuerpo: (
      <>
        <p>
          Haz clic en cualquier fila. A la izquierda te muestra, de arriba abajo,{" "}
          <b>cómo se llegó a ese precio</b>:
        </p>
        <ul className="list-disc space-y-1 pl-5">
          <li>Rubro, tipo y de dónde salió el tipo.</li>
          <li>Procedencia y qué regla la decidió.</li>
          <li>Las fechas de las últimas compras, importada y nacional.</li>
          <li>El factor, el costo, el stock y lo que viene en tránsito.</li>
          <li>El precio calculado, el que tiene hoy el ERP y el precio final con su estado.</li>
        </ul>
        <p>
          Más abajo quedan los cambios que detectó el recálculo y el último envío al ERP con su
          fecha. Si un precio te extraña, la respuesta está acá: se lee de corrido.
        </p>
      </>
    ),
  },
  {
    titulo: "Decidir sobre un precio",
    icono: <Pencil size={16} />,
    cuerpo: (
      <>
        <p>En la misma ficha, al lado derecho:</p>
        <ul className="list-disc space-y-1.5 pl-5">
          <li><b>Precio fijo</b>: ese es el precio. Gana a todo, incluso si no hay stock.</li>
          <li><b>Congelar</b>: deja el precio que tiene hoy aunque después cambie el costo.</li>
          <li><b>Tipo o Procedencia a mano</b>: para cuando la regla se equivoca.</li>
          <li><b>No es un producto</b>: servicios, mano de obra y cargos, que quedan sin precio.</li>
          <li><b>Observación</b>: para dejar dicho por qué.</li>
        </ul>
        <p>
          <b>Volver a la regla</b> borra todo eso de una y el producto se vuelve a calcular solo.
        </p>
        <Nota>
          Lo que tú decides acá <b>no lo pisa nunca el recálculo</b>: se guarda aparte, a
          propósito. Puedes recalcular las veces que quieras sin perder ninguna decisión.
        </Nota>
      </>
    ),
  },
  {
    titulo: "Crear un producto",
    icono: <Plus size={16} />,
    cuerpo: (
      <>
        <p>
          El botón <b>Nuevo producto</b>, a la derecha de los filtros, sirve para lo que todavía
          no está en el ERP. El código se escribe como allá, con el rubro adelante
          (por ejemplo <span className="font-mono">71 2720142</span>).
        </p>
        <p>
          Puedes dejarle la glosa, el tipo, la procedencia, el costo, el stock y un precio fijo.
          Lo que no llenes lo resuelve la regla. Queda en la lista igual que los demás y sale en
          el próximo envío al ERP.
        </p>
      </>
    ),
  },
  {
    titulo: "Marcar los cambios revisados",
    icono: <Bell size={16} />,
    cuerpo: (
      <>
        <p>
          Cuando terminaste de mirar los cambios pendientes, aprieta <b>Marcar revisados</b> y el
          contador de arriba vuelve a cero.
        </p>
        <p>
          Si tienes un filtro puesto, marca <b>solo los que estás viendo</b> y el botón te lo
          avisa. Así puedes ir cerrando por rubro sin dar por revisado lo que no miraste.
        </p>
        <p>El botón aparece únicamente cuando hay algo pendiente.</p>
      </>
    ),
  },
  {
    titulo: "Exportar al ERP",
    icono: <Download size={16} />,
    cuerpo: (
      <>
        <ul className="list-disc space-y-1.5 pl-5">
          <li><b>Exportar completa</b>: baja toda la lista.</li>
          <li>
            <b>Solo diferencias</b>: baja únicamente lo que cambió desde el último envío. Es lo
            normal del día a día, y el número al lado te dice cuántos van.
          </li>
        </ul>
        <p>
          El archivo trae tres columnas: el <b>código</b>, el <b>precio</b> y el <b>costo</b>,
          las mismas que aceptaba el programa antiguo.
        </p>
        <Nota>
          Las dos exportaciones quedan registradas como envío. O sea que si bajas la lista
          completa, el contador de diferencias parte de cero desde ahí.
        </Nota>
      </>
    ),
  },
  {
    titulo: "La política",
    icono: <Sigma size={16} />,
    cuerpo: (
      <>
        <p>
          El botón <b>Política</b>, arriba, lleva a la pantalla donde están los factores por
          tipo y procedencia, con el margen que deja cada uno, y el tipo y la procedencia fija
          de cada rubro.
        </p>
        <p>
          Cambiar un factor o un rubro <b>recalcula la lista entera</b> al guardar, por eso solo
          lo puede tocar un administrador. Mirarla la puedes mirar cuando quieras: es el lugar
          donde se ve de dónde salió el factor que estás viendo en un producto.
        </p>
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
          tu nombre y la fecha, y <b>Volver a la regla</b> deshace cualquier decisión que hayas
          tomado sobre un producto.
        </p>
        <p>
          Lo único que sale de la plataforma es el archivo que exportas tú. Mientras no lo
          subas al ERP, nada de lo que hagas acá le cambia el precio a nadie.
        </p>
        <p>
          Si no ves los botones para editar, crear o recalcular, es que a tu usuario todavía no
          le habilitaron los precios. Se pide y listo.
        </p>
        <p className="text-ink-500">
          Este recorrido queda en el botón <b>Tutorial</b>, arriba. Ábrelo las veces que
          necesites.
        </p>
      </>
    ),
  },
];

/** Boton "Tutorial" de la barra superior de /precios y el recorrido que abre. */
export function TutorialPrecios() {
  const [abierto, setAbierto] = useState(false);
  const [paso, setPaso] = useState(0);

  useEffect(() => {
    // En el servidor no hay localStorage, por eso la primera apertura se decide
    // aca y no en el estado inicial.
    if (localStorage.getItem(LS_VISTO) !== "1") setAbierto(true);
  }, []);

  function cerrar() {
    localStorage.setItem(LS_VISTO, "1");
    setAbierto(false);
  }

  function abrir() {
    setPaso(0);
    setAbierto(true);
  }

  const actual = PASOS[paso];
  const esUltimo = paso === PASOS.length - 1;

  return (
    <>
      <Button variant="outline" size="sm" onClick={abrir}>
        <GraduationCap size={15} /> Tutorial
      </Button>

      <Dialog
        open={abierto}
        onClose={cerrar}
        title="Cómo funciona la lista de precios"
        description={`Un recorrido de ${PASOS.length} pasos por la pantalla. Ciérralo cuando quieras.`}
        className="max-w-2xl"
      >
        <div className="mb-4 flex items-center gap-1">
          {PASOS.map((p, i) => (
            <button
              key={p.titulo}
              onClick={() => setPaso(i)}
              aria-label={`Ir al paso ${i + 1}: ${p.titulo}`}
              aria-current={i === paso ? "step" : undefined}
              className={`h-1.5 flex-1 rounded-full transition-colors ${
                i === paso ? "bg-brand" : i < paso ? "bg-brand-200" : "bg-ink-200 hover:bg-ink-300"
              }`}
            />
          ))}
        </div>

        <div className="min-h-[280px]">
          <h3 className="mb-2 flex items-center gap-2 font-display text-[15px] font-medium text-ink-900">
            <span className="text-brand">{actual.icono}</span>
            {actual.titulo}
          </h3>
          <div className="space-y-2.5 text-[13.5px] leading-relaxed text-ink-600">
            {actual.cuerpo}
          </div>
        </div>

        <div className="mt-5 flex items-center justify-between gap-3 border-t border-ink-100 pt-3">
          <span className="text-[12px] text-ink-500">
            Paso {paso + 1} de {PASOS.length}
          </span>
          <div className="flex gap-2">
            <Button
              variant="outline"
              size="sm"
              disabled={paso === 0}
              onClick={() => setPaso(paso - 1)}
            >
              <ChevronLeft size={15} /> Anterior
            </Button>
            {esUltimo ? (
              <Button size="sm" onClick={cerrar}>Listo</Button>
            ) : (
              <Button size="sm" onClick={() => setPaso(paso + 1)}>
                Siguiente <ChevronRight size={15} />
              </Button>
            )}
          </div>
        </div>
      </Dialog>
    </>
  );
}
