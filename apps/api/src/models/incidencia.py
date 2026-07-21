"""Tabla `incidencia`: mesa de reportes de errores de la plataforma.

Cuando un usuario ve algo raro (un sugerido que no cuadra, un stock que no es el
real, una pantalla que falla), lo reporta desde donde lo vio. La incidencia
guarda el contexto automaticamente (pantalla, producto, sucursal) para que quien
la revise no tenga que adivinar de que se trataba.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

# Estados del ciclo de vida de una incidencia.
ESTADOS = ("abierta", "en_revision", "resuelta", "descartada")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Incidencia(Base):
    __tablename__ = "incidencia"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    titulo: Mapped[str] = mapped_column(String, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Contexto: lo llena el frontend con lo que el usuario estaba mirando.
    pantalla: Mapped[str | None] = mapped_column(String, nullable=True)
    producto: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    sucursal_id: Mapped[str | None] = mapped_column(String, nullable=True)

    estado: Mapped[str] = mapped_column(String, nullable=False, default="abierta", index=True)
    # Respuesta de quien la revisa (se le notifica al que reporto).
    respuesta: Mapped[str | None] = mapped_column(Text, nullable=True)

    reportado_por: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    resuelto_por: Mapped[str | None] = mapped_column(String, nullable=True)

    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
