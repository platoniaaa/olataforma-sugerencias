"""Tabla `venta_historica`: la venta desde 2018, agregada por mes.

Distinta de `venta_mensual`, que son los ultimos 12 meses que el sugerido usa
para calcular la demanda y se reemplaza en cada sync. Esta es el historico
completo para CONSULTA: responde "¿como se vendio esto en 2019?" sin que nadie
tenga que bajar un Excel de 40 MB.

Se guarda agregada por (periodo, producto, sucursal) y no transaccion por
transaccion: 1,89 millones de lineas se convierten en 594 mil filas (~45 MB) sin
perder nada de lo que se consulta a este nivel.
"""
from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class VentaHistorica(Base):
    __tablename__ = "venta_historica"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    periodo: Mapped[str] = mapped_column(String, nullable=False, index=True)  # YYYYMM
    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sucursal: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    cantidad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Venta neta en CLP del periodo (sin impuestos), para consultas por valor.
    neto: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Cuantas lineas de venta se agregaron en esa fila (contexto del dato).
    n_lineas: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_vh_prod_periodo", "producto", "periodo"),
        Index("ix_vh_periodo_suc", "periodo", "sucursal"),
    )
