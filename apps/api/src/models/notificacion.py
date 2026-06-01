"""Tabla `notificacion`: avisos in-app del equipo (campanita del header).

Una notificacion se crea cuando alguien hace algo relevante (crear/modificar/eliminar
una sugerencia, crear una recurrencia). Cada usuario ve la lista y puede marcar como
leida; el campo `vistas_por_json` guarda los emails que ya la leyeron.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Notificacion(Base):
    __tablename__ = "notificacion"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    tipo: Mapped[str] = mapped_column(String, nullable=False)
    titulo: Mapped[str] = mapped_column(String, nullable=False)
    mensaje: Mapped[str | None] = mapped_column(Text, nullable=True)

    creado_por_email: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )

    # Para que la campanita pueda linkear al producto si aplica.
    producto: Mapped[str | None] = mapped_column(String, nullable=True)
    sucursal_id: Mapped[str | None] = mapped_column(String, nullable=True)

    # Lista de emails que ya marcaron leida (CSV simple para no agregar otra tabla).
    vistas_por: Mapped[str | None] = mapped_column(Text, nullable=True, default="")
