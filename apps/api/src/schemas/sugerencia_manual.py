"""Schemas de las sugerencias manuales."""
from datetime import date, datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from .sugerido import SugeridoFiltros


class SugerenciaManualCreate(BaseModel):
    producto: str
    sucursal_id: str
    unidades: int = Field(gt=0, description="Unidades adicionales (entero positivo)")
    motivo: str | None = None


class SugerenciaManualMasiva(BaseModel):
    """Crea la misma cantidad para todos los productos que cumplen los filtros."""

    filtros: SugeridoFiltros = Field(default_factory=SugeridoFiltros)
    unidades: int = Field(gt=0, description="Unidades adicionales para cada producto")
    motivo: str | None = None


class SugerenciaManualMasivaResultado(BaseModel):
    creadas: int


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


class RecurrenteCreate(BaseModel):
    modo: Literal["individual", "grupo"]
    producto: str | None = None
    sucursal_id: str | None = None
    filtros: SugeridoFiltros | None = None  # modo grupo
    unidades: int = Field(gt=0)
    motivo: str | None = None
    cada_dias: int = Field(gt=0, le=365, description="Repetir cada N días")
    fecha_fin: date | None = None


class RecurrenteOut(BaseModel):
    id: str
    modo: str
    resumen: str
    unidades: int
    motivo: str | None = None
    cada_dias: int
    proxima_ejecucion: date
    fecha_fin: date | None = None
    activa: bool
    ultima_ejecucion: date | None = None
