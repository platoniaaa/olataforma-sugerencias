"use client";

// Guia para quien queda a cargo del motor: que mirar cada dia en Fuentes de
// datos, como dejar el PC listo una vez y el paso mensual de ventas. Sin jerga:
// la lee alguien que no programa. Solo admin, como el panel.
//
// Lo que dice esta corroborado en el motor (rama arreglar-job-diario):
// - la tarea corre a las 09:30 de cada dia habil y dura cerca de media hora;
// - los respaldos de venta se eligen por descarte: todo .xlsx de la carpeta con
//   el año en curso o el anterior en el nombre (`_archivos_de_ventas`), asi que
//   dos copias del mismo año se leen las dos;
// - sin el mes cerrado avisa hasta el dia 3 y frena desde el 4
//   (`revisar_ventas_mes_cerrado`, DIA_DESDE_QUE_FRENA_VENTAS).
import { useEffect } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ArrowLeft, BookOpen } from "lucide-react";
import { getEsAdmin } from "@/lib/auth";
import { NivelBadge } from "@/components/fuentes/comun";

const CASOS: { etiqueta: string; nivel: "rojo" | "amarillo"; hacer: string }[] = [
  {
    etiqueta: "El PC titular no corrió hoy",
    nivel: "rojo",
    hacer: "Revisa que el PC del motor esté prendido, con la sesión abierta y con internet. La tarea corre a las 09:30.",
  },
  {
    etiqueta: "Vencido",
    nivel: "rojo",
    hacer: "El archivo no se actualizó a tiempo. Revisa que el programa del ERP haya corrido hoy y que OneDrive esté sincronizado.",
  },
  {
    etiqueta: "Falta",
    nivel: "rojo",
    hacer: "No hay ningún archivo con el nombre que se espera. Revisa que esté en su carpeta, con el nombre de siempre.",
  },
  {
    etiqueta: "Carpeta no encontrada",
    nivel: "rojo",
    hacer: "Ese PC no tiene la carpeta. Agrégala en OneDrive y déjala en «Mantener siempre en este dispositivo» (ver más abajo).",
  },
  {
    etiqueta: "Llegó vacío o incompleto",
    nivel: "rojo",
    hacer: "El archivo llegó con muchas menos filas que ayer. Vuelve a correr el programa del ERP.",
  },
  {
    etiqueta: "Ventas sin el mes cerrado",
    nivel: "rojo",
    hacer: "Falta el paso mensual de ventas (más abajo).",
  },
  {
    etiqueta: "Abierto en Excel",
    nivel: "amarillo",
    hacer: "Cierra ese archivo en el PC del motor: abierto, el programa del ERP no lo puede actualizar.",
  },
  {
    etiqueta: "Bajando de OneDrive",
    nivel: "amarillo",
    hacer: "OneDrive no terminó de bajar el archivo. Espera a que sincronice y revisa al día siguiente.",
  },
  {
    etiqueta: "Archivo nuevo en la carpeta",
    nivel: "amarillo",
    hacer: "Alguien dejó un archivo nuevo. Abre la fuente para ver cuál es; si no es de ninguna fuente, no pasa nada.",
  },
];

