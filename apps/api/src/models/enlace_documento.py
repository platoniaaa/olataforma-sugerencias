"""Tabla `enlace_documento`: accesos directos a archivos que viven en SharePoint.

La plataforma NO guarda los archivos (las ventas historicas desde 2018 pesan
decenas de MB por ano cada una): guarda solo el enlace, su categoria y quien lo
publico. El usuario hace clic y descarga desde SharePoint con su propia cuenta
corporativa, asi que los permisos de la biblioteca siguen mandando y no hay
copias desactualizadas dando vueltas.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class EnlaceDocumento(Base):
    __tablename__ = "enlace_documento"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    titulo: Mapped[str] = mapped_column(String, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    url: Mapped[str] = mapped_column(Text, nullable=False)

    # Agrupa la vista: "Ventas historicas", "Stock", "Seguimiento de compras"...
    categoria: Mapped[str] = mapped_column(String, nullable=False, default="General", index=True)
    # Orden manual dentro de la categoria (menor primero); empate -> por titulo.
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    creado_por_email: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )
