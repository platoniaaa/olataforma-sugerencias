"""Tablas de Fuentes de datos: de donde saca el motor cada archivo y que encontro.

Hasta oct-2026 el motor sabia que archivo leer por dos variables del `.env` del PC
(`MOTOR_CRUDOS_DIR`, `MOTOR_STOCK_DIR`) y patrones escritos en su codigo. Un archivo
nuevo en la carpeta boto la corrida diaria tres veces y nadie podia ver que archivo
habia leido ni de que fecha era. Con estas dos tablas la configuracion pasa a ser
DATO que edita un admin, y cada corrida deja su reporte.

- `fuente_config`: **append-only**, igual que `configuracion_modelo`. La vigente es
  la de mayor `version` del tenant; revertir inserta una copia. Sin filas, el modo
  es `sin_configurar` y el motor sigue con su `.env`.
- `motor_corrida`: una fila por corrida. El motor manda un reporte al partir y otro
  al terminar, con el mismo `id`, y los dos caen en la misma fila.

La configuracion y el reporte van como JSON en `Text` (lo valida Pydantic en
`schemas/fuentes.py`): `db.py` ya acumula decenas de `ALTER TABLE`, y asi un campo
nuevo del motor o un tipo de carpeta de otra empresa no necesita migracion. Las
dos tablas son nuevas, asi que las crea `create_all`.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import Boolean, DateTime, Index, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


class FuenteConfig(Base):
    __tablename__ = "fuente_config"
    # Dos admins guardando a la vez no pueden crear la misma version: el segundo
    # choca con esta restriccion y recibe un 409 en vez de pisar al primero.
    __table_args__ = (
        UniqueConstraint("tenant_id", "version", name="uq_fuente_config_tenant_version"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    # JSON de `ConfigFuentes` (modo, pc_titular, pcs, catalogo, carpetas, fuentes).
    config: Mapped[str] = mapped_column(Text, nullable=False)
    # sha256 del JSON canonico: el motor lo informa y asi se sabe con que version corrio.
    hash: Mapped[str] = mapped_column(String, nullable=False)
    # JSON: que cambio respecto de la version anterior (["stock_bodegas"], ["modo"],
    # ["pc_titular"], ["carpeta:databi_datos"], ["pcs"]). Alimenta el historial por fuente.
    claves_cambiadas: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    nota: Mapped[str] = mapped_column(Text, nullable=False)
    # Version que se copio al revertir (null si no es una reversa).
    revierte_a: Mapped[int | None] = mapped_column(Integer, nullable=True)
    creado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, index=True)


class MotorCorrida(Base):
    __tablename__ = "motor_corrida"
    __table_args__ = (
        Index("ix_motor_corrida_tenant_iniciada", "tenant_id", "iniciada_en"),
    )

    # UUID que genera el motor: el reporte de inicio y el de fin caen en la misma fila.
    id: Mapped[str] = mapped_column(String, primary_key=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    # Hostname del PC que corrio.
    pc: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # oficial | comparacion | probar
    tipo: Mapped[str] = mapped_column(String, nullable=False)
    # Si el PC era titular segun la configuracion que uso.
    titular: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # Si la corrida publico el sugerido en la plataforma.
    publico: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    iniciada_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=_now)
    terminada_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # en_curso | ok | frenada | fallo | incompleta | cortada | no_titular
    resultado: Mapped[str] = mapped_column(String, nullable=False, default="en_curso")
    # El texto de `_fallar`, como sale en el log (el panel lo traduce).
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    # plataforma | cache | env
    config_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    config_version: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Commit corto + rama del motor.
    version_motor: Mapped[str | None] = mapped_column(String, nullable=True)
    # JSON: {fuentes: {clave: estado}, carpetas: [listado], avisos: [...]}.
    reporte: Mapped[str | None] = mapped_column(Text, nullable=True)
    # JSON: lo que el motor usa hoy (catalogo, carpetas, fuentes). Desde aca se siembra.
    config_efectiva: Mapped[str | None] = mapped_column(Text, nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now)
