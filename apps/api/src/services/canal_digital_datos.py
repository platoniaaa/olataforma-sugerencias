"""Canal Digital: la pestana Datos (de donde sale lo que se calcula y si esta al dia).

Es solo lectura y no guarda nada: ni tablas nuevas ni historial de corridas. Todo se arma al momento con lo que
ya existe: la corrida que el router tiene en cache, `meta_ventas`, una consulta agregada de la venta por mes y la
fecha de la tabla de plazos. La respuesta es chica (14 meses, una decena de numeros, seis fuentes).

Las funciones de aqui no conocen HTTP.
"""
from __future__ import annotations

import datetime as dt

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import CanalDigitalVenta, LeadTimeProveedorSucursal
from . import canal_digital_calculo as calculo
from . import canal_digital_service as svc
from . import canal_digital_vista as vista
from .canal_digital_service import _tenant

MESES_EN_TABLA = 14

ESTADO_OK = "ok"
ESTADO_AVISO = "aviso"
ESTADO_FALTA = "falta"

# Como se carga un mes nuevo de venta. El motor lo hara solo cuando esa parte este publicada; mientras tanto la
# carga la hace un admin con el script de la carpeta api.
COMO_CARGAR = [
    "Cada mes cerrado se carga una sola vez. Cuando esa parte del motor esté publicada, el motor sube la venta "
    "del canal solo y no hay que hacer nada.",
    "Mientras tanto la sube quien administra el motor, desde la carpeta api, con: python "
    "scripts/canal_digital_cargar_ventas.py --carpeta \"<carpeta de ventas>\" --anios 2025 2026 --publicar-lineas",
    "Se envía un mes por vez y se reemplaza solo ese mes: repetir la carga no duplica nada.",
    "Al terminar, vuelve a esta pestaña: «Ventas del canal» debe decir «Al día» y el mes nuevo debe aparecer en "
    "la tabla de arriba.",
]


def _mes(periodo: str | None) -> str:
    """"202609" -> "09-2026"."""
    return f"{periodo[4:]}-{periodo[:4]}" if periodo and len(periodo) == 6 else "—"


def _n(x: float) -> str:
    """Numero con punto de miles: 1234567 -> "1.234.567"."""
    return f"{round(x):,}".replace(",", ".")


def _s(n: int, uno: str, varios: str) -> str:
    return uno if n == 1 else varios


def ventas_por_mes(db: Session, bodega: str, n: int = MESES_EN_TABLA) -> list[dict]:
    """Venta de los ultimos `n` periodos cargados, del mas reciente al mas antiguo, con UNA consulta agregada.

    unidades_netas = brutas - devueltas (lo mismo que usa la corrida); lineas = lineas de documento que la
    originaron (0 en un mes cargado por la ruta heredada, que no trae lineas).
    """
    V = CanalDigitalVenta
    filas = db.execute(
        select(V.periodo, func.sum(V.unid_brutas), func.sum(V.unid_devueltas), func.sum(V.n_lineas))
        .where(V.tenant_id == _tenant(), V.bodega == bodega)
        .group_by(V.periodo)
        .order_by(V.periodo.desc())
        .limit(n)
    ).all()
    return [
        {
            "periodo": periodo,
            "unidades_netas": round((brutas or 0.0) - (devueltas or 0.0), 2),
            "unidades_devueltas": round(devueltas or 0.0, 2),
            "lineas": int(lineas or 0),
        }
        for periodo, brutas, devueltas, lineas in filas
    ]


def cobertura(corrida) -> dict:
    """Cuantos productos de la corrida tienen cada dato. Sale de la corrida ya calculada: no consulta ni recalcula.

    `proveedor_menos_5_muestras` es un subconjunto de `con_proveedor`. `sin_proveedor` es lo mismo que cuenta el
    aviso de la corrida: productos que usan el plazo de respaldo (sin proveedor, o con uno que el motor no mide).
    `costo_sin_respaldo_stock` son los que tienen costo pero hoy no tienen stock en el maestro: costo posiblemente
    viejo. `con_transito_otro_destino` son los que tienen OC a otro destino ademas (o en vez) de la bodega.
    """
    productos = sin_proveedor = pocas = sin_costo = sin_respaldo = 0
    con_stock = con_aparte = con_transito = con_otro = 0
    for pc in corrida.productos:
        d = pc.datos
        productos += 1
        sin_proveedor += d.plazo_confianza == calculo.CONFIANZA_PLAZO_SIN_PROVEEDOR
        pocas += d.plazo_confianza == calculo.CONFIANZA_PLAZO_POCAS_MUESTRAS
        sin_costo += d.costo_actual is None
        sin_respaldo += d.costo_actual is not None and d.costo_respaldo == calculo.COSTO_SIN_RESPALDO_STOCK
        con_stock += d.stock_disponible > 0
        con_aparte += d.stock_aparte > 0
        con_transito += d.transito > 0
        con_otro += (d.transito_cualquier_destino or 0.0) - (d.transito or 0.0) > 1e-9
    return {
        "productos": productos,
        "con_proveedor": productos - sin_proveedor, "sin_proveedor": sin_proveedor,
        "proveedor_menos_5_muestras": pocas,
        "con_costo": productos - sin_costo, "sin_costo": sin_costo, "costo_sin_respaldo_stock": sin_respaldo,
        "con_stock_bodega": con_stock, "sin_stock_bodega": productos - con_stock, "con_stock_aparte": con_aparte,
        "con_transito_a_la_bodega": con_transito, "con_transito_otro_destino": con_otro,
    }


