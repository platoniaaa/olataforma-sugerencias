"use client";

// TEMPORAL (solo vista previa): reemplaza la API por datos de ejemplo para poder mirar la
// vista del vendedor sin tocar producción. NO se commitea; se borra al terminar.
import type { ReactNode } from "react";
import { api } from "@/lib/api-client";

type P = {
  producto: string; glosa: string; familia: string; categoria: string | null; procedencia: string | null;
  precio: number; stock: number; reemplazo: string | null;
};

const P: P[] = [
  { producto: "19 SZ6Z3B437B", glosa: "TERMINAL DE DIRECCION EXTERIOR FOCUS", familia: "DIRECCION", categoria: "SUSPENSION", procedencia: "IMPORTADO", precio: 45000, stock: 7, reemplazo: "19 SZ6Z3B437C, 19 SZ6Z3B437D" },
  { producto: "19 SZ6Z3B437C", glosa: "TERMINAL DE DIRECCION EXTERIOR FOCUS (NUEVO)", familia: "DIRECCION", categoria: "SUSPENSION", procedencia: "IMPORTADO", precio: 52000, stock: 12, reemplazo: "19 SZ6Z3B437B, 19 SZ6Z3B437D" },
  { producto: "19 SZ6Z3B437D", glosa: "TERMINAL DE DIRECCION EXTERIOR FOCUS ALTERNATIVO", familia: "DIRECCION", categoria: "SUSPENSION", procedencia: "NACIONAL", precio: 38900, stock: 0, reemplazo: "19 SZ6Z3B437B, 19 SZ6Z3B437C" },
  { producto: "70 2723982", glosa: "FILTRO DE ACEITE", familia: "FILTROS", categoria: "MOTOR", procedencia: "NACIONAL", precio: 8500, stock: 0, reemplazo: null },
  { producto: "70 5876150170", glosa: "FILTRO DE AIRE MOTOR", familia: "FILTROS", categoria: "MOTOR", procedencia: "IMPORTADO", precio: 14990, stock: 41, reemplazo: null },
  { producto: "25 MB3Z19N619C", glosa: "MODULO DE CONTROL DE CLIMATIZACION CON UNA DESCRIPCION BASTANTE LARGA PARA PROBAR EL CORTE DEL TEXTO", familia: "ELECTRICO", categoria: "CLIMA", procedencia: "ORIGINAL", precio: 189990, stock: 2, reemplazo: "19 MB3Z19N619A" },
  { producto: "19 MB3Z19N619A", glosa: "MODULO DE CONTROL DE CLIMATIZACION", familia: "ELECTRICO", categoria: "CLIMA", procedencia: "ORIGINAL", precio: 204990, stock: 1, reemplazo: "25 MB3Z19N619C" },
  { producto: "31 PF0A8001", glosa: "PASTILLAS DE FRENO DELANTERAS", familia: "FRENOS", categoria: "FRENOS", procedencia: "IMPORTADO", precio: 32990, stock: 26, reemplazo: null },
  { producto: "31 AM4400X", glosa: "AMORTIGUADOR DELANTERO IZQUIERDO", familia: "SUSPENSION", categoria: "SUSPENSION", procedencia: "NACIONAL", precio: 67990, stock: 5, reemplazo: null },
  { producto: "44 BJ0031", glosa: "BUJIA DE ENCENDIDO IRIDIUM", familia: "ENCENDIDO", categoria: "MOTOR", procedencia: "IMPORTADO", precio: 9990, stock: 88, reemplazo: null },
  { producto: "44 CD7712", glosa: "CORREA DE DISTRIBUCION", familia: "MOTOR", categoria: "MOTOR", procedencia: "IMPORTADO", precio: 29990, stock: 0, reemplazo: null },
  { producto: "60 BT12V60", glosa: "BATERIA 12V 60AH", familia: "ELECTRICO", categoria: "BATERIAS", procedencia: "NACIONAL", precio: 79990, stock: 9, reemplazo: null },
  { producto: "60 ESC2400", glosa: "ESCOBILLA LIMPIAPARABRISAS 24 PULGADAS", familia: "ACCESORIOS", categoria: "CARROCERIA", procedencia: "NACIONAL", precio: 6990, stock: 33, reemplazo: null },
  { producto: "70 ACM5W30", glosa: "ACEITE MOTOR 5W30 SINTETICO 1 LITRO", familia: "LUBRICANTES", categoria: "LUBRICANTES", procedencia: "IMPORTADO", precio: 11990, stock: 120, reemplazo: null },
];

