"""Venta del canal por producto, semana y periodo: la regla pura, sin Excel ni base de datos.

Entra una lista de lineas de venta del ERP (ya leidas) y salen filas agregadas por
(producto, semana, periodo del documento). Lo usa el cargador de Excel y lo prueban los
tests con lineas inventadas. Reglas (decisiones del dueno, 20-10-2026):

  Universo        la linea entra si su Tipo-Venta esta en los tipos de la bodega, en cualquier local.
  Signo           una nota de credito trae cantidad POSITIVA y resta; una venta con cantidad negativa
                  ya resta sola. El signo se aplica una sola vez: unidades netas por |costo unitario|.
  Mes             todo cuenta en el periodo del documento (la devolucion resta en el mes de su nota).
  Semana          la venta cuenta en la semana (lunes a domingo) de su fecha; la devolucion en la
                  semana de la venta que anula (documento de referencia + producto). Si no se
                  encuentra el original, o su fecha es posterior a la nota, cuenta la fecha de la nota.
  Liquidaciones   cuentan como venta, marcadas en `unid_liquidacion`.
  Excepciones     tipos de documento que no son venta y productos sin ficha se omiten y se cuentan.
"""
from __future__ import annotations

import datetime as dt
import re
from collections import Counter
from dataclasses import dataclass, field
from typing import Iterable, Mapping

TIPOS_VENTA_DEFECTO = ("VTA ML", "VTA SHOPIFY", "VTA WALMART", "VTA PARIS")
TIPODOCTO_ESPERADOS = (
    "FA-ELECTR REPTO", "BOLETA-REPUESTOS", "NC-ELECTR REPTO", "LIQ FACT-REPUESTOS", "NC LIQ FACT",
)
TIPODOCTO_DEVOLUCION_EXTRA = ("NOTA CREDITO ST", "NOTA CREDITO S/T", "DEVOLUCION V/C ST")
TIPODOCTO_LIQUIDACION = ("LIQ FACT-REPUESTOS", "NC LIQ FACT")
EXCLUIR_PRODUCTOS = ("CUP000492",)  # sin costo ni ficha en ninguna fuente (1 unidad, abr-2026)

_ESPACIOS_RAROS = re.compile("[   -   　]")
_INVISIBLES = re.compile("[​‌‍⁠﻿]")


def normalizar_codigo(valor) -> str | None:
    """Llave de producto: sin invisibles, un solo espacio, sin bordes, MAYUSCULAS. Conserva ceros y rubro."""
    if valor is None:
        return None
    t = _INVISIBLES.sub("", str(valor))
    t = _ESPACIOS_RAROS.sub(" ", t)
    t = re.sub(r"\s+", " ", t).strip().upper()
    return t or None


def normalizar_numero(valor) -> str:
    """Numero de documento como texto: 835066.0 -> '835066'; sin ceros a la izquierda."""
    if valor is None:
        return ""
    if isinstance(valor, float) and valor == int(valor):
        valor = int(valor)
    return str(valor).strip().lstrip("0")


def lunes_de(fecha: dt.date) -> dt.date:
    return fecha - dt.timedelta(days=fecha.weekday())


@dataclass(frozen=True)
class LineaVenta:
    periodo: str            # YYYYMM del documento
    tipo_docto: str
    numero: str
    fecha: dt.date
    tipo_venta: str
    producto: str           # ya normalizado
    cantidad: float
    costo_neto: float
    doc_ref: str = ""
    nro_doc_ref: str = ""


@dataclass
class FilaVenta:
    producto: str
    semana: str
    periodo: str
    unid_brutas: float = 0.0
    unid_devueltas: float = 0.0
    valor_costo: float = 0.0
    unid_liquidacion: float = 0.0
    n_lineas: int = 0


@dataclass
class ResultadoAgregado:
    filas: list[FilaVenta]
    estadisticas: Counter = field(default_factory=Counter)

    @property
    def unidades_netas(self) -> float:
        return sum(f.unid_brutas - f.unid_devueltas for f in self.filas)


def es_devolucion(tipo_docto: str) -> bool:
    return tipo_docto.startswith("NC") or tipo_docto in TIPODOCTO_DEVOLUCION_EXTRA


def clave_original(tipo_docto: str, numero: str, producto: str) -> tuple[str, str, str]:
    return (tipo_docto.strip(), numero, producto)


def indice_originales(lineas: Iterable[LineaVenta], tipos_venta: Iterable[str]) -> dict[tuple[str, str, str], dt.date]:
    """(tipo de documento, numero, producto) -> fecha mas antigua de esa venta, solo del canal."""
    tipos = set(tipos_venta)
    indice: dict[tuple[str, str, str], dt.date] = {}
    for l in lineas:
        if l.tipo_venta not in tipos or es_devolucion(l.tipo_docto):
            continue
        k = clave_original(l.tipo_docto, l.numero, l.producto)
        if k not in indice or l.fecha < indice[k]:
            indice[k] = l.fecha
    return indice


def agregar(
    lineas: Iterable[LineaVenta],
    tipos_venta: Iterable[str] = TIPOS_VENTA_DEFECTO,
    originales: Mapping[tuple[str, str, str], dt.date] | None = None,
    periodos: Iterable[str] | None = None,
) -> ResultadoAgregado:
    """Agrega las lineas del canal por (producto, semana, periodo).

    `periodos` (opcional) limita a esos periodos del documento (un archivo anual solo
    reemplaza los suyos). `originales` es el indice de `indice_originales`; sin el, toda
    devolucion cuenta en la semana de su nota.
    """
    tipos = set(tipos_venta)
    solo = set(periodos) if periodos is not None else None
    originales = originales or {}
    est: Counter = Counter()
    acum: dict[tuple[str, str, str], FilaVenta] = {}
    for l in lineas:
        if l.tipo_venta not in tipos:
            continue
        if solo is not None and l.periodo not in solo:
            continue
        est["lineas_canal"] += 1
        if l.tipo_docto not in TIPODOCTO_ESPERADOS and not es_devolucion(l.tipo_docto):
            est["omitidas_tipo_documento"] += 1
            est[f"omitida_tipo:{l.tipo_docto}"] += 1
            continue
        if l.producto in EXCLUIR_PRODUCTOS:
            est["omitidas_producto_sin_ficha"] += 1
            continue
        dev = es_devolucion(l.tipo_docto)
        neta = -l.cantidad if dev else l.cantidad
        fecha_efectiva = l.fecha
        if dev:
            orig = originales.get(clave_original(l.doc_ref, normalizar_numero(l.nro_doc_ref), l.producto))
            if orig is None:
                est["devoluciones_sin_original"] += 1
            elif orig > l.fecha:
                est["devoluciones_con_original_posterior"] += 1
            else:
                fecha_efectiva = orig
        semana = lunes_de(fecha_efectiva).isoformat()
        clave = (l.producto, semana, l.periodo)
        fila = acum.get(clave)
        if fila is None:
            fila = acum[clave] = FilaVenta(l.producto, semana, l.periodo)
        fila.unid_brutas += neta if neta > 0 else 0.0
        fila.unid_devueltas += -neta if neta < 0 else 0.0
        fila.valor_costo += abs(l.costo_neto) * neta
        if l.tipo_docto in TIPODOCTO_LIQUIDACION:
            fila.unid_liquidacion += neta
        fila.n_lineas += 1
        est["lineas_cargadas"] += 1
    return ResultadoAgregado(list(acum.values()), est)
