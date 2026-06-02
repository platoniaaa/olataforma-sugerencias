"""Schemas de la Planilla Post Venta (metadatos y request de exportación)."""
from datetime import datetime

from pydantic import BaseModel, Field


class PostVentaMetaOut(BaseModel):
    """Metadatos del snapshot disponible para exportar."""

    columnas: list[str] = Field(default_factory=list)
    filas: int = 0
    periodos: list[str] = Field(default_factory=list)
    sucursales: list[str] = Field(default_factory=list)
    actualizado_en: datetime | None = None


class PostVentaFiltros(BaseModel):
    """Filtros de exportación (todos opcionales).

    `periodo_*` acotan por mes (YYYYMM). `fecha_*` acotan por día exacto
    (YYYY-MM-DD). Si se pasa fecha, esa gana sobre periodo (mas precisa).
    """

    periodo_desde: str | None = None
    periodo_hasta: str | None = None
    fecha_desde: str | None = None  # YYYY-MM-DD
    fecha_hasta: str | None = None  # YYYY-MM-DD
    sucursal: str | None = None
