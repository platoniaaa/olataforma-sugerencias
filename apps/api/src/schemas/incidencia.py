"""Contratos de la API de incidencias."""
from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator

from ..models.incidencia import ESTADOS


class IncidenciaOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    titulo: str
    descripcion: str | None = None
    pantalla: str | None = None
    producto: str | None = None
    sucursal_id: str | None = None
    estado: str
    respuesta: str | None = None
    reportado_por: str | None = None
    resuelto_por: str | None = None
    creado_en: datetime
    actualizado_en: datetime | None = None


class IncidenciaCreate(BaseModel):
    titulo: str
    descripcion: str | None = None
    pantalla: str | None = None
    producto: str | None = None
    sucursal_id: str | None = None

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("Contanos en una linea que paso")
        return v


class IncidenciaUpdate(BaseModel):
    estado: str | None = None
    respuesta: str | None = None

    @field_validator("estado")
    @classmethod
    def _estado(cls, v: str | None) -> str | None:
        if v is None:
            return None
        if v not in ESTADOS:
            raise ValueError(f"Estado invalido. Validos: {', '.join(ESTADOS)}")
        return v


class IncidenciasResponse(BaseModel):
    items: list[IncidenciaOut]
    abiertas: int = 0
