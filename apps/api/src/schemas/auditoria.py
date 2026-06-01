"""Schemas para auditoria y notificaciones."""
from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditoriaLogOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    accion: str
    entidad: str
    entidad_id: str | None = None
    usuario_email: str | None = None
    producto: str | None = None
    sucursal_id: str | None = None
    unidades: int | None = None
    dias_inventario: int | None = None
    motivo: str | None = None
    detalle: str | None = None
    creado_en: datetime


class AuditoriaPage(BaseModel):
    items: list[AuditoriaLogOut]
    total: int
    limit: int
    offset: int


class NotificacionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    tipo: str
    titulo: str
    mensaje: str | None = None
    creado_por_email: str | None = None
    producto: str | None = None
    sucursal_id: str | None = None
    creado_en: datetime
    leida: bool = False


class NotificacionesResponse(BaseModel):
    items: list[NotificacionOut]
    no_leidas: int


class MarcarLeidasRequest(BaseModel):
    ids: list[str] | None = None  # None = marcar todas
