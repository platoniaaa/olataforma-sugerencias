"""Tabla `sugerencia_recurrente`: regla que crea sugerencias manuales periódicamente.

Cada N días (hasta una fecha de término opcional) la plataforma re-aplica la sugerencia:
archiva la instancia anterior creada por esta regla y crea una nueva (modo "mantener
vigente", sin acumular). El disparo lo hace un cron diario (GitHub Actions).
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import Boolean, Date, DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class SugerenciaRecurrente(Base):
    __tablename__ = "sugerencia_recurrente"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    modo: Mapped[str] = mapped_column(String, nullable=False)  # "individual" | "grupo"
    producto: Mapped[str | None] = mapped_column(String, nullable=True)
    sucursal_id: Mapped[str | None] = mapped_column(String, nullable=True)
    filtros: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON (modo grupo)

    unidades: Mapped[int] = mapped_column(Integer, nullable=False)
    # Si es por dias de inventario, lo guardamos para recalcular en cada ejecucion
    # (la demanda diaria del BI puede cambiar entre disparos).
    dias_inventario: Mapped[int | None] = mapped_column(Integer, nullable=True)
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)

    cada_dias: Mapped[int] = mapped_column(Integer, nullable=False)
    proxima_ejecucion: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    fecha_fin: Mapped[date | None] = mapped_column(Date, nullable=True)
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)
    ultima_ejecucion: Mapped[date | None] = mapped_column(Date, nullable=True)

    creado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
