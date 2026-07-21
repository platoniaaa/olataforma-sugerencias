"""Contratos de la API de documentos (enlaces a SharePoint)."""
from __future__ import annotations

from datetime import datetime
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, field_validator

_ESQUEMAS_VALIDOS = {"http", "https"}


def _validar_url(v: str) -> str:
    """Solo http/https. Bloquea `javascript:` y `data:`, que en un enlace que la
    web renderiza serian ejecucion de codigo en el navegador del usuario."""
    v = (v or "").strip()
    if not v:
        raise ValueError("La URL es obligatoria")
    if urlparse(v).scheme.lower() not in _ESQUEMAS_VALIDOS:
        raise ValueError("La URL debe empezar con http:// o https://")
    return v


class DocumentoOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    titulo: str
    descripcion: str | None = None
    url: str
    categoria: str
    orden: int
    activo: bool
    creado_por_email: str | None = None
    actualizado_en: datetime | None = None


class DocumentoCreate(BaseModel):
    titulo: str
    url: str
    descripcion: str | None = None
    categoria: str = "General"
    orden: int = 0

    @field_validator("url")
    @classmethod
    def _url(cls, v: str) -> str:
        return _validar_url(v)

    @field_validator("titulo")
    @classmethod
    def _titulo(cls, v: str) -> str:
        v = (v or "").strip()
        if not v:
            raise ValueError("El titulo es obligatorio")
        return v


class DocumentoUpdate(BaseModel):
    titulo: str | None = None
    url: str | None = None
    descripcion: str | None = None
    categoria: str | None = None
    orden: int | None = None
    activo: bool | None = None

    @field_validator("url")
    @classmethod
    def _url(cls, v: str | None) -> str | None:
        return None if v is None else _validar_url(v)
