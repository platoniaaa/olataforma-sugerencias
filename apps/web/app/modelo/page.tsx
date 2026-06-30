"use client";

import type { ReactNode } from "react";
import {
  Boxes,
  CalendarDays,
  Info,
  Lightbulb,
  Minus,
  Plus,
  Truck,
} from "lucide-react";

/* Documentación del modelo de sugerido, en lenguaje de negocio (audiencia:
   Abastecimiento, no técnica). Refleja la lógica REAL del modelo de Power BI,
   extraída de la tabla 'Sugerido por Sucursal' y sus medidas. Si el modelo
   cambia, actualizar también acá. */

type Seccion = { id: string; titulo: string };

const SECCIONES: Seccion[] = [
  { id: "que-hace", titulo: "Para qué sirve" },
  { id: "clasificacion", titulo: "Cómo se clasifican los productos" },
  { id: "quien-compra", titulo: "Quién compra cada producto" },
  { id: "como-decide", titulo: "Cómo se calcula cuánto pedir" },
  { id: "colchon", titulo: "El colchón de seguridad" },
  { id: "ventas", titulo: "Qué ventas se consideran" },
  { id: "sucursales", titulo: "Sucursales y prioridad del CD" },
];

export default function ModeloPage() {
  return (
    <div className="space-y-8">
      {/* Encabezado */}
      <header className="border-b border-ink-200 pb-5">
        <p className="kicker mb-2 flex items-center gap-1.5">
          <Lightbulb size={13} className="text-accent-500" /> Cómo funciona
        </p>
        <h1 className="font-display text-3xl font-medium tracking-tight text-ink-900">
          Cómo se calcula el sugerido
        </h1>
        <p className="mt-2 max-w-3xl text-[14.5px] leading-relaxed text-ink-600">
          Esta página explica, en simple, de dónde sale cada número que ves en la
          plataforma: cómo se clasifican los productos, quién los compra (la
          sucursal o el Centro de Distribución) y cómo se decide la cantidad a
          pedir. Es la base para revisar y validar el sugerido con confianza.
        </p>
      </header>

      <div className="lg:grid lg:grid-cols-[230px_1fr] lg:gap-10">
        {/* Tabla de contenidos */}
        <nav className="mb-8 lg:mb-0">
          <div className="lg:sticky lg:top-24">
            <p className="kicker mb-3">En esta página</p>
            <ul className="space-y-1.5 border-l border-ink-200">
              {SECCIONES.map((s) => (
                <li key={s.id}>
                  <a
                    href={`#${s.id}`}
                    className="-ml-px block border-l-2 border-transparent py-0.5 pl-3 text-[13px] text-ink-600 transition-colors hover:border-accent-500 hover:text-ink-900"
                  >
                    {s.titulo}
                  </a>
                </li>
              ))}
            </ul>
          </div>
        </nav>

        {/* Contenido */}
        <div className="min-w-0 space-y-12">
          {/* 1. Para qué sirve */}
          <Section id="que-hace" titulo="Para qué sirve">
            <P>
              La herramienta calcula, para cada repuesto y cada sucursal,{" "}
              <strong>cuánto conviene pedir</strong>. El objetivo es simple: que no
              falte stock para vender, sin comprar de más y dejar plata detenida en
              la bodega.
            </P>
            <P>
              Para eso mira las ventas de cada producto, cada cuánto se vende, cuánto
              demora el proveedor en entregar, cuánto stock hay hoy y cuánto ya viene
              en camino. Con eso propone una cantidad, que el equipo de compras
              revisa antes de generar la orden.
            </P>
          </Section>

          {/* 2. Clasificación */}
          <Section id="clasificacion" titulo="Cómo se clasifican los productos">
            <P>
              Lo primero que hace el modelo es ponerle una nota a cada producto según{" "}
              <strong>qué tan seguido se vende</strong>: en cuántos de los últimos
              meses tuvo venta. Esa nota (A, B, C o D) define cómo se trata después.
            </P>
            <div className="space-y-2.5">
              <ClaseRow
                clase="A"
                tono="a"
                titulo="Se vende casi todos los meses"
                regla="Tuvo venta en 5 o 6 de los últimos 6 meses"
                desc="Los más constantes y críticos. Quebrarse en uno de estos es lo que más duele."
              />
              <ClaseRow
                clase="B"
                tono="b"
                titulo="Se vende seguido"
                regla="Tuvo venta en 4 de los últimos 6 meses"
                desc="Rotación buena pero algo menos pareja que la clase A."
              />
              <ClaseRow
                clase="C"
                tono="c"
                titulo="Se vende de a poco"
                regla="Venta en 3 de los últimos 6 meses, con presencia reciente (o respaldo de los últimos 12)"
                desc="Rotación baja pero real. Se le hace seguimiento más holgado."
              />
              <ClaseRow
                clase="D"
                tono="d"
                titulo="Venta esporádica o nula"
                regla="El resto: casi no registra venta reciente"
                desc="Por sí solo no se repone en la sucursal. Puede entrar igual si a nivel global vende bien (ver abajo)."
              />
            </div>
            <Callout tono="info">
              <strong>Dos miradas de la misma nota.</strong> Cada producto tiene su
              clase <strong>en la sucursal</strong> (cómo se vende ahí) y su clase{" "}
              <strong>global</strong> (cómo se vende sumando todas las sucursales). La
              diferencia entre las dos es la que decide si conviene que el CD lo
              consolide. La clasificación se basa en la frecuencia de venta, no en el
              monto facturado.
            </Callout>
          </Section>

          {/* 3. Quién compra */}
          <Section id="quien-compra" titulo="Quién compra cada producto">
            <P>
              Según la clase del producto (en la sucursal y a nivel global) y si es
              importado, el modelo decide quién lo compra:
            </P>

            <div className="max-w-3xl overflow-hidden rounded-sm border border-ink-200 bg-white">
              <table className="w-full text-[13.5px]">
                <thead>
                  <tr className="border-b border-ink-200 bg-ink-50 text-left">
                    <th className="px-4 py-2.5 font-semibold text-ink-700">Situación</th>
                    <th className="px-4 py-2.5 font-semibold text-ink-700">
                      Quién lo abastece
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  <FilaAbast
                    tipo="Clase A, B o C en la sucursal (y no importado)"
                    modo="directo"
                    como="La sucursal le compra directo al proveedor."
                  />
                  <FilaAbast
                    tipo="Importado"
                    modo="cd"
                    como="Siempre se abastece desde el CD."
                  />
                  <FilaAbast
                    tipo="Clase D en la sucursal, pero A/B/C a nivel global"
                    modo="cd"
                    como="El CD lo consolida y lo reparte por traslado: en vez de que cada sucursal chica lo pida suelto, lo centraliza."
                  />
                  <FilaAbast
                    tipo="Clase D en la sucursal y también a nivel global"
                    modo="ninguno"
                    como="No se pide (venta demasiado esporádica). Excepción: importados con stock en el CD."
                  />
                </tbody>
              </table>
            </div>

            <Callout tono="info">
              El <strong>Centro de Distribución (CD)</strong> compra un producto cuando,
              mirándolo a nivel global, es clase A, B o C. Después lo reparte a las
              sucursales que lo necesitan por orden de prioridad (ver más abajo).
            </Callout>

            <P>El sugerido se muestra en tres listas separadas, según el caso:</P>
            <div className="space-y-3">
              <VistaCard
                n="1"
                icon={Boxes}
                titulo="Compra directa de sucursal"
                desc="Lo que cada sucursal le pide directamente a su proveedor."
              />
              <VistaCard
                n="2"
                icon={Boxes}
                titulo="Compra del Centro de Distribución"
                desc="Lo que compra el CD para abastecer a varias sucursales (importados y productos que conviene consolidar)."
              />
              <VistaCard
                n="3"
                icon={Truck}
                titulo="Traslados desde el CD"
                desc="Lo que el CD envía a cada sucursal desde su propio stock, sin volver a comprarlo."
              />
            </div>
          </Section>

          {/* 4. Cómo se calcula cuánto pedir */}
          <Section id="como-decide" titulo="Cómo se calcula cuánto pedir">
            <P>
              Una vez que se sabe quién compra, la cantidad sale de sumar y restar
              cuatro cosas, producto por producto y sucursal por sucursal:
            </P>
            <div className="max-w-2xl space-y-2.5 rounded-sm border border-ink-200 bg-white p-5">
              <Ingrediente
                signo="mas"
                titulo="Lo que se espera vender hasta el próximo pedido"
                desc="El ritmo de venta del producto, multiplicado por el tiempo que tarda en llegar (entrega del proveedor) más el ciclo de pedido."
              />
              <Ingrediente
                signo="mas"
                titulo="Un colchón de seguridad"
                desc="Stock extra para no quebrar si la venta sube o el proveedor se atrasa. Depende de la clase (ver abajo)."
              />
              <Ingrediente
                signo="menos"
                titulo="Lo que ya hay en la sucursal"
                desc="El stock disponible hoy no hay que volver a pedirlo."
              />
              <Ingrediente
                signo="menos"
                titulo="Lo que ya viene en camino"
                desc="Las órdenes de compra pendientes de llegar también se descuentan."
              />
              <div className="mt-1 border-t border-ink-100 pt-3 text-[13px] text-ink-600">
                Si el resultado da <strong>mayor que cero</strong>, ese es el sugerido
                a pedir. Si da cero o negativo, ya hay suficiente y{" "}
                <strong>no se pide</strong>.
              </div>
            </div>
            <div className="grid max-w-3xl gap-3 sm:grid-cols-2">
              <DatoCard icon={CalendarDays} titulo="Ciclo de pedido">
                <strong>5 días</strong> si la sucursal compra directo;{" "}
                <strong>3 días</strong> si el producto se abastece desde el CD (se
                pide más seguido).
              </DatoCard>
              <DatoCard icon={Truck} titulo="Tiempo de entrega">
                El tiempo <strong>real</strong> de cada proveedor (calculado con su
                historial). Para traslados internos del CD a la sucursal: 1 a 2 días.
              </DatoCard>
            </div>
            <P className="text-[13px] text-ink-600">
              El ritmo de venta se promedia sobre los <strong>últimos 6 meses</strong>{" "}
              para los productos de mayor rotación (A y B), y sobre los{" "}
              <strong>últimos 12 meses</strong> para los de baja rotación (C y D), para
              suavizar los altibajos.
            </P>
          </Section>

          {/* 5. Colchón de seguridad */}
          <Section id="colchon" titulo="El colchón de seguridad">
            <P>
              El colchón (o stock de seguridad) es el extra que se pide para no
              quebrar ante imprevistos. Mientras más importante el producto, más alto
              el nivel de servicio al que apunta el modelo:
            </P>
            <div className="max-w-2xl overflow-hidden rounded-sm border border-ink-200 bg-white">
              <table className="w-full text-[13.5px]">
                <thead>
                  <tr className="border-b border-ink-200 bg-ink-50 text-left">
                    <th className="px-4 py-2.5 font-semibold text-ink-700">Clase</th>
                    <th className="px-4 py-2.5 font-semibold text-ink-700">
                      Apunta a no quebrar en…
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  <FilaServicio clase="A" nivel="~95% de los casos" />
                  <FilaServicio clase="B" nivel="~90% de los casos" />
                  <FilaServicio clase="C" nivel="~80% de los casos" />
                  <FilaServicio clase="D" nivel="Sin colchón (solo lo justo)" apagado />
                </tbody>
              </table>
            </div>
            <P className="text-[13px] text-ink-600">
              El tamaño del colchón también crece cuando el producto vende de forma
              más irregular (más altibajos mes a mes) o cuando el proveedor tarda más
              en entregar. Los importados gestionados por el CD usan un colchón algo
              más bajo, porque se piden con más anticipación.
            </P>
          </Section>

          {/* 6. Qué ventas se consideran */}
          <Section id="ventas" titulo="Qué ventas se consideran">
            <P>
              Para que la demanda refleje lo que de verdad se vende, el modelo limpia
              las ventas antes de calcular:
            </P>
            <ul className="max-w-3xl space-y-2 text-[14px] text-ink-700">
              <Bullet>
                <strong>No cuenta las notas de crédito</strong> (devoluciones): se
                descuentan para no inflar la venta.
              </Bullet>
              <Bullet>
                <strong>Solo meses cerrados.</strong> El mes en curso no se usa,
                porque está incompleto y distorsionaría el promedio.
              </Bullet>
              <Bullet>
                <strong>Deja fuera lo que no es repuesto comprable</strong> — insumos
                de taller, incentivos y ajustes (6 conceptos), más las categorías{" "}
                <strong>Colisión</strong> y <strong>Campañas</strong>.
              </Bullet>
              <Bullet>
                <strong>Los productos que se reemplazan entre sí se suman juntos.</strong>{" "}
                Cuando un repuesto sustituye a otro, su venta y su stock se miran como
                un solo grupo, para no pedir de más.
              </Bullet>
            </ul>
          </Section>

          {/* 7. Sucursales y prioridad */}
          <Section id="sucursales" titulo="Sucursales y prioridad del CD">
            <SubTitulo icon={Info}>Sucursales que no entran al cálculo</SubTitulo>
            <P className="!mt-1">
              9 sucursales quedan fuera del sugerido: La Florida, Lira, Lo Blanco, las
              3 de Mall Plaza (Norte, Sur y Vespucio), Ovalle (3), Gran Avenida y
              Coquimbo.
            </P>
            <P className="text-[13px] text-ink-600">
              Además, Oficinas Centrales, Canal Digital y Linderos Vta Móvil se
              manejan <strong>dentro del CD</strong>, y Rancagua 2 se suma a Rancagua.
            </P>

            <SubTitulo icon={Truck}>Cuándo el CD sale a comprar</SubTitulo>
            <P className="!mt-1">
              Cuando varias sucursales necesitan el mismo producto desde el CD, su
              stock se reparte por <strong>orden de prioridad de sucursal</strong>. El
              CD sale a comprar solo cuando la necesidad acumulada de las sucursales
              con prioridad supera el stock que ya tiene; si no alcanza para todas,
              primero se cubre a las de mayor prioridad.
            </P>
            <div className="max-w-2xl rounded-sm border border-ink-200 bg-white p-4">
              <p className="kicker mb-2.5">Orden de prioridad</p>
              <div className="flex flex-wrap gap-1.5 text-[12.5px]">
                {[
                  "Diez de Julio (2)",
                  "Brasil 18",
                  "Linderos",
                  "Placilla",
                  "Rancagua",
                  "Rancagua 2",
                  "Curicó",
                  "Talca",
                  "Talca (2)",
                  "Chillán",
                  "Chillán Viejo",
                ].map((s, i) => (
                  <span
                    key={s}
                    className="inline-flex items-center gap-1.5 rounded-sm border border-ink-200 bg-paper-50 px-2 py-1"
                  >
                    <span className="font-mono font-semibold text-accent-600">
                      {i + 1}
                    </span>
                    <span className="text-ink-700">{s}</span>
                  </span>
                ))}
              </div>
              <p className="mt-2.5 text-[12px] text-ink-500">
                El resto de las sucursales queda en prioridad más baja.
              </p>
            </div>
          </Section>
        </div>
      </div>
    </div>
  );
}

