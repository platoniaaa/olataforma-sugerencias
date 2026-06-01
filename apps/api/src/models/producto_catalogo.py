"""Catálogo maestro de productos (carga única desde CSV del ERP).

Se usa para que la plataforma sepa de TODOS los productos, no solo los que el BI
mete en el sugerido. Cuando el comprador busca un código en el dashboard y no está
en el sugerido, se le muestra desde aquí con las columnas del sugerido vacías.

Granularidad: 1 fila por producto. El Stock viene SUMADO de todas las bodegas del
CSV original (que trae 1 fila por producto-bodega).
"""
from sqlalchemy import Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ProductoCatalogo(Base):
    __tablename__ = "producto_catalogo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Identidad
    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    glosa: Mapped[str | None] = mapped_column(Text, nullable=True)  # descripción

    # Clasificación
    familia: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    subfamilia: Mapped[str | None] = mapped_column(String, nullable=True)
    procedencia: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    tipo_repuesto: Mapped[str | None] = mapped_column(String, nullable=True)
    categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    sub_categoria: Mapped[str | None] = mapped_column(String, nullable=True)
    tipo_producto: Mapped[str | None] = mapped_column(String, nullable=True)
    clasificacion_stock: Mapped[str | None] = mapped_column(String, nullable=True)

    # Precios / costo
    costo: Mapped[float | None] = mapped_column(Float, nullable=True)
    precio: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Stock (sumado de todas las bodegas)
    stock_total: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_minimo: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_maximo: Mapped[float | None] = mapped_column(Float, nullable=True)

    # Datos automotrices (útiles para repuestos)
    sub_modelo: Mapped[str | None] = mapped_column(String, nullable=True)
    cilindrada: Mapped[str | None] = mapped_column(String, nullable=True)
    combustible: Mapped[str | None] = mapped_column(String, nullable=True)
    anio: Mapped[str | None] = mapped_column(String, nullable=True)

    # Otros
    unidad: Mapped[str | None] = mapped_column(String, nullable=True)
    reemplazo: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_catalogo_producto_tenant", "producto", "tenant_id", unique=True),
        Index("ix_catalogo_familia_proc", "familia", "procedencia"),
    )
