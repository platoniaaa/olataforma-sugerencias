"""Tabla `precio_producto`: la lista de precios que se sube al ERP.

Una fila por producto. Es la version viva de `LISTA DE PRECIOS.xlsx`: lo que
antes se recalculaba con formulas en Excel y un .exe en el PC de Hugo, aca lo
recalcula `precios_service.recalcular` leyendo el stock, el costo y las compras
que la plataforma ya recibe del motor.

Casi todas las columnas son CALCULADAS y se pisan en cada recalculo. Lo unico
humano que vive aca es `origen`: "maestro" para lo que vino del ERP y "manual"
para los productos creados desde la plataforma. Una recarga del maestro borra
solo las filas "maestro"; las manuales sobreviven (misma leccion que InStock:
sin esa columna, lo agregado a mano desaparece en la siguiente carga y nadie se
entera).

Las decisiones de las personas -precio fijo, congelar, tipo o procedencia
escritos a mano- NO estan en esta tabla sino en `precio_override`. Asi es
imposible que un recalculo las pise: la tabla que se reconstruye y la tabla que
escribe la gente son distintas.
"""
from datetime import date, datetime, timezone

from sqlalchemy import Date, DateTime, Float, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


def _now() -> datetime:
    return datetime.now(timezone.utc)


class PrecioProducto(Base):
    __tablename__ = "precio_producto"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Codigo del ERP con rubro ("71 2720142"). Es la llave con la que se cruza
    # contra stock, ventas y compras.
    producto: Mapped[str] = mapped_column(String, nullable=False)
    glosa: Mapped[str | None] = mapped_column(Text, nullable=True)
    # El prefijo del codigo, como texto ("71"). Se guarda aparte para filtrar y
    # para cruzar con `politica_rubro`.
    rubro: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # --- Clasificacion (calculada; el override le gana) ---
    tipo: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # De donde salio el tipo: "manual" | "rubro" | "glosa" | None.
    tipo_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    # La procedencia que dice el maestro del ERP (columna Procedencia).
    procedencia_maestro: Mapped[str | None] = mapped_column(String, nullable=True)
    # La que se usa para el factor: "Nacional" | "Importado" | "SIN REVISION".
    procedencia_final: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Que regla la decidio: "manual" | "rubro" | "compras" | "maestro" | "default".
    procedencia_origen: Mapped[str | None] = mapped_column(String, nullable=True)
    factor: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Insumos del calculo (foto de la ultima corrida) ---
    costo: Mapped[float | None] = mapped_column(Float, nullable=True)
    # El precio que tiene HOY el ERP (columna Precio del maestro). Sirve para ver
    # la desviacion contra el optimo y para saber si el ERP ya refleja el envio.
    precio_erp: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_transito: Mapped[float | None] = mapped_column(Float, nullable=True)
    ult_recep_importado: Mapped[date | None] = mapped_column(Date, nullable=True)
    ult_pe_nacional: Mapped[date | None] = mapped_column(Date, nullable=True)
    ultima_venta: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Precio de lista del proveedor cuando el tipo es Sugerido (Gildemeister).
    precio_sugerido: Mapped[float | None] = mapped_column(Float, nullable=True)

    # --- Resultado ---
    # Lo que da la regla sin mirar overrides.
    precio_calculado: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Lo que se manda al ERP: override si hay, calculado si no.
    precio_final: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "OK" | "FIJO" | "CONGELADO" | "SUGERIDO" | "SIN REVISION" | "NO PRODUCTO" | "SIN STOCK"
    estado: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Cambios detectados en la ultima corrida que nadie marco como vistos.
    cambios_pendientes: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # "maestro" (vino del ERP) | "manual" (creado desde la plataforma).
    origen: Mapped[str] = mapped_column(String, nullable=False, default="maestro", index=True)
    creado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    creado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)
    actualizado_en: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now)

    __table_args__ = (
        Index("ix_precio_producto_clave", "tenant_id", "producto", unique=True),
    )
