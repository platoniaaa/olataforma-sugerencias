"""Tabla `stock_transito`: unidades ya pedidas que todavia no llegan.

El motor ya calculaba este numero, pero solo lo publicaba pegado a las filas del
sugerido (`sugerido.stock_en_transito_suc`). El sugerido es un subconjunto chico
del catalogo -1.936 filas para Linderos de 409K productos-, asi que cuando un
vendedor pedia un repuesto que el modelo no evalua (que es el caso normal: pide
justo lo que no se stockea) el comprador no tenia forma de saber si ya venia en
camino, y podia comprar de nuevo algo que ya estaba pedido.

Es una FOTO, no un historico: se reemplaza completa en cada corrida oficial.
"""
from datetime import date

from sqlalchemy import Date, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class StockTransito(Base):
    __tablename__ = "stock_transito"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    producto: Mapped[str] = mapped_column(String, nullable=False)
    sucursal_id: Mapped[str | None] = mapped_column(String, nullable=True)
    cantidad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)

    # OC mas antigua del grupo. "Vienen 5" no dice lo mismo que "vienen 5 pedidas
    # hace 4 meses": lo segundo es una OC que probablemente no va a llegar.
    pedido_desde: Mapped[date | None] = mapped_column(Date, nullable=True)

    __table_args__ = (
        Index("ix_transito_producto", "producto", "tenant_id"),
        Index("ix_transito_producto_sucursal", "producto", "sucursal_id"),
    )
