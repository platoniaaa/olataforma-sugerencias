"""Margen de los productos FORD: precio de lista contra el costo unitario.

Sirve para priorizar la compra: entre dos productos que el modelo sugiere por
igual, conviene saber cual deja mas plata.

Que precio es "el precio de venta": la lista de FORD trae varios y no todos son
comparables con el costo.

- **Publico** (`precio_publico_ford`, sin IVA) es el precio de lista al cliente
  final: es el que se usa como principal para el margen.
- **Flota** (`precio_flota_ford`) es el precio a clientes flota, mas bajo: se
  calcula aparte porque el mix de venta cambia el margen real.
- **Dealer** (`precio_dealer_ford`) NO es un precio de venta: es lo que FORD le
  cobra al concesionario. Se expone como referencia de costo de reposicion
  (`sobrecosto_vs_dealer_pct`): si el costo unitario de Curifor esta muy por
  encima del dealer, hay algo que revisar en la compra.

Todos los campos quedan en None cuando falta el precio o el costo, para no
inventar margenes con datos incompletos.
"""
from __future__ import annotations

# Precio de venta principal, en orden de preferencia. Un producto esta en UNA de
# las listas, no en las dos: FORD publica su precio publico y Gildemeister su
# precio sugerido, que cumplen el mismo rol. Si algun dia se agrega otra lista,
# se suma aca y el margen la toma sin tocar nada mas.
PRECIOS_VENTA = ("precio_publico_ford", "precio_sugerido_gilde")
PRECIOS_DEALER = ("precio_dealer_ford", "precio_dealer_gilde")

# Compatibilidad: habia codigo y tests que miraban esta constante.
PRECIO_VENTA_PRINCIPAL = PRECIOS_VENTA[0]


def _primero(fila: dict, campos) -> float | None:
    """Primer campo con valor > 0 de la lista (None si ninguno)."""
    for c in campos:
        v = fila.get(c)
        if v and v > 0:
            return v
    return None

# Campos derivados que este modulo agrega a cada fila del sugerido.
CAMPOS_MARGEN = (
    "margen_unitario_clp",
    "margen_pct",
    "margen_flota_pct",
    "margen_sugerido_clp",
    "sobrecosto_vs_dealer_pct",
)


def _pct(numerador: float, denominador: float) -> float:
    return round(numerador / denominador * 100, 1)


def calcular_margen(fila: dict) -> None:
    """Agrega los campos de margen a UNA fila del sugerido (muta el dict).

    Se llama para todas las filas, incluidas las que no son FORD: ahi los precios
    vienen en None y los margenes quedan en None (la columna sale vacia)."""
    for campo in CAMPOS_MARGEN:
        fila.setdefault(campo, None)

    costo = fila.get("costo_unitario")
    if not costo or costo <= 0:
        return

    publico = _primero(fila, PRECIOS_VENTA)
    if publico and publico > 0:
        fila["margen_unitario_clp"] = round(publico - costo)
        fila["margen_pct"] = _pct(publico - costo, publico)
        # Margen potencial de lo que el modelo esta sugiriendo comprar.
        sugerido = fila.get("total_sugerido_suc") or 0
        if sugerido > 0:
            fila["margen_sugerido_clp"] = round((publico - costo) * sugerido)

    flota = fila.get("precio_flota_ford")
    if flota and flota > 0:
        fila["margen_flota_pct"] = _pct(flota - costo, flota)

    dealer = _primero(fila, PRECIOS_DEALER)
    if dealer and dealer > 0:
        # Positivo = el costo de Curifor esta POR ENCIMA del precio dealer de FORD.
        fila["sobrecosto_vs_dealer_pct"] = _pct(costo - dealer, dealer)


def agregar_margen(items: list[dict]) -> None:
    """Aplica `calcular_margen` a una lista de filas (muta in-place)."""
    for fila in items:
        calcular_margen(fila)
