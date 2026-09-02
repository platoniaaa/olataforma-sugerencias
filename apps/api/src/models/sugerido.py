"""Tabla `sugerido`: snapshot pre-calculado que viene del Power BI.

Incluye los campos de la tabla del BI + las "medidas" que el BI calcula dinamicamente
(ej. total_sugerido_suc). En Fase 0 todo llega pre-calculado en el Excel/CSV que se sube.
La columna `tenant_id` esta presente desde ya para el multi-tenant de la Fase 2.
"""
from sqlalchemy import Boolean, Float, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..db import Base


class Sugerido(Base):
    __tablename__ = "sugerido"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    tenant_id: Mapped[str] = mapped_column(String, nullable=False, default="curifor", index=True)

    # Empresa del grupo (Curifor / Frontera). Viene del BI desde 2026-06.
    empresa: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # --- Identificacion producto x sucursal ---
    producto: Mapped[str] = mapped_column(String, nullable=False, index=True)
    descripcion: Mapped[str | None] = mapped_column(String, nullable=True)
    sucursal_id: Mapped[str] = mapped_column(String, nullable=False, index=True)
    nombre_sucursal: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Clasificacion / origen ---
    clasificacion_abc: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    # Meses CON venta de los ultimos 3/6/12 (la frecuencia con que se mueve el
    # repuesto en esa sucursal). Es de donde sale la clase ABC, y es el dato con
    # el que un comprador decide rapido: 6 de 12 meses se compra, 1 de 12 no.
    # El motor las venia publicando desde siempre y la carga las descartaba con
    # un "Columnas ignoradas (sin mapeo)" que nadie leyo.
    meses_con_venta_3m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meses_con_venta_6m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    meses_con_venta_12m: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Venta mes a mes de los ultimos 12, del grupo de reemplazos en esa sucursal.
    # El nombre es POSICIONAL: `venta_mes_01` es el ultimo mes cerrado y
    # `venta_mes_12` el mas antiguo. Nombrarlas por mes obligaria a agregar y
    # borrar columnas en cada corrida; a que mes corresponde el 01 lo dice
    # `periodo_ultimo_mes`, que el motor publica en la misma fila.
    # Float y no Integer: hay granel (litros, ml) y las notas de credito restan.
    venta_mes_01: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_02: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_03: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_04: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_05: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_06: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_07: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_08: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_09: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_10: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_11: Mapped[float | None] = mapped_column(Float, nullable=True)
    venta_mes_12: Mapped[float | None] = mapped_column(Float, nullable=True)
    # Promedio simple de las columnas de arriba, SIN winsorizar: el comprador tiene
    # que poder sumar los meses y que le de esto. `demanda_mensual` recorta los
    # peaks a proposito y por eso no coincide con `prom_vta_12m`.
    prom_vta_3m: Mapped[float | None] = mapped_column(Float, nullable=True)
    prom_vta_6m: Mapped[float | None] = mapped_column(Float, nullable=True)
    prom_vta_12m: Mapped[float | None] = mapped_column(Float, nullable=True)
    # "YYYYMM" del mes al que corresponde `venta_mes_01`.
    periodo_ultimo_mes: Mapped[str | None] = mapped_column(String, nullable=True)
    # Clase ABC del producto a nivel AGREGADO (todas las sucursales), no local.
    clasificacion_abc_agregada: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    proveedor: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    filtro1_final: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    tipo_origen: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    es_importado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    unidad_medida: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Lead time ---
    lead_time_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lt_efectivo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lt_cd_a_sucursal_dias: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lt_origen: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Abastecimiento desde CD ---
    abastece_cd: Mapped[str | None] = mapped_column(String, nullable=True)
    prioridad_cd: Mapped[int | None] = mapped_column(Integer, nullable=True)
    comprar_en_el_cd: Mapped[str | None] = mapped_column(String, nullable=True)
    tiene_stock_cd: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    # Solo en la fila del CD: sucursales cuya demanda consolida esta compra
    # centralizada (texto: "PLACILLA, RANCAGUA"). Para mostrar a quien abastece.
    sucursales_origen_cd: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Demanda / parametros de inventario ---
    demanda_mensual: Mapped[float | None] = mapped_column(Float, nullable=True)
    demanda_diaria: Mapped[float | None] = mapped_column(Float, nullable=True)
    desv_std_mensual: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_seguridad: Mapped[int | None] = mapped_column(Integer, nullable=True)
    punto_de_pedido: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Nivel al que se repone: CEILING(demanda diaria x (ciclo + LT) + stock seguridad).
    # Entero a proposito: es "cuantas unidades quiero tener", y el comprador tiene que
    # poder leer "mi maximo es 2, tengo 1, por eso pide 1". Lo calcula la plataforma en
    # la carga (`services/nivel_maximo.py`), no viene en el archivo del motor.
    nivel_maximo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    costo_unitario: Mapped[float | None] = mapped_column(Float, nullable=True)
    pedir: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    reemplazos: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Medidas pre-calculadas del BI ---
    sugerido_suc: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_activo_suc: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_en_transito_suc: Mapped[float | None] = mapped_column(Float, nullable=True)
    stock_en_cd: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugerido_traslado: Mapped[float | None] = mapped_column(Float, nullable=True)
    sugerido_compra_neto: Mapped[float | None] = mapped_column(Float, nullable=True)
    total_sugerido_suc: Mapped[float | None] = mapped_column(Float, nullable=True, index=True)
    total_valor_sugerido_clp: Mapped[float | None] = mapped_column(Float, nullable=True)
    pedir_flag: Mapped[str | None] = mapped_column(String, nullable=True)
    # Traslado lateral sugerido: "N unidades desde X; M desde Y" (medida del BI).
    trasladar_desde: Mapped[str | None] = mapped_column(String, nullable=True)

    # --- Stock por bodega/sucursal (columnas fisicas del BI, incluyen grupo de
    # reemplazo). Espejo de las columnas hardcodeadas del modelo: si se agrega
    # una sucursal alla, hay que agregarla aca tambien. ---
    stock_linderos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_curico: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_talca: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_rancagua: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_diez_de_julio_2: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_chillan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_cd_repuestos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_brasil_18: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_placilla: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_chillan_viejo: Mapped[int | None] = mapped_column(Integer, nullable=True)
    stock_talca_2: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # --- Precios FORD (cruce por codigo contra la tabla Precios del BI) ---
    # El modelo cruza el codigo del producto SIN el rubro contra el PartNumber de
    # FORD sin los "/". Vienen en blanco (None) si el producto no esta en la lista
    # de precios FORD. Enteros en CLP.
    precio_flota_ford: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # El MENOR de los precios de compra de FORD (dealer, reposicion, urgente VOR,
    # promociones, urgente +15% y flota). Los de publico quedan fuera a proposito:
    # son lo que paga el cliente, no lo que Curifor le paga a FORD. Lo calcula el
    # motor, que es donde estan las listas.
    precio_recomendado_compra: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precio_dealer_ford: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precio_publico_ford: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precio_publico_iva_ford: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precio_reposicion_ford: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precio_urgente_vor_ford: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precio_promociones_ford: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precio_urgente_recargo15_ford: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # Lista de precios de Gildemeister (Hyundai, JAC, Mahindra, Brilliance, BAIC...).
    # Tiene tres conceptos, no los ocho de FORD: sugerido al publico, dealer y
    # dealer final. Van en columnas propias para no mentir con el sufijo _ford.
    precio_sugerido_gilde: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precio_dealer_gilde: Mapped[int | None] = mapped_column(Integer, nullable=True)
    precio_final_dealer_gilde: Mapped[int | None] = mapped_column(Integer, nullable=True)

    __table_args__ = (
        Index("ix_sugerido_prod_suc", "producto", "sucursal_id"),
    )
