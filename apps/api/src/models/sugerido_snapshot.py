"""Tabla `sugerido_snapshot`: foto diaria y flaca del sugerido.

La tabla `sugerido` se reemplaza completa en cada sincronizacion, asi que sin
esto no queda rastro de como evoluciono un producto. El snapshot guarda una fila
por (fecha, producto, sucursal) con las pocas columnas que sirven para mirar la
historia y, mas adelante, medir la precision del modelo (lo que se sugirio contra
lo que efectivamente se vendio).

Se guarda SOLO lo que tiene actividad (sugerido o stock o punto de pedido): las
filas en cero son la mayoria y no aportan historia. Con retencion configurable
para que la base no crezca sin control.
"""
from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class SugeridoSnapshot(Base):
    __tablename__ = "sugerido_snapshot"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    fecha: Mapped[date] = mapped_column(Date, nullable=False, index=True)
    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sucursal_id: Mapped[str] = mapped_column(String, nullable=False, index=True)

    clasificacion_abc: Mapped[str | None] = mapped_column(String, nullable=True)
    total_sugerido_suc: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_activo_suc: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_en_transito_suc: Mapped[float | None] = mapped_column(Float, nullable=True)
    punto_de_pedido: Mapped[int | None] = mapped_column(Integer, nullable=True)
    demanda_diaria: Mapped[float | None] = mapped_column(Float, nullable=True)
    costo_unitario: Mapped[float | None] = mapped_column(Float, nullable=True)
    pedir: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("ix_snapshot_prod_suc_fecha", "producto", "sucursal_id", "fecha"),
    )
