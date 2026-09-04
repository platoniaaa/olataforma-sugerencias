"""Politica de precios: los factores y la clasificacion por rubro.

Son la hoja `Politica` y la hoja `Rubros` del Excel de precios, pasadas a DATO
para que se editen desde la plataforma y el recalculo las lea en cada corrida.

- `politica_precio`: por par (tipo, procedencia) el factor que multiplica al
  costo (`Precio = Costo x Factor`). El descuento maximo y el margen que queda
  despues de aplicarlo son informativos: no entran al calculo, pero son lo que
  Abastecimiento mira para decidir el factor.
- `politica_rubro`: que tipo le corresponde a cada rubro del ERP ("71" es
  Liviano, "13" es Pesado) y, si aplica, una procedencia forzada que le gana a
  todo lo demas (los rubros 40, 45, 84, 86, 93 y 97 son siempre nacionales).

Un cambio aca mueve miles de precios en la proxima corrida: por eso la edicion
es de admin y queda en la auditoria con quien y cuando.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PoliticaPrecio(Base):
    __tablename__ = "politica_precio"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Tal como se escriben en el Excel: "Liviano", "Pesado", "Filtro Liviano",
    # "Neumatico" (singular, sin tilde). La comparacion es insensible a mayusculas.
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    # "Nacional" | "Importado". Algunos tipos tienen un solo factor para las dos
    # procedencias (Bateria, Neumatico): se guardan como dos filas iguales.
    procedencia: Mapped[str] = mapped_column(String, nullable=False)
    factor: Mapped[float] = mapped_column(Float, nullable=False)
    descuento_max: Mapped[float | None] = mapped_column(Float, nullable=True)
    margen_post: Mapped[float | None] = mapped_column(Float, nullable=True)

    actualizado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_politica_precio_clave", "tenant_id", "tipo", "procedencia", unique=True),
    )


class PoliticaRubro(Base):
    __tablename__ = "politica_rubro"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # El prefijo del codigo del ERP, como texto ("05", "71", "100"). Se guarda tal
    # cual viene: "05" y "5" son rubros distintos para el ERP.
    rubro: Mapped[str] = mapped_column(String, nullable=False)
    tipo: Mapped[str | None] = mapped_column(String, nullable=True)
    procedencia_forzada: Mapped[str | None] = mapped_column(String, nullable=True)

    actualizado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_politica_rubro_clave", "tenant_id", "rubro", unique=True),
    )
