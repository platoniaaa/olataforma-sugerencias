"""Requerimiento de compra: lo arma un vendedor de sucursal, lo revisa el comprador.

Antes esto viajaba por correo. El vendedor escribia los codigos y las cantidades en
un mail, el comprador los pegaba en su Excel. Dos transcripciones a mano, ninguna
trazabilidad y ninguna forma de saber que paso con lo que se pidio.

Aca el vendedor arma un carro contra la lista de precios de Curifor —solo puede
pedir lo que existe, asi que el codigo mal escrito deja de ser posible— y el
comprador lo recibe en su bandeja con el mismo contexto que usa para decidir.

Se guarda una FOTO de la descripcion y el precio al momento de enviarlo. La lista
de precios se recarga todos los dias; sin la foto, un requerimiento de la semana
pasada mostraria precios que el vendedor nunca vio y la conversacion se vuelve
imposible ("yo pedi eso a otro precio").
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Float, ForeignKey, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


# Flujo real, en orden:
#   enviado      el vendedor lo mando; el comprador todavia no lo abre.
#   en_revision  el comprador lo abrio y esta decidiendo.
#   procesado    se compro (o se resolvio con traslado). Fin del camino.
#   rechazado    no se compra. Lleva nota del comprador para que el vendedor sepa.
ESTADOS = ("enviado", "en_revision", "procesado", "rechazado")

# Un requerimiento cerrado no se toca mas: es el registro de lo que se decidio.
CERRADOS = ("procesado", "rechazado")


class Requerimiento(Base):
    __tablename__ = "requerimiento"

    # El id es el folio con el que se habla del requerimiento ("el 27"), asi que
    # es correlativo y no un uuid.
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Sucursal que pide. No la escribe el vendedor: sale de su usuario.
    sucursal_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    nombre_sucursal: Mapped[str | None] = mapped_column(String, nullable=True)

    creado_por: Mapped[str] = mapped_column(String, nullable=False, index=True)
    creado_por_nombre: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_now, nullable=False, index=True
    )

    estado: Mapped[str] = mapped_column(String, nullable=False, default="enviado", index=True)
    # Contexto que el vendedor quiera dar ("es para el taller, lo necesito el jueves").
    nota: Mapped[str | None] = mapped_column(Text, nullable=True)

    revisado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    revisado_en: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Respuesta del comprador. Obligatoria al rechazar: un "no" sin motivo obliga
    # al vendedor a volver a preguntar por correo, que es justo lo que se saca.
    nota_comprador: Mapped[str | None] = mapped_column(Text, nullable=True)

    lineas: Mapped[list["RequerimientoLinea"]] = relationship(
        back_populates="requerimiento",
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="RequerimientoLinea.id",
    )

    __table_args__ = (Index("ix_requerimiento_tenant_estado", "tenant_id", "estado"),)


class RequerimientoLinea(Base):
    __tablename__ = "requerimiento_linea"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    requerimiento_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("requerimiento.id", ondelete="CASCADE"), nullable=False, index=True
    )

    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Foto de la lista de precios al enviar (ver el docstring del modulo).
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    precio_lista: Mapped[float | None] = mapped_column(Float, nullable=True)

    cantidad_pedida: Mapped[float] = mapped_column(Float, nullable=False)
    # Lo que el comprador decidio comprar. NULL mientras no la haya tocado: asi se
    # distingue "todavia no la reviso" de "la dejo igual a la pedida".
    cantidad_aprobada: Mapped[float | None] = mapped_column(Float, nullable=True)
    comentario: Mapped[str | None] = mapped_column(Text, nullable=True)

    requerimiento: Mapped[Requerimiento] = relationship(back_populates="lineas")
