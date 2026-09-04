"""Tabla `precio_override`: lo que las personas deciden sobre un precio.

Es la contraparte humana de `precio_producto`. Aca viven las dos columnas que
Hugo agrego al Excel (Obs Precio y Precio Fijo), la marca de Congelar, y el
tipo o la procedencia cuando alguien los escribio a mano porque la regla se
equivocaba.

Ningun job escribe en esta tabla. Nunca. El recalculo la LEE para saber que
precio respetar y sigue de largo. Es lo que hace imposible que una corrida pise
un precio fijo: en el Excel las dos cosas convivian en la misma fila y habia que
tener cuidado en cada corrida; aca son tablas distintas y el cuidado sobra.

Orden en que gana cada decision (ver `precios_service.calcular`):
  1. `precio_fijo`      -> ese es el precio, pase lo que pase con el costo.
  2. `congelar`         -> se queda con el precio que tenia al momento de
                           congelar (`congelado_precio`), aunque el costo cambie.
  3. `no_producto`      -> no lleva precio (servicios, cargos, mano de obra).
  4. `tipo_manual` / `procedencia_manual` -> cambian el factor que se aplica,
                           pero el precio se sigue calculando.
"""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PrecioOverride(Base):
    __tablename__ = "precio_override"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    producto: Mapped[str] = mapped_column(String, nullable=False)

    precio_fijo: Mapped[float | None] = mapped_column(Float, nullable=True)
    congelar: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # El precio que tenia cuando se congelo. Se anota al marcar `congelar`, no
    # en cada corrida: si se recalculara, congelar no congelaria nada.
    congelado_precio: Mapped[float | None] = mapped_column(Float, nullable=True)
    congelado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    tipo_manual: Mapped[str | None] = mapped_column(String, nullable=True)
    procedencia_manual: Mapped[str | None] = mapped_column(String, nullable=True)
    # Servicios, cargos y mano de obra: existen en el ERP pero no llevan precio
    # de lista (era la hoja No_Productos del Excel).
    no_producto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # La "Obs Precio" del Excel: por que este precio no sigue la regla.
    obs: Mapped[str | None] = mapped_column(Text, nullable=True)
    editado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    editado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_precio_override_clave", "tenant_id", "producto", unique=True),
    )
