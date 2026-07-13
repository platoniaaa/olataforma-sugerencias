"use client";

import type { ReactNode } from "react";
import { Download, Info, Lightbulb, Truck } from "lucide-react";

/* Documentación del modelo de sugerido, en lenguaje de negocio (audiencia:
   Abastecimiento, no técnica). Refleja la lógica REAL del modelo de Power BI
   (tabla 'Sugerido por Sucursal' y sus medidas). Si el modelo cambia, actualizar los
   TRES lugares: acá, el .docx de /public (modelo-sugerido-de-compras.docx) y el
   contexto del chatbot (apps/api/src/services/modelo_negocio.md). */

const DOC = "/modelo-sugerido-de-compras.docx";

type Seccion = { id: string; titulo: string };

const SECCIONES: Seccion[] = [
  { id: "que-hace", titulo: "Qué hace el modelo" },
  { id: "fuentes", titulo: "De dónde salen los datos" },
  { id: "limpieza", titulo: "1 · Limpieza de las ventas" },
  { id: "abc", titulo: "2 · Clasificación ABC" },
  { id: "demanda", titulo: "3 · Demanda mensual" },
  { id: "proveedor", titulo: "4 · Proveedor y lead time" },
  { id: "cd", titulo: "5 · ¿Se abastece por el CD?" },
  { id: "colchon", titulo: "6 · Stock de seguridad" },
  { id: "sugerido", titulo: "7 · El sugerido de compra" },
  { id: "traslados", titulo: "8 · Distribución y traslados" },
  { id: "reglas", titulo: "Reglas de negocio" },
  { id: "parametros", titulo: "Parámetros de referencia" },
];

const ETAPAS = [
  "Limpiar las ventas",
  "Clasificar cada producto (ABC)",
  "Estimar la demanda",
  "Asignar proveedor y tiempo de entrega",
  "Decidir si se abastece por el CD",
  "Calcular el stock de seguridad",
  "Calcular el sugerido de compra",
  "Repartir el stock del CD (traslados)",
];

const PRIORIDAD = [
  "Diez de Julio (2)", "Brasil 18", "Linderos", "Placilla", "Rancagua",
  "Rancagua 2", "Curicó", "Talca", "Talca (2)", "Chillán", "Chillán Viejo",
];

