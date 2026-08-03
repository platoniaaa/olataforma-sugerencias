"""Schemas del requerimiento de sucursal (pegar lista -> decidir -> archivo)."""
from pydantic import BaseModel, Field


class LineaPegada(BaseModel):
    """Una linea tal como salio del texto pegado."""

    producto: str
    cantidad: float | None = None
    texto_original: str | None = None


class AnalizarTextoRequest(BaseModel):
    """Lo que pega el comprador, tal cual. El parseo va en el servidor."""

    sucursal_id: str
    texto: str


class AnalizarLineasRequest(BaseModel):
    """Re-analisis con las lineas ya editadas en pantalla."""

    sucursal_id: str
    lineas: list[LineaPegada] = Field(default_factory=list)


class FrecuenciaOtraSucursal(BaseModel):
    sucursal_id: str
    nombre_sucursal: str
    meses_con_venta_12m: int
    clasificacion_abc: str | None = None


class LineaRequerimiento(BaseModel):
    """Una linea con todo lo necesario para decidir comprarla o no."""

    producto: str
    texto_original: str | None = None
    cantidad: float | None = None
    # en_sugerido | sin_venta_local | no_existe
    estado: str
    duplicado: bool = False
    descripcion: str | None = None
    proveedor: str | None = None
    costo_unitario: float | None = None
    reemplazos: str | None = None
    nombre_sucursal: str | None = None
    stock_sucursal: float | None = None
    stock_cd: float | None = None
    stock_nacional: float | None = None
    meses_con_venta_3m: int | None = None
    meses_con_venta_6m: int | None = None
    meses_con_venta_12m: int | None = None
    clasificacion_abc: str | None = None
    total_sugerido_suc: float | None = None
    frecuencia_otra_sucursal: FrecuenciaOtraSucursal | None = None


class ResumenRequerimiento(BaseModel):
    total: int = 0
    en_sugerido: int = 0
    sin_venta_local: int = 0
    no_existe: int = 0
    duplicados: int = 0


class RequerimientoResponse(BaseModel):
    lineas: list[LineaRequerimiento] = Field(default_factory=list)
    resumen: ResumenRequerimiento = Field(default_factory=ResumenRequerimiento)


class ArchivoPortalRequest(BaseModel):
    """Lineas ya decididas -> archivo del portal."""

    proveedor: str  # FORD | GILDEMEISTER
    sucursal_id: str | None = None
    lineas: list[LineaPegada] = Field(default_factory=list)


class SkuProveedorFila(BaseModel):
    clave: str
    sku: str


class SkuProveedorCarga(BaseModel):
    """Lo que publica el motor: la equivalencia codigo -> SKU del portal."""

    proveedor: str
    filas: list[SkuProveedorFila] = Field(default_factory=list)
