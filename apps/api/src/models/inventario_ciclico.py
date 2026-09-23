"""Tablas del modulo Inventario ciclico (prefijo `ic_`).

Cada lunes se cargan los productos que cada bodega debe contar esa semana. Bodega
registra lo que conto, una observacion y, si se le pide, evidencia (foto o PDF).
Con eso jefatura ve el avance y las diferencias contra el stock del sistema.

Los permisos del modulo viven en `ic_rol` y no en `usuario`, para no mezclar el
acceso a inventario con el del sugerido de compras.
"""
import uuid
from datetime import date, datetime, timezone

from sqlalchemy import (
    Boolean,
    Date,
    DateTime,
    Float,
    Index,
    Integer,
    LargeBinary,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

ROLES = ("admin", "bodega")


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class IcItem(Base):
    """Un producto asignado a una sucursal para contarse en una semana."""

    __tablename__ = "ic_item"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor")
    # Lunes de la semana a la que pertenece la asignacion.
    semana: Mapped[date] = mapped_column(Date, nullable=False)
    sucursal_id: Mapped[str] = mapped_column(String, nullable=False)
    producto: Mapped[str] = mapped_column(String, nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)
    clase: Mapped[str] = mapped_column(String, nullable=False)
    # Stock segun sistema al momento de la carga.
    cantidad_sistema: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    costo_unitario: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    requiere_evidencia: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    cantidad_contada: Mapped[float | None] = mapped_column(Float, nullable=True)
    observacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    contado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    contado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    cargado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    cargado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, onupdate=_now
    )

    __table_args__ = (
        UniqueConstraint("tenant_id", "semana", "sucursal_id", "producto", name="uq_ic_item"),
        Index("ix_ic_item_semana_suc", "tenant_id", "semana", "sucursal_id"),
        Index("ix_ic_item_producto", "tenant_id", "producto"),
    )


class IcEvidencia(Base):
    """Foto o archivo que respalda el conteo de un item.

    Se guarda en la misma base: la plataforma no tiene almacenamiento de archivos
    y el volumen es chico (las fotos se reducen en el celular antes de subir)."""

    __tablename__ = "ic_evidencia"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    item_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String, nullable=False)
    content_type: Mapped[str] = mapped_column(String, nullable=False)
    tamano: Mapped[int] = mapped_column(Integer, nullable=False)
    contenido: Mapped[bytes] = mapped_column(LargeBinary, nullable=False)
    subido_por: Mapped[str | None] = mapped_column(String, nullable=True)
    subido_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)


class IcRol(Base):
    """Quien puede usar el modulo y con que rol.

    admin: carga la semana y ve todo. bodega: cuenta en sus sucursales.
    `sucursales` es una lista JSON de sucursal_id; vacia = todas (menos el CD).
    Los admin de la plataforma (usuario.es_admin) son admin aqui sin fila."""

    __tablename__ = "ic_rol"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    rol: Mapped[str] = mapped_column(String, nullable=False)
    sucursales: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
