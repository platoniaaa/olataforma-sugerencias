"""Tabla `auditoria_log`: registro de eventos sobre sugerencias (manuales y recurrentes).

Cada accion del usuario (crear, modificar, eliminar) y cada disparo automatico de una
regla recurrente queda registrado para tener trazabilidad.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class AuditoriaLog(Base):
    __tablename__ = "auditoria_log"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # creada | modificada | eliminada | recurrente_creada | recurrente_aplicada |
    # recurrente_eliminada | masiva_creada
    accion: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # sugerencia_manual | sugerencia_recurrente
    entidad: Mapped[str] = mapped_column(String, nullable=False)
    entidad_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    usuario_email: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # Snapshot para evitar joins al renderizar (las sugerencias pueden borrarse).
    producto: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    sucursal_id: Mapped[str | None] = mapped_column(String, nullable=True)
    unidades: Mapped[int | None] = mapped_column(Integer, nullable=True)
    dias_inventario: Mapped[int | None] = mapped_column(Integer, nullable=True)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Texto descriptivo extra (ej. "filtros: marca=ACDELCO", "modifico unidades 10 -> 25").
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
