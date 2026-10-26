"use client";

// Datos: de donde sale lo que se calcula y si esta al dia. Solo lectura; todo se arma al momento en el servidor.
import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { CheckCircle2, CircleAlert, RefreshCw, TriangleAlert } from "lucide-react";
import { formatoNumero } from "@/lib/formato";
import {
  canalDigitalApi,
  periodoLegible,
  type CoberturaDatos,
  type DatosCanalDigital,
  type EstadoFuente,
  type FuenteDatos,
  type VentaMesDatos,
} from "@/lib/canal-digital";

/** Lo mismo que PLAZO_RESPALDO_DIAS del servidor: los productos sin proveedor usan este plazo. */
const DIAS_RESPALDO = 3;
const MESES_EN_TABLA = 14;

const CHIP: Record<EstadoFuente, { texto: string; clase: string; Icono: typeof CheckCircle2 }> = {
  ok: { texto: "En orden", clase: "border-emerald-200 bg-emerald-50 text-emerald-800", Icono: CheckCircle2 },
  aviso: { texto: "Revisar", clase: "border-amber-200 bg-amber-50 text-amber-900", Icono: TriangleAlert },
  falta: { texto: "Falta", clase: "border-red-200 bg-red-50 text-red-700", Icono: CircleAlert },
};

/** Estado de una fuente: palabra e icono ademas del color, para que no dependa de distinguir colores. */
export function ChipEstado({ estado }: { estado: EstadoFuente }) {
  const { texto, clase, Icono } = CHIP[estado];
  return (
    <span
      data-estado={estado}
      className={`inline-flex shrink-0 items-center gap-1 whitespace-nowrap rounded-full border px-2 py-0.5 text-[11px] font-medium ${clase}`}
    >
      <Icono size={12} aria-hidden="true" />
      {texto}
    </span>
  );
}

const plural = (n: number, uno: string, varios: string) => (n === 1 ? uno : varios);
/** "25,7 %" de parte sobre total; sin total no hay porcentaje. */
const porcentaje = (parte: number, total: number) => (total > 0 ? `${formatoNumero((parte / total) * 100, 1)} %` : "—");

function Seccion({ titulo, children }: { titulo: string; children: ReactNode }) {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-4 shadow-sm">
      <h2 className="mb-2 text-[13px] font-semibold text-slate-900">{titulo}</h2>
      {children}
    </section>
  );
}

function TarjetaFuente({ f }: { f: FuenteDatos }) {
  return (
    <li className="rounded-xl border border-slate-200 bg-white p-3 shadow-sm">
      <div className="flex items-start justify-between gap-2">
        <h3 className="text-[13px] font-semibold text-slate-900">{f.nombre}</h3>
        <ChipEstado estado={f.estado} />
      </div>
      <p className="mt-1.5 text-[12.5px] text-slate-600">{f.detalle}</p>
    </li>
  );
}

