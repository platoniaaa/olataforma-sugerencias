"""Tabla `linea_pedida`: que del sugerido ya se pidio de verdad.

Cierra la mitad del ciclo que hoy vive fuera de la plataforma: el sugerido dice
"pide 13", alguien emite la OC, y la plataforma nunca se entera. Sin este
registro el mismo producto se vuelve a sugerir al dia siguiente como si nada, y
no hay forma de medir cuanto de lo sugerido se compro realmente.

La otra mitad (confirmar la recepcion contra el seguimiento de compras) se
completa sola cuando el seguimiento entre a la plataforma: los campos
`recibido`/`fecha_recepcion` ya estan para eso.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Float, Index, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LineaPedida(Base):
    __tablename__ = "linea_pedida"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sucursal_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    unidades: Mapped[float] = mapped_column(Float, nullable=False, default=0)

    # Numero de orden de compra: la llave para cruzar con el seguimiento.
    n_oc: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    proveedor: Mapped[str | None] = mapped_column(String, nullable=True)

    recibido: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    fecha_recepcion: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    creado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)

    __table_args__ = (
        Index("ix_pedida_prod_suc", "producto", "sucursal_id"),
    )
