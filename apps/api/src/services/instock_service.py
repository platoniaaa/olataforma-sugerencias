"""Regla InStock: los repuestos de pauta nunca bajan del mínimo en las sucursales con taller.

Curifor hace las mantenciones de las pautas del fabricante. Los repuestos de esas
pautas se van a vender sí o sí, así que no pueden faltar: si una sucursal con
taller no llega al mínimo entre lo que tiene, lo que viene en camino y lo que el
modelo ya sugiere, el sugerido se completa hasta el mínimo aunque el BI no pida
nada (típico caso de un repuesto clase D, sin venta registrada, con stock 0).

Dos cosas separadas, y conviene no confundirlas:

- **La marca** (`instock`): informativa. Dice "este repuesto es de pauta". Se
  pone en TODAS las filas del producto, en cualquier sucursal, para que el
  comprador lo reconozca en la grilla y pueda filtrar por la columna.
- **El mínimo**: la compra. Solo se aplica en `SUCURSALES_INSTOCK` (las que
  tienen taller); en el resto la marca es solo informativa.

La lista de repuestos vive en `repuesto_instock` y sale de las pautas del
fabricante (ver `models/repuesto_instock.py` y `jobs/cargar_instock.py`).
"""
from __future__ import annotations

import math

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import DimSucursal, RepuestoInstock

# Sucursales con taller de mantención: son las únicas donde el mínimo obliga a
# comprar. Decisión de Abastecimiento (jul-2026). Mismo criterio de comparación
# que `SUCURSALES_OCULTAS`: exacto, en minúsculas, sobre `sucursal_id`. OJO:
# "RANCAGUA 2" y "CHILLAN VIEJO" son sucursales distintas y NO están incluidas.
SUCURSALES_INSTOCK = ("LINDEROS", "RANCAGUA", "CURICO", "CHILLAN")
_INSTOCK_LOWER = {s.lower() for s in SUCURSALES_INSTOCK}

# Unidades que nunca pueden faltar. Es el default de la tabla; cada repuesto
# puede traer el suyo en `repuesto_instock.minimo`.
MINIMO_DEFECTO = 2


def en_alcance(sucursal_id: str | None) -> bool:
    """La sucursal tiene taller, así que el mínimo la obliga a comprar."""
    return bool(sucursal_id) and sucursal_id.strip().lower() in _INSTOCK_LOWER


def catalogo(db: Session) -> dict[str, dict]:
    """{producto: {minimo, marca, modelos}} de los repuestos InStock activos.

    Tolerante a que la tabla no exista todavía (despliegue viejo o base local sin
    la carga): devuelve vacío y la plataforma se comporta como antes de la regla.
    """
    try:
        filas = db.execute(
            select(
                RepuestoInstock.producto,
                RepuestoInstock.minimo,
                RepuestoInstock.marca,
                RepuestoInstock.modelos,
            ).where(RepuestoInstock.activo.is_(True))
        ).all()
    except Exception:  # noqa: BLE001 - tabla ausente: la regla queda inactiva
        db.rollback()
        return {}
    return {
        p: {"minimo": int(m or MINIMO_DEFECTO), "marca": marca, "modelos": modelos}
        for p, m, marca, modelos in filas
    }


