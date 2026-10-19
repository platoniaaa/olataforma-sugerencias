"""Tabla `solicitud_actualizacion`: pedidos de "actualizar ahora" hechos desde la web.

La plataforma corre en la nube y los Excel de "Bases de datos" viven en el PC de quien
mantiene los datos, asi que el servidor NO puede recalcular por su cuenta: no ve esos
archivos. El boton de la web solo deja una solicitud en esta tabla; un agente instalado
en ese PC la consulta cada minuto, corre el motor y vuelve a marcar el resultado aca.

Esta fila es el unico canal entre la web y ese PC. Por eso guarda tambien el desenlace
(mensaje de error incluido): sin eso, quien apreto el boton se queda mirando un spinner
sin saber si fallo, si el PC estaba apagado, o si todavia esta calculando.

Tipos (columna `tipo`):
    recalcular        correr el motor y publicar (boton "Actualizar ahora")
    actualizar_motor  bajar la ultima version del motor desde GitHub en ese PC, sin
                      recalcular nada (boton "Actualizar motor", solo admin)

Estados:
    pendiente  recien creada, ningun agente la ha tomado
    en_curso   un agente la tomo: corre el motor (22 a 35 min) o lo actualiza (1-2 min)
    ok         el agente termino bien
    error      fallo; `mensaje` dice por que
    expirada   nadie la tomo a tiempo (tipicamente: el PC esta apagado)
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, String, Text, text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

PENDIENTE = "pendiente"
EN_CURSO = "en_curso"
OK = "ok"
ERROR = "error"
EXPIRADA = "expirada"

# Estados en los que la solicitud sigue "viva" (no aceptar otra en paralelo).
ACTIVOS = (PENDIENTE, EN_CURSO)

RECALCULAR = "recalcular"
ACTUALIZAR_MOTOR = "actualizar_motor"
TIPOS = (RECALCULAR, ACTUALIZAR_MOTOR)


def _uuid() -> str:
    return str(uuid.uuid4())


def _now() -> datetime:
    return datetime.now(timezone.utc)


# La condicion del indice de abajo: los mismos estados de ACTIVOS.
_VIVA = text("estado IN ('pendiente', 'en_curso')")


class SolicitudActualizacion(Base):
    __tablename__ = "solicitud_actualizacion"
    __table_args__ = (
        # Una sola solicitud viva por tenant, garantizado por la base. El control del
        # router no basta: dos clics casi simultaneos pasan los dos antes de que el otro
        # guarde. Indice parcial: sirve igual en Postgres y en SQLite (tests). En la
        # tabla que ya existe en produccion lo crea la migracion de db.py.
        Index(
            "ux_solicitud_viva", "tenant_id", unique=True,
            sqlite_where=_VIVA, postgresql_where=_VIVA,
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=_uuid)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    estado: Mapped[str] = mapped_column(String, nullable=False, default=PENDIENTE, index=True)
    # Que se le pide al PC. Las filas de antes de que existiera la columna quedan como
    # "recalcular" (el DEFAULT de la migracion en db.py): era lo unico que se pedia.
    tipo: Mapped[str] = mapped_column(
        String, nullable=False, default=RECALCULAR, server_default=RECALCULAR
    )
    solicitado_por: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Nombre del PC que tomo la solicitud. Sirve para saber cual de las maquinas
    # respondio cuando haya mas de un agente instalado.
    agente: Mapped[str | None] = mapped_column(String, nullable=True)
    # Resultado en lenguaje de usuario (lo muestra la tarjeta de la web tal cual).
    mensaje: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Version del motor que reporto el agente al terminar ("<sha corto> <rama>").
    version: Mapped[str | None] = mapped_column(String, nullable=True)

    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, index=True
    )
    tomado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    terminado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
