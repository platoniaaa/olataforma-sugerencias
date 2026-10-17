/**
 * Fuentes de datos (/cargar/fuentes): de donde lee el motor cada archivo.
 *
 * Lo que estos tests cuidan:
 *
 * 1. Que la pantalla sea solo de admin: el que no es admin vuelve al inicio, y un
 *    403 del servidor se muestra como falta de permiso.
 * 2. Que el semaforo se vea con su etiqueta y su texto (el color nunca va solo),
 *    con la franja "En prueba" y "El PC titular no corrió hoy".
 * 3. Que el editor no guarde sin nota, mande solo lo que cambio con la version de
 *    base, muestre la vista previa (conflictos en rojo), esconda lo avanzado y
 *    muestre el 409 de otro admin.
 * 4. Que `lib/fuentes-datos.ts` llame a las rutas correctas.
 */
import "@testing-library/jest-dom/vitest";
import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import FuentesDatosPage from "@/app/cargar/fuentes/page";
import { EditorCarpeta } from "@/components/fuentes/editor-carpeta";
import { EditorFuente } from "@/components/fuentes/editor-fuente";
import {
  archivosEnUbicacion,
  cambiosFuente,
  cuando,
  fechaHora,
  formDesde,
  fuentesApi,
  type ArchivoCarpeta,
  type Corrida,
  type FuenteCfg,
  type FuenteDetalle,
  type FuentePanel,
  type Panel,
} from "@/lib/fuentes-datos";

const mocks = vi.hoisted(() => {
  const replace = vi.fn();
  // El mismo objeto en cada render, como el router real: uno nuevo por render
  // dispararia el efecto de carga en un ciclo sin fin.
  return { req: vi.fn(), replace, router: { replace, push: vi.fn() }, esAdmin: true };
});

// El mismo texto que `MENSAJE_SIN_SERVIDOR` de lib/api-client.ts.
const SIN_SERVIDOR = "No se pudo conectar con el servidor. Puede estar reiniciándose: espera un minuto y vuelve a intentar.";

vi.mock("@/lib/api-client", () => ({
  req: mocks.req,
  // Igual que el real: el `detail` en texto del servidor, o el texto por defecto.
  mensajeError: async (res: Response, fallback: string) => {
    const b = (await res.json().catch(() => ({}))) as { detail?: unknown };
    return typeof b.detail === "string" ? b.detail : fallback;
  },
  MENSAJE_SIN_SERVIDOR: "No se pudo conectar con el servidor. Puede estar reiniciándose: espera un minuto y vuelve a intentar.",
}));

vi.mock("@/lib/auth", () => ({ getEsAdmin: () => mocks.esAdmin }));

vi.mock("next/navigation", () => ({ useRouter: () => mocks.router }));

const AHORA = "2026-10-16T12:00:00-03:00";

function respuesta(cuerpo: unknown, status = 200): Response {
  return new Response(JSON.stringify(cuerpo), { status, headers: { "Content-Type": "application/json" } });
}

/** `req` falso: responde segun "METODO ruta" (la ruta sin el query string). */
function servidor(rutas: Record<string, unknown | ((init?: RequestInit) => Response)>) {
  mocks.req.mockImplementation(async (path: string, init?: RequestInit) => {
    const clave = `${init?.method ?? "GET"} ${path.split("?")[0]}`;
    const r = rutas[clave];
    if (r === undefined) return respuesta({ detail: `sin respuesta para ${clave}` }, 404);
    return typeof r === "function" ? (r as (i?: RequestInit) => Response)(init) : respuesta(r);
  });
}

function fuente(over: Partial<FuentePanel>): FuentePanel {
  return {
    clave: "x", nombre: "X", nivel: "verde", etiqueta: "Al día", texto: "", regla: "al_dia", alertas: [],
    hecho: "encontrado", archivo: null, archivos: [], modificado_en: null, edad_dias_habiles: null, filas: null,
    carpeta: null, carpeta_nombre: null, obligatoria: false, frecuencia_dias: 2, al_vencer: "frena", activa: true,
    prueba: null, dato_de: null,
    ...over,
  };
}

