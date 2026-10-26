"""Tablas del modulo Canal Digital (reposicion semanal de una bodega del canal, hoy la 430).

Son tablas NUEVAS e independientes: ninguna reemplaza ni lee de las del sugerido actual.

  canal_digital_bodega   una fila por bodega del canal con sus parametros (tipos de venta que
                         cuentan, semanas de revision, ventana, cortes del Pareto).
  canal_digital_venta    la venta del canal por producto, semana y periodo del documento. Es
                         lo que `venta_historica` no trae (esa agrega por mes y sucursal y
                         descarta el tipo de venta y la fecha).
  canal_digital_linea    las lineas de documento del ERP que originan esa venta (una fila por
                         linea, repetidas incluidas). Con ellas la plataforma recalcula la venta
                         completa y una devolucion de un mes encuentra su venta de otro mes.
  canal_digital_politica las 27 filas de politica (cluster Frecuencia-Piezas-Valor) por bodega.
"""
from datetime import datetime

from sqlalchemy import Boolean, DateTime, Float, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class CanalDigitalBodega(Base):
    __tablename__ = "canal_digital_bodega"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    bodega: Mapped[str] = mapped_column(String, nullable=False)  # "430"
    nombre: Mapped[str] = mapped_column(String, nullable=False, default="")
    activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    # Tipos de venta del ERP que cuentan como venta del canal, separados por coma.
    tipos_venta: Mapped[str] = mapped_column(
        String, nullable=False, default="VTA ML,VTA SHOPIFY,VTA WALMART,VTA PARIS"
    )
    r_semanas: Mapped[float] = mapped_column(Float, nullable=False, default=1)
    ventana_meses: Mapped[int] = mapped_column(Integer, nullable=False, default=12)
    nuevo_meses: Mapped[int] = mapped_column(Integer, nullable=False, default=6)
    corte_a_pct: Mapped[float] = mapped_column(Float, nullable=False, default=80)
    corte_b_pct: Mapped[float] = mapped_column(Float, nullable=False, default=95)
    gestion_dias: Mapped[float] = mapped_column(Float, nullable=False, default=1)
    # Nombres de bodega del stock (ERP) que forman el disponible de este canal, separados por coma.
    bodegas_stock: Mapped[str] = mapped_column(String, nullable=False, default="BODEGA ML")
    # Bodegas cuyo stock se muestra aparte y NO suma al disponible (ML-FULL), y las informativas (CD).
    bodegas_aparte: Mapped[str] = mapped_column(String, nullable=False, default="BODEGA ML-FULL")
    bodegas_informativas: Mapped[str] = mapped_column(String, nullable=False, default="CD REPUESTOS")
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "bodega", name="uq_cd_bodega"),)


class CanalDigitalVenta(Base):
    __tablename__ = "canal_digital_venta"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    bodega: Mapped[str] = mapped_column(String, nullable=False, index=True)

    producto: Mapped[str] = mapped_column(String, nullable=False)  # codigo normalizado (sin padre)
    # Lunes de la semana en que cuenta la venta; una devolucion cuenta en la semana de la venta que anula.
    semana: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD (lunes)
    # Periodo (YYYYMM) del documento: la devolucion resta en el mes de su nota.
    periodo: Mapped[str] = mapped_column(String, nullable=False)

    unid_brutas: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    unid_devueltas: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Costo unitario del documento x unidades netas (con signo una sola vez).
    valor_costo: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    # Unidades netas que vienen de liquidaciones (se cuentan, pero quedan a la vista).
    unid_liquidacion: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    n_lineas: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    __table_args__ = (
        UniqueConstraint("tenant_id", "bodega", "producto", "semana", "periodo", name="uq_cd_venta"),
        Index("ix_cd_venta_prod", "bodega", "producto"),
        Index("ix_cd_venta_periodo", "bodega", "periodo"),
        Index("ix_cd_venta_semana", "bodega", "semana"),
    )


class CanalDigitalLinea(Base):
    __tablename__ = "canal_digital_linea"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    bodega: Mapped[str] = mapped_column(String, nullable=False)

    periodo: Mapped[str] = mapped_column(String, nullable=False)  # YYYYMM del documento
    tipo_docto: Mapped[str] = mapped_column(String, nullable=False)
    numero: Mapped[str] = mapped_column(String, nullable=False, default="")  # sin ceros a la izquierda
    fecha: Mapped[str] = mapped_column(String, nullable=False)  # YYYY-MM-DD
    tipo_venta: Mapped[str] = mapped_column(String, nullable=False)
    producto: Mapped[str] = mapped_column(String, nullable=False)  # codigo normalizado
    # Las notas de credito vienen con cantidad POSITIVA; el signo lo pone `ventas_semanales.agregar`.
    cantidad: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    costo_neto: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)  # unitario
    doc_ref: Mapped[str] = mapped_column(String, nullable=False, default="")
    nro_doc_ref: Mapped[str] = mapped_column(String, nullable=False, default="")

    # Sin unique: el origen trae lineas genuinamente repetidas y se guardan todas.
    __table_args__ = (
        Index("ix_cd_linea_periodo", "bodega", "periodo"),
        Index("ix_cd_linea_doc", "bodega", "tipo_docto", "numero"),
    )


class CanalDigitalPolitica(Base):
    __tablename__ = "canal_digital_politica"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)
    bodega: Mapped[str] = mapped_column(String, nullable=False, index=True)
    cluster: Mapped[str] = mapped_column(String, nullable=False)  # AAA .. CCC
    modo: Mapped[str] = mapped_column(String, nullable=False)  # formula | contra_pedido | minimo_fijo
    nivel_servicio: Mapped[float | None] = mapped_column(Float, nullable=True)  # fraccion (0,95)
    z: Mapped[float | None] = mapped_column(Float, nullable=True)
    minimo_fijo: Mapped[float | None] = mapped_column(Float, nullable=True)
    actualizado_por: Mapped[str | None] = mapped_column(String, nullable=True)
    actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    __table_args__ = (UniqueConstraint("tenant_id", "bodega", "cluster", name="uq_cd_politica"),)