def _con_codigos_agrupados(corrida) -> int:
    """Productos que reunen la venta de mas de un codigo (el vigente y los que reemplaza)."""
    return sum(" | " in (pc.datos.codigos_vendidos or "") for pc in corrida.productos)


def _fuente(nombre: str, estado: str, detalle: str) -> dict:
    return {"nombre": nombre, "detalle": detalle, "estado": estado}


def fuentes(cob: dict, ventas: dict, aviso: dict, agrupados: int, plazos_actualizados: dt.date | None) -> list[dict]:
    """Una linea por fuente de datos, con su estado: ok, aviso (hay algo que mirar) o falta (no se puede confiar)."""
    n = cob["productos"]
    sin_productos = "Se revisa cuando haya venta cargada: todavía no hay productos."
    out = []

    # Ventas del canal: lo que manda para la demanda y las clases.
    ultimo, faltan = ventas["ultimo_periodo_cargado"], ventas["meses_sin_cargar"]
    lineas = (
        f" Hay {_n(ventas['lineas'])} líneas del ERP guardadas, hasta {_mes(ventas['lineas_periodo_hasta'])}."
        if ventas["lineas"] else ""
    )
    if not ultimo:
        out.append(_fuente("Ventas del canal", ESTADO_FALTA, "Todavía no hay ningún mes cerrado cargado para esta bodega."))
    elif not faltan:
        out.append(_fuente("Ventas del canal", ESTADO_OK, f"Al día: cargada hasta {_mes(ultimo)}.{lineas}"))
    else:
        out.append(_fuente(
            "Ventas del canal", ESTADO_AVISO,
            f"Faltan {faltan} {_s(faltan, 'mes cerrado', 'meses cerrados')}: la venta llega hasta {_mes(ultimo)}. "
            f"La demanda y las clases se calculan hasta ese mes.{lineas}",
        ))

    # Stock de la bodega.
    if not n:
        out.append(_fuente("Stock de la bodega", ESTADO_AVISO, sin_productos))
    elif not cob["con_stock_bodega"]:
        out.append(_fuente(
            "Stock de la bodega", ESTADO_FALTA,
            f"Ninguno de los {_n(n)} productos tiene stock en la bodega: revisa que el motor haya publicado el stock.",
        ))
    else:
        out.append(_fuente(
            "Stock de la bodega", ESTADO_OK,
            f"{_n(cob['con_stock_bodega'])} de {_n(n)} productos tienen stock en la bodega y "
            f"{_n(cob['sin_stock_bodega'])} no. {_n(cob['con_stock_aparte'])} tienen stock aparte, que no suma al disponible.",
        ))

    # Plazos de entrega: la tabla del motor por proveedor; sin proveedor se usa un respaldo.
    fecha = f" La tabla del motor se actualizó el {plazos_actualizados.strftime('%d-%m-%Y')}." if plazos_actualizados else ""
    respaldo = f"{calculo.PLAZO_RESPALDO_DIAS:g}"
    if not n:
        out.append(_fuente("Plazos de entrega", ESTADO_AVISO, sin_productos))
    elif not cob["con_proveedor"]:
        out.append(_fuente(
            "Plazos de entrega", ESTADO_FALTA,
            f"Ningún producto tiene proveedor con plazo medido: los {_n(n)} usan {respaldo} días de respaldo.{fecha}",
        ))
    elif cob["sin_proveedor"] or cob["proveedor_menos_5_muestras"]:
        out.append(_fuente(
            "Plazos de entrega", ESTADO_AVISO,
            f"{_n(cob['sin_proveedor'])} de {_n(n)} productos sin proveedor: usan {respaldo} días de respaldo. "
            f"{_n(cob['proveedor_menos_5_muestras'])} tienen un proveedor con menos de 5 pedidos medidos.{fecha}",
        ))
    else:
        out.append(_fuente(
            "Plazos de entrega", ESTADO_OK, f"Todos los productos tienen un proveedor con 5 o más pedidos medidos.{fecha}"
        ))

    # Costos: del maestro de precios; sin costo el valor a pedir sale en $0.
    if not n:
        out.append(_fuente("Costos", ESTADO_AVISO, sin_productos))
    elif not cob["con_costo"]:
        out.append(_fuente("Costos", ESTADO_FALTA, "Ningún producto tiene costo: el valor a pedir sale en $0."))
    elif cob["sin_costo"] or cob["costo_sin_respaldo_stock"]:
        out.append(_fuente(
            "Costos", ESTADO_AVISO,
            f"{_n(cob['sin_costo'])} de {_n(n)} productos sin costo: su valor a pedir sale en $0. "
            f"{_n(cob['costo_sin_respaldo_stock'])} tienen costo pero hoy no tienen stock: el costo puede estar viejo.",
        ))
    else:
        out.append(_fuente("Costos", ESTADO_OK, f"Los {_n(n)} productos tienen costo y stock que lo respalda."))

    # Grupos de reemplazo: el motor junta bajo un codigo vigente la venta de los que reemplaza.
    dobles = aviso.get("codigos_en_dos_grupos") or 0
    if not n:
        out.append(_fuente("Grupos de reemplazo", ESTADO_AVISO, sin_productos))
    elif dobles:
        out.append(_fuente(
            "Grupos de reemplazo", ESTADO_AVISO,
            f"{_n(dobles)} {_s(dobles, 'código figura', 'códigos figuran')} en dos grupos a la vez: cada uno se asigna a un solo grupo. "
            f"{_n(agrupados)} productos reúnen la venta de más de un código.",
        ))
    else:
        out.append(_fuente(
            "Grupos de reemplazo", ESTADO_OK,
            f"{_n(agrupados)} de {_n(n)} productos reúnen la venta de más de un código; ningún código está en dos grupos.",
        ))

    # Transito: solo las OC con destino a la bodega suman a la posicion.
    if not n:
        out.append(_fuente("Tránsito", ESTADO_AVISO, sin_productos))
    elif not cob["con_transito_a_la_bodega"]:
        otro = (
            f" {_n(cob['con_transito_otro_destino'])} tienen pedidos en camino a otro destino, que no suman."
            if cob["con_transito_otro_destino"] else ""
        )
        out.append(_fuente(
            "Tránsito", ESTADO_AVISO, f"Ningún producto tiene pedidos en camino a la bodega.{otro}"
        ))
    else:
        out.append(_fuente(
            "Tránsito", ESTADO_OK,
            f"{_n(cob['con_transito_a_la_bodega'])} productos tienen pedidos en camino a la bodega. "
            f"{_n(cob['con_transito_otro_destino'])} tienen pedidos a otro destino, que no suman.",
        ))
    return out