export default function ModeloPage() {
  return (
    <div className="space-y-8">
      {/* Encabezado */}
      <header className="border-b border-ink-200 pb-5">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <p className="kicker mb-2 flex items-center gap-1.5">
              <Lightbulb size={13} className="text-accent-500" /> Cómo funciona
            </p>
            <h1 className="font-display text-3xl font-medium tracking-tight text-ink-900">
              Cómo se calcula el sugerido
            </h1>
          </div>
          <a
            href={DOC}
            download
            className="inline-flex shrink-0 items-center gap-2 rounded-sm border border-ink-300 bg-white px-3.5 py-2 text-[13px] font-semibold text-ink-800 transition-colors hover:border-accent-500 hover:text-accent-600"
          >
            <Download size={15} /> Exportar a Word
          </a>
        </div>
        <p className="mt-3 max-w-3xl text-[14.5px] leading-relaxed text-ink-600">
          Esta página explica, en simple, de dónde sale cada número que ves en la
          plataforma: qué datos usa, cómo se clasifican los productos, cómo se
          estima la demanda y cómo se decide cuánto pedir o trasladar. Es la
          documentación completa del modelo, para revisar y validar con confianza.
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
          <Section id="que-hace" titulo="Qué hace el modelo">
            <P>
              A partir del <strong>historial de ventas</strong>, el{" "}
              <strong>stock actual</strong>, las <strong>órdenes de compra</strong> y
              los <strong>tiempos de entrega de cada proveedor</strong>, el modelo
              estima cuánto se vende y cuánto stock hace falta para no quebrar, y con
              eso calcula <strong>cuánto pedir</strong> (al proveedor) o{" "}
              <strong>cuánto trasladar</strong> (desde el Centro de Distribución) en
              cada producto y sucursal.
            </P>
            <P>
              El cálculo es una cadena de <strong>8 etapas</strong>; cada una usa el
              resultado de la anterior:
            </P>
            <ol className="grid max-w-3xl gap-1.5 sm:grid-cols-2">
              {ETAPAS.map((e, i) => (
                <li
                  key={e}
                  className="flex items-center gap-2.5 rounded-sm border border-ink-200 bg-white px-3 py-2 text-[13px] text-ink-700"
                >
                  <span className="flex h-5 w-5 shrink-0 items-center justify-center rounded-sm bg-brand text-[11px] font-semibold text-white">
                    {i + 1}
                  </span>
                  {e}
                </li>
              ))}
            </ol>
          </Section>

          <Section id="fuentes" titulo="De dónde salen los datos">
            <Tabla
              headers={["Fuente", "Qué aporta al modelo"]}
              rows={[
                ["Ventas (Curifor + Frontera)", "El historial de venta mensual por producto y sucursal. Base para clasificar y estimar la demanda."],
                ["Seguimiento de compras (OC)", "Las órdenes de compra: proveedor, fechas de OC y recepción (para el lead time) y lo que está en tránsito."],
                ["Stock por bodega (Curifor + Frontera)", "El stock disponible hoy en cada sucursal y en el CD."],
                ["Catálogos y reemplazos", "Descripción, marca, unidad, región de la sucursal y qué códigos son reemplazo de cuál (se tratan como un mismo producto)."],
              ]}
            />
          </Section>

          <Section id="limpieza" titulo="1 · Limpieza de las ventas">
            <P>Antes de calcular nada, se depura la venta para que el número sea real y comparable:</P>
            <ul className="max-w-3xl space-y-2 text-[14px] text-ink-700">
              <Bullet><strong>Venta neta:</strong> se descuentan devoluciones y notas de crédito (no la venta bruta).</Bullet>
              <Bullet><strong>Solo meses cerrados:</strong> se ignora el mes en curso (incompleto).</Bullet>
              <Bullet><strong>Reemplazos agrupados:</strong> si un código reemplaza a otro, su venta y stock se suman al producto “maestro”.</Bullet>
              <Bullet><strong>Sucursales excluidas:</strong> las cerradas o fuera de alcance (La Florida, Lira, Lo Blanco, los Mall Plaza, Ovalle (3), Gran Avenida, Coquimbo y Diez de Julio antigua).</Bullet>
              <Bullet><strong>Productos internos excluidos:</strong> conceptos que no se compran a proveedor (taller D&P, insumos mecánica, incentivos, deducciones).</Bullet>
              <Bullet><strong>Categorías excluidas:</strong> Colisión y Campañas no participan del sugerido de reposición.</Bullet>
              <Bullet><strong>Ventas móviles y canales al CD:</strong> Linderos “venta móvil”, Canal Digital y Oficinas Centrales se consolidan en el CD.</Bullet>
            </ul>
            <Callout>
              Para las <strong>compras</strong> (proveedor y tránsito) se usan solo las OC con motivo
              <strong> “reposición”</strong>; las compras puntuales (colisión, garantía, calzada) no
              cuentan como abastecimiento normal.
            </Callout>
          </Section>

          <Section id="abc" titulo="2 · Clasificación ABC (por frecuencia de venta)">
            <P>
              No es un ABC de Pareto (por facturación). Acá la clase mide{" "}
              <strong>con qué frecuencia se vende</strong>: se cuentan los meses con venta en los
              últimos 3, 6 y 12 meses.
            </P>
            <Tabla
              headers={["Clase", "Condición (meses con venta)", "Lectura"]}
              rows={[
                ["A", "5 o 6 de los últimos 6 meses", "Muy frecuente"],
                ["B", "4 de los últimos 6 meses", "Frecuente"],
                ["C", "3 de los últimos 6 (con apoyo en 3m o 12m)", "Intermitente"],
                ["D", "el resto", "Esporádico / casi sin venta"],
              ]}
            />
            <Callout>
              Se calcula en dos niveles: <strong>local</strong> (el producto en esa sucursal) y{" "}
              <strong>agregada</strong> (el producto en toda la empresa). La combinación de ambas
              decide si conviene centralizar el producto en el CD. La clase define casi todo lo que
              sigue: cuántos meses de historia se miran, cuánto colchón se exige y si se compra
              directo o vía CD.
            </Callout>
          </Section>

          <Section id="demanda" titulo="3 · Demanda mensual">
            <P>Es el motor del cálculo: cuántas unidades por mes se espera vender.</P>
            <ul className="max-w-3xl space-y-2 text-[14px] text-ink-700">
              <Bullet><strong>Ventana según clase:</strong> los A/B miran los últimos 6 meses; los C/D, los últimos 12.</Bullet>
              <Bullet><strong>Se arma la serie mensual</strong> (la venta de cada mes; 0 en los meses sin venta).</Bullet>
              <Bullet><strong>Winsorización:</strong> se recortan los meses atípicamente altos con un tope robusto (mediana + k × 1,4826 × MAD, con k = 3) para que un pedido puntual no infle la demanda. El detalle está en el documento “Método de winsorización”.</Bullet>
              <Bullet><strong>Demanda mensual = promedio</strong> de la serie ya recortada; la demanda diaria = demanda mensual ÷ 22 días hábiles.</Bullet>
              <Bullet><strong>Caso CD:</strong> para los productos que el CD centraliza, la demanda consolida su venta más la de las sucursales que se abastecen de él, sobre 12 meses.</Bullet>
            </ul>
          </Section>

          <Section id="proveedor" titulo="4 · Proveedor y tiempo de entrega (lead time)">
            <P>
              <strong>Proveedor:</strong> se toma el de la orden de compra de reposición más reciente
              de ese producto en esa sucursal. Si esa sucursal nunca lo compró por reposición, se
              completa con el proveedor que el modelo deduce del histórico del producto (válido porque
              cada código tiene un único proveedor).
            </P>
            <P>
              <strong>Lead time</strong> (días que tarda en llegar): se calcula desde el seguimiento,
              midiendo los días entre la OC y su recepción, descartando la cola de casos lentos y
              promediando el resto. La jerarquía:
            </P>
            <ul className="max-w-3xl space-y-2 text-[14px] text-ink-700">
              <Bullet>el lead time de ese proveedor en esa sucursal (si hay historial);</Bullet>
              <Bullet>si no, el lead time general de ese proveedor;</Bullet>
              <Bullet>si tampoco hay, 8 días por defecto.</Bullet>
            </ul>
            <P className="text-[13px] text-ink-600">
              <strong>Lead time del CD a la sucursal:</strong> 1 día en la Región Metropolitana, 2 en
              el resto (casos fijos: Diez de Julio (2) = 1, Talca (2) = 2). El{" "}
              <strong>lead time efectivo</strong> es el del CD si el producto se abastece por el CD, o
              el del proveedor si se compra directo.
            </P>
          </Section>

          <Section id="cd" titulo="5 · ¿Se abastece por el Centro de Distribución?">
            <P>
              Algunos productos conviene centralizarlos en el CD y desde ahí distribuir, en vez de que
              cada sucursal le compre al proveedor:
            </P>
            <ul className="max-w-3xl space-y-2 text-[14px] text-ink-700">
              <Bullet><strong>En una sucursal:</strong> se abastece por el CD si el producto es importado, o si es de baja rotación local (C/D) pero de alta rotación a nivel empresa (agregada A/B).</Bullet>
              <Bullet><strong>En el CD:</strong> solo se abastece a sí mismo si el producto es importado.</Bullet>
            </ul>
            <P className="text-[13px] text-ink-600">
              Esta decisión cambia el ciclo de orden y el lead time efectivo, y habilita los traslados
              (etapa 8).
            </P>
          </Section>

          <Section id="colchon" titulo="6 · Stock de seguridad">
            <P>
              Es el colchón para no quebrar mientras llega la reposición, frente a la variabilidad de
              la venta:
            </P>
            <Formula>Stock de seguridad = Z × desviación × √(meses de protección)</Formula>
            <Tabla
              headers={["Clase", "Z (normal)", "Z (importado por CD)"]}
              rows={[
                ["A", "1,645", "1,282"],
                ["B", "1,282", "1,036"],
                ["C", "0,842", "—"],
                ["D", "0", "—"],
              ]}
            />
            <ul className="max-w-3xl space-y-2 text-[14px] text-ink-700">
              <Bullet><strong>Z (nivel de servicio) según la clase:</strong> cuanto más importante el producto, más colchón.</Bullet>
              <Bullet><strong>Desviación:</strong> cuánto varía la venta mes a mes (de la misma serie ya winsorizada).</Bullet>
              <Bullet><strong>Meses de protección = (lead time efectivo + ciclo de orden) ÷ 22.</strong> El ciclo de orden es 5 días directo y 3 vía CD.</Bullet>
            </ul>
            <P className="text-[13px] text-ink-600">
              En criollo: productos importantes y de venta irregular llevan más colchón; los parejos o
              de baja clase, menos o nada.
            </P>
          </Section>

          <Section id="sugerido" titulo="7 · El sugerido de compra">
            <P>Con la demanda, el lead time y el colchón se calcula la necesidad y se descuenta lo que ya se tiene:</P>
            <Formula>
              Necesidad = Demanda diaria × (ciclo orden + lead time) + Stock seguridad − Stock actual − En tránsito
            </Formula>
            <ul className="max-w-3xl space-y-2 text-[14px] text-ink-700">
              <Bullet><strong>Stock actual:</strong> lo disponible hoy en la sucursal (sumando el grupo de reemplazos, Curifor + Frontera).</Bullet>
              <Bullet><strong>En tránsito:</strong> las OC pendientes que ya vienen en camino (nacional de reposición hasta 30 días, importado hasta 180, frontera hasta 30).</Bullet>
              <Bullet><strong>Sugerido:</strong> esa necesidad (nunca negativa), pero solo se sugiere comprar en productos cuya clase que compra es A/B; los de baja clase quedan en 0.</Bullet>
              <Bullet><strong>Punto de pedido = Demanda diaria × lead time + Stock seguridad.</strong> Indica <em>cuándo</em> reponer (no cuánto).</Bullet>
              <Bullet><strong>Pedir:</strong> la fila queda “Sí” cuando el sugerido es mayor que 0.</Bullet>
            </ul>
          </Section>

          <Section id="traslados" titulo="8 · Distribución desde el CD y traslados">
            <P>Para los productos centralizados, antes de comprarle al proveedor se reparte el stock que ya está en el CD:</P>
            <ul className="max-w-3xl space-y-2 text-[14px] text-ink-700">
              <Bullet><strong>Reparto por prioridad:</strong> el stock del CD se asigna a las sucursales elegibles siguiendo un ranking fijo. Cada una recibe hasta cubrir su necesidad, con lo que quede después de las de mayor prioridad.</Bullet>
              <Bullet><strong>Comprar en el CD:</strong> se marca “Sí” cuando, al llegar el turno de una sucursal, la necesidad acumulada supera el stock del CD (señal de que el CD debe reponerse).</Bullet>
              <Bullet><strong>Compra neta:</strong> el sugerido menos lo que se cubre con traslado desde el CD. Es lo que efectivamente hay que comprarle al proveedor.</Bullet>
              <Bullet><strong>Traslado lateral (informativo):</strong> para las filas con sugerido, se listan otras sucursales con stock del producto, por si conviene un traslado en vez de comprar.</Bullet>
            </ul>
            <div className="max-w-2xl rounded-sm border border-ink-200 bg-white p-4">
              <p className="flex items-center gap-1.5 kicker mb-2.5">
                <Truck size={13} className="text-accent-500" /> Orden de prioridad del CD
              </p>
              <div className="flex flex-wrap gap-1.5 text-[12.5px]">
                {PRIORIDAD.map((s, i) => (
                  <span
                    key={s}
                    className="inline-flex items-center gap-1.5 rounded-sm border border-ink-200 bg-paper-50 px-2 py-1"
                  >
                    <span className="font-mono font-semibold text-accent-600">{i + 1}</span>
                    <span className="text-ink-700">{s}</span>
                  </span>
                ))}
              </div>
              <p className="mt-2.5 text-[12px] text-ink-500">El resto de las sucursales queda en prioridad más baja.</p>
            </div>
          </Section>

          <Section id="reglas" titulo="Reglas de negocio adicionales">
            <P>Sobre el cálculo del modelo, la plataforma aplica algunos ajustes de sentido común:</P>
            <ul className="max-w-3xl space-y-2 text-[14px] text-ink-700">
              <Bullet><strong>Stock cubre + sin venta reciente → no pedir:</strong> si una sucursal tiene stock suficiente para su demanda mensual y no vendió el producto el mes anterior, no se sugiere comprar.</Bullet>
              <Bullet><strong>Sucursales cerradas ocultas:</strong> la Diez de Julio antigua (cerrada) no se muestra; solo la Diez de Julio (2) activa.</Bullet>
              <Bullet><strong>Proveedores rellenados:</strong> los productos sin reposición confirmada en la sucursal muestran igual el proveedor deducido, para reducir las filas “sin proveedor”.</Bullet>
              <Bullet><strong>Aceites en mililitros:</strong> se mantienen como vienen (decisión de Abastecimiento); pueden inflar totales pero es esperado.</Bullet>
            </ul>
          </Section>

          <Section id="parametros" titulo="Parámetros y clasificaciones de referencia">
            <P>Valores fijos del modelo (auditados jul-2026):</P>
            <Tabla
              headers={["Parámetro", "Valor", "Qué es"]}
              rows={[
                ["Escalar winsorización (k)", "3", "Qué tan estricto es el recorte de meses pico (antes 1)."],
                ["Días hábiles por mes", "22", "Divisor para pasar de demanda mensual a diaria."],
                ["Ciclo de orden", "5 directo / 3 vía CD", "Días de cobertura extra que se agregan al pedir."],
                ["Lead time por defecto", "8 días", "Cuando no hay proveedor ni historial de OC."],
                ["Lead time CD → sucursal", "1 (RM) / 2 (resto)", "Días de traslado del CD a la sucursal."],
                ["Vigencia de tránsito", "30 d nacional / 180 d importado", "Ventana para contar una OC como “en camino”."],
                ["Nivel de servicio Z", "A 1,645 · B 1,282 · C 0,842 · D 0", "Colchón por clase (más alto = más stock de seguridad)."],
              ]}
            />
          </Section>
        </div>
      </div>
    </div>
  );
}

