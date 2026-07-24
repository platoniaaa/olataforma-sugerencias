"""Tabla `configuracion_modelo`: los parametros calibrables del modelo de sugerido.

Hasta ahora estos valores (ciclo de orden, niveles de servicio Z, lead time por
defecto, winsor) vivian como constantes en el codigo (`motor/parametros.py` y su
espejo `simulador_service.py`). Cambiar uno obligaba a editar codigo, correr
tests y redesplegar. Con esta tabla pasan a ser DATO: la plataforma los edita y
el motor los lee antes de cada corrida.

**Append-only**: cada cambio inserta una fila nueva; la vigente es la mas
reciente. Asi el historial y la reversa salen gratis (para volver atras se
inserta una copia de una version vieja), y queda registrado quien y cuando.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class ConfiguracionModelo(Base):
    __tablename__ = "configuracion_modelo"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)
    creado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    # Por que se hizo el cambio (opcional pero recomendado).
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)

    # --- Ciclo de orden (dias de cobertura extra al pedir) ---
    ciclo_orden_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=5)
    ciclo_orden_dias_cd: Mapped[int] = mapped_column(Integer, nullable=False, default=5)

    # --- Nivel de servicio (Z) por clase ABC ---
    z_a: Mapped[float] = mapped_column(Float, nullable=False, default=1.645)
    z_b: Mapped[float] = mapped_column(Float, nullable=False, default=1.282)
    z_c: Mapped[float] = mapped_column(Float, nullable=False, default=0.842)
    z_d: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Z reducido para importado abastecido por CD (A/B; C/D no aplican).
    z_imp_cd_a: Mapped[float] = mapped_column(Float, nullable=False, default=1.282)
    z_imp_cd_b: Mapped[float] = mapped_column(Float, nullable=False, default=1.036)

    # --- Otros parametros de reposicion ---
    lead_time_fallback_dias: Mapped[int] = mapped_column(Integer, nullable=False, default=8)
    winsor_k: Mapped[float] = mapped_column(Float, nullable=False, default=3.0)