const PANEL: Panel = {
  modo: "prueba",
  modo_texto: "En prueba",
  version: 4,
  pc_titular: "PC-ABAST-01",
  pc_titular_alias: "PC de Abastecimiento",
  ahora: AHORA,
  franja: {
    nivel: "rojo",
    ultima_corrida: {
      id: "c1", pc: "PC-ABAST-01", alias: "PC de Abastecimiento", tipo: "oficial", titular: true, publico: true,
      iniciada_en: "2026-10-15T12:30:00Z", terminada_en: "2026-10-15T12:58:00Z", duracion_min: 28, resultado: "ok",
      resultado_texto: "Publicó", motivo_texto: null, config_origen: "env", config_version: null,
      resolucion: "env", modo_config: "prueba", avisos: [], version_motor: null, resumen: {},
    },
    alertas: [{
      nivel: "rojo", etiqueta: "El PC titular no corrió hoy", regla: "titular_no_corrio",
      texto: "El PC de Abastecimiento no corre desde ayer a las 09:30. Revisa que esté prendido y con la sesión abierta.",
    }],
  },
  corrida_id: "c1",
  dato_de_corrida: "Dato de la corrida del 15-10 a las 09:30",
  fuentes: [
    fuente({
      clave: "stock_bodegas_frontera", nombre: "Stock bodegas Frontera", nivel: "rojo", etiqueta: "Vencido", regla: "vencido",
      obligatoria: true, dato_de: "Dato de la corrida del 15-10 a las 09:30",
      texto: "Vencido: el stock de Frontera tiene 3 días hábiles y se espera cada 2. Mientras siga así, el sugerido no se publica.",
    }),
    fuente({
      clave: "ventas_frontera", nombre: "Ventas Frontera", nivel: "amarillo", etiqueta: "Atrasado, no frena", regla: "atrasado",
      texto: "Atrasado: vtas frontera.xlsx tiene 62 días hábiles y se espera cada 35. No frena la publicación.",
    }),
    fuente({
      clave: "precios_ford", nombre: "Precios Ford", nivel: "gris", etiqueta: "Sin datos", regla: "sin_datos",
      texto: "Todavía no hay una corrida que haya revisado esta fuente.",
    }),
    fuente({
      clave: "stock_bodegas", nombre: "Stock bodegas Curifor", nivel: "verde", etiqueta: "Al día", regla: "al_dia",
      texto: "Al día: Stock bodegas.xlsx, de hoy a las 09:34, 19.883 filas.", archivo: "Stock bodegas.xlsx",
      modificado_en: "2026-10-16T09:34:00-03:00", filas: 19883, carpeta_nombre: "Data BI › Datos",
      prueba: { resultado: "coincide", archivo: "Stock bodegas.xlsx", texto: "La configuración de la plataforma toma el mismo archivo.", frenaria: false },
    }),
  ],
  reconoce: [],
  carpetas_por_pc: [{
    pc: "PC-ABAST-01", alias: "PC de Abastecimiento", es_titular: true, corrida_id: "c1", tipo: "oficial",
    iniciada_en: "2026-10-15T12:30:00Z",
    carpetas: [
      { clave: "bases_de_datos", nombre: "Bases de datos", tipo: "onedrive", ruta_portable: "%OneDriveCommercial%\\Documentos\\Desarrollos\\Bases de datos", metodo: "onedrive", existe: true, archivos: 35, truncado: false },
      // El motor resuelve la carpeta de SharePoint por su acceso directo: metodo "atajo".
      { clave: "databi_datos", nombre: "Data BI › Datos (SharePoint del equipo)", tipo: "sharepoint", ruta_portable: "%OneDriveCommercial%\\Abastecimiento y Logística-Data BI - Datos", metodo: "atajo", existe: true, archivos: 16, truncado: false },
    ],
  }],
  activacion: {
    puede_activar: false, corridas_necesarias: 2, corridas_en_verde: 0,
    motivo: "Para activar hacen falta 2 corridas oficiales seguidas del PC titular en verde, y hay 0.",
  },
  sembrar_desde: [],
};

const CFG: FuenteCfg = {
  clave: "stock_bodegas", nombre: "Stock bodegas Curifor",
  ubicaciones: [{ carpeta: "bases_de_datos", subcarpeta: "stock", recursiva: false }],
  modo: "mas_reciente", nombre_archivo: null, incluye: ["*stock*bodega*"], excluye: ["*frontera*"],
  extensiones: [".xlsx", ".xlsm", ".csv"], frecuencia_dias: 2, al_vencer: "frena", obligatoria: true, activa: true,
  diferencia_esperada: false, hoja: null, fila_encabezado: null,
};

const DETALLE: FuenteDetalle = {
  clave: "stock_bodegas", nombre: "Stock bodegas Curifor", uso: "lee", modo: "prueba", version: 4, config: CFG,
  catalogo: { uso: "lee", requerida: true, modos: ["archivo_exacto", "mas_reciente"], frecuencia_max: 5, al_vencer_fijo: "frena", efecto_si_falta: "Sin stock el motor no calcula." },
  bloqueos: {
    obligatoria: "Sin esta fuente el motor no calcula: tiene que ser obligatoria.",
    activa: "Sin esta fuente el motor no calcula: no se puede desactivar.",
    frecuencia_dias: "El motor fija un plazo máximo de 5 días hábiles: con un dato más viejo el sugerido sale mal.",
    al_vencer: "El motor exige que esta fuente frene la publicación si se atrasa.",
  },
  hoja_texto: "Automático (detectado: hoja 'Hoja1', fila 1)",
  estado: null, corridas: [], competencia: [], descartados: [], versiones: [],
};