def _plazos_actualizados(db: Session) -> dt.date | None:
    """Cuando el motor actualizo por ultima vez la tabla de plazos por proveedor (una consulta, una fila)."""
    L = LeadTimeProveedorSucursal
    ultima = db.scalar(select(func.max(L.actualizado_en)).where(L.tenant_id == _tenant(), L.sucursal_id.is_(None)))
    return ultima.date() if ultima else None


def armar(db: Session, bodega: str, corrida, aviso: dict) -> dict:
    """La respuesta de GET /datos para una bodega que ya existe. `corrida` y `aviso` son los del router."""
    meta = svc.meta_ventas(db, bodega)
    ventas = {
        "ultimo_periodo_cargado": aviso.get("ultimo_periodo_cargado"),
        "meses_sin_cargar": aviso.get("meses_sin_cargar"),
        "periodo_desde": meta["periodo_desde"],
        "filas": meta["filas"],
        "productos": meta["productos"],
        "lineas": meta["n_lineas"],
        "lineas_periodo_hasta": meta["lineas_periodo_hasta"],
        "por_mes": ventas_por_mes(db, bodega),
    }
    cob = cobertura(corrida)
    return {
        "ventas": ventas,
        "cobertura": cob,
        "fuentes": fuentes(cob, ventas, aviso, _con_codigos_agrupados(corrida), _plazos_actualizados(db)),
        "validaciones": vista.validaciones(corrida),
        "como_cargar": list(COMO_CARGAR),
    }
