"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import Link from "next/link";
import { Boxes, ChevronDown, ChevronRight, ChevronsRight, Layers, Lock, Repeat, Trash2, Wrench } from "lucide-react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { api } from "@/lib/api-client";
import { formatoCLP, formatoFecha, formatoFechaHora, formatoNumero } from "@/lib/formato";
import type { InstockResumen, Recurrente, SugerenciaManual } from "@/lib/types";

type Tab = "unicas" | "recurrentes";

/**
 * Enlace al detalle de una sugerencia.
 *
 * La tarjeta muestra el titular; el detalle responde si eso esta aportando algo.
 * Va como enlace explicito y no como card clickeable entera porque la card ya
 * tiene botones (borrar, expandir) y un click que a veces navega y a veces no
 * es justo el tipo de ambiguedad que hay que evitar.
 */
function VerDetalle({ tipo, id }: { tipo: string; id: string }) {
  return (
    <Link
      href={`/sugerencias-manuales/${tipo}/${encodeURIComponent(id)}`}
      className="inline-flex shrink-0 items-center gap-1 rounded-md border border-slate-200 bg-white px-2.5 py-1.5 text-[12px] font-medium text-slate-600 transition-colors hover:border-brand hover:text-brand"
    >
      Ver detalle <ChevronsRight size={13} />
    </Link>
  );
}

// expira_en apunta a la medianoche del día SIGUIENTE a la fecha límite elegida
// (la sugerencia vive todo ese día). Para mostrar la fecha límite inclusive se
// resta un minuto al instante de vencimiento.
function fechaLimite(expiraEn: string): string {
  const d = new Date(expiraEn);
  if (Number.isNaN(d.getTime())) return "—";
  return formatoFecha(new Date(d.getTime() - 60000).toISOString());
}

/** Con qué criterio se pidió, y qué implica.
 *
 * Los tres tipos NO se comportan igual y la diferencia decide plata: "días" y
 * "mantener" completan un nivel —descuentan lo que ya hay en bodega, así que
 * pueden terminar pidiendo 0—, mientras que "unidades" suma una cantidad fija
 * pase lo que pase con el stock. Antes esa última decía solo "unidades
 * directas", que no dice nada: el título explica el comportamiento al pasar el
 * mouse, para no depender de que alguien sepa la diferencia de memoria.
 */
function EtiquetaTipo({ m }: { m: SugerenciaManual }) {
  if (m.stock_objetivo)
    return (
      <Badge
        className="bg-emerald-50 text-emerald-700"
        title={`Completa hasta dejar ${formatoNumero(m.stock_objetivo)} u en stock. Descuenta lo que ya hay, así que si la sucursal ya llegó a ese nivel no pide nada.`}
      >
        completar a {formatoNumero(m.stock_objetivo)} u
      </Badge>
    );
  if (m.dias_inventario)
    return (
      <Badge
        className="bg-blue-50 text-blue-700"
        title={`Completa lo que falte para cubrir ${m.dias_inventario} días de venta según la demanda del modelo. Descuenta lo que ya hay.`}
      >
        cubrir {m.dias_inventario} días
      </Badge>
    );
  return (
    <Badge
      className="bg-slate-100 text-slate-600"
      title={`Suma ${formatoNumero(m.unidades)} u fijas al sugerido, sin mirar el stock: se piden igual aunque la sucursal ya tenga de sobra.`}
    >
      suma {formatoNumero(m.unidades)} u fijas
    </Badge>
  );
}

/** La misma etiqueta para un lote entero.
 *
 * Una carga masiva por filtros usa el mismo criterio y el mismo número en todas
 * sus filas, pero una carga pegada trae un valor por línea. Mostrar el de la
 * primera fila como si fuera el de todas diría un número que no es cierto para
 * las demás, así que cuando varían se dice que varían.
 */
