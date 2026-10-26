// Cliente del modulo Canal Digital (/api/canal-digital): reposicion semanal de la bodega 430.
import { mensajeError, req } from "./api-client";

export type EstadoProducto = "CLASIFICADO" | "NUEVO" | "SIN MOVIMIENTO";
export type ModoPolitica = "formula" | "contra_pedido" | "minimo_fijo";

export interface ClusterResumen {
  cluster: string;
  frecuencia: string;
  piezas: string;
  valor: string;
  productos: number;
  unidades_12m: number;
  pct_unidades: number;
  valor_12m: number;
  pct_valor: number;
  modo: ModoPolitica;
  nivel_servicio: number | null;
  z: number | null;
  minimo_fijo: number | null;
  productos_que_piden: number;
  unidades_sugeridas: number;
  sugerido_pesos: number;
}

export interface ValidacionCD {
  nombre: string;
  ok: boolean;
  detalle: string;
}

export interface AvisoCorrida {
  periodos: [string, string];
  semanas: [string, string];
  fecha_referencia: string;
  productos: number;
  sin_proveedor: number;
  ultimo_mes_con_ventas: string | null;
  ultimo_periodo_cargado: string | null;
  /** Meses cerrados que faltan cargar; 0 = al dia. */
  meses_sin_cargar: number | null;
  codigos_en_dos_grupos: number;
}

export interface ResumenCanalDigital {
  aviso: AvisoCorrida;
  estados: Record<EstadoProducto, number>;
  clusters: ClusterResumen[];
  totales: {
    productos: number;
    productos_que_piden: number;
    unidades_sugeridas: number;
    sugerido_pesos: number;
  };
  validaciones: ValidacionCD[];
  provisorio: string[];
}

export interface ProductoCanalDigital {
  producto: string;
  descripcion: string | null;
  codigos_vendidos: string;
  estado: EstadoProducto;
  cluster: string | null;
  frecuencia: string | null;
  piezas: string | null;
  valor: string | null;
  meses_con_venta: number;
  unidades_12m: number;
  valor_12m: number;
  primera_venta: string | null;
  modo: ModoPolitica | null;
  nivel_servicio: number | null;
  z: number | null;
  demanda_semanal: number;
  sigma_semanal: number;
  plazo_dias: number;
  plazo_semanas: number;
  plazo_origen: string;
  plazo_confianza: string;
  proveedor: string;
  stock_seguridad: number | null;
  nivel_objetivo: number | null;
  stock_disponible: number;
  stock_aparte: number;
  stock_cd: number;
  transito: number;
  transito_cualquier_destino: number;
  comprometido: string;
  posicion: number;
  necesidad_bruta: number;
  minimo_compra: number;
  multiplo: number;
  sugerido: number;
  costo_actual: number | null;
  sugerido_pesos: number;
  costo_respaldo: string;
  motivo: string;
  avisos: string[];
}

export interface ProductosCanalDigital {
  total: number;
  items: ProductoCanalDigital[];
  aviso: AvisoCorrida;
}

export interface PasoCanalDigital {
  numero: number;
  titulo: string;
  formula: string;
  numeros: string;
  resultado: string;
}

export interface FilaPoliticaCD {
  cluster: string;
  modo: ModoPolitica;
  nivel_servicio: number | null;
  z: number | null;
  minimo_fijo: number | null;
}

export interface PoliticaCanalDigital {
  bodega: string;
  modos: ModoPolitica[];
  problemas: string[];
  filas: FilaPoliticaCD[];
}

export interface FiltrosProductosCD {
  cluster?: string;
  estado?: string;
  q?: string;
  solo_pide?: boolean;
}

async function getJSON<T>(path: string, fallback: string): Promise<T> {
  const res = await req(path);
  if (!res.ok) throw new Error(await mensajeError(res, fallback));
  return res.json();
}

function consulta(bodega: string, f: FiltrosProductosCD = {}): URLSearchParams {
  const p = new URLSearchParams({ bodega });
  if (f.cluster) p.set("cluster", f.cluster);
  if (f.estado) p.set("estado", f.estado);
  if (f.q) p.set("q", f.q);
  if (f.solo_pide) p.set("solo_pide", "true");
  return p;
}

export const NOMBRE_MODO: Record<ModoPolitica, string> = {
  formula: "Fórmula",
  contra_pedido: "Contra pedido",
  minimo_fijo: "Mínimo fijo",
};

export const canalDigitalApi = {
  resumen(bodega = "430"): Promise<ResumenCanalDigital> {
    return getJSON(`/api/canal-digital/resumen?bodega=${encodeURIComponent(bodega)}`, "No se pudo calcular el resumen");
  },

  productos(bodega: string, f: FiltrosProductosCD): Promise<ProductosCanalDigital> {
    return getJSON(
      `/api/canal-digital/productos?${consulta(bodega, f).toString()}`,
      "No se pudieron cargar los productos"
    );
  },

  async pasoAPaso(producto: string, bodega = "430"): Promise<PasoCanalDigital[]> {
    const p = new URLSearchParams({ producto, bodega });
    const r = await getJSON<{ pasos: PasoCanalDigital[] }>(
      `/api/canal-digital/producto/paso-a-paso?${p.toString()}`,
      "No se pudo explicar el producto"
    );
    return r.pasos;
  },

  politica(bodega = "430"): Promise<PoliticaCanalDigital> {
    return getJSON(`/api/canal-digital/politica?bodega=${encodeURIComponent(bodega)}`, "No se pudo leer la política");
  },

  async guardarPolitica(bodega: string, filas: FilaPoliticaCD[]): Promise<PoliticaCanalDigital> {
    const res = await req(`/api/canal-digital/politica?bodega=${encodeURIComponent(bodega)}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ filas }),
    });
    if (!res.ok) {
      const cuerpo = await res.clone().json().catch(() => ({}));
      const problemas = (cuerpo as { detail?: { problemas?: string[] } })?.detail?.problemas;
      if (Array.isArray(problemas) && problemas.length) throw new Error(problemas.join("\n"));
      throw new Error(await mensajeError(res, "No se pudo guardar la política"));
    }
    return res.json();
  },

  async exportarCSV(bodega: string, f: FiltrosProductosCD): Promise<void> {
    const res = await req(`/api/canal-digital/productos/export-csv?${consulta(bodega, f).toString()}`);
    if (!res.ok) throw new Error(await mensajeError(res, "No se pudo generar el archivo"));
    const url = URL.createObjectURL(await res.blob());
    const a = document.createElement("a");
    a.href = url;
    a.download = `canal_digital_${bodega}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  },
};