def resumen(db: Session) -> dict:
    """Descripcion de la regla para mostrarla junto a las sugerencias recurrentes.

    La regla InStock no es una sugerencia que alguien cargo: es una regla del
    sistema. Pero desde el punto de vista del comprador hace lo mismo que una
    recurrente de "mantener N unidades" y no vence nunca, asi que tiene que verse
    donde el equipo las busca. Es de solo lectura: se cambia recargando la lista
    desde las pautas (`jobs/cargar_instock.py`), no borrandola de la pantalla.
    """
    try:
        filas = db.execute(
            select(RepuestoInstock.marca, RepuestoInstock.minimo)
            .where(RepuestoInstock.activo.is_(True))
        ).all()
    except Exception:  # noqa: BLE001 - tabla ausente: la regla no esta activa
        db.rollback()
        filas = []
    por_marca: dict[str, int] = {}
    for marca, _m in filas:
        por_marca[marca or "(sin marca)"] = por_marca.get(marca or "(sin marca)", 0) + 1
    minimos = sorted({int(m or MINIMO_DEFECTO) for _marca, m in filas})
    # Nombres bonitos para la pantalla: el id es "CURICO" y la sucursal se llama
    # "Curicó". Si falta la dimension, se muestra el id (mejor eso que nada).
    try:
        nombres = {
            s: n or s
            for s, n in db.execute(
                select(DimSucursal.sucursal_id, DimSucursal.nombre)
                .where(DimSucursal.sucursal_id.in_(SUCURSALES_INSTOCK))
            ).all()
        }
    except Exception:  # noqa: BLE001
        db.rollback()
        nombres = {}
    return {
        # Sin repuestos cargados la regla existe en el codigo pero no hace nada:
        # conviene decirlo en pantalla en vez de mostrar una regla vacia.
        "activo": bool(filas),
        "n_repuestos": len(filas),
        "minimo": minimos[0] if len(minimos) == 1 else (minimos[0] if minimos else MINIMO_DEFECTO),
        "minimo_uniforme": len(minimos) <= 1,
        "sucursales": [nombres.get(s, s) for s in SUCURSALES_INSTOCK],
        "por_marca": por_marca,
    }


def faltante(
    minimo: int,
    stock: float | None,
    transito: float | None,
    sugerido: float | None,
) -> int:
    """Unidades que faltan para que la sucursal llegue al mínimo.

    Descuenta lo mismo que `_faltante_para_objetivo` del sugerido: lo que hay, lo
    que viene en camino y lo que ya se está sugiriendo comprar (incluidas las
    sugerencias manuales, que a esta altura ya están sumadas en el total). Sin
    ese último descuento la regla compraría dos veces el mismo nivel.
    """
    cubierto = (stock or 0) + (transito or 0) + (sugerido or 0)
    return max(0, math.ceil(minimo - cubierto))


def faltante_de_fila(fila: dict, minimo: int) -> int:
    """`faltante` leyendo los campos de una fila del sugerido."""
    return faltante(
        minimo,
        fila.get("stock_activo_suc"),
        fila.get("stock_en_transito_suc"),
        fila.get("total_sugerido_suc"),
    )


def _marcar(fila: dict, info: dict | None) -> None:
    fila["instock"] = bool(info)
    fila["instock_modelos"] = info.get("modelos") if info else None
    fila["instock_minimo"] = info.get("minimo") if info else None


def aplicar_a_fila(fila: dict, minimo: int) -> int:
    """Sube el sugerido de la fila hasta el mínimo. Devuelve las unidades agregadas.

    Muta `fila` in-place con la misma mecánica que `_aplicar_manuales_a_fila`:
    suma al total y al neto de compra, revaloriza y deja `pedir = Si` (si falta
    stock de un repuesto de pauta, hay que comprarlo; el toggle "solo pedir" del
    dashboard no puede esconderlo).
    """
    faltan = faltante_de_fila(fila, minimo)
    if faltan <= 0:
        return 0
    fila["total_sugerido_suc"] = float(fila.get("total_sugerido_suc") or 0) + faltan
    base_neto = fila.get("sugerido_compra_neto")
    if base_neto is None:
        base_neto = float(fila.get("total_sugerido_suc") or 0) - faltan
    fila["sugerido_compra_neto"] = float(base_neto) + faltan
    if fila.get("costo_unitario"):
        fila["total_valor_sugerido_clp"] = (
            float(fila.get("total_valor_sugerido_clp") or 0)
            + faltan * float(fila["costo_unitario"])
        )
    fila["pedir"] = "Si"
    fila["pedir_flag"] = "Si"
    fila["instock_agregado"] = float(fila.get("instock_agregado") or 0) + faltan
    return faltan


def aplicar(items: list[dict], cat: dict[str, dict]) -> None:
    """Marca las filas InStock y completa el mínimo donde corresponde.

    Muta `items` in-place. Se llama con la lista ya armada (filas del BI, extras
    por sugerencia manual, filas sintéticas y filas del catálogo) para que la
    regla valga igual en todas y no dependa de por dónde entró la fila.
    """
    if not items:
        return
    for fila in items:
        info = cat.get(fila.get("producto")) if cat else None
        _marcar(fila, info)
        if info and en_alcance(fila.get("sucursal_id")):
            aplicar_a_fila(fila, info["minimo"])
