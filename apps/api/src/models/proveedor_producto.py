"""A quien se le compra cada producto (`proveedor_producto`).

El proveedor no es un dato del maestro: se DEDUCE de las ordenes de compra
historicas. El motor ya hacia esa deduccion, pero solo para los pares
producto x sucursal que evalua, y la plataforma recibia el resultado dentro de
la tabla `sugerido`.

Eso dejaba en blanco a las filas que el motor no calcula —minimo InStock y
sugerencias manuales—, que la plataforma inyecta despues. Caso real (10-08-2026):
de 114 filas sin proveedor, 14 correspondian a productos con OC conocidas; una de
ellas, `25 KV6Z9155D`, tenia 78 ordenes a FORD. No es cosmetico:
`compras_service` filtra por `proveedor IS NOT NULL`, asi que esas lineas no
llegaban a ningun carro de compra.

Esta tabla trae la deduccion para TODO producto con OC, exista o no en el
sugerido de hoy. Es una FOTO: se reemplaza completa en cada corrida oficial.
"""
from sqlalchemy import Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ProveedorProducto(Base):
    __tablename__ = "proveedor_producto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Codigo de Curifor, con rubro ("25 KV6Z9155D").
    producto: Mapped[str] = mapped_column(String, nullable=False)
    # Razon social deducida de las OC.
    proveedor: Mapped[str] = mapped_column(String, nullable=False)

    __table_args__ = (
        Index("ix_proveedor_producto_prod", "producto", "tenant_id"),
    )
