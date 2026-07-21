"""Tabla `comparacion_motor`: resultado de contrastar el motor propio con el Power BI.

Mientras la plataforma se independiza del Power BI, el motor Python corre EN
SOMBRA: produce su version del sugerido, se compara contra la que esta viva, y
solo se guarda el REPORTE de esa comparacion.

Guardar el reporte y no las 19k filas del motor es deliberado: la pregunta que
hay que responder es "¿coincide?", y una tabla paralela completa duplicaria el
snapshot en la base sin que nadie la consulte. El dia que la paridad se sostenga,
el motor pasa a cargar por el endpoint oficial y esta tabla queda como bitacora
de que la migracion estaba justificada.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ComparacionMotor(Base):
    __tablename__ = "comparacion_motor"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    filas_motor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filas_bi: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filas_comunes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filas_solo_motor: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    filas_solo_bi: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    # % de filas comunes en las que TODAS las columnas comparadas coinciden.
    paridad_pct: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # JSON: coincidencias por columna y las primeras divergencias, para diagnosticar
    # sin volver a correr la comparacion.
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)
    ejecutado_por: Mapped[str | None] = mapped_column(String, nullable=True)
