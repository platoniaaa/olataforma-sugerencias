"""Schemas de Fuentes de datos (contratos de /api/admin/fuentes).

Dos clientes usan estas rutas:

- **El motor** pide la configuracion al partir (`GET /config`) y reporta cada
  corrida al partir y al terminar (`POST /reporte`).
- **La pantalla de admin** `/cargar/fuentes` muestra el panel (semaforo calculado
  aca, en el servidor) y edita la configuracion.

Lo que se guarda en `fuente_config.config` es `ConfigFuentes`. Las piezas que
declara el motor (catalogo, carpetas, fuentes) aceptan campos que esta version de
la plataforma todavia no conoce y los guardan tal cual: un campo nuevo del motor no
necesita migracion ni se pierde al sembrar. Lo que edita una persona, en cambio, es
estricto (`extra="forbid"`): la pantalla no puede colar campos.

El reporte del motor (`ReporteIn.reporte`) se guarda como viene. Su forma esperada
esta documentada en `EstadoFuenteIn` y `ListadoCarpetaIn`, pero se valida suelta a
proposito: un reporte que no calza con el esquema se guarda con un aviso en vez de
perderse con un 422 (el motor no reintenta para siempre).
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

ModoConfig = Literal["prueba", "activa"]
ModoPanel = Literal["sin_configurar", "prueba", "activa"]
AlVencer = Literal["frena", "avisa"]
TipoCorrida = Literal["oficial", "comparacion", "probar"]
Resultado = Literal["en_curso", "ok", "frenada", "fallo", "incompleta", "cortada", "no_titular"]
ConfigOrigen = Literal["plataforma", "cache", "env"]
Nivel = Literal["rojo", "amarillo", "verde", "gris"]


class _Abierto(BaseModel):
    # Lo que declara el motor puede traer campos que esta version de la plataforma
    # todavia no conoce: se guardan tal cual en vez de perderse.
    model_config = ConfigDict(extra="allow")


# --------------------------------------------------------------------------- #
# Configuracion (lo que se guarda en fuente_config.config)
# --------------------------------------------------------------------------- #
class CatalogoFuente(_Abierto):
    """Lo que el motor declara de cada fuente. La plataforma valida contra esto y
    no tiene ninguna clave de fuente escrita en el codigo."""

    uso: Literal["lee", "reconoce"]
    # Sin ella el motor no calcula: no puede quedar no obligatoria ni inactiva.
    requerida: bool = False
    # Modos de eleccion permitidos (archivo_exacto, mas_reciente, por_descarte).
    modos: list[str] = Field(default_factory=lambda: ["archivo_exacto", "mas_reciente"])
    # Tope de dias habiles que se puede poner como plazo (null = sin tope).
    frecuencia_max: int | None = None
    # Si viene, la conducta al vencer no se puede cambiar.
    al_vencer_fijo: AlVencer | None = None
    # Que pasa si falta (texto para la persona, sin jerga).
    efecto_si_falta: str | None = None
    # Si el semaforo controla que el archivo no llegue vacio o incompleto. Si el
    # motor no lo declara, aplica a las fuentes que tienen `frecuencia_max`.
    controla_filas: bool | None = None


class UbicacionCfg(BaseModel):
    model_config = ConfigDict(extra="forbid")

    carpeta: str = Field(min_length=1, max_length=60)
    # Separador "/"; "" = la raiz de la carpeta.
    subcarpeta: str = Field(default="", max_length=100)
    recursiva: bool = False


class CarpetaCfg(_Abierto):
    clave: str
    nombre: str
    tipo: str  # sharepoint | onedrive
    # sharepoint: sitio_url, biblioteca, ruta, nombre_atajo. onedrive: ruta.
    params: dict[str, Any] = Field(default_factory=dict)
    # Unico lugar con rutas absolutas: amarradas a un hostname. El motor solo las
    # acepta dentro de las carpetas de OneDrive.
    rutas_por_pc: dict[str, str] = Field(default_factory=dict)
    activa: bool = True


class FuenteCfg(_Abierto):
    clave: str
    nombre: str
    ubicaciones: list[UbicacionCfg] = Field(default_factory=list)
    # archivo_exacto | mas_reciente | por_descarte
    modo: str = "mas_reciente"
    nombre_archivo: str | None = None
    incluye: list[str] = Field(default_factory=list)
    excluye: list[str] = Field(default_factory=list)
    extensiones: list[str] = Field(default_factory=lambda: [".xlsx", ".xlsm", ".csv"])
    # Dias habiles; null = sin plazo.
    frecuencia_dias: int | None = None
    al_vencer: AlVencer = "frena"
    obligatoria: bool = False
    activa: bool = True
    # Solo sirve en modo prueba: la diferencia con el .env es un ensayo a proposito.
    diferencia_esperada: bool = False
    # Se muestran, no se editan (Fase 2).
    hoja: str | int | None = None
    fila_encabezado: int | None = None


class PcCfg(_Abierto):
    alias: str | None = None


class ConfigFuentes(BaseModel):
    """La configuracion completa de una version."""

    modo: ModoConfig = "prueba"
    pc_titular: str | None = None
    pcs: dict[str, PcCfg] = Field(default_factory=dict)
    catalogo: dict[str, CatalogoFuente] = Field(default_factory=dict)
    carpetas: list[CarpetaCfg] = Field(default_factory=list)
    fuentes: list[FuenteCfg] = Field(default_factory=list)


class ConfigEfectiva(_Abierto):
    """Lo que el motor usa hoy, tal como lo manda en cada reporte. Desde aca se siembra."""

    catalogo: dict[str, CatalogoFuente] = Field(default_factory=dict)
    carpetas: list[CarpetaCfg] = Field(default_factory=list)
    fuentes: list[FuenteCfg] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Lo que manda el motor
# --------------------------------------------------------------------------- #
class ArchivoReportadoIn(_Abierto):
    """Un archivo elegido para una fuente (ventas trae varios)."""

    carpeta: str | None = None          # clave de la carpeta
    ruta_relativa: str                  # relativa a la carpeta, separador "/" o "\"
    modificado_en: datetime | None = None   # ISO con zona; sin zona se toma hora de Chile
    tamano: int | None = None
    sha256: str | None = None
    onedrive: str | None = None         # solo_nube | fijado | liberable | local


class EstadoFuenteIn(_Abierto):
    """Forma esperada de `reporte.fuentes[clave]` (documental: se guarda suelto)."""

    # encontrado | falta | carpeta_no_encontrada | error_lectura | inestable
    hecho: str
    archivos: list[ArchivoReportadoIn] = Field(default_factory=list)
    # El motor manda la lista (hasta 20, con la forma de `archivos` sin sha256).
    candidatos: list[ArchivoReportadoIn] | int | None = None
    carpetas_con_candidatos: list[str] | int | None = None
    descartados: list[dict[str, Any]] = Field(default_factory=list)   # [{nombre, motivo}]
    filas: int | None = None
    hoja_leida: str | int | None = None
    # La fila detectada como se ve en Excel (desde 1). En `FuenteCfg` va desde 0.
    fila_encabezado: int | None = None
    edad_dias_habiles: int | None = None
    mismo_contenido_que_anterior: bool = False
    abierto_en_excel: bool = False
    # Solo en modo prueba: {resultado: coincide|difiere|difiere_esperado|falta, archivo, frenaria}
    prueba: dict[str, Any] | None = None
    # ventas: {periodo_ultimo_mes: "202609", total_mes_cerrado: 123.0}
    extra: dict[str, Any] = Field(default_factory=dict)
    mensaje: str | None = None


class ArchivoListadoIn(_Abierto):
    ruta_relativa: str
    tamano: int | None = None
    modificado_en: datetime | None = None
    onedrive: str | None = None
    fuente: str | None = None       # clave de la fuente que lo reconoce (si alguna)
    elegido: bool = False


class ListadoCarpetaIn(_Abierto):
    """Forma esperada de cada elemento de `reporte.carpetas` (documental)."""

    clave: str
    existe: bool
    metodo: str | None = None       # env | ruta_por_pc | onedrive | atajo (SharePoint)
    ruta_portable: str | None = None   # %OneDriveCommercial%\...
    ruta_absoluta: str | None = None   # trae el usuario de Windows: solo en el detalle
    archivos: list[ArchivoListadoIn] = Field(default_factory=list)
    truncado: bool = False


class ReporteContenido(_Abierto):
    fuentes: dict[str, dict[str, Any]] = Field(default_factory=dict)
    carpetas: list[dict[str, Any]] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    # Si OneDrive.exe estaba corriendo (tasklist). null = no se pudo saber.
    onedrive_corriendo: bool | None = None
    # Cuando se guardo la cache que uso la corrida (solo con config_origen=cache).
    cache_guardada_en: datetime | None = None


class ReporteIn(BaseModel):
    """`POST /reporte`: el reporte de inicio o de fin de una corrida (upsert por id)."""

    model_config = ConfigDict(extra="ignore")

    id: str = Field(min_length=1, max_length=64)
    fase: Literal["inicio", "fin"]
    pc: str = Field(min_length=1, max_length=100)
    tipo: TipoCorrida
    titular: bool | None = None
    publico: bool | None = None
    iniciada_en: datetime | None = None
    terminada_en: datetime | None = None
    resultado: Resultado | None = None
    # Sin tope aca: un motivo largo (con traceback) se recorta al guardar en vez de
    # perder el reporte entero con un 422.
    motivo: str | None = None
    config_origen: ConfigOrigen | None = None
    config_version: int | None = None
    version_motor: str | None = None
    reporte: ReporteContenido | None = None
    config_efectiva: dict[str, Any] | None = None

    @model_validator(mode="after")
    def _fin_trae_resultado(self) -> "ReporteIn":
        if self.fase == "fin" and self.resultado in (None, "en_curso"):
            raise ValueError("El reporte de fin tiene que traer el resultado de la corrida")
        return self


class ReporteOut(BaseModel):
    id: str
    resultado: str
    avisos: list[str] = Field(default_factory=list)
    notificados: int = 0


# --------------------------------------------------------------------------- #
# Lo que manda la pantalla (escrituras)
# --------------------------------------------------------------------------- #
class CambiosFuente(BaseModel):
    """Cambios a una fuente. Solo se tocan los campos que vienen; `frecuencia_dias`
    puede venir en null (= sin plazo), por eso se mira `model_fields_set`."""

    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    ubicaciones: list[UbicacionCfg] | None = None
    modo: str | None = None
    nombre_archivo: str | None = Field(default=None, max_length=100)
    incluye: list[str] | None = None
    excluye: list[str] | None = None
    extensiones: list[str] | None = None
    frecuencia_dias: int | None = None
    al_vencer: AlVencer | None = None
    obligatoria: bool | None = None
    activa: bool | None = None
    diferencia_esperada: bool | None = None


class GuardarFuenteIn(BaseModel):
    """`PUT /{clave}`."""

    model_config = ConfigDict(extra="forbid")

    cambios: CambiosFuente
    nota: str = Field(min_length=1, max_length=500)
    base_version: int


class VistaPreviaIn(BaseModel):
    """`POST /{clave}/vista-previa`: los mismos cambios que se guardarian. No guarda."""

    model_config = ConfigDict(extra="forbid")

    cambios: CambiosFuente = Field(default_factory=CambiosFuente)


class CarpetaNueva(BaseModel):
    model_config = ConfigDict(extra="forbid")

    clave: str = Field(min_length=1, max_length=40)
    nombre: str = Field(min_length=1, max_length=100)
    tipo: Literal["sharepoint", "onedrive"]
    params: dict[str, str] = Field(default_factory=dict)
    rutas_por_pc: dict[str, str] = Field(default_factory=dict)
    activa: bool = True


class CrearCarpetaIn(BaseModel):
    """`POST /carpetas`."""

    model_config = ConfigDict(extra="forbid")

    carpeta: CarpetaNueva
    nota: str = Field(min_length=1, max_length=500)
    base_version: int


class CambiosCarpeta(BaseModel):
    model_config = ConfigDict(extra="forbid")

    nombre: str | None = Field(default=None, min_length=1, max_length=100)
    tipo: Literal["sharepoint", "onedrive"] | None = None
    params: dict[str, str] | None = None
    # Reemplaza el mapa completo; una ruta vacia borra la de ese PC.
    rutas_por_pc: dict[str, str] | None = None
    activa: bool | None = None


class EditarCarpetaIn(BaseModel):
    """`PUT /carpetas/{clave}`."""

    model_config = ConfigDict(extra="forbid")

    cambios: CambiosCarpeta
    nota: str = Field(min_length=1, max_length=500)
    base_version: int


class AliasPcIn(BaseModel):
    """`PUT /pcs/{hostname}`."""

    model_config = ConfigDict(extra="forbid")

    alias: str = Field(min_length=1, max_length=60)
    nota: str | None = Field(default=None, max_length=500)
    base_version: int


class TitularIn(BaseModel):
    """`POST /titular`."""

    model_config = ConfigDict(extra="forbid")

    pc: str = Field(min_length=1, max_length=100)
    nota: str = Field(min_length=1, max_length=500)
    base_version: int


class ModoIn(BaseModel):
    """`POST /modo`."""

    model_config = ConfigDict(extra="forbid")

    modo: ModoConfig
    nota: str = Field(min_length=1, max_length=500)
    base_version: int


class SembrarIn(BaseModel):
    """`POST /sembrar`."""

    model_config = ConfigDict(extra="forbid")

    corrida_id: str = Field(min_length=1, max_length=64)
    nota: str | None = Field(default=None, max_length=500)


class RevertirIn(BaseModel):
    """`POST /revertir/{version}`. Con `clave`, vuelve solo esa fuente."""

    model_config = ConfigDict(extra="forbid")

    nota: str | None = Field(default=None, max_length=500)
    base_version: int | None = None
    clave: str | None = Field(default=None, max_length=60)


class GuardadoOut(BaseModel):
    """Respuesta de toda escritura: la version nueva y lo que cambio."""

    version: int
    modo: ModoConfig
    hash: str
    claves_cambiadas: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)


# --------------------------------------------------------------------------- #
# Lo que lee la pantalla
# --------------------------------------------------------------------------- #
class AlertaOut(BaseModel):
    nivel: Nivel
    # Etiqueta corta del semaforo ("Vencido", "Al día"...).
    etiqueta: str
    # Frase para la persona: siempre dice que hacer.
    texto: str
    # Identificador estable de la regla (para tests y para la web).
    regla: str


class ArchivoOut(BaseModel):
    carpeta: str | None = None
    carpeta_nombre: str | None = None
    ruta_relativa: str
    nombre: str
    modificado_en: datetime | None = None
    tamano: int | None = None
    onedrive: str | None = None


class PruebaOut(BaseModel):
    """Modo prueba: lo que tomaria la configuracion de la plataforma vs el .env."""

    resultado: str                  # coincide | difiere | difiere_esperado | falta
    archivo: str | None = None
    texto: str
    frenaria: bool = False


class FuentePanelOut(BaseModel):
    clave: str
    nombre: str
    nivel: Nivel
    etiqueta: str
    texto: str
    regla: str
    # Todas las reglas que aplican (la principal es la primera de la peor).
    alertas: list[AlertaOut] = Field(default_factory=list)
    hecho: str | None = None
    archivo: str | None = None          # nombre del archivo principal
    archivos: list[ArchivoOut] = Field(default_factory=list)
    modificado_en: datetime | None = None
    # Recalculada hoy en dias habiles a partir de modificado_en.
    edad_dias_habiles: int | None = None
    filas: int | None = None
    carpeta: str | None = None
    carpeta_nombre: str | None = None
    obligatoria: bool = False
    frecuencia_dias: int | None = None
    al_vencer: str | None = None
    activa: bool = True
    prueba: PruebaOut | None = None
    # "Dato de la corrida del 14-10 a las 09:30" cuando el titular no corrio hoy.
    dato_de: str | None = None


class FuenteReconoceOut(BaseModel):
    """Fuentes que el motor solo reconoce (para que no caigan como ventas)."""

    clave: str
    nombre: str
    incluye: list[str] = Field(default_factory=list)
    excluye: list[str] = Field(default_factory=list)
    archivos: list[ArchivoOut] = Field(default_factory=list)


class CorridaOut(BaseModel):
    id: str
    pc: str
    alias: str | None = None
    tipo: str
    titular: bool
    publico: bool
    iniciada_en: datetime
    terminada_en: datetime | None = None
    duracion_min: int | None = None
    resultado: str
    # Frase corta del resultado ("Publicó", "Frenada: no publicó"...).
    resultado_texto: str
    # El motivo del log traducido (sin opciones de linea de comandos).
    motivo_texto: str | None = None
    config_origen: str | None = None
    config_version: int | None = None
    # Con que eligio el motor lo que leyo: `env` (el .env del PC) o `plataforma`. En
    # prueba y sin configurar la plataforma responde (config_origen=plataforma), pero
    # el motor lee con el .env.
    resolucion: str | None = None
    # El modo de la configuracion con que corrio (sin_configurar | prueba | activa).
    modo_config: str | None = None
    # Los avisos del motor (`reporte.avisos`) para la persona y sin la ruta del PC: por
    # ejemplo, por que uso la configuracion guardada.
    avisos: list[str] = Field(default_factory=list)
    version_motor: str | None = None
    # Cuantas fuentes `lee` quedaron en cada color en esa corrida.
    resumen: dict[str, int] = Field(default_factory=dict)


class FranjaOut(BaseModel):
    nivel: Nivel
    ultima_corrida: CorridaOut | None = None
    alertas: list[AlertaOut] = Field(default_factory=list)


class CarpetaPcOut(BaseModel):
    clave: str
    nombre: str
    tipo: str | None = None
    ruta_portable: str | None = None
    metodo: str | None = None
    existe: bool
    archivos: int = 0
    truncado: bool = False


class PcPanelOut(BaseModel):
    pc: str
    alias: str | None = None
    es_titular: bool
    corrida_id: str
    tipo: str
    iniciada_en: datetime
    carpetas: list[CarpetaPcOut] = Field(default_factory=list)


class ActivacionOut(BaseModel):
    puede_activar: bool
    # Lo que corta la racha, sin la cuenta (la pantalla ya la muestra). Null si se puede
    # activar o si solo faltan corridas.
    motivo: str | None = None
    corridas_necesarias: int
    corridas_en_verde: int


class SembrarDesdeOut(BaseModel):
    corrida_id: str
    pc: str
    alias: str | None = None
    tipo: str
    iniciada_en: datetime


class PanelOut(BaseModel):
    """`GET /`: todo lo que muestra `/cargar/fuentes`, en el orden de la pantalla."""

    modo: ModoPanel
    modo_texto: str
    version: int | None = None
    pc_titular: str | None = None
    pc_titular_alias: str | None = None
    ahora: datetime
    franja: FranjaOut
    # Corrida de la que salen los datos de las fuentes.
    corrida_id: str | None = None
    dato_de_corrida: str | None = None
    fuentes: list[FuentePanelOut] = Field(default_factory=list)
    reconoce: list[FuenteReconoceOut] = Field(default_factory=list)
    carpetas_por_pc: list[PcPanelOut] = Field(default_factory=list)
    activacion: ActivacionOut
    # Solo sin configurar: corridas desde las que se puede sembrar (una por PC).
    sembrar_desde: list[SembrarDesdeOut] = Field(default_factory=list)


class CorridasOut(BaseModel):
    items: list[CorridaOut]


class ArchivoCarpetaOut(BaseModel):
    ruta_relativa: str
    nombre: str
    subcarpeta: str
    tamano: int | None = None
    modificado_en: datetime | None = None
    onedrive: str | None = None
    fuente: str | None = None
    elegido: bool = False
    # Patron propuesto para "el más reciente cuyo nombre contenga...": fechas y
    # numeros como comodin ("Precios Gildemeister 20260728.xlsx" -> "precios gildemeister *").
    patron_propuesto: str


class ArchivosCarpetaOut(BaseModel):
    """`GET /carpetas/{clave}/archivos?pc=`: el ultimo listado de esa carpeta."""

    clave: str
    nombre: str | None = None
    pc: str | None = None
    alias: str | None = None
    corrida_id: str | None = None
    iniciada_en: datetime | None = None
    existe: bool = False
    metodo: str | None = None
    ruta_portable: str | None = None
    ruta_absoluta: str | None = None
    truncado: bool = False
    subcarpetas: list[str] = Field(default_factory=list)
    archivos: list[ArchivoCarpetaOut] = Field(default_factory=list)


class CorridaFuenteOut(BaseModel):
    corrida_id: str
    pc: str
    alias: str | None = None
    tipo: str
    iniciada_en: datetime
    resultado: str
    hecho: str | None = None
    nivel: Nivel
    etiqueta: str
    archivos: list[ArchivoOut] = Field(default_factory=list)
    filas: int | None = None
    hoja_leida: str | int | None = None
    prueba: PruebaOut | None = None
    # El error exacto que mando el motor (`error_lectura`). Va solo aca, en el detalle:
    # es la excepcion cruda y puede traer la ruta del PC.
    mensaje: str | None = None


class CompetenciaOut(BaseModel):
    """Archivos que calzan con la fuente, por carpeta (el ganador marcado)."""

    carpeta: str
    carpeta_nombre: str | None = None
    ruta_absoluta: str | None = None
    candidatos: list[ArchivoCarpetaOut] = Field(default_factory=list)


class DescartadoOut(BaseModel):
    nombre: str
    motivo: str | None = None
    # No estaba en la corrida anterior.
    nuevo: bool = False


class VersionOut(BaseModel):
    version: int
    creado_por: str | None = None
    creado_en: datetime
    nota: str
    revierte_a: int | None = None
    claves_cambiadas: list[str] = Field(default_factory=list)


class FuenteDetalleOut(BaseModel):
    """`GET /{clave}`."""

    clave: str
    nombre: str
    uso: str | None = None
    modo: ModoPanel
    version: int | None = None
    config: FuenteCfg
    catalogo: CatalogoFuente | None = None
    # Controles bloqueados por el catalogo y por que ({"obligatoria": "...", ...}).
    bloqueos: dict[str, str] = Field(default_factory=dict)
    # "Automático (detectado: hoja 'Hoja1', fila 1)".
    hoja_texto: str
    estado: FuentePanelOut | None = None
    corridas: list[CorridaFuenteOut] = Field(default_factory=list)
    competencia: list[CompetenciaOut] = Field(default_factory=list)
    descartados: list[DescartadoOut] = Field(default_factory=list)
    versiones: list[VersionOut] = Field(default_factory=list)


class SeleccionOut(BaseModel):
    archivos: list[ArchivoOut] = Field(default_factory=list)
    candidatos: int = 0
    texto: str


class ListadoUsadoOut(BaseModel):
    pc: str
    alias: str | None = None
    corrida_id: str
    iniciada_en: datetime


class VistaPreviaOut(BaseModel):
    """`POST /{clave}/vista-previa`: que tomaria el motor con el cambio. No guarda."""

    elegiria: SeleccionOut
    hoy_toma: SeleccionOut
    # En rojo: con alguno de estos, `PUT` responde 422.
    conflictos: list[str] = Field(default_factory=list)
    avisos: list[str] = Field(default_factory=list)
    # El listado contra el que se probo (null si el titular nunca reporto carpetas).
    listado: ListadoUsadoOut | None = None
