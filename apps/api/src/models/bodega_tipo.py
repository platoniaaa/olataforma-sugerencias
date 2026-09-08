"""Tabla `bodega_tipo`: que bodegas son reales y cuales no.

El stock del ERP mezcla bodegas fisicas con bodegas de proceso: danados,
devolucion, scrap, PE por regularizar, importacion en transito. Para decidir un
precio solo cuenta lo que se puede vender, asi que la lista de precios mira solo
las **REAL**.

Tres tipos, tal como los clasifico Abastecimiento:

- `REAL`: bodega fisica de la que se vende.
- `VIRT`: bodega de proceso (danados, devolucion, scrap). El stock existe pero no
  esta disponible.
- `ELIM`: bodega dada de baja. Si todavia aparece con stock, es residuo.

Es una dimension, no un dato de la corrida: cambia pocas veces al ano y la
mantiene una persona, igual que `politica_rubro`. Por eso vive en su propia tabla
y ningun job la pisa; se carga desde `POST /api/admin/bodegas-tipo`.

**La clave se guarda normalizada** (`clave`): el mismo deposito aparece escrito
de varias formas entre el ERP y el Excel -"CHILLAN 2" y "CHILLAN2", "TALCA (2)" y
"TALCA(2)"- y comparar el texto crudo dejaba 1,4 millones de unidades sin
clasificar.
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base

REAL = "REAL"
VIRT = "VIRT"
ELIM = "ELIM"


def _now() -> datetime:
    return datetime.now(timezone.utc)


class BodegaTipo(Base):
    __tablename__ = "bodega_tipo"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Nombre tal como viene del ERP, para poder leerlo en pantalla.
    bodega: Mapped[str] = mapped_column(String, nullable=False)
    # El nombre sin espacios ni signos, en mayusculas y sin tildes. Es por donde
    # se cruza contra `stock_unificado.bodega`.
    clave: Mapped[str] = mapped_column(String, nullable=False, index=True)
    tipo: Mapped[str] = mapped_column(String, nullable=False)

    actualizado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_bodega_tipo_tenant_clave", "tenant_id", "clave", unique=True),
    )