function EtiquetaTipoLote({ filas }: { filas: SugerenciaManual[] }) {
  const primera = filas[0];
  if (!primera) return null;
  const criterio = (m: SugerenciaManual) =>
    m.stock_objetivo ? "objetivo" : m.dias_inventario ? "dias" : "unidades";
  const valor = (m: SugerenciaManual) =>
    `${criterio(m)}:${m.stock_objetivo ?? m.dias_inventario ?? m.unidades}`;

  const mismoCriterio = filas.every((m) => criterio(m) === criterio(primera));
  const mismoValor = filas.every((m) => valor(m) === valor(primera));
  if (mismoValor) return <EtiquetaTipo m={primera} />;
  if (mismoCriterio) {
    const etiqueta =
      criterio(primera) === "objetivo"
        ? "completar a un nivel por línea"
        : criterio(primera) === "dias"
          ? "cubrir días por línea"
          : "suma fija por línea";
    return (
      <Badge
        className="bg-slate-100 text-slate-600"
        title="Cada línea de esta carga trae su propia cantidad."
      >
        {etiqueta}
      </Badge>
    );
  }
  return (
    <Badge
      className="bg-slate-100 text-slate-600"
      title="Esta carga mezcla los tres criterios: cada línea trae el suyo. Ábrela para ver el detalle."
    >
      criterio mixto
    </Badge>
  );
}

function BadgeVencimiento({ expiraEn }: { expiraEn: string }) {
  const vencida = new Date(expiraEn).getTime() <= Date.now();
  return vencida ? (
    <Badge className="bg-red-50 text-red-700">vencida — ya no suma</Badge>
  ) : (
    <Badge className="bg-amber-50 text-amber-700">hasta el {fechaLimite(expiraEn)}</Badge>
  );
}

export default function SugerenciasManualesPage() {
  const [tab, setTab] = useState<Tab>("unicas");
  const [unicas, setUnicas] = useState<SugerenciaManual[] | null>(null);
  const [recurrentes, setRecurrentes] = useState<Recurrente[] | null>(null);
  const [instock, setInstock] = useState<InstockResumen | null>(null);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(async () => {
    setError(null);
    try {
      const [u, r] = await Promise.all([
        api.sugerenciasManuales({ soloUnicas: true }),
        api.recurrentes(),
      ]);
      setUnicas(u);
      setRecurrentes(r);
    } catch (e) {
      setError(e instanceof Error ? e.message : "Error al cargar");
    }
    // La regla InStock va aparte: si el backend todavia no la expone (despliegue
    // viejo), la pantalla tiene que seguir mostrando las sugerencias igual.
    try {
      setInstock(await api.instockResumen());
    } catch {
      setInstock(null);
    }
  }, []);

  useEffect(() => {
    cargar();
  }, [cargar]);

  const eliminarUnica = async (id: string) => {
    if (!confirm("¿Eliminar esta sugerencia? Se quita de la compra.")) return;
    await api.eliminarSugerenciaManual(id);
    cargar();
  };

  const eliminarLote = async (loteId: string, n: number) => {
    if (
      !confirm(
        `¿Eliminar las ${formatoNumero(n)} sugerencias de esta carga masiva? Esta acción no se puede deshacer.`
      )
    )
      return;
    await api.eliminarLoteSugerencias(loteId);
    cargar();
  };

  const eliminarRecurrente = async (id: string) => {
    if (
      !confirm(
        "¿Eliminar esta recurrencia? Su ajuste vigente dejará de sumar a la compra."
      )
    )
      return;
    await api.eliminarRecurrente(id);
    cargar();
  };

  const tabs: { id: Tab; icon: React.ReactNode; label: string; count: number | null }[] = [
    {
      id: "unicas",
      icon: <Boxes size={15} />,
      label: "Únicas",
      count: unicas?.length ?? null,
    },
    {
      id: "recurrentes",
      icon: <Repeat size={15} />,
      label: "Recurrentes",
      count: recurrentes?.length ?? null,
    },
  ];

  return (
    <div className="mx-auto max-w-4xl space-y-4">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-900">
          Sugerencias manuales
        </h1>
        <p className="text-[13px] text-slate-500">
          Ajustes del equipo que se suman al sugerido del BI. Se crean desde el botón
          “Sugerencia manual” en el dashboard.
        </p>
      </div>

      <div className="flex gap-1 border-b border-slate-200">
        {tabs.map((t) => (
          <button
            key={t.id}
            onClick={() => setTab(t.id)}
            className={`flex items-center gap-1.5 border-b-2 px-3 py-2 text-[13px] font-medium transition-colors ${
              tab === t.id
                ? "border-brand text-brand"
                : "border-transparent text-slate-500 hover:text-slate-800"
            }`}
          >
            {t.icon} {t.label}
            {t.count !== null && (
              <span className="rounded bg-slate-100 px-1.5 py-px text-[10px] text-slate-600">
                {t.count}
              </span>
            )}
          </button>
        ))}
      </div>

      {error && (
        <div className="rounded-md border border-amber-200 bg-amber-50 px-4 py-3 text-[13px] text-amber-800">
          {error}
        </div>
      )}

      {tab === "unicas" && (
        <SeccionUnicas
          items={unicas}
          onEliminar={eliminarUnica}
          onEliminarLote={eliminarLote}
        />
      )}

      {tab === "recurrentes" && (
        <>
          <TarjetaInstock resumen={instock} />
          <SeccionRecurrentes
            items={recurrentes}
            onEliminar={eliminarRecurrente}
          />
        </>
      )}
    </div>
  );
}

