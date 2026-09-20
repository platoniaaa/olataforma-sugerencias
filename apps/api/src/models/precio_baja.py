"""Tabla `precio_baja`: los productos que alguien saco de la lista de precios A MANO.

Existe por el feed del ERP. Cada semana la lista se alimenta del export del ERP
y crea lo que no esta y tiene stock; sin esta marca, un servicio o un codigo mal
creado que un comprador saco con clic derecho volveria a aparecer a la semana
siguiente, y la persona pensaria que el boton no hizo nada.

Solo se marca lo que se saca desde la pantalla (una decision de persona sobre un
producto). Las depuraciones masivas del maestro -"sin stock y sin venta desde
2025"- NO marcan: un producto de esos que vuelve a tener stock tiene que volver a
la lista, y esa es justamente la gracia del feed.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PrecioBaja(Base):
    __tablename__ = "precio_baja"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    producto: Mapped[str] = mapped_column(String, nullable=False)
    motivo: Mapped[str | None] = mapped_column(String, nullable=True)
    sacado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    sacado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_precio_baja_tenant_producto", "tenant_id", "producto", unique=True),
    )