/* ---------- Componentes de presentación ---------- */

function Section({
  id,
  titulo,
  children,
}: {
  id: string;
  titulo: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <h2 className="font-display text-2xl font-medium tracking-tight text-ink-900 editorial-rule">
        {titulo}
      </h2>
      {children}
    </section>
  );
}

function SubTitulo({
  children,
  icon: Icon,
}: {
  children: ReactNode;
  icon: typeof Boxes;
}) {
  return (
    <h3 className="flex items-center gap-2 pt-2 text-[15px] font-semibold text-ink-900">
      <Icon size={16} className="text-accent-500" />
      {children}
    </h3>
  );
}

function P({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p className={`max-w-3xl text-[14.5px] leading-relaxed text-ink-700 ${className}`}>
      {children}
    </p>
  );
}

function Ingrediente({
  signo,
  titulo,
  desc,
}: {
  signo: "mas" | "menos";
  titulo: string;
  desc: string;
}) {
  const esMas = signo === "mas";
  return (
    <div className="flex gap-3">
      <span
        className={`mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-sm ${
          esMas ? "bg-emerald-50 text-emerald-700" : "bg-accent-50 text-accent-700"
        }`}
      >
        {esMas ? <Plus size={15} /> : <Minus size={15} />}
      </span>
      <div>
        <p className="text-[14px] font-semibold text-ink-900">{titulo}</p>
        <p className="text-[13px] leading-relaxed text-ink-600">{desc}</p>
      </div>
    </div>
  );
}

