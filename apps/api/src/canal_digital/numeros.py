"""Ayudas numericas y de fechas del nucleo de Canal Digital.

Solo biblioteca estandar. Las usan `clasificacion` y `reposicion`; viven aparte para
que ninguna de las dos importe a la otra solo por esto.

Decision de aritmetica: todo lo que decide una letra (Pareto, frecuencia) se suma con
`Fraction`, no con `float`. Con floats, "acumulado antes del producto < 80%" puede
dar distinto segun el orden de las sumas; con fracciones exactas dos corridas con
los mismos datos dan siempre lo mismo.
"""
from __future__ import annotations

import calendar
import math
import numbers
from datetime import date, datetime
from decimal import Decimal
from fractions import Fraction


def a_fraccion(valor) -> Fraction:
    """Convierte un numero a `Fraction` exacta, sin arrastrar el error binario.

    - int, Fraction y Decimal pasan tal cual (exactos).
    - float: se lee su representacion decimal mas corta (`repr`), de modo que
      4339.95 es 433995/100 y no 4339.9499999999998181... Asi un monto que viene
      de un Excel se comporta como el numero que se ve en la celda.
    - bool, NaN, infinito y cualquier otro tipo se rechazan: un dato roto debe
      parar el calculo, no colarse como 0.
    """
    if isinstance(valor, bool):
        raise TypeError("un booleano no es una cantidad")
    if isinstance(valor, Fraction):
        return valor
    if isinstance(valor, numbers.Integral):
        return Fraction(int(valor))
    if isinstance(valor, Decimal):
        if not valor.is_finite():
            raise ValueError(f"cantidad no finita: {valor!r}")
        return Fraction(valor)
    if isinstance(valor, numbers.Real):
        numero = float(valor)
        if not math.isfinite(numero):
            raise ValueError(f"cantidad no finita: {valor!r}")
        return Fraction(repr(numero))
    raise TypeError(f"no es una cantidad: {valor!r}")


def a_fecha(valor) -> date:
    """`date` (o `datetime`, del que se toma solo el dia)."""
    if isinstance(valor, datetime):
        return valor.date()
    if isinstance(valor, date):
        return valor
    raise TypeError(f"no es una fecha: {valor!r}")


def restar_meses(fecha: date, meses: int) -> date:
    """`fecha` menos `meses` meses calendario; si el dia no existe, el ultimo del mes.

    2026-10-01 - 6 meses = 2026-04-01.  2026-08-31 - 6 meses = 2026-02-28.
    """
    total = fecha.year * 12 + (fecha.month - 1) - meses
    anio, mes0 = divmod(total, 12)
    mes = mes0 + 1
    dia = min(fecha.day, calendar.monthrange(anio, mes)[1])
    return date(anio, mes, dia)


def limpio(valor):
    """int si el valor es entero (Fraction o float), float si no. Para mostrar y exportar."""
    if isinstance(valor, Fraction):
        return int(valor) if valor.denominator == 1 else float(valor)
    if isinstance(valor, float):
        return int(valor) if valor.is_integer() else valor
    return valor
