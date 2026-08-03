"""Equivalencia entre el codigo de Curifor y el SKU del portal del proveedor.

Curifor usa "<rubro> <codigo>" ("19 SZ6Z3B437B"). El portal de Ford pide su
formato con barras ("SZ6Z/3B437/B/"), que separa prefijo/basico/sufijos y NO se
deriva con una regla: hay que mirarlo en la lista de Ford. Antes el comprador
hacia esa conversion con un BUSCARV contra una tabla de 111.773 filas pegada en
su Excel.

La llena el motor desde la misma lista de precios que ya lee, con
`POST /api/admin/sku-proveedor`. Se guarda por CLAVE normalizada (sin rubro y
solo alfanumerico) y no por codigo completo: asi un mismo repuesto sirve para
todos los rubros con que Curifor lo tenga cargado.
"""
from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class SkuProveedor(Base):
    __tablename__ = "sku_proveedor"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    # Proveedor del portal: FORD, GILDEMEISTER, ...
    proveedor: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Codigo normalizado (sin rubro, solo alfanumerico, mayuscula).
    clave: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # SKU tal cual lo quiere el portal.
    sku: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("ix_sku_proveedor_prov_clave", "proveedor", "clave"),
    )