export default function GuiaFuentesPage() {
  const router = useRouter();
  useEffect(() => {
    if (!getEsAdmin()) router.replace("/");
  }, [router]);

  return (
    <div className="mx-auto max-w-3xl space-y-6 p-6 text-[14px] leading-relaxed text-ink-700">
      <header className="space-y-1">
        <p className="text-[11px] font-semibold uppercase tracking-wide text-ink-400">
          <Link href="/cargar/fuentes" className="inline-flex items-center gap-1 hover:text-brand">
            <ArrowLeft className="h-3 w-3" aria-hidden="true" /> Fuentes de datos
          </Link>
        </p>
        <h1 className="flex items-center gap-2 text-2xl font-semibold text-ink-900">
          <BookOpen className="h-5 w-5 text-brand" aria-hidden="true" /> Guía para el día a día
        </h1>
        <p className="text-ink-500">
          Para quien queda a cargo del motor del sugerido. Cada mañana el motor lee los Excel de unas carpetas
          sincronizadas con OneDrive, calcula el sugerido y lo publica. Esta guía dice qué mirar y qué hacer cuando algo
          no está bien.
        </p>
      </header>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-ink-900">Cada día hábil, pasadas las 10:00</h2>
        <p>La corrida empieza a las 09:30 y dura cerca de media hora.</p>
        <ol className="list-decimal space-y-1 pl-5">
          <li>
            Abre <b>Cargar datos › Fuentes de datos</b>.
          </li>
          <li>
            Mira la franja de arriba. Si dice <b>Última corrida: Publicó</b> y no hay nada en rojo, está todo bien.
          </li>
          <li>Si algo está en rojo o en amarillo, lee su texto: siempre dice qué hacer. Abajo están los casos más comunes.</li>
        </ol>
        <ul className="space-y-1 pt-1">
          <li><NivelBadge nivel="rojo" etiqueta="Rojo" /> El sugerido no se publicó, o no se va a publicar si sigue así. Hay que hacer algo hoy.</li>
          <li><NivelBadge nivel="amarillo" etiqueta="Amarillo" /> Se publica igual, pero conviene revisarlo.</li>
          <li><NivelBadge nivel="verde" etiqueta="Verde" /> Al día.</li>
          <li><NivelBadge nivel="gris" etiqueta="Gris" /> Todavía no hay datos, o la fuente está desactivada.</li>
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-ink-900">Los casos más comunes</h2>
        <ul className="divide-y divide-ink-100 rounded-sm border border-ink-200 bg-white">
          {CASOS.map((c) => (
            <li key={c.etiqueta} className="flex flex-col gap-1 px-3 py-2 sm:flex-row sm:items-start sm:gap-3">
              <NivelBadge nivel={c.nivel} etiqueta={c.etiqueta} className="shrink-0 self-start" />
              <span>{c.hacer}</span>
            </li>
          ))}
        </ul>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-ink-900">Dejar el PC listo (una vez)</h2>
        <ol className="list-decimal space-y-2 pl-5">
          <li>OneDrive abierto y con la cuenta de la empresa.</li>
          <li>
            En el Explorador de archivos, entra a <b>OneDrive › Documentos › Desarrollos</b>, haz clic derecho sobre la
            carpeta <b>Bases de datos</b> y elige <b>Mantener siempre en este dispositivo</b>. Así los archivos quedan en el
            PC y no solo en la nube.
          </li>
          <li>
            Si una fuente lee de una biblioteca de SharePoint (por ejemplo <b>Data BI › Datos</b>): ábrela en el
            navegador, elige <b>Agregar acceso directo a Mis archivos</b> y después, en el Explorador, haz clic derecho
            sobre ese acceso directo y elige <b>Mantener siempre en este dispositivo</b>.
          </li>
          <li>El PC tiene que estar prendido y con la sesión abierta a las 09:30.</li>
          <li>No dejes abiertos en Excel los archivos de esas carpetas: abiertos, el programa del ERP no los puede actualizar.</li>
        </ol>
        <p className="text-ink-500">
          En el panel, la sección <b>Carpetas por PC</b> muestra si cada PC encontró sus carpetas y cuántos archivos tienen.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-ink-900">Cada mes: el respaldo de ventas</h2>
        <ol className="list-decimal space-y-2 pl-5">
          <li>
            Apenas cierre el mes, baja el respaldo de ventas del año desde la biblioteca <b>Respaldos BBDD</b> de
            SharePoint.
          </li>
          <li>
            Déjalo en <b>Bases de datos › Ventas</b>, reemplazando el del mismo año. El nombre tiene que llevar el año,
            como lo baja Respaldos BBDD (por ejemplo, <i>2026 (6).xlsx</i>).
          </li>
          <li>
            Deja un solo respaldo por año en esa carpeta: el motor lee todos los que tengan el año en el nombre, y dos
            copias del mismo año se leerían las dos.
          </li>
        </ol>
        <p>
          Si el respaldo no trae el mes que acaba de cerrar, el panel lo marca como <b>Ventas sin el mes cerrado</b>. Hasta
          el día 3 el sugerido se publica igual, con ese mes en cero; desde el día 4 no se publica hasta que el respaldo
          esté al día.
        </p>
      </section>

      <section className="space-y-2">
        <h2 className="text-lg font-semibold text-ink-900">Si cambia el PC del motor</h2>
        <p>
          El motor solo publica desde el <b>PC titular</b>. Cuando el motor ya esté instalado en el PC nuevo y su revisión
          diaria salga en verde, en <b>Carpetas por PC</b> aprieta <b>Hacer titular</b> en ese PC, y ese mismo día
          deshabilita la tarea diaria en el PC anterior.
        </p>
      </section>
    </div>
  );
}
