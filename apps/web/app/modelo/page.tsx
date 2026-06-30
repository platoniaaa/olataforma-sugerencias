"use client";

import type { ReactNode } from "react";
import {
  Boxes,
  Building2,
  Info,
  Lightbulb,
  Minus,
  Plus,
  Truck,
} from "lucide-react";

/* Documentación del modelo de sugerido, en lenguaje de negocio (audiencia:
   Abastecimiento, no técnica). Refleja las reglas vigentes del modelo de Power BI.
   Fuente de verdad: "CLAUDE contexto modelo.md" en la raíz del repo. Si el modelo
   cambia, actualizar también acá. */

type Seccion = { id: string; titulo: string };

const SECCIONES: Seccion[] = [
  { id: "que-hace", titulo: "Para qué sirve" },
  { id: "como-decide", titulo: "Cómo decide cuánto pedir" },
  { id: "clasificacion", titulo: "Cómo se clasifican los productos" },
  { id: "abastecimiento", titulo: "Cómo se abastece cada tipo" },
  { id: "vistas", titulo: "Las 3 formas de comprar" },
  { id: "ventas", titulo: "Qué ventas se consideran" },
  { id: "reglas", titulo: "Reglas que respeta" },
  { id: "cd", titulo: "Cuándo el CD compra por las sucursales" },
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
          plataforma: qué considera la herramienta para decidir cuánto pedir, cómo
          clasifica los productos y cómo se abastece cada tipo. Es la base para
          revisar y validar el sugerido con confianza.
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
              Para eso mira las ventas de cada producto, cuánto se demora el
              proveedor en entregar, cuánto stock hay hoy y cuánto ya viene en
              camino. Con eso propone una cantidad a pedir, que el equipo de compras
              revisa antes de generar la orden.
            </P>
          </Section>

          {/* 2. Cómo decide cuánto pedir */}
          <Section id="como-decide" titulo="Cómo decide cuánto pedir">
            <P>
              La cantidad sugerida sale de sumar y restar cuatro cosas, producto por
              producto y sucursal por sucursal:
            </P>
            <div className="max-w-2xl space-y-2.5 rounded-sm border border-ink-200 bg-white p-5">
              <Ingrediente
                signo="mas"
                titulo="Lo que se espera vender hasta el próximo pedido"
                desc="Según el ritmo de venta del producto y el tiempo que tarda el proveedor en entregar."
              />
              <Ingrediente
                signo="mas"
                titulo="Un colchón de seguridad"
                desc="Stock extra para cubrir imprevistos y que no se quiebre si la venta sube o el proveedor se atrasa."
              />
              <Ingrediente
                signo="menos"
                titulo="Lo que ya hay en la sucursal"
                desc="El stock disponible hoy se descuenta: eso no hay que pedirlo de nuevo."
              />
              <Ingrediente
                signo="menos"
                titulo="Lo que ya viene en camino"
                desc="Las órdenes de compra pendientes de llegar también se descuentan."
              />
              <div className="mt-1 border-t border-ink-100 pt-3 text-[13px] text-ink-600">
                Si el resultado da <strong>mayor que cero</strong>, ese es el sugerido
                a pedir. Si da cero o negativo, significa que ya hay suficiente y{" "}
                <strong>no se pide</strong>.
              </div>
            </div>
            <Callout tono="info">
              El colchón de seguridad y el ritmo de venta se calculan con un nivel de
              servicio objetivo (el modelo apunta a cubrir la gran mayoría de la
              demanda, no el 100% teórico, para no sobre-stockear).
            </Callout>
          </Section>

          {/* 3. Clasificación de productos */}
          <Section id="clasificacion" titulo="Cómo se clasifican los productos">
            <P>
              Antes de calcular, el modelo separa los productos en dos dimensiones.
              Esto define cómo se trata cada uno.
            </P>

            <SubTitulo icon={Boxes}>Según su origen</SubTitulo>
            <div className="grid gap-3 sm:grid-cols-3">
              <TipoCard titulo="Nacional" color="brand">
                Se compra a proveedores en Chile. Es el grueso del catálogo.
              </TipoCard>
              <TipoCard titulo="Importado" color="accent">
                Viene del extranjero. Siempre pasa por el Centro de Distribución (CD).
              </TipoCard>
              <TipoCard titulo="No Representado" color="ink">
                Productos de marcas que no reponemos normalmente. No se piden, salvo
                que sean importados con stock en el CD.
              </TipoCard>
            </div>

            <SubTitulo icon={Boxes}>Según su rotación (clasificación A, B, C)</SubTitulo>
            <P className="!mt-1">
              Es una nota que ordena los productos por su importancia de venta. Las
              tres clases calculan sugerido; la diferencia está en cómo se mira su
              demanda y cómo se abastecen.
            </P>
            <div className="space-y-2.5">
              <ClaseRow
                clase="A"
                tono="a"
                titulo="Los más importantes"
                desc="Mayor rotación y peso en la venta. Son los críticos: quebrarse en uno de estos duele."
              />
              <ClaseRow
                clase="B"
                tono="b"
                titulo="Rotación media"
                desc="Venden de forma constante pero sin ser los protagonistas."
              />
              <ClaseRow
                clase="C"
                tono="c"
                titulo="Baja rotación"
                desc="Venden de a poco. Por eso su demanda se mira con una ventana de 6 meses, no de un período corto, para no subestimar lo que realmente se vende."
              />
            </div>
          </Section>

          {/* 4. Cómo se abastece cada tipo */}
          <Section id="abastecimiento" titulo="Cómo se abastece cada tipo">
            <P>
              No todos los productos se compran igual. Según su origen y su clase, o
              bien la sucursal compra directo al proveedor, o el producto se trae
              desde el Centro de Distribución (CD).
            </P>

            <div className="max-w-3xl overflow-hidden rounded-sm border border-ink-200 bg-white">
              <table className="w-full text-[13.5px]">
                <thead>
                  <tr className="border-b border-ink-200 bg-ink-50 text-left">
                    <th className="px-4 py-2.5 font-semibold text-ink-700">
                      Tipo de producto
                    </th>
                    <th className="px-4 py-2.5 font-semibold text-ink-700">
                      Cómo se abastece
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-ink-100">
                  <FilaAbast
                    tipo="Nacional, clase A o B"
                    modo="directo"
                    como="La sucursal lo compra directo al proveedor."
                  />
                  <FilaAbast
                    tipo="Nacional, clase C"
                    modo="cd"
                    como="Se abastece desde el CD (la sucursal recibe traslados)."
                  />
                  <FilaAbast
                    tipo="Importado"
                    modo="cd"
                    como="Siempre se abastece desde el CD."
                  />
                  <FilaAbast
                    tipo="No Representado"
                    modo="ninguno"
                    como="No se pide, salvo que sea importado con stock en el CD."
                  />
                </tbody>
              </table>
            </div>

            <Callout tono="info">
              <strong>Sucursales especiales</strong> — Oficinas Centrales, Canal
              Digital y Linderos Vta Móvil — siempre se abastecen desde el CD, sin
              importar la clase del producto.
            </Callout>
          </Section>

          {/* 5. Las 3 vistas */}
          <Section id="vistas" titulo="Las 3 formas de comprar">
            <P>
              Como hay productos que se compran directo y otros que pasan por el CD,
              el sugerido se muestra en tres listas separadas que no se pisan entre
              sí (juntas dan el total):
            </P>
            <div className="space-y-3">
              <VistaCard
                n="1"
                icon={Building2}
                titulo="Compra directa de sucursal"
                desc="Lo que cada sucursal le pide directamente a su proveedor (nacional clase A o B)."
              />
              <VistaCard
                n="2"
                icon={Boxes}
                titulo="Compra del Centro de Distribución"
                desc="Lo que compra el CD para abastecer a las sucursales (importados, clase C y sucursales especiales)."
              />
              <VistaCard
                n="3"
                icon={Truck}
                titulo="Traslados desde el CD"
                desc="Lo que el CD envía a cada sucursal desde su propio stock, sin volver a comprarlo."
              />
            </div>
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
                porque todavía está incompleto y distorsionaría el promedio.
              </Bullet>
              <Bullet>
                <strong>Deja fuera conceptos que no son repuestos comprables</strong>{" "}
                (insumos de taller, incentivos, ajustes), para que no contaminen la
                demanda.
              </Bullet>
              <Bullet>
                <strong>Productos que se reemplazan entre sí se suman juntos.</strong>{" "}
                Cuando un repuesto sustituye a otro, su venta y su stock se consideran
                como un solo grupo, para no pedir de más.
              </Bullet>
            </ul>
          </Section>

          {/* 7. Reglas que respeta */}
          <Section id="reglas" titulo="Reglas que respeta">
            <ul className="max-w-3xl space-y-3 text-[14px] text-ink-700">
              <Regla t="Siempre el proveedor real">
                Cada producto se asocia a su proveedor de verdad, nunca al CD como si
                fuera el proveedor.
              </Regla>
              <Regla t="Tiempo de entrega real">
                Usa el tiempo que de verdad demora cada proveedor en entregar, no un
                valor fijo. Para los traslados internos desde el CD a la sucursal, el
                tiempo es de 1 a 2 días.
              </Regla>
              <Regla t="Sucursales que no entran al cálculo">
                9 sucursales quedan fuera del sugerido (La Florida, Lira, Lo Blanco,
                las 3 de Mall Plaza, Ovalle 3, Gran Avenida y Coquimbo).
              </Regla>
              <Regla t="Todas las clases se calculan">
                A, B y C generan sugerido. Ninguna clase queda sin reponer por ser
                “menos importante”.
              </Regla>
            </ul>
          </Section>

          {/* 8. Cuándo el CD compra por las sucursales */}
          <Section id="cd" titulo="Cuándo el CD compra por las sucursales">
            <P>
              Cuando varias sucursales necesitan el mismo producto vía CD, el stock
              del CD se reparte por <strong>orden de prioridad de sucursal</strong>. El
              CD sale a comprar solo cuando la necesidad acumulada de las sucursales
              con prioridad supera el stock que ya tiene disponible.
            </P>
            <P className="text-[13px] text-ink-600">
              El orden de prioridad está definido por sucursal (Diez de Julio, Brasil
              18, Linderos, Placilla, Rancagua, y así sucesivamente). Así, si el stock
              del CD no alcanza para todas, primero se cubre a las de mayor prioridad.
            </P>
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

function TipoCard({
  titulo,
  color,
  children,
}: {
  titulo: string;
  color: "brand" | "accent" | "ink";
  children: ReactNode;
}) {
  const barra =
    color === "brand"
      ? "bg-brand"
      : color === "accent"
        ? "bg-accent-500"
        : "bg-ink-400";
  return (
    <div className="overflow-hidden rounded-sm border border-ink-200 bg-white">
      <div className={`h-1 ${barra}`} />
      <div className="p-3.5">
        <p className="text-[14px] font-semibold text-ink-900">{titulo}</p>
        <p className="mt-1 text-[12.5px] leading-relaxed text-ink-600">{children}</p>
      </div>
    </div>
  );
}

function ClaseRow({
  clase,
  tono,
  titulo,
  desc,
}: {
  clase: string;
  tono: "a" | "b" | "c";
  titulo: string;
  desc: string;
}) {
  const cls =
    tono === "a"
      ? "bg-accent-500 text-white"
      : tono === "b"
        ? "bg-brand text-white"
        : "bg-ink-200 text-ink-700";
  return (
    <div className="flex items-start gap-3 rounded-sm border border-ink-200 bg-white p-3.5">
      <span
        className={`flex h-9 w-9 shrink-0 items-center justify-center rounded-sm font-display text-lg font-semibold ${cls}`}
      >
        {clase}
      </span>
      <div>
        <p className="text-[14px] font-semibold text-ink-900">{titulo}</p>
        <p className="mt-0.5 text-[13px] leading-relaxed text-ink-600">{desc}</p>
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
          className={`ml-2 inline-block rounded-sm px-1.5 py-0.5 text-[10.5px] font-semibold ${etiqueta.cls}`}
        >
          {etiqueta.txt}
        </span>
      </td>
      <td className="px-4 py-3 text-ink-600">{como}</td>
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

function Regla({ t, children }: { t: string; children: ReactNode }) {
  return (
    <li className="border-l-2 border-ink-200 pl-3">
      <span className="font-semibold text-ink-900">{t}.</span>{" "}
      <span className="text-ink-700">{children}</span>
    </li>
  );
}