/* ---------- Componentes de presentación ---------- */

function Section({ id, titulo, children }: { id: string; titulo: string; children: ReactNode }) {
  return (
    <section id={id} className="scroll-mt-24 space-y-4">
      <h2 className="font-display text-2xl font-medium tracking-tight text-ink-900 editorial-rule">
        {titulo}
      </h2>
      {children}
    </section>
  );
}

function P({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <p className={`max-w-3xl text-[14.5px] leading-relaxed text-ink-700 ${className}`}>{children}</p>
  );
}

function Formula({ children }: { children: ReactNode }) {
  return (
    <div className="max-w-3xl overflow-x-auto rounded-sm border border-brand-200 bg-brand-50/40 px-4 py-3 text-center font-mono text-[13px] font-semibold text-brand-900">
      {children}
    </div>
  );
}

function Callout({ children }: { children: ReactNode }) {
  return (
    <div className="flex max-w-3xl gap-2.5 rounded-sm border border-brand-200 bg-brand-50/60 px-4 py-3 text-[13.5px] leading-relaxed text-ink-700">
      <Info size={16} className="mt-0.5 shrink-0 text-brand" />
      <div>{children}</div>
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

function Tabla({ headers, rows }: { headers: string[]; rows: string[][] }) {
  return (
    <div className="max-w-3xl overflow-x-auto rounded-sm border border-ink-200 bg-white">
      <table className="w-full text-[13.5px]">
        <thead>
          <tr className="border-b border-ink-200 bg-ink-50 text-left">
            {headers.map((h) => (
              <th key={h} className="px-4 py-2.5 font-semibold text-ink-700">{h}</th>
            ))}
          </tr>
        </thead>
        <tbody className="divide-y divide-ink-100">
          {rows.map((r, i) => (
            <tr key={i} className="align-top">
              {r.map((c, j) => (
                <td
                  key={j}
                  className={`px-4 py-2.5 ${j === 0 ? "font-semibold text-ink-900" : "text-ink-600"}`}
                >
                  {c}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
