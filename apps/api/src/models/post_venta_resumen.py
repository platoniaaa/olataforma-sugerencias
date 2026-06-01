"""Resumen agregado de la Planilla Post Venta (periodo x sucursal).

Se recalcula completo en cada carga del job push_to_cloud. Sirve para que los
endpoints de /ventas respondan rapido sin tener que parsear el JSON posicional
de cada fila de post_venta_fila.
"""
from sqlalchemy import Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class PostVentaResumen(Base):
    __tablename__ = "post_venta_resumen"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    periodo: Mapped[str] = mapped_column(String, nullable=False)  # YYYYMM
    sucursal: Mapped[str | None] = mapped_column(String, nullable=True)
    total_clp: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    total_unidades: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    n_lineas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        Index("ix_pvr_periodo_suc", "periodo", "sucursal", "tenant_id"),
    )
