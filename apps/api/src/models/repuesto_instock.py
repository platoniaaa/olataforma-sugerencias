"""Tabla `repuesto_instock`: repuestos de pauta que deben estar SIEMPRE en bodega.

Son los repuestos de las pautas de mantención de los modelos que Curifor atiende
en taller. La regla de negocio es simple: en las sucursales con taller nunca
puede haber menos de `minimo` unidades, aunque el modelo del BI no las pida
(mantención agendada = venta segura, quebrar stock es perder el trabajo).

La lista NO se escribe a mano: sale de las pautas del fabricante con
`scripts/extraer_instock_pautas.py` (genera `src/data/pautas_instock.csv`) y se
carga con `python -m src.jobs.cargar_instock`, que cruza el part number de la
pauta contra el codigo de producto del maestro.

Granularidad: 1 fila por producto. Las sucursales donde aplica NO son columna de
esta tabla: son las sucursales con taller y viven en
`services/instock_service.SUCURSALES_INSTOCK`.
"""
from sqlalchemy import Boolean, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class RepuestoInstock(Base):
    __tablename__ = "repuesto_instock"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Codigo de producto del maestro, CON rubro (ej. "95 2630035505"). Es la llave
    # con la que se cruza contra el sugerido.
    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    # Codigo tal como viene en la pauta del fabricante, sin rubro (ej. "2630035505").
    # Un mismo part number puede existir bajo varios rubros: son varias filas.
    part_number: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    marca: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Modelos de la pauta que usan el repuesto ("F-150, Ranger"). Es lo que se
    # muestra en la columna "InStock Modelos" del sugerido.
    modelos: Mapped[str | None] = mapped_column(String, nullable=True)
    # Operacion de la pauta ("Filtro de Aceite"), para poder auditar de donde salio.
    operacion: Mapped[str | None] = mapped_column(String, nullable=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)

    # Unidades que nunca pueden faltar en una sucursal con taller.
    minimo: Mapped[int] = mapped_column(Integer, nullable=False, default=2)

    # De donde salio la fila: "pauta" (el CSV del fabricante) o "manual" (alguien
    # la agrego desde la plataforma).
    #
    # No es informativo: la carga BORRA la lista entera y la reinserta desde el
    # CSV, y desde ago-2026 esa carga se dispara sola en cada corrida del motor.
    # Sin esta columna, un repuesto agregado a mano desapareceria en horas y nadie
    # se enteraria. `cargar_instock` borra solo las filas con origen "pauta".
    origen: Mapped[str] = mapped_column(String, nullable=False, default="pauta",
                                        index=True)
    # Por que se agrego. Solo para las manuales: la pauta ya se explica sola.
    motivo: Mapped[str | None] = mapped_column(Text, nullable=True)
    creado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[str | None] = mapped_column(String, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, index=True)

    __table_args__ = (
        Index("ix_instock_producto_tenant", "producto", "tenant_id", unique=True),
    )