const SUC = ["CURICO", "LINDEROS", "TALCA", "RANCAGUA", "CHILLAN", "PLACILLA"];
const MESES = ["202511", "202512", "202601", "202602", "202603", "202604", "202605", "202606", "202607", "202608", "202609", "202610"];
const norm = (s: string) => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const semilla = (s: string) => Array.from(s).reduce((a, c) => (a * 31 + c.charCodeAt(0)) % 9973, 7);
const serie = (cod: string) => MESES.map((m, i) => ({ mes: m, cantidad: (semilla(cod + m) % 7) + (i % 3) }));
const fila = (p: P) => ({
  producto: p.producto, glosa: p.glosa, familia: p.familia, subfamilia: null, procedencia: p.procedencia,
  categoria: p.categoria, unidad: "UN", precio: p.precio, stock_total: p.stock, reemplazo: p.reemplazo,
});
const buscar = (cod: string) => P.find((p) => p.producto === cod) ?? P[0];
const espera = <T,>(v: T, ms = 250) => new Promise<T>((r) => setTimeout(() => r(v), ms));

Object.assign(api, {
  consultaProductos: async (f: { q?: string; con_stock?: boolean }) => {
    const q = norm(f.q ?? "");
    const lista = P.filter((p) => (!q || norm(p.producto).includes(q) || norm(p.glosa).includes(q)) && (!f.con_stock || p.stock > 0));
    return espera({ items: lista.map(fila), total: lista.length, page: 1, limit: 50 });
  },
  consultaDetalle: async (cod: string) => {
    const p = buscar(cod);
    // El stock se reparte entre sucursales de forma estable.
    let resto = p.stock;
    const stock_por_sucursal = SUC.map((s, i) => {
      const n = i === SUC.length - 1 ? resto : Math.min(resto, semilla(cod + s) % (Math.max(2, Math.ceil(p.stock / 2))));
      resto -= n;
      return { bodega: s, sucursal_id: s, stock: n, origen: null };
    });
    return espera({
      ...fila(p), sub_categoria: null, tipo_producto: null, sub_modelo: "FOCUS", cilindrada: "2.0",
      combustible: "Bencina", anio: "2015", stock_por_sucursal,
      reemplazo_ford: p.producto === "19 SZ6Z3B437B"
        ? { producto: p.producto, reemplazado_por: "19 SZ6Z3B437C", reemplazado_por_ford: "SZ6Z/3B437/C/", cadena: "SZ6Z/3B437/B/ > SZ6Z/3B437/C/", reemplaza_a: [], sucesor_confirmado: true, agrupado: true, aviso: null, extraido_en: "2026-10-26T09:00:00" }
        : null,
    });
  },
  consultaSucursales: async (cod: string) => espera({ producto: cod, sucursales: SUC.slice(0, 4).sort() }),
  consultaVentas: async (cod: string, suc?: string) => {
    const s = serie(cod);
    // La venta de una sucursal: una parte estable del total del producto.
    const ms = suc ? s.map((x) => ({ mes: x.mes, cantidad: Math.max(0, Math.round(x.cantidad * (0.25 + (semilla(suc) % 30) / 100))) })) : [];
    return espera({
      producto: cod, sucursal_id: suc ?? "", total_general: s.reduce((a, x) => a + x.cantidad, 0),
      total_sucursal: ms.reduce((a, x) => a + x.cantidad, 0), meses_sucursal: ms, meses_general: s,
    });
  },
  consultaGrupoVentas: async (cod: string, suc?: string) => {
    const p = buscar(cod);
    const f = suc ? 0.25 + (semilla(suc) % 30) / 100 : 1;
    const codigos = [p.producto, ...(p.reemplazo ? p.reemplazo.split(",").map((x) => x.trim()) : [])];
    if (codigos.length < 2) return espera({ producto: cod, miembros: [], meses: [] });
    const series = codigos.map((c) => ({ c, s: serie(c).map((x) => ({ ...x, cantidad: Math.round(x.cantidad * f) })) }));
    return espera({
      producto: cod, vigente: codigos[1], sucursal: suc ?? null,
      total_venta_12m: series.reduce((a, { s }) => a + s.reduce((b, x) => b + x.cantidad, 0), 0),
      total_stock: codigos.reduce((a, c) => a + Math.round(buscar(c).stock * f), 0),
      miembros: series.map(({ c, s }, i) => ({
        producto: c, es_vigente: i === 1, sku_ford: null, venta_12m: s.reduce((a, x) => a + x.cantidad, 0),
        venta_total: s.reduce((a, x) => a + x.cantidad, 0) + 20, ultimo_mes_con_venta: "202610",
        stock: Math.round(buscar(c).stock * f), cuenta_en_el_total: true, motivo_fuera: null,
      })),
      meses: MESES.map((m, k) => Object.fromEntries([["mes", m], ...series.map(({ c, s }) => [c, s[k].cantidad])])),
    });
  },
});

export default function LayoutPrevia({ children }: { children: ReactNode }) {
  return (
    <>
      <div className="mb-3 rounded-md border border-amber-300 bg-amber-50 px-3 py-2 text-[12.5px] text-amber-900">
        <b>VISTA PREVIA</b> con datos de ejemplo. Nada de esto es real ni se guarda.
      </div>
      {children}
    </>
  );
}
