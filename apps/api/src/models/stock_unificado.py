"""Stock real por producto-bodega. Lo publica el motor en cada corrida oficial.

Se reemplaza completo en cada push. Granularidad: 1 fila por (producto, bodega, origen)
para soportar productos que existen en más de una empresa (Curifor / Frontera).

Sale de los Excel de "Stock bodegas" que el motor ya lee para calcular el sugerido.
Hasta jul-2026 la llenaba el Power BI Desktop, y al retirarlo quedó congelada: el
catálogo mostraba stock viejo como si fuera de hoy.
"""
from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class StockUnificado(Base):
    __tablename__ = "stock_unificado"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    producto: Mapped[str] = mapped_column(String, nullable=False)
    bodega: Mapped[str | None] = mapped_column(String, nullable=True)
    sucursal_id: Mapped[str | None] = mapped_column(String, nullable=True)
    stock: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    origen: Mapped[str | None] = mapped_column(String, nullable=True)

    __table_args__ = (
        Index("ix_stock_producto", "producto", "tenant_id"),
        Index("ix_stock_sucursal", "sucursal_id"),
    )
