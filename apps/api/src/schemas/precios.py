"""Schemas del modulo de precios (contratos de /api/precios)."""
from __future__ import annotations

from pydantic import BaseModel, Field


class PrecioRow(BaseModel):
    """Una fila de la lista de precios: lo calculado mas lo decidido a mano."""

    producto: str
    glosa: str | None = None
    rubro: str | None = None
    tipo: str | None = None
    tipo_origen: str | None = None
    procedencia_maestro: str | None = None
    procedencia_final: str | None = None
    procedencia_origen: str | None = None
    factor: float | None = None
    costo: float | None = None
    precio_erp: float | None = None
    stock: float | None = None
    stock_transito: float | None = None
    ult_recep_importado: str | None = None
    ult_pe_nacional: str | None = None
    ultima_venta: str | None = None
    precio_sugerido: float | None = None
    precio_calculado: float | None = None
    precio_final: float | None = None
    estado: str | None = None
    cambios_pendientes: int = 0
    origen: str = "maestro"
    desviacion_pesos: float | None = None
    desviacion_pct: float | None = None
    # Override (decision humana), aplanado en la fila para la grilla.
    precio_fijo: float | None = None
    congelar: bool = False
    congelado_precio: float | None = None
    no_producto: bool = False
    obs: str | None = None
    tipo_manual: str | None = None
    procedencia_manual: str | None = None
    editado_por: str | None = None
    editado_en: str | None = None
    actualizado_en: str | None = None


class PrecioCambioOut(BaseModel):
    campo: str
    antes: str | None = None
    despues: str | None = None
    visto: bool = False
    detectado_en: str | None = None


class PrecioEnvioOut(BaseModel):
    precio: float | None = None
    costo: float | None = None
    lote_id: str
    enviado_en: str | None = None
    enviado_por: str | None = None


class PrecioDetalleOut(PrecioRow):
    """La ficha: la fila mas su historia. Sin este schema FastAPI recortaba
    `cambios` y `envios` de la respuesta y la ficha se caia al abrirse."""

    cambios: list[PrecioCambioOut] = Field(default_factory=list)
    envios: list[PrecioEnvioOut] = Field(default_factory=list)


class PrecioPage(BaseModel):
    items: list[PrecioRow]
    total: int
    page: int
    limit: int


class PrecioFiltros(BaseModel):
    q: str | None = None
    rubro: list[str] = Field(default_factory=list)
    tipo: list[str] = Field(default_factory=list)
    procedencia: list[str] = Field(default_factory=list)
    estado: list[str] = Field(default_factory=list)
    origen: str | None = None
    con_cambios: bool = False
    con_stock: bool = False


class OverrideIn(BaseModel):
    """Lo que una persona decide sobre un precio. Todos opcionales: se aplican
    solo los que vengan. `precio_fijo: null` explicitamente quita el fijo."""

    precio_fijo: float | None = Field(default=None, ge=0)
    congelar: bool | None = None
    tipo_manual: str | None = Field(default=None, max_length=40)
    procedencia_manual: str | None = Field(default=None, max_length=20)
    no_producto: bool | None = None
    obs: str | None = Field(default=None, max_length=500)

    model_config = {"extra": "forbid"}


class ProductoNuevoIn(BaseModel):
    producto: str = Field(min_length=2, max_length=60)
    glosa: str | None = Field(default=None, max_length=200)
    rubro: str | None = Field(default=None, max_length=5)
    tipo: str | None = Field(default=None, max_length=40)
    procedencia: str | None = Field(default=None, max_length=20)
    costo: float | None = Field(default=None, ge=0)
    stock: float | None = Field(default=None, ge=0)
    precio_fijo: float | None = Field(default=None, ge=0)
    obs: str | None = Field(default=None, max_length=500)


class FactorIn(BaseModel):
    tipo: str = Field(min_length=1, max_length=40)
    procedencia: str = Field(min_length=1, max_length=20)
    factor: float = Field(gt=1.0, le=10.0)
    descuento_max: float | None = Field(default=None, ge=0, le=100)
    margen_post: float | None = Field(default=None, ge=-100, le=100)


class FactoresIn(BaseModel):
    filas: list[FactorIn]


class RubroIn(BaseModel):
    rubro: str = Field(min_length=1, max_length=5)
    tipo: str | None = Field(default=None, max_length=40)
    procedencia_forzada: str | None = Field(default=None, max_length=20)


class RubrosIn(BaseModel):
    filas: list[RubroIn]


class VistosIn(BaseModel):
    productos: list[str] | None = None
