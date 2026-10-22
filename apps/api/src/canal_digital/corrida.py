"""Una corrida de Canal Digital para una bodega: clasifica y calcula el sugerido de todos los productos.

Funcion PURA: recibe por producto padre lo que ya se junto de las tablas (ventas por mes y por
semana, stock, transito, plazo, costo) y la politica, y entrega una fila por producto con todos
los intermedios. La usan el Excel de la primera version y la plataforma, para que ambos
calculen exactamente lo mismo.
"""
from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from fractions import Fraction
from typing import Iterable, Sequence

from .clasificacion import (
    ESTADO_CLASIFICADO, ParametrosClasificacion, ResultadoClasificacion, VentaProducto, clasificar,
)
from .politica import FilaPolitica, Politica
from .reposicion import EntradaReposicion, ParametrosReposicion, ResultadoReposicion, calcular_reposicion


@dataclass(frozen=True)
class DatosProducto:
    """Todo lo que hace falta saber de un producto padre para una corrida."""

    codigo: str
    descripcion: str = ""
    codigos_vendidos: str = ""
    unidades_mes: Sequence = ()          # una por mes de la ventana, del mas antiguo al mas reciente
    valor_mes: Sequence = ()
    primera_venta: dt.date | None = None
    unidades_semana: Sequence = ()       # una por semana, de la mas antigua a la mas reciente
    plazo_dias: float = 4.0              # lead time en dias (ya con el dia de gestion)
    plazo_origen: str = ""
    plazo_confianza: str = ""
    proveedor: str = ""
    plazo_motor_dias: float | None = None
    stock_disponible: float = 0.0        # el de la bodega del canal
    stock_aparte: float = 0.0            # ML-FULL: informativo, no suma
    stock_cd: float = 0.0                # informativo
    transito: float = 0.0                # solo OC con destino a la bodega
    transito_430_cd: float = 0.0         # informativo
    transito_cualquier_destino: float = 0.0  # informativo
    comprometido: float | None = None
    minimo_compra: float | None = None
    multiplo: float | None = None
    costo_actual: float | None = None
    costo_respaldo: str = ""             # "con stock del 19-oct" | "sin respaldo de stock" | "sin costo"


@dataclass(frozen=True)
class ProductoCalculado:
    datos: DatosProducto
    clasificacion_estado: str
    reposicion: ResultadoReposicion
    fila_politica: FilaPolitica | None
    sugerido_pesos: float


@dataclass(frozen=True)
class Corrida:
    clasificacion: ResultadoClasificacion
    productos: tuple[ProductoCalculado, ...]
    politica: Politica
    parametros: ParametrosClasificacion
    parametros_reposicion: ParametrosReposicion
    fecha_referencia: dt.date

    def por_codigo(self) -> dict[str, ProductoCalculado]:
        return {p.datos.codigo: p for p in self.productos}

    def sugerido_pesos(self) -> dict[str, float]:
        return {p.datos.codigo: p.sugerido_pesos for p in self.productos}


def correr(
    productos: Iterable[DatosProducto],
    politica: Politica,
    fecha_referencia: dt.date,
    parametros: ParametrosClasificacion | None = None,
    parametros_reposicion: ParametrosReposicion | None = None,
) -> Corrida:
    """Clasifica a todos y calcula el sugerido de cada uno con la fila de politica de su cluster."""
    parametros = parametros or ParametrosClasificacion()
    parametros_reposicion = parametros_reposicion or ParametrosReposicion()
    datos = list(productos)
    ventas = [
        VentaProducto(d.codigo, list(d.unidades_mes), list(d.valor_mes), d.primera_venta) for d in datos
    ]
    clasif = clasificar(ventas, fecha_referencia, parametros)
    calculados = []
    for d in datos:
        c = clasif.producto(d.codigo)
        fila = politica.fila(c.cluster) if c.estado == ESTADO_CLASIFICADO else None
        entrada = EntradaReposicion(
            codigo=d.codigo, unidades_semana=list(d.unidades_semana), lead_time_semanas=d.plazo_dias / 7,
            origen_lead_time=d.plazo_origen, stock_disponible=d.stock_disponible, en_transito=d.transito,
            comprometido=d.comprometido, minimo_compra=d.minimo_compra, multiplo=d.multiplo,
        )
        r = calcular_reposicion(entrada, fila, cluster=c.cluster, estado=c.estado, parametros=parametros_reposicion)
        pesos = r.sugerido * d.costo_actual if d.costo_actual is not None else 0.0
        calculados.append(ProductoCalculado(d, c.estado, r, fila, pesos))
    return Corrida(clasif, tuple(calculados), politica, parametros, parametros_reposicion, fecha_referencia)
