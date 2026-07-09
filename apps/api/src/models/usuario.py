"""Usuarios de la plataforma (login por email + contrasena)."""
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class Usuario(Base):
    __tablename__ = "usuario"

    email: Mapped[str] = mapped_column(String, primary_key=True)
    password_hash: Mapped[str] = mapped_column(String, nullable=False)
    nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    # Acceso a vistas/endpoints solo de admin (ej. "Cargar datos").
    es_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Restriccion de acceso por sucursal: lista JSON de sucursal_id que el usuario
    # puede ver (ej. ["BRASIL 18","DIEZ DE JULIO"]). NULL o vacio = ve todas.
    sucursales_permitidas: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Usuario de solo lectura: ve todo (dentro de sus sucursales) pero NO puede
    # crear/editar/borrar sugerencias manuales (el backend da 403 en esas rutas).
    solo_lectura: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