function Callout({
  children,
  tono = "info",
}: {
  children: ReactNode;
  tono?: "info" | "warn";
}) {
  const estilos =
    tono === "warn"
      ? "border-accent-100 bg-accent-50/60"
      : "border-brand-200 bg-brand-50/60";
  const colorIcono = tono === "warn" ? "text-accent-600" : "text-brand";
  return (
    <div
      className={`flex max-w-3xl gap-2.5 rounded-sm border px-4 py-3 text-[13.5px] leading-relaxed text-ink-700 ${estilos}`}
    >
      <Info size={16} className={`mt-0.5 shrink-0 ${colorIcono}`} />
      <div>{children}</div>
    </div>
  );
}

function DatoCard({
  icon: Icon,
  titulo,
  children,
}: {
  icon: typeof Boxes;
  titulo: string;
  children: ReactNode;
}) {
  return (
    <div className="rounded-sm border border-ink-200 bg-white p-3.5">
      <p className="flex items-center gap-1.5 text-[13px] font-semibold text-ink-900">
        <Icon size={15} className="text-brand" />
        {titulo}
      </p>
      <p className="mt-1 text-[12.5px] leading-relaxed text-ink-600">{children}</p>
    </div>
  );
}

function ClaseRow({
  clase,
  tono,
  titulo,
  regla,
  desc,
}: {
  clase: string;
  tono: "a" | "b" | "c" | "d";
  titulo: string;
  regla: string;
  desc: string;
}) {
  const cls =
    tono === "a"
      ? "bg-accent-500 text-white"
      : tono === "b"
        ? "bg-brand text-white"
        : tono === "c"
          ? "bg-brand-200 text-brand-900"
          : "bg-ink-200 text-ink-600";
  return (
    <div className="flex items-start gap-3 rounded-sm border border-ink-200 bg-white p-3.5">
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-sm font-display text-lg font-semibold ${cls}`}
      >
        {clase}
      </span>
      <div className="min-w-0">
        <p className="text-[14px] font-semibold text-ink-900">{titulo}</p>
        <p className="mt-0.5 text-[12px] font-medium uppercase tracking-wide text-accent-600">
          {regla}
        </p>
        <p className="mt-1 text-[13px] leading-relaxed text-ink-600">{desc}</p>
      </div>
    </div>
  );
}

function FilaAbast({
  tipo,
  modo,
  como,
}: {
  tipo: string;
  modo: "directo" | "cd" | "ninguno";
  como: string;
}) {
  const etiqueta =
    modo === "directo"
      ? { txt: "Compra directa", cls: "bg-brand-50 text-brand" }
      : modo === "cd"
        ? { txt: "Vía CD", cls: "bg-accent-50 text-accent-700" }
        : { txt: "No se pide", cls: "bg-ink-100 text-ink-500" };
  return (
    <tr className="align-top">
      <td className="px-4 py-3">
        <span className="font-semibold text-ink-900">{tipo}</span>
        <span
          className={`ml-2 inline-block whitespace-nowrap rounded-sm px-1.5 py-0.5 text-[10.5px] font-semibold ${etiqueta.cls}`}
        >
          {etiqueta.txt}
        </span>
      </td>
      <td className="px-4 py-3 text-ink-600">{como}</td>
    </tr>
  );
}

function FilaServicio({
  clase,
  nivel,
  apagado = false,
}: {
  clase: string;
  nivel: string;
  apagado?: boolean;
}) {
  return (
    <tr>
      <td className="px-4 py-2.5">
        <span
          className={`inline-flex h-6 w-6 items-center justify-center rounded-sm font-display text-sm font-semibold ${
            apagado ? "bg-ink-200 text-ink-600" : "bg-brand text-white"
          }`}
        >
          {clase}
        </span>
      </td>
      <td className={`px-4 py-2.5 ${apagado ? "text-ink-500" : "text-ink-800"}`}>
        {nivel}
      </td>
    </tr>
  );
}

function VistaCard({
  n,
  icon: Icon,
  titulo,
  desc,
}: {
  n: string;
  icon: typeof Boxes;
  titulo: string;
  desc: string;
}) {
  return (
    <div className="flex items-center gap-4 rounded-sm border border-ink-200 bg-white p-4">
      <span className="figure shrink-0 text-2xl text-accent-500">{`0${n}.`}</span>
      <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-sm bg-ink-50 text-brand">
        <Icon size={18} />
      </div>
      <div className="min-w-0">
        <p className="text-[14.5px] font-semibold text-ink-900">{titulo}</p>
        <p className="mt-0.5 text-[13px] leading-relaxed text-ink-600">{desc}</p>
      </div>
    </div>
  );
}

function Bullet({ children }: { children: ReactNode }) {
  return (
    <li className="flex gap-2.5">
      <span className="mt-2 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-500" />
      <span className="leading-relaxed">{children}</span>
    </li>
  );
}