const ARCHIVO: ArchivoCarpeta = {
  ruta_relativa: "stock/Stock bodegas.xlsx", nombre: "Stock bodegas.xlsx", subcarpeta: "stock", tamano: 2_100_000,
  modificado_en: "2026-10-16T09:34:00-03:00", onedrive: "local", fuente: "stock_bodegas", elegido: true,
  patron_propuesto: "stock bodegas.*",
};

const LISTADO = {
  clave: "bases_de_datos", nombre: "Bases de datos", pc: "PC-ABAST-01", alias: null, corrida_id: "c1",
  iniciada_en: "2026-10-16T12:30:00Z", existe: true, truncado: false, subcarpetas: ["stock", "Ventas"], archivos: [ARCHIVO],
};

const VISTA = {
  elegiria: { archivos: [], candidatos: 1, texto: "Con este cambio el motor tomaría Stock bodegas.xlsx (modificado hoy a las 09:34)." },
  hoy_toma: { archivos: [], candidatos: 1, texto: "Hoy toma Stock bodegas.xlsx (modificado hoy a las 09:34)." },
  conflictos: [] as string[],
  avisos: [] as string[],
  listado: { pc: "PC-ABAST-01", alias: null, corrida_id: "c1", iniciada_en: "2026-10-16T12:30:00Z" },
};

// Con llaves: si beforeEach devuelve una funcion, vitest la llama al terminar la
// prueba como limpieza, y mockReset() devuelve el propio mock.
beforeEach(() => {
  mocks.req.mockReset();
  mocks.replace.mockReset();
  mocks.esAdmin = true;
});

describe("acceso", () => {
  it("al que no es admin lo manda al inicio sin pedir nada", async () => {
    mocks.esAdmin = false;
    servidor({});
    render(<FuentesDatosPage />);
    await waitFor(() => expect(mocks.replace).toHaveBeenCalledWith("/"));
    expect(mocks.req).not.toHaveBeenCalled();
  });

  it("un 403 del servidor se muestra como falta de permiso", async () => {
    servidor({
      "GET /api/admin/fuentes": () => respuesta({ detail: "Solo administradores" }, 403),
      "GET /api/admin/fuentes/config": () => respuesta({ detail: "Solo administradores" }, 403),
    });
    render(<FuentesDatosPage />);
    expect(await screen.findByText(/No tienes permiso para ver Fuentes de datos/)).toBeInTheDocument();
  });
});

