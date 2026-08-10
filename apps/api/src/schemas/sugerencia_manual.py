"""Schemas de las sugerencias manuales."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .sugerido import SugeridoFiltros


class SugerenciaManualCreate(BaseModel):
    producto: str
    sucursal_id: str
    unidades: int | None = Field(default=None, gt=0, description="Unidades adicionales (si modo='unidades')")
    dias_inventario: int | None = Field(
        default=None, gt=0,
        description="Dias de inventario a cubrir (si modo='dias'). Se pide solo lo que falte "
        "para llegar a esa cobertura, descontando stock, transito y lo que ya sugiere el sistema.",
    )
    stock_objetivo: int | None = Field(
        default=None, gt=0,
        description="Nivel de stock a mantener (si modo='objetivo'). Se pide solo lo que falta "
        "para llegar a ese nivel, descontando stock, transito y lo que ya sugiere el sistema.",
    )
    expira_en: date | None = Field(
        default=None,
        description="Fecha limite (inclusive) hasta la que la sugerencia sigue vigente; al pasar se archiva. None = no vence.",
    )
    motivo: str | None = None


class SugerenciaManualMasiva(BaseModel):
    """Crea la misma cantidad para todos los productos que cumplen los filtros."""

    filtros: SugeridoFiltros = Field(default_factory=SugeridoFiltros)
    unidades: int | None = Field(default=None, gt=0)
    dias_inventario: int | None = Field(default=None, gt=0)
    stock_objetivo: int | None = Field(
        default=None, gt=0, description="Nivel de stock a mantener en cada producto/sucursal."
    )
    expira_en: date | None = Field(
        default=None,
        description="Fecha limite (inclusive) hasta la que las sugerencias siguen vigentes; al pasar se archivan. None = no vencen.",
    )
    motivo: str | None = None


class SugerenciaManualMasivaResultado(BaseModel):
    creadas: int
    # Por dias: pares sin demanda diaria o que ya tienen esos dias cubiertos.
    # Por objetivo: pares que ya estaban en el nivel pedido.
    omitidas: int = 0
    # Lote (UUID) que agrupa las filas creadas en esta llamada — sirve para
    # borrarlas juntas via DELETE /lote/{lote_id}. None si no se creo ninguna.
    lote_id: str | None = None


class SugerenciaManualPegada(BaseModel):
    """Lista pegada donde cada linea trae su propia cantidad.

    A diferencia de `SugerenciaManualMasiva`, que aplica UN criterio y UN numero a
    todos los pares de un filtro, aca cada linea decide lo suyo. `previsualizar`
    devuelve lo que se va a crear sin escribir nada: la lista sale de un Excel
    armado a mano y conviene mirarla antes.
    """

    texto: str
    previsualizar: bool = False
    expira_en: date | None = Field(
        default=None,
        description="Fecha limite (inclusive) para todas las lineas de esta carga.",
    )
    motivo: str | None = None


class LineaManualPegada(BaseModel):
    producto: str
    sucursal: str
    unidades: int | None = None
    dias: int | None = None
    mantener: int | None = None
    # 'mantener' | 'dias' | 'unidades', ya resuelto por la regla de prioridad.
    criterio: str
    # Lo que efectivamente se va a pedir. None cuando el par no da (sin demanda
    # para calcular los dias, o ya esta en el nivel pedido): esas se omiten.
    unidades_resultantes: int | None = None
    # Por que se omite, en lenguaje de usuario. None si la linea entra.
    omitida_porque: str | None = None


class SugerenciaManualPegadaResultado(BaseModel):
    creadas: int = 0
    omitidas: int = 0
    lote_id: str | None = None
    # Solo en previsualizacion: lo que se crearia, linea por linea.
    lineas: list[LineaManualPegada] = Field(default_factory=list)
    # Lineas que no se pudieron leer, con su numero para poder corregirlas.
    errores: list[dict] = Field(default_factory=list)
    encabezado_detectado: bool = False


class SugerenciaManualUpdate(BaseModel):
    aprobado: bool | None = None
    usado_en_compra: bool | None = None
    unidades: int | None = Field(default=None, gt=0)
    motivo: str | None = None


class SugerenciaManualOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    producto: str
    sucursal_id: str
    unidades: int
    motivo: str | None = None
    creado_por: str | None = None
    creado_en: datetime
    aprobado: bool
    usado_en_compra: bool
    archivada: bool = False
    lote_id: str | None = None  # UUID compartido por las filas de una misma carga masiva
    expira_en: datetime | None = None  # Fecha en que se archiva; None = no vence
    # Como se pidio: permite explicar de donde salio el numero de unidades.
    dias_inventario: int | None = None
    stock_objetivo: int | None = None
    # Si vino de una regla que se repite (para distinguirla de una carga puntual).
    recurrente_id: str | None = None

    # --- Contexto del producto, para poder LEER la lista ---
    # La pantalla mostraba el codigo pelado ("74 1324409TBW0000") y habia que ir al
    # catalogo a ver que repuesto era. Salen del mismo camino que llena la grilla
    # (services/sugerido_service.contexto_de_pares), asi los dos dicen lo mismo.
    # Todos opcionales: si el codigo no esta en ninguna fuente, quedan en None.
    descripcion: str | None = None
    nombre_sucursal: str | None = None
    marca: str | None = None
    proveedor: str | None = None
    costo_unitario: float | None = None
    # unidades x costo unitario: lo que cuesta esta sugerencia.
    valor_clp: float | None = None
    # Stock que hay hoy en esa sucursal, para juzgar si la sugerencia sigue teniendo
    # sentido (se cargo hace un mes y quiza ya llego).
    stock_actual: float | None = None


class RecurrenteCreate(BaseModel):
    modo: Literal["individual", "grupo"]
    producto: str | None = None
    sucursal_id: str | None = None
    filtros: SugeridoFiltros | None = None  # modo grupo
    unidades: int | None = Field(default=None, gt=0)
    dias_inventario: int | None = Field(
        default=None, gt=0,
        description="Dias de inventario a cubrir. En cada ejecucion se recalcula contra la "
        "demanda y el stock del momento: si esos dias ya estan cubiertos, no pide nada.",
    )
    stock_objetivo: int | None = Field(
        default=None, gt=0,
        description="Nivel de stock a mantener. En cada ejecucion se recalcula contra el "
        "stock del momento, que es lo que hace automatica la mantencion del nivel.",
    )
    motivo: str | None = None
    cada_dias: int = Field(gt=0, le=365, description="Repetir cada N días")
    fecha_fin: date | None = None


class RecurrenteOut(BaseModel):
    id: str
    modo: str
    resumen: str
    unidades: int
    dias_inventario: int | None = None
    stock_objetivo: int | None = None
    motivo: str | None = None
    cada_dias: int
    proxima_ejecucion: date
    fecha_fin: date | None = None
    activa: bool
    ultima_ejecucion: date | None = None
