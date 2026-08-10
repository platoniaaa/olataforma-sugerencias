"""Tabla `reemplazo_ford`: que codigo descontinuado sustituyo a cual.

FORD publica la cadena de reemplazo en su portal (WINGS) y desde ago-2026 la
extraccion la trae junto a los precios. Sirve para dos cosas distintas:

1. **Agrupar** el stock y la demanda del codigo viejo con los del vigente, para
   no comprar de nuevo algo que ya esta en bodega bajo otro codigo. Eso lo hace
   el MOTOR y no depende de esta tabla.
2. **Avisarle al comprador** que el codigo que le pidieron esta descontinuado y
   cual es el vigente. Para eso es esta tabla.

Se guarda solo lo que toca a productos que Curifor tiene: el resto de la lista
(39.622 codigos) no se puede mostrar en ninguna pantalla.

`agrupado` distingue los dos casos de arriba. Cuando FORD marca el reemplazo
como "Sin candidato vigente" no se sabe si realmente no hay sucesor o si el
codigo consultado se armo mal, asi que ese par se muestra pero NO agrupa: se
publica con agrupado=False y sucesor_confirmado=False.

Es una FOTO: se reemplaza completa en cada corrida oficial.
"""
from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class ReemplazoFord(Base):
    __tablename__ = "reemplazo_ford"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Codigo de Curifor al que se refiere la fila.
    producto: Mapped[str] = mapped_column(String, nullable=False)

    # El vigente, en codigo de Curifor. Null cuando FORD nombra un sucesor que
    # Curifor no tiene en su maestro: ahi el aviso sirve igual ("esta
    # descontinuado") aunque no se pueda ofrecer el reemplazo.
    reemplazado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    # El mismo codigo como lo escribe FORD ("MB3Z/19N619/A/"), para buscarlo en
    # el portal cuando no esta en Curifor.
    reemplazado_por_ford: Mapped[str | None] = mapped_column(String, nullable=True)

    # Camino completo hasta el vigente ("A > B > C"), tal cual lo da FORD.
    cadena: Mapped[str | None] = mapped_column(Text, nullable=True)
    # Codigos de Curifor que ESTA pieza reemplazo, separados por "; ".
    reemplaza_a: Mapped[str | None] = mapped_column(Text, nullable=True)

    # FORD resolvio el sucesor (codigo y precio). False = "Sin candidato vigente".
    sucesor_confirmado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    # El motor efectivamente fusiono los dos codigos en un grupo.
    agrupado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)

    # Bifurcaciones, ciclos o "revisar a mano". Vacio = sin nada raro.
    aviso: Mapped[str | None] = mapped_column(Text, nullable=True)

    __table_args__ = (
        Index("ix_reemplazo_producto", "producto", "tenant_id"),
    )
