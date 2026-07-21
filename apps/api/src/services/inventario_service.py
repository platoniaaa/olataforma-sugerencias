"""Salud del inventario: donde esta la plata detenida y donde falta.

El sugerido responde "que comprar". Esto responde lo complementario: que hay en
las bodegas que no se mueve, que esta sobre-stockeado y que esta en quiebre.

Universo: la tabla `sugerido` (producto x sucursal), que es la unica que tiene
junto el stock, la demanda y el costo. Respeta los mismos filtros del dashboard,
incluidas las sucursales ocultas y el acceso por sucursal del usuario.

Se traen las filas y se agregan en Python en vez de resolverlo con SQL: hacen
falta medianas y cortes por producto que no son portables entre SQLite (local) y
Postgres (produccion), y son ~19k filas livianas (10 columnas).
"""
from __future__ import annotations

from statistics import median

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Sugerido
from ..schemas import SugeridoFiltros

# Sobre cuantos dias de cobertura se considera que hay sobre-stock.
DIAS_SOBRE_STOCK = 180
# Tope para no ensuciar la mediana con productos sin demanda (cobertura infinita).
COBERTURA_TOPE_DIAS = 3650


def _valor(unidades: float, costo: float | None) -> float:
    return round(unidades * costo) if costo else 0.0


def _cobertura_dias(stock: float, demanda_diaria: float | None) -> float | None:
    """Dias que alcanza el stock al ritmo de venta actual. None si no hay demanda."""
    if not demanda_diaria or demanda_diaria <= 0:
        return None
    return min(stock / demanda_diaria, COBERTURA_TOPE_DIAS)


def salud(
    db: Session, f: SugeridoFiltros, dias_sobre_stock: int = DIAS_SOBRE_STOCK
) -> dict:
    """Indicadores de inventario segun los filtros aplicados."""
    from .sugerido_service import _apply_filters

    # solo_pedir=False: el inventario incluye lo que NO se sugiere comprar (que es
    # justamente donde aparece el inmovilizado).
    filtros = f.model_copy(update={"solo_pedir": False})
    stmt = _apply_filters(
        select(
            Sugerido.producto,
            Sugerido.descripcion,
            Sugerido.sucursal_id,
            Sugerido.nombre_sucursal,
            Sugerido.filtro1_final,
            Sugerido.clasificacion_abc,
            Sugerido.stock_activo_suc,
            Sugerido.stock_en_transito_suc,
            Sugerido.demanda_mensual,
            Sugerido.demanda_diaria,
            Sugerido.punto_de_pedido,
            Sugerido.costo_unitario,
        ),
        filtros,
    )
    filas = db.execute(stmt).all()

    resumen = {
        "valor_inventario_clp": 0.0, "unidades": 0.0, "n_filas": 0,
        "inmovilizado_clp": 0.0, "inmovilizado_n": 0,
        "sobre_stock_clp": 0.0, "sobre_stock_n": 0,
        "quiebre_con_demanda_n": 0, "bajo_punto_pedido_n": 0,
        "sin_costo_n": 0,
    }
    por_sucursal: dict[str, dict] = {}
    por_marca: dict[str, dict] = {}
    coberturas: list[float] = []
    inmovilizados: list[dict] = []

    for r in filas:
        stock = r.stock_activo_suc or 0.0
        demanda_mes = r.demanda_mensual or 0.0
        valor = _valor(stock, r.costo_unitario)
        cobertura = _cobertura_dias(stock, r.demanda_diaria)

        resumen["n_filas"] += 1
        resumen["unidades"] += stock
        resumen["valor_inventario_clp"] += valor
        if stock > 0 and not r.costo_unitario:
            resumen["sin_costo_n"] += 1

        suc = por_sucursal.setdefault(
            r.sucursal_id,
            {"sucursal_id": r.sucursal_id, "nombre_sucursal": r.nombre_sucursal or r.sucursal_id,
             "valor_clp": 0.0, "unidades": 0.0, "inmovilizado_clp": 0.0, "sobre_stock_clp": 0.0,
             "quiebre_con_demanda_n": 0, "bajo_punto_pedido_n": 0, "n_productos": 0},
        )
        suc["valor_clp"] += valor
        suc["unidades"] += stock
        suc["n_productos"] += 1

        marca = por_marca.setdefault(
            r.filtro1_final or "(sin marca)",
            {"marca": r.filtro1_final or "(sin marca)", "valor_clp": 0.0,
             "inmovilizado_clp": 0.0, "n_productos": 0},
        )
        marca["valor_clp"] += valor
        marca["n_productos"] += 1

        # Inmovilizado: hay stock y el modelo no le ve demanda.
        if stock > 0 and demanda_mes <= 0:
            resumen["inmovilizado_clp"] += valor
            resumen["inmovilizado_n"] += 1
            suc["inmovilizado_clp"] += valor
            marca["inmovilizado_clp"] += valor
            inmovilizados.append({
                "producto": r.producto, "descripcion": r.descripcion,
                "sucursal_id": r.sucursal_id,
                "nombre_sucursal": r.nombre_sucursal or r.sucursal_id,
                "unidades": stock, "valor_clp": valor,
            })
        # Sobre-stock: se mueve, pero alcanza para demasiado tiempo.
        elif cobertura is not None and cobertura > dias_sobre_stock:
            resumen["sobre_stock_clp"] += valor
            resumen["sobre_stock_n"] += 1
            suc["sobre_stock_clp"] += valor

        # Quiebre: sin stock y con demanda viva.
        if stock <= 0 and demanda_mes > 0:
            resumen["quiebre_con_demanda_n"] += 1
            suc["quiebre_con_demanda_n"] += 1

        # Bajo punto de pedido (contando lo que viene en camino).
        disponible = stock + (r.stock_en_transito_suc or 0.0)
        if r.punto_de_pedido and demanda_mes > 0 and disponible < r.punto_de_pedido:
            resumen["bajo_punto_pedido_n"] += 1
            suc["bajo_punto_pedido_n"] += 1

        if cobertura is not None:
            coberturas.append(cobertura)

    resumen["cobertura_dias_mediana"] = round(median(coberturas), 1) if coberturas else None
    total = resumen["valor_inventario_clp"] or 1
    resumen["inmovilizado_pct"] = round(resumen["inmovilizado_clp"] / total * 100, 1)
    resumen["sobre_stock_pct"] = round(resumen["sobre_stock_clp"] / total * 100, 1)
    for clave in ("valor_inventario_clp", "unidades", "inmovilizado_clp", "sobre_stock_clp"):
        resumen[clave] = round(resumen[clave])

    def _ordenar(d: dict, campo: str) -> list[dict]:
        filas_ = sorted(d.values(), key=lambda x: x[campo], reverse=True)
        for x in filas_:
            for k, v in x.items():
                if isinstance(v, float):
                    x[k] = round(v)
        return filas_

    inmovilizados.sort(key=lambda x: x["valor_clp"], reverse=True)
    return {
        "resumen": resumen,
        "por_sucursal": _ordenar(por_sucursal, "valor_clp"),
        "por_marca": _ordenar(por_marca, "valor_clp")[:15],
        "top_inmovilizado": inmovilizados[:25],
        "dias_sobre_stock": dias_sobre_stock,
    }