/**
 * Qué repuesto es y cuánto cuesta la sugerencia. La lista mostraba solo el código
 * ("74 1324409TBW0000") y había que ir al catálogo a averiguar el resto; con esto
 * se puede revisar lo cargado sin salir de la pantalla.
 */
function FichaProducto({ m }: { m: SugerenciaManual }) {
  const datos = [
    m.marca,
    m.proveedor,
    typeof m.stock_actual === "number"
      ? `stock ${formatoNumero(m.stock_actual)} u`
      : null,
    typeof m.valor_clp === "number" && m.valor_clp > 0
      ? formatoCLP(m.valor_clp)
      : null,
  ].filter(Boolean);
  if (!m.descripcion && datos.length === 0) return null;
  return (
    <p className="mt-0.5 text-[13px] text-slate-700">
      {m.descripcion ?? <span className="text-slate-400">sin descripción</span>}
      {datos.length > 0 && (
        <span className="text-slate-500"> · {datos.join(" · ")}</span>
      )}
    </p>
  );
}

/** Enumera en castellano: "Linderos, Rancagua, Curicó y Chillán". */
function enumerar(xs: string[]): string {
  if (xs.length <= 1) return xs[0] ?? "";
  return `${xs.slice(0, -1).join(", ")} y ${xs[xs.length - 1]}`;
}

/**
 * La regla InStock entre las recurrentes. No la creó nadie desde la interfaz —sale
 * de las pautas del fabricante— pero para el comprador hace lo mismo que una
 * recurrente de "mantener N unidades" que no vence nunca, así que tiene que verse
 * donde el equipo las busca. Es de solo lectura: se cambia recargando la lista.
 */
function TarjetaInstock({ resumen }: { resumen: InstockResumen | null }) {
  if (!resumen) return null;
  const marcas = Object.entries(resumen.por_marca).sort((a, b) => b[1] - a[1]);
  return (
    <Card className="border-amber-200 bg-amber-50/40">
      <CardContent className="py-3">
        <div className="flex flex-wrap items-center gap-2">
          <Wrench size={15} className="shrink-0 text-amber-700" />
          <span className="font-semibold text-slate-900">InStock · repuestos de pauta</span>
          <Badge className="bg-emerald-50 text-emerald-700">
            mantener {formatoNumero(resumen.minimo)} u
          </Badge>
          <Badge className="bg-slate-100 text-slate-600">permanente</Badge>
          {!resumen.activo && (
            <Badge className="bg-amber-100 text-amber-800">sin cargar</Badge>
          )}
          <span className="ml-auto inline-flex shrink-0 items-center gap-1 text-[11px] text-slate-500">
            <Lock size={11} /> regla del sistema
          </span>
          <VerDetalle tipo="instock" id="instock" />
        </div>
        {resumen.activo ? (
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-600">
            <b>{formatoNumero(resumen.n_repuestos)} repuestos</b>
            {marcas.length > 0 && (
              <> ({marcas.map(([m, n]) => `${m} ${formatoNumero(n)}`).join(" · ")})</>
            )}{" "}
            de las pautas de mantención nunca bajan de{" "}
            {formatoNumero(resumen.minimo)} unidades en{" "}
            <b>{enumerar(resumen.sucursales)}</b>, las sucursales con taller. Si el
            stock, el tránsito y el sugerido no llegan a esa cifra, el sugerido se
            completa solo. Se revisa en cada consulta, no en una fecha.
          </p>
        ) : (
          <p className="mt-1.5 text-[13px] leading-relaxed text-slate-600">
            Todavía no hay repuestos cargados, así que la regla no está pidiendo nada.
            La lista se genera desde las pautas del fabricante y se carga con el job{" "}
            <code className="rounded bg-slate-100 px-1 text-[12px]">cargar_instock</code>.
          </p>
        )}
      </CardContent>
    </Card>
  );
}

