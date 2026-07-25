"""Tabla `lead_time_proveedor_sucursal`: el lead time que CALCULO el motor.

No es configuracion: es el resultado de promediar el historial de OC (dias entre
la orden y la recepcion) por proveedor y sucursal, descartando la cola de
outliers. El motor la publica en cada corrida y la plataforma la muestra en el
modulo de Lead time de Calibracion.

Sirve para entender de donde sale el numero: cuando el sugerido de un producto se
ve raro, lo primero que se mira es el lead time de su proveedor y con cuantas
muestras se calculo (N Muestras bajo = promedio poco confiable).
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class LeadTimeProveedorSucursal(Base):
    __tablename__ = "lead_time_proveedor_sucursal"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    proveedor: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Nulo = la fila es el lead time GLOBAL del proveedor (todas las sucursales).
    sucursal_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    lead_time_dias: Mapped[float] = mapped_column(Float, nullable=False)
    # Cuantas OC entraron al promedio. Pocas muestras = numero poco confiable.
    n_muestras: Mapped[int | None] = mapped_column(Integer, nullable=True)