function TablaMeses({ meses }: { meses: VentaMesDatos[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full min-w-[420px] text-[12.5px]">
        <thead className="text-left text-[11px] uppercase tracking-wide text-slate-500">
          <tr>
            <th className="py-1.5 pr-3">Mes</th>
            <th className="px-3 py-1.5 text-right">Unidades netas</th>
            <th className="px-3 py-1.5 text-right">Devueltas</th>
            <th className="py-1.5 pl-3 text-right">Líneas</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100 tabular-nums">
          {meses.slice(0, MESES_EN_TABLA).map((m) => (
            <tr key={m.periodo}>
              <td className="py-1.5 pr-3 font-medium text-slate-800">{periodoLegible(m.periodo)}</td>
              <td className="px-3 py-1.5 text-right">{formatoNumero(m.unidades_netas)}</td>
              <td className="px-3 py-1.5 text-right text-slate-500">{formatoNumero(m.unidades_devueltas)}</td>
              <td className="py-1.5 pl-3 text-right text-slate-500">
                {m.lineas > 0 ? (
                  formatoNumero(m.lineas)
                ) : (
                  <span title="Mes cargado sin líneas del ERP" aria-label="Sin líneas del ERP">
                    —
                  </span>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

/** Un dato de cobertura: la frase con su porcentaje y una barra de cuanto esta cubierto. */
function FilaCobertura({ titulo, cubiertos, total, frase, nota }: {
  titulo: string;
  cubiertos: number;
  total: number;
  frase: string;
  nota?: string;
}) {
  const ancho = total > 0 ? Math.round((cubiertos / total) * 100) : 0;
  return (
    <li className="py-2">
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[12.5px] font-medium text-slate-800">{titulo}</span>
        <span className="text-[12px] tabular-nums text-slate-500">{porcentaje(cubiertos, total)} cubierto</span>
      </div>
      <div className="mt-1 h-1.5 overflow-hidden rounded-full bg-slate-100" aria-hidden="true">
        <div className="h-full rounded-full bg-brand" style={{ width: `${ancho}%` }} />
      </div>
      <p className="mt-1 text-[12.5px] text-slate-600">{frase}</p>
      {nota && <p className="text-[12px] text-slate-500">{nota}</p>}
    </li>
  );
}

function Cobertura({ c }: { c: CoberturaDatos }) {
  const n = c.productos;
  if (n === 0) {
    return <p className="text-[12.5px] text-slate-500">Todavía no hay productos: la cobertura se calcula cuando haya venta cargada.</p>;
  }
  const productos = (k: number) => `${formatoNumero(k)} de ${formatoNumero(n)} ${plural(n, "producto", "productos")}`;
  return (
    <ul className="divide-y divide-slate-100">
      <FilaCobertura
        titulo="Plazo de entrega"
        cubiertos={c.con_proveedor}
        total={n}
        frase={`${productos(c.sin_proveedor)} sin proveedor: usan ${DIAS_RESPALDO} días de respaldo (${porcentaje(c.sin_proveedor, n)}).`}
        nota={`${formatoNumero(c.proveedor_menos_5_muestras)} tienen un proveedor con menos de 5 pedidos medidos.`}
      />
      <FilaCobertura
        titulo="Costo"
        cubiertos={c.con_costo}
        total={n}
        frase={`${productos(c.sin_costo)} sin costo: su valor a pedir sale en $0 (${porcentaje(c.sin_costo, n)}).`}
        nota={`${formatoNumero(c.costo_sin_respaldo_stock)} tienen costo pero hoy no tienen stock: el costo puede estar viejo.`}
      />
      <FilaCobertura
        titulo="Stock en la bodega"
        cubiertos={c.con_stock_bodega}
        total={n}
        frase={`${productos(c.con_stock_bodega)} tienen stock en la bodega (${porcentaje(c.con_stock_bodega, n)}); ${formatoNumero(c.sin_stock_bodega)} no tienen.`}
        nota={`${formatoNumero(c.con_stock_aparte)} tienen stock aparte, que no suma al disponible.`}
      />
      <FilaCobertura
        titulo="Pedidos en camino"
        cubiertos={c.con_transito_a_la_bodega}
        total={n}
        frase={`${productos(c.con_transito_a_la_bodega)} tienen pedidos en camino a la bodega (${porcentaje(c.con_transito_a_la_bodega, n)}).`}
        nota={`${formatoNumero(c.con_transito_otro_destino)} tienen pedidos a otro destino, que no suman.`}
      />
    </ul>
  );
}

/** Un paso que trae el comando al final ("... con: python scripts/...") lo muestra en su propio renglon. */
function Paso({ texto }: { texto: string }) {
  const i = texto.indexOf("python ");
  if (i < 0) return <li>{texto}</li>;
  return (
    <li>
      {texto.slice(0, i).trimEnd()}
      <code className="mt-1 block overflow-x-auto rounded bg-slate-100 px-2 py-1 font-mono text-[11.5px] text-slate-800">
        {texto.slice(i)}
      </code>
    </li>
  );
}

export function PestanaDatos({ bodega }: { bodega: string }) {
  const [datos, setDatos] = useState<DatosCanalDigital | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const peticion = useRef(0);

  const cargar = useCallback(() => {
    const mia = ++peticion.current;
    setCargando(true);
    setError(null);
    canalDigitalApi
      .datos(bodega)
      .then((d) => mia === peticion.current && setDatos(d))
      .catch((e) => {
        if (mia !== peticion.current) return;
        setDatos(null); // sin datos confiables no se deja a la vista lo de la consulta anterior
        setError(e instanceof Error ? e.message : "No se pudieron cargar los datos");
      })
      .finally(() => mia === peticion.current && setCargando(false));
  }, [bodega]);

  useEffect(() => {
    cargar();
    return () => {
      peticion.current++; // una respuesta que llega con la pestana cerrada se descarta
    };
  }, [cargar]);

  if (error) {
    return (
      <div className="space-y-2">
        <p role="alert" className="rounded-md bg-red-50 px-3 py-2 text-[13px] text-red-700">
          {error}
        </p>
        <button
          type="button"
          onClick={cargar}
          disabled={cargando}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-[13px] text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw size={14} /> Reintentar
        </button>
      </div>
    );
  }

  if (!datos) {
    return (
      <p role="status" className="text-[13px] text-slate-500">
        Cargando datos…
      </p>
    );
  }

  const { ventas, cobertura, fuentes, validaciones, como_cargar } = datos;
  const sinVenta = ventas.por_mes.length === 0;

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[12.5px] text-slate-500">
          Lo que alimenta el cálculo de la bodega {bodega} y si está al día. Se recalcula al abrir esta pestaña.
        </p>
        <button
          type="button"
          onClick={cargar}
          disabled={cargando}
          className="inline-flex items-center gap-1.5 rounded-md border border-slate-300 px-3 py-1.5 text-[13px] text-slate-700 hover:bg-slate-50 disabled:opacity-50"
        >
          <RefreshCw size={14} /> {cargando ? "Actualizando…" : "Actualizar"}
        </button>
      </div>

      <section aria-label="Fuentes de datos">
        <ul className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {fuentes.map((f) => (
            <TarjetaFuente key={f.nombre} f={f} />
          ))}
        </ul>
      </section>

      <Seccion titulo="Venta del canal por mes">
        {sinVenta ? (
          <p className="rounded-md bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
            Todavía no hay venta cargada para esta bodega. Abajo está cómo cargar el primer mes.
          </p>
        ) : (
          <>
            <TablaMeses meses={ventas.por_mes} />
            <p className="mt-2 text-[12px] text-slate-500">
              Cargada desde {periodoLegible(ventas.periodo_desde)} hasta {periodoLegible(ventas.ultimo_periodo_cargado)} ·{" "}
              {formatoNumero(ventas.filas)} filas de venta · {formatoNumero(ventas.productos)} códigos vendidos ·{" "}
              {formatoNumero(ventas.lineas)} líneas del ERP
              {ventas.lineas > 0 && ` (hasta ${periodoLegible(ventas.lineas_periodo_hasta)})`}. Se muestran los últimos{" "}
              {MESES_EN_TABLA} meses.
            </p>
          </>
        )}
      </Seccion>

      <Seccion titulo="Cobertura: cuántos productos tienen cada dato">
        <Cobertura c={cobertura} />
      </Seccion>

      <Seccion titulo="Validaciones">
        <ul className="space-y-1.5">
          {validaciones.map((v) => (
            <li key={v.nombre} className="flex items-start gap-2 text-[12.5px]">
              {v.ok ? (
                <CheckCircle2 size={15} className="mt-0.5 shrink-0 text-emerald-600" aria-label="Pasa" />
              ) : (
                <CircleAlert size={15} className="mt-0.5 shrink-0 text-red-600" aria-label="Falla" />
              )}
              <span>
                <span className="font-medium text-slate-800">{v.nombre}.</span>{" "}
                <span className="text-slate-500">{v.detalle}</span>
              </span>
            </li>
          ))}
        </ul>
      </Seccion>

      <Seccion titulo="Cómo cargar un mes nuevo de venta">
        <ol className="list-decimal space-y-1.5 pl-5 text-[12.5px] text-slate-700">
          {como_cargar.map((p) => (
            <Paso key={p} texto={p} />
          ))}
        </ol>
      </Seccion>
    </div>
  );
}