function SeccionUnicas({
  items,
  onEliminar,
  onEliminarLote,
}: {
  items: SugerenciaManual[] | null;
  onEliminar: (id: string) => void;
  onEliminarLote: (loteId: string, n: number) => void;
}) {
  // Separamos en lotes (cargas masivas) e individuales para mostrarlos
  // como cards distintas: el lote se colapsa para no inundar la pantalla
  // con miles de filas.
  const { lotes, individuales } = useMemo(() => {
    const lotesMap = new Map<string, SugerenciaManual[]>();
    const ind: SugerenciaManual[] = [];
    for (const s of items ?? []) {
      if (s.lote_id) {
        const arr = lotesMap.get(s.lote_id) ?? [];
        arr.push(s);
        lotesMap.set(s.lote_id, arr);
      } else {
        ind.push(s);
      }
    }
    // Lote más reciente primero (creado_en del primer item).
    const lotesOrdenados = Array.from(lotesMap.entries()).sort((a, b) => {
      const ta = new Date(a[1][0]?.creado_en ?? 0).getTime();
      const tb = new Date(b[1][0]?.creado_en ?? 0).getTime();
      return tb - ta;
    });
    return { lotes: lotesOrdenados, individuales: ind };
  }, [items]);

  if (items === null) return <p className="text-slate-500">Cargando…</p>;
  if (items.length === 0)
    return (
      <Card>
        <CardContent className="text-[13px] text-slate-500">
          No hay sugerencias únicas vigentes. Para crear una, andá al dashboard, hacé
          click en “Sugerencia manual” y <b>no</b> marqués “Repetir periódicamente”.
        </CardContent>
      </Card>
    );
  return (
    <div className="space-y-2">
      {lotes.map(([loteId, filas]) => (
        <LoteCard
          key={loteId}
          loteId={loteId}
          filas={filas}
          onEliminarLote={onEliminarLote}
          onEliminarUna={onEliminar}
        />
      ))}
      {individuales.map((s) => (
        <Card key={s.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">{s.producto}</span>
                <span className="text-[13px] text-slate-500">·</span>
                <span className="text-[13px] text-slate-600">
                  {s.nombre_sucursal ?? s.sucursal_id}
                </span>
                <Badge className="bg-emerald-50 text-emerald-700">
                  +{formatoNumero(s.unidades)} u
                </Badge>
                <EtiquetaTipo m={s} />
                {s.expira_en && <BadgeVencimiento expiraEn={s.expira_en} />}
              </div>
              <FichaProducto m={s} />
              <p className="mt-1 text-[12px] text-slate-500">
                {s.creado_por && <>{s.creado_por} · </>}
                {formatoFechaHora(s.creado_en)}
                {s.motivo && <> · {s.motivo}</>}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <VerDetalle tipo="unica" id={s.id} />
              <button
                onClick={() => onEliminar(s.id)}
                className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                aria-label="Eliminar sugerencia"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

const EXPANDIDO_MAX = 100;

function LoteCard({
  loteId,
  filas,
  onEliminarLote,
  onEliminarUna,
}: {
  loteId: string;
  filas: SugerenciaManual[];
  onEliminarLote: (loteId: string, n: number) => void;
  onEliminarUna: (id: string) => void;
}) {
  const [expandido, setExpandido] = useState(false);
  const primera = filas[0];
  const totalUnidades = filas.reduce((acc, f) => acc + (f.unidades ?? 0), 0);
  const filasVisibles = expandido ? filas.slice(0, EXPANDIDO_MAX) : [];
  const ocultas = expandido ? filas.length - filasVisibles.length : 0;

  return (
    <Card>
      <CardContent className="py-3">
        <div className="flex flex-wrap items-start justify-between gap-3">
          <button
            onClick={() => setExpandido((v) => !v)}
            className="flex min-w-0 flex-1 items-start gap-2 text-left"
          >
            <span className="mt-0.5 text-slate-400">
              {expandido ? <ChevronDown size={16} /> : <ChevronRight size={16} />}
            </span>
            <span className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <Layers size={14} className="text-brand" />
                <span className="font-semibold text-slate-900">Carga masiva</span>
                <Badge className="bg-brand-50 text-brand">
                  {formatoNumero(filas.length)} productos
                </Badge>
                <Badge className="bg-emerald-50 text-emerald-700">
                  +{formatoNumero(totalUnidades)} u en total
                </Badge>
                {primera && <EtiquetaTipoLote filas={filas} />}
                {primera?.expira_en && <BadgeVencimiento expiraEn={primera.expira_en} />}
              </div>
              <p className="mt-1 text-[12px] text-slate-500">
                {primera?.creado_por && <>{primera.creado_por} · </>}
                {primera?.creado_en && formatoFechaHora(primera.creado_en)}
                {primera?.motivo && <> · {primera.motivo}</>}
              </p>
            </span>
          </button>
          <div className="flex shrink-0 items-center gap-2">
            <VerDetalle tipo="lote" id={loteId} />
            <button
              onClick={() => onEliminarLote(loteId, filas.length)}
              className="flex items-center gap-1 rounded-md border border-red-200 bg-white px-3 py-1.5 text-[12px] font-medium text-red-600 hover:bg-red-50"
            >
              <Trash2 size={14} /> Eliminar las {formatoNumero(filas.length)}
            </button>
          </div>
        </div>

        {expandido && (
          <div className="mt-3 divide-y divide-slate-100 rounded-md border border-slate-200">
            {filasVisibles.map((s) => (
              <div
                key={s.id}
                className="flex items-center justify-between gap-2 px-3 py-2 text-[12.5px]"
              >
                <div className="min-w-0 flex-1">
                  <span className="font-medium text-slate-900">{s.producto}</span>
                  <span className="text-slate-400"> · </span>
                  <span className="text-slate-600">
                    {s.nombre_sucursal ?? s.sucursal_id}
                  </span>
                  <span className="text-slate-400"> · </span>
                  <span className="font-mono text-emerald-700">
                    +{formatoNumero(s.unidades)} u
                  </span>
                  {s.descripcion && (
                    <span className="block truncate text-[12px] text-slate-500">
                      {s.descripcion}
                    </span>
                  )}
                </div>
                <button
                  onClick={() => onEliminarUna(s.id)}
                  className="rounded p-1 text-slate-300 hover:bg-red-50 hover:text-red-600"
                  aria-label="Eliminar solo esta fila"
                  title="Eliminar solo esta fila"
                >
                  <Trash2 size={14} />
                </button>
              </div>
            ))}
            {ocultas > 0 && (
              <p className="px-3 py-2 text-center text-[11px] text-slate-500">
                Y {formatoNumero(ocultas)} más. Usa “Eliminar las {formatoNumero(filas.length)}”
                para borrarlas todas juntas.
              </p>
            )}
          </div>
        )}
      </CardContent>
    </Card>
  );
}

function SeccionRecurrentes({
  items,
  onEliminar,
}: {
  items: Recurrente[] | null;
  onEliminar: (id: string) => void;
}) {
  if (items === null) return <p className="text-slate-500">Cargando…</p>;
  if (items.length === 0)
    return (
      <Card>
        <CardContent className="text-[13px] text-slate-500">
          No hay recurrencias activas. Se crean desde el dashboard, marcando “Repetir
          periódicamente” en el modal de sugerencia manual.
        </CardContent>
      </Card>
    );
  return (
    <div className="space-y-2">
      {items.map((r) => (
        <Card key={r.id}>
          <CardContent className="flex flex-wrap items-center justify-between gap-3 py-3">
            <div className="min-w-0">
              <div className="flex flex-wrap items-center gap-2">
                <span className="font-semibold text-slate-900">{r.resumen}</span>
                <Badge className="bg-brand-50 text-brand">
                  {r.stock_objetivo
                    ? `mantener ${formatoNumero(r.stock_objetivo)} u`
                    : r.dias_inventario
                      ? `cubrir ${r.dias_inventario} días`
                      : `+${formatoNumero(r.unidades)} u`}
                </Badge>
                <Badge className="bg-slate-100 text-slate-600">
                  cada {r.cada_dias} días
                </Badge>
                <Badge className="bg-slate-100 text-slate-500">
                  {r.modo === "individual" ? "Individual" : "Por grupo"}
                </Badge>
              </div>
              <p className="mt-1 text-[12px] text-slate-500">
                Próxima: <b>{formatoFecha(r.proxima_ejecucion)}</b>
                {r.fecha_fin && <> · termina {formatoFecha(r.fecha_fin)}</>}
                {r.ultima_ejecucion && <> · última {formatoFecha(r.ultima_ejecucion)}</>}
                {r.motivo && <> · {r.motivo}</>}
              </p>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <VerDetalle tipo="recurrente" id={r.id} />
              <button
                onClick={() => onEliminar(r.id)}
                className="rounded-md p-1.5 text-slate-400 hover:bg-red-50 hover:text-red-600"
                aria-label="Eliminar recurrencia"
              >
                <Trash2 size={16} />
              </button>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}
