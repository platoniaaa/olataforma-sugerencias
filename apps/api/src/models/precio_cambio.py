"""Historia de la lista de precios: que cambio y que se mando al ERP.

`precio_cambio` es lo que responde "que paso desde la ultima vez que mire": cada
recalculo compara el valor nuevo contra el que habia y deja una fila por
diferencia (la procedencia paso de Nacional a Importado, el costo subio, el
stock se fue a cero, el precio final se movio). La pantalla las muestra como
pendientes hasta que alguien las marca como vistas.

`precio_envio` es la memoria de lo que ya se subio al ERP, por producto. Con
eso "exportar solo las diferencias" es una resta: lo que hoy da el calculo
contra lo ultimo que se envio. Antes vivia en un archivo local del PC que corria
el .exe (`Envios\\_estado\\`); en la base queda compartido y auditable.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _uuid() -> str:
    return str(uuid.uuid4())


class PrecioCambio(Base):
    __tablename__ = "precio_cambio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)

    # "procedencia" | "costo" | "stock" | "precio" | "tipo"
    campo: Mapped[str] = mapped_column(String, nullable=False)
    antes: Mapped[str | None] = mapped_column(Text, nullable=True)
    despues: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Agrupa los cambios de una misma corrida.
    corrida_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    detectado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    visto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, index=True)
    visto_por: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("ix_precio_cambio_pendiente", "tenant_id", "visto", "producto"),
    )


class PrecioEnvio(Base):
    __tablename__ = "precio_envio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)

    precio: Mapped[float | None] = mapped_column(Float, nullable=True)
    costo: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Todos los productos de una misma exportacion comparten el lote.
    lote_id: Mapped[str] = mapped_column(String, nullable=False, default=_uuid, index=True)
    enviado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    enviado_por: Mapped[str | None] = mapped_column(String, nullable=True)