describe("panel", () => {
  it("muestra cada color con su etiqueta y su texto, la franja en prueba y que el titular no corrió", async () => {
    servidor({ "GET /api/admin/fuentes": PANEL, "GET /api/admin/fuentes/config": { modo: "prueba", carpetas: [], fuentes: [] } });
    render(<FuentesDatosPage />);

    const franja = await screen.findByRole("region", { name: "Estado general" });
    expect(within(franja).getByText("En prueba")).toBeInTheDocument();
    expect(within(franja).getByText("El PC titular no corrió hoy")).toBeInTheDocument();
    expect(within(franja).getByText(/no corre desde ayer a las 09:30/)).toBeInTheDocument();
    expect(within(franja).getByText("Publicó")).toBeInTheDocument();
    // Activar sigue apagado hasta tener las corridas en verde.
    expect(within(franja).getByRole("button", { name: "Activar" })).toBeDisabled();
    expect(within(franja).getByText(/0 de 2 corridas diarias seguidas en verde/)).toBeInTheDocument();

    const rojo = screen.getByTestId("fuente-stock_bodegas_frontera");
    expect(within(rojo).getByText("Vencido")).toBeInTheDocument();
    expect(within(rojo).getByText(/se espera cada 2/)).toBeInTheDocument();
    expect(within(rojo).getByText("Dato de la corrida del 15-10 a las 09:30")).toBeInTheDocument();
    expect(within(screen.getByTestId("fuente-ventas_frontera")).getByText("Atrasado, no frena")).toBeInTheDocument();
    expect(within(screen.getByTestId("fuente-precios_ford")).getByText("Sin datos")).toBeInTheDocument();

    const verde = screen.getByTestId("fuente-stock_bodegas");
    expect(within(verde).getByText("Al día")).toBeInTheDocument();
    expect(within(verde).getByText("Al día: Stock bodegas.xlsx, de hoy a las 09:34, 19.883 filas.")).toBeInTheDocument();
    expect(within(verde).getByText("hoy a las 09:34")).toBeInTheDocument();
    expect(within(verde).getByText("16-10-2026 09:34")).toBeInTheDocument();
    expect(within(verde).getByText(/Prueba: Coincide/)).toBeInTheDocument();

    // De la peor a la mejor, como las manda el servidor.
    const orden = screen.getAllByTestId(/^fuente-/).map((el) => el.dataset.testid);
    expect(orden).toEqual(["fuente-stock_bodegas_frontera", "fuente-ventas_frontera", "fuente-precios_ford", "fuente-stock_bodegas"]);

    // Las carpetas por PC muestran la ruta portable, no la del usuario de Windows.
    expect(screen.getByText("%OneDriveCommercial%\\Documentos\\Desarrollos\\Bases de datos")).toBeInTheDocument();
    // Como resolvio el motor cada carpeta, en palabras y no con su clave interna.
    expect(screen.getByText(/16 archivos · acceso directo a SharePoint/)).toBeInTheDocument();
    expect(screen.queryByText(/· atajo/)).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Cargar datos/ })).toHaveAttribute("href", "/cargar");
  });

  it("sin configurar ofrece usar la configuración de un PC como punto de partida", async () => {
    servidor({
      "GET /api/admin/fuentes": {
        ...PANEL, modo: "sin_configurar", modo_texto: "Sin configurar", version: null,
        sembrar_desde: [{ corrida_id: "c-probar", pc: "PC-ABAST-01", alias: null, tipo: "probar", iniciada_en: "2026-10-16T14:00:00Z" }],
      },
      "GET /api/admin/fuentes/config": { modo: "sin_configurar" },
      "POST /api/admin/fuentes/sembrar": { version: 1, modo: "prueba", hash: "h", claves_cambiadas: ["modo"], avisos: [] },
    });
    render(<FuentesDatosPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Usar la configuración del PC PC-ABAST-01 como punto de partida" }));
    fireEvent.click(screen.getByRole("button", { name: "Usar como punto de partida" }));
    await waitFor(() => expect(mocks.req).toHaveBeenCalledWith("/api/admin/fuentes/sembrar", expect.objectContaining({ method: "POST" })));
    const init = mocks.req.mock.calls.find((c) => c[0] === "/api/admin/fuentes/sembrar")![1];
    expect(JSON.parse(init.body)).toEqual({ corrida_id: "c-probar" });
  });

  const cuerpoDe = (ruta: string) => JSON.parse(mocks.req.mock.calls.find((c) => c[0] === ruta)![1].body);

  it("activar pide nota y manda el modo con la versión de base", async () => {
    servidor({
      "GET /api/admin/fuentes": { ...PANEL, activacion: { puede_activar: true, motivo: null, corridas_necesarias: 2, corridas_en_verde: 2 } },
      "GET /api/admin/fuentes/config": { modo: "prueba" },
      "POST /api/admin/fuentes/modo": { version: 5, modo: "activa", hash: "h", claves_cambiadas: ["modo"], avisos: [] },
    });
    render(<FuentesDatosPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Activar" }));
    const dialogo = screen.getByRole("dialog", { name: "Activar la configuración" });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Activar" }));
    expect(await within(dialogo).findByText(/Escribe una nota/)).toBeInTheDocument();
    fireEvent.change(within(dialogo).getByLabelText("Nota"), { target: { value: "2 de 2 en verde" } });
    fireEvent.click(within(dialogo).getByRole("button", { name: "Activar" }));
    await waitFor(() => expect(cuerpoDe("/api/admin/fuentes/modo")).toEqual({ modo: "activa", nota: "2 de 2 en verde", base_version: 4 }));
    expect(await screen.findByText(/Activada: desde la próxima corrida/)).toBeInTheDocument();
  });

  it("el detalle muestra las versiones y vuelve a una con su clave", async () => {
    servidor({
      "GET /api/admin/fuentes": PANEL,
      "GET /api/admin/fuentes/config": { modo: "prueba", carpetas: [], fuentes: [] },
      "GET /api/admin/fuentes/stock_bodegas": {
        ...DETALLE,
        estado: PANEL.fuentes[3],
        descartados: [{ nombre: "Motorcraft 2026.xlsx", motivo: "no tiene forma de respaldo de venta", nuevo: true }],
        versiones: [
          { version: 3, creado_por: "admin@ejemplo.cl", creado_en: "2026-10-16T13:00:00Z", nota: "Ensayo", revierte_a: null, claves_cambiadas: ["stock_bodegas"] },
          { version: 1, creado_por: "admin@ejemplo.cl", creado_en: "2026-10-14T13:00:00Z", nota: "Siembra", revierte_a: null, claves_cambiadas: ["stock_bodegas"] },
        ],
      },
      "POST /api/admin/fuentes/revertir/1": { version: 5, modo: "prueba", hash: "h", claves_cambiadas: ["stock_bodegas"], avisos: [] },
    });
    render(<FuentesDatosPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Stock bodegas Curifor" }));
    const detalle = await screen.findByRole("dialog", { name: "Stock bodegas Curifor" });
    expect(await within(detalle).findByText("Motorcraft 2026.xlsx")).toBeInTheDocument();
    expect(within(detalle).getByText("Nuevo")).toBeInTheDocument();
    // La versión de hoy no se ofrece: volver a ella no cambia nada.
    const botones = within(detalle).getAllByRole("button", { name: "Volver a esta versión" });
    expect(botones).toHaveLength(1);
    fireEvent.click(botones[0]);
    const confirmar = screen.getByRole("dialog", { name: "Volver a la versión 1" });
    fireEvent.click(within(confirmar).getByRole("button", { name: "Volver a esta versión" }));
    await waitFor(() => expect(cuerpoDe("/api/admin/fuentes/revertir/1")).toEqual({ base_version: 4, clave: "stock_bodegas" }));
  });

  it("el error exacto de lectura sale en las últimas corridas del detalle", async () => {
    const mensaje = "PermissionError: [Errno 13] Permission denied: 'Stock bodegas.xlsx'";
    servidor({
      "GET /api/admin/fuentes": PANEL,
      "GET /api/admin/fuentes/config": { modo: "prueba", carpetas: [], fuentes: [] },
      "GET /api/admin/fuentes/stock_bodegas": {
        ...DETALLE,
        corridas: [{
          corrida_id: "c1", pc: "PC-ABAST-01", alias: null, tipo: "oficial", iniciada_en: "2026-10-16T12:30:00Z",
          resultado: "ok", hecho: "error_lectura", nivel: "rojo", etiqueta: "No se pudo leer", archivos: [],
          filas: null, hoja_leida: null, prueba: null, mensaje,
        }],
      },
    });
    render(<FuentesDatosPage />);
    fireEvent.click(await screen.findByRole("button", { name: "Stock bodegas Curifor" }));
    const detalle = await screen.findByRole("dialog", { name: "Stock bodegas Curifor" });
    expect(await within(detalle).findByText(mensaje)).toBeInTheDocument();
  });

  it("con la API caída dice qué pasó, no 'Failed to fetch'", async () => {
    mocks.req.mockRejectedValue(new TypeError("Failed to fetch"));
    render(<FuentesDatosPage />);
    const alerta = await screen.findByRole("alert");
    expect(alerta).toHaveTextContent(SIN_SERVIDOR);
    expect(alerta).not.toHaveTextContent(/failed to fetch/i);
  });

  const conCorrida = (corrida: Partial<Corrida>, franja: Partial<Panel["franja"]> = {}): Panel => ({
    ...PANEL,
    franja: { ...PANEL.franja, alertas: [], nivel: "verde", ...franja, ultima_corrida: { ...PANEL.franja.ultima_corrida!, ...corrida } },
  });

  it("dice que el motor leyó con la configuración del PC cuando no estaba activa", async () => {
    // En prueba la plataforma responde (config_origen=plataforma), pero el motor lee con el .env.
    servidor({
      "GET /api/admin/fuentes": conCorrida({ config_origen: "plataforma", resolucion: "env", modo_config: "prueba" }),
      "GET /api/admin/fuentes/config": { modo: "prueba" },
    });
    render(<FuentesDatosPage />);
    const franja = await screen.findByRole("region", { name: "Estado general" });
    expect(within(franja).getByText(/leyó con la configuración escrita en el PC y comparó con la de esta pantalla/)).toBeInTheDocument();
    expect(within(franja).queryByText(/usó la configuración de esta pantalla/)).not.toBeInTheDocument();
  });

  it("sin configurar no dice que comparó con esta pantalla", async () => {
    servidor({
      "GET /api/admin/fuentes": {
        ...conCorrida({ config_origen: "plataforma", resolucion: "env", modo_config: "sin_configurar" }),
        modo: "sin_configurar", modo_texto: "Sin configurar", version: null,
      },
      "GET /api/admin/fuentes/config": { modo: "sin_configurar" },
    });
    render(<FuentesDatosPage />);
    const franja = await screen.findByRole("region", { name: "Estado general" });
    expect(within(franja).getByText(/leyó con la configuración escrita en el PC$/)).toBeInTheDocument();
    expect(within(franja).queryByText(/configuración de esta pantalla/)).not.toBeInTheDocument();
  });

  it("en activa dice que usó la configuración de esta pantalla", async () => {
    servidor({
      "GET /api/admin/fuentes": {
        ...conCorrida({ config_origen: "plataforma", resolucion: "plataforma", modo_config: "activa" }),
        modo: "activa", modo_texto: "Activa",
      },
      "GET /api/admin/fuentes/config": { modo: "activa" },
    });
    render(<FuentesDatosPage />);
    const franja = await screen.findByRole("region", { name: "Estado general" });
    expect(within(franja).getByText(/usó la configuración de esta pantalla/)).toBeInTheDocument();
  });

  it("una corrida que no publicó no dice 'Sin alertas.' y se ve en rojo", async () => {
    servidor({
      "GET /api/admin/fuentes": conCorrida({
        resultado: "frenada", resultado_texto: "Frenada: no publicó", publico: false,
        motivo_texto: "No se publicó: falta un archivo obligatorio o hay uno vencido. Revisa las fuentes en rojo.",
      }),
      "GET /api/admin/fuentes/config": { modo: "prueba" },
    });
    render(<FuentesDatosPage />);
    const franja = await screen.findByRole("region", { name: "Estado general" });
    expect(within(franja).getByText("Frenada: no publicó")).toBeInTheDocument();
    expect(within(franja).queryByText("Sin alertas.")).not.toBeInTheDocument();
    expect(within(franja).getByTestId("ultima-corrida")).toHaveClass("border-rose-300");
  });

  it("una corrida que publicó sin alertas sí dice 'Sin alertas.'", async () => {
    servidor({ "GET /api/admin/fuentes": conCorrida({}), "GET /api/admin/fuentes/config": { modo: "prueba" } });
    render(<FuentesDatosPage />);
    const franja = await screen.findByRole("region", { name: "Estado general" });
    expect(within(franja).getByText("Sin alertas.")).toBeInTheDocument();
    expect(within(franja).getByTestId("ultima-corrida")).not.toHaveClass("border-rose-300");
  });

  it("muestra los avisos del motor de la última corrida", async () => {
    const aviso = "El motor no aceptó la configuración de esta pantalla (lista_erp: patron invalido '*:x*'). Corrige esa fuente: mientras tanto el motor usa la última configuración que sí aceptó.";
    servidor({ "GET /api/admin/fuentes": conCorrida({ avisos: [aviso] }), "GET /api/admin/fuentes/config": { modo: "prueba" } });
    render(<FuentesDatosPage />);
    const franja = await screen.findByRole("region", { name: "Estado general" });
    expect(within(franja).getByText(aviso)).toBeInTheDocument();
  });

  it("el texto de Activar no repite la cuenta", async () => {
    servidor({
      "GET /api/admin/fuentes": { ...PANEL, activacion: { puede_activar: false, motivo: null, corridas_necesarias: 2, corridas_en_verde: 1 } },
      "GET /api/admin/fuentes/config": { modo: "prueba" },
    });
    render(<FuentesDatosPage />);
    const franja = await screen.findByRole("region", { name: "Estado general" });
    const texto = within(franja).getByText(/corridas diarias seguidas en verde/);
    expect(texto).toHaveTextContent(/^1 de 2 corridas diarias seguidas en verde\.$/);
    expect(within(franja).getByRole("button", { name: "Activar" })).toBeDisabled();
  });
});

describe("editor", () => {
  function abrir(rutas: Record<string, unknown | ((init?: RequestInit) => Response)> = {}) {
    servidor({
      "GET /api/admin/fuentes/carpetas/bases_de_datos/archivos": LISTADO,
      "POST /api/admin/fuentes/stock_bodegas/vista-previa": VISTA,
      ...rutas,
    });
    const onGuardado = vi.fn();
    render(
      <EditorFuente
        detalle={DETALLE}
        carpetas={[{ clave: "bases_de_datos", nombre: "Bases de datos", tipo: "onedrive", params: { ruta: "Documentos/Desarrollos/Bases de datos" }, rutas_por_pc: {}, activa: true }]}
        version={4}
        onClose={() => {}}
        onGuardado={onGuardado}
        onRecargar={() => {}}
      />
    );
    return { onGuardado };
  }

  const puts = () => mocks.req.mock.calls.filter((c) => c[1]?.method === "PUT");

  it("no guarda sin nota", async () => {
    abrir();
    fireEvent.change(screen.getByLabelText("Se actualiza cada"), { target: { value: "3" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText(/Escribe una nota/)).toBeInTheDocument();
    expect(puts()).toHaveLength(0);
  });

  it("manda solo lo que cambió, con la nota y la versión de base", async () => {
    const { onGuardado } = abrir({
      "PUT /api/admin/fuentes/stock_bodegas": { version: 5, modo: "prueba", hash: "h", claves_cambiadas: ["stock_bodegas"], avisos: [] },
    });
    fireEvent.change(screen.getByLabelText("Se actualiza cada"), { target: { value: "3" } });
    fireEvent.click(screen.getByLabelText(/Es una diferencia esperada/));
    fireEvent.change(screen.getByLabelText("Nota del cambio"), { target: { value: "Plazo de 3 días por feriado" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));

    await waitFor(() => expect(onGuardado).toHaveBeenCalled());
    const [ruta, init] = puts()[0];
    expect(ruta).toBe("/api/admin/fuentes/stock_bodegas");
    expect(JSON.parse(init.body)).toEqual({
      cambios: { frecuencia_dias: 3, diferencia_esperada: true },
      nota: "Plazo de 3 días por feriado",
      base_version: 4,
    });
  });

  it("muestra la vista previa y los conflictos en rojo", async () => {
    abrir({
      "POST /api/admin/fuentes/stock_bodegas/vista-previa": {
        ...VISTA,
        conflictos: ["Stock bodegas Frontera y Stock bodegas Curifor tomarían el mismo archivo: Stock bodegas.xlsx."],
      },
    });
    expect(await screen.findByText("Con este cambio el motor tomaría Stock bodegas.xlsx (modificado hoy a las 09:34).")).toBeInTheDocument();
    expect(screen.getByText("Hoy toma Stock bodegas.xlsx (modificado hoy a las 09:34).")).toBeInTheDocument();
    const conflicto = screen.getByText(/tomarían el mismo archivo/);
    expect(conflicto).toHaveAttribute("role", "alert");
    expect(conflicto).toHaveClass("text-rose-700");
  });

  it("esconde lo avanzado y bloquea lo que fija el motor", async () => {
    abrir();
    expect(screen.getByLabelText("Patrones (uno por línea)")).not.toBeVisible();
    fireEvent.click(screen.getByText("Avanzado"));
    expect(screen.getByLabelText("Patrones (uno por línea)")).toBeVisible();
    expect(screen.getByLabelText(/^Obligatoria/)).toBeDisabled();
    expect(screen.getByText(DETALLE.bloqueos.obligatoria!)).toBeInTheDocument();
    expect(screen.getByText("Hoja y fila: Automático (detectado: hoja 'Hoja1', fila 1)")).toBeInTheDocument();
    await screen.findByText(/Con este cambio el motor tomaría/);
  });

  it("propone el patrón a partir de un archivo de la carpeta", async () => {
    abrir();
    const proponer = await screen.findByLabelText("Proponer a partir de un archivo de la carpeta");
    fireEvent.change(proponer, { target: { value: "stock bodegas.*" } });
    expect(screen.getByLabelText("Patrones (uno por línea)")).toHaveValue("stock bodegas.*");
  });

  it("muestra el 409 de otro admin", async () => {
    abrir({
      "PUT /api/admin/fuentes/stock_bodegas": () => respuesta({ detail: "Otro admin guardó un cambio; recarga" }, 409),
    });
    fireEvent.change(screen.getByLabelText("Se actualiza cada"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Nota del cambio"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText("Otro admin guardó un cambio; recarga")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Recargar" })).toBeInTheDocument();
  });

  it("con la API caída, Guardar dice qué pasó y no 'Failed to fetch'", async () => {
    abrir({
      "PUT /api/admin/fuentes/stock_bodegas": () => {
        throw new TypeError("Failed to fetch");
      },
    });
    fireEvent.change(screen.getByLabelText("Se actualiza cada"), { target: { value: "3" } });
    fireEvent.change(screen.getByLabelText("Nota del cambio"), { target: { value: "x" } });
    fireEvent.click(screen.getByRole("button", { name: "Guardar" }));
    expect(await screen.findByText(SIN_SERVIDOR)).toBeInTheDocument();
    expect(screen.queryByText(/failed to fetch/i)).not.toBeInTheDocument();
  });
});

describe("editor de carpetas", () => {
  it("en SharePoint pide el nombre del acceso directo y dice que es lo que usa el motor", () => {
    render(<EditorCarpeta open carpeta={null} pcs={[]} version={4} onClose={() => {}} onGuardado={() => {}} />);
    fireEvent.click(screen.getByLabelText("Biblioteca de SharePoint sincronizada"));
    const atajo = screen.getByLabelText(/Nombre del acceso directo en OneDrive/);
    expect(atajo).toBeRequired();
    expect(screen.getByText(/Es lo único que usa el motor para encontrar la carpeta en cada PC/)).toBeInTheDocument();
  });
});

describe("lib/fuentes-datos", () => {
  const ok = { version: 5, modo: "prueba", hash: "h", claves_cambiadas: [], avisos: [] };

  it("llama a las rutas correctas", async () => {
    mocks.req.mockImplementation(async () => respuesta(ok));
    await fuentesApi.panel();
    await fuentesApi.config();
    await fuentesApi.corridas(30);
    await fuentesApi.archivosCarpeta("bases_de_datos", "PC-ABAST-01");
    await fuentesApi.detalle("stock_bodegas");
    await fuentesApi.vistaPrevia("stock_bodegas", { frecuencia_dias: null });
    await fuentesApi.guardar("stock_bodegas", { al_vencer: "frena" }, "nota", 4);
    await fuentesApi.cambiarModo("activa", "nota", 4);
    await fuentesApi.cambiarTitular("PC-NUEVO", "nota", 4);
    await fuentesApi.nombrarPc("PC-NUEVO", "PC de la jefatura", 4);
    await fuentesApi.sembrar("c1");
    await fuentesApi.revertir(2, 4, { clave: "stock_bodegas" });
    await fuentesApi.editarCarpeta("databi_datos", { nombre: "Data BI" }, "nota", 4);

    const llamadas = mocks.req.mock.calls.map(([ruta, init]) => [init?.method ?? "GET", ruta, init?.body ? JSON.parse(init.body) : undefined]);
    expect(llamadas).toEqual([
      ["GET", "/api/admin/fuentes", undefined],
      ["GET", "/api/admin/fuentes/config", undefined],
      ["GET", "/api/admin/fuentes/corridas?limit=30", undefined],
      ["GET", "/api/admin/fuentes/carpetas/bases_de_datos/archivos?pc=PC-ABAST-01", undefined],
      ["GET", "/api/admin/fuentes/stock_bodegas", undefined],
      ["POST", "/api/admin/fuentes/stock_bodegas/vista-previa", { cambios: { frecuencia_dias: null } }],
      ["PUT", "/api/admin/fuentes/stock_bodegas", { cambios: { al_vencer: "frena" }, nota: "nota", base_version: 4 }],
      ["POST", "/api/admin/fuentes/modo", { modo: "activa", nota: "nota", base_version: 4 }],
      ["POST", "/api/admin/fuentes/titular", { pc: "PC-NUEVO", nota: "nota", base_version: 4 }],
      ["PUT", "/api/admin/fuentes/pcs/PC-NUEVO", { alias: "PC de la jefatura", base_version: 4 }],
      ["POST", "/api/admin/fuentes/sembrar", { corrida_id: "c1" }],
      ["POST", "/api/admin/fuentes/revertir/2", { base_version: 4, clave: "stock_bodegas" }],
      ["PUT", "/api/admin/fuentes/carpetas/databi_datos", { cambios: { nombre: "Data BI" }, nota: "nota", base_version: 4 }],
    ]);
  });

  it("un 409 sin texto se muestra igual como el aviso de otro admin", async () => {
    mocks.req.mockResolvedValue(new Response("", { status: 409 }));
    await expect(fuentesApi.guardar("stock_bodegas", {}, "nota", 1)).rejects.toMatchObject({
      status: 409,
      message: "Otro admin guardó un cambio; recarga",
    });
  });

  it("solo viajan los campos que cambiaron; vaciar el plazo es 'sin plazo'", () => {
    const form = formDesde(CFG);
    expect(cambiosFuente(CFG, form)).toEqual({});
    expect(cambiosFuente(CFG, { ...form, sin_plazo: true })).toEqual({ frecuencia_dias: null });
    expect(cambiosFuente(CFG, { ...form, incluye: "*stock*bodega*\n\n stock curifor.* " })).toEqual({
      incluye: ["*stock*bodega*", "stock curifor.*"],
    });
    expect(cambiosFuente(CFG, { ...form, ubicaciones: [{ carpeta: "bases_de_datos", subcarpeta: "\\stock\\", recursiva: false }] })).toEqual({});
  });

  it("el nombre de archivo solo viaja con 'Siempre este archivo'", () => {
    const form = formDesde(CFG);
    // Escrito en "Siempre este archivo" y vuelto a "El más reciente…": no se manda.
    expect(cambiosFuente(CFG, { ...form, nombre_archivo: "stock/Stock bodegas.xlsx" })).toEqual({});
    expect(cambiosFuente(CFG, { ...form, modo: "archivo_exacto", nombre_archivo: "Stock bodegas.xlsx" })).toEqual({
      modo: "archivo_exacto",
      nombre_archivo: "Stock bodegas.xlsx",
    });
    const exacto: FuenteCfg = { ...CFG, modo: "archivo_exacto", nombre_archivo: "Stock bodegas.xlsx" };
    expect(cambiosFuente(exacto, { ...formDesde(exacto), modo: "mas_reciente" })).toEqual({
      modo: "mas_reciente",
      nombre_archivo: null,
    });
  });

  it("las horas se muestran en hora de Chile: a las 22:00 'hoy' sigue siendo hoy", () => {
    // 22:00 del 16-10 en Chile es el 17-10 en UTC.
    const ahora = "2026-10-17T01:00:00Z";
    expect(cuando("2026-10-16T12:34:00Z", ahora)).toBe("hoy a las 09:34");
    expect(cuando("2026-10-15T12:30:00Z", ahora)).toBe("ayer a las 09:30");
    expect(cuando("2026-10-13T12:30:00Z", ahora)).toBe("el martes a las 09:30");
    expect(cuando("2026-10-05T12:30:00Z", ahora)).toBe("el 05-10 a las 09:30");
    expect(fechaHora("2026-10-17T01:00:00Z")).toBe("16-10-2026 22:00");
  });

  it("los selectores del editor respetan la subcarpeta, las subcarpetas y la extensión", () => {
    const a = (ruta: string): ArchivoCarpeta => {
      const partes = ruta.split("/");
      return { ...ARCHIVO, ruta_relativa: ruta, nombre: partes.pop()!, subcarpeta: partes.join("/") };
    };
    const lista = [a("stock/Stock bodegas.xlsx"), a("stock/viejo/Stock 2025.xlsx"), a("Ventas/2026 (6).xlsx"), a("stock/~$Stock bodegas.xlsx"), a("stock/notas.txt")];
    const nombres = (sub: string, recursiva: boolean) =>
      archivosEnUbicacion(lista, { subcarpeta: sub, recursiva }, [".xlsx"]).map((x) => x.ruta_relativa);
    expect(nombres("Stock", false)).toEqual(["stock/Stock bodegas.xlsx"]);
    expect(nombres("stock", true)).toEqual(["stock/Stock bodegas.xlsx", "stock/viejo/Stock 2025.xlsx"]);
    expect(nombres("", false)).toEqual([]);
    expect(nombres("", true)).toHaveLength(3);
  });
});
