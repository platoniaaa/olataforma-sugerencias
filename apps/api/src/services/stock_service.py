"""Stock por producto-bodega: lo publica el motor, lo consultan catalogo y sugerido."""
from __future__ import annotations

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import DimSucursal, StockUnificado

settings = get_settings()

# Insert por lotes: el snapshot completo son ~30k filas y una por una tarda de mas.
_LOTE = 1000


def reemplazar(db: Session, filas: list[dict]) -> dict:
    """Reemplaza la foto del stock con la que acaba de leer el motor.

    Cada fila: producto, bodega, sucursal_id, stock, origen. Es una foto del
    stock vigente, no un historico: se borra todo y se vuelve a insertar.

    Antes esta tabla solo la llenaba el Power BI Desktop; al retirarlo quedo
    congelada y el catalogo mostraba stock viejo como si fuera de hoy.
    """
    tenant = settings.default_tenant_id
    validas: list[dict] = []
    for f in filas:
        prod = (f.get("producto") or "").strip()
        if not prod:
            continue
        try:
            stock = float(f.get("stock") or 0)
        except (TypeError, ValueError):
            continue
        validas.append(
            {
                "tenant_id": tenant,
                "producto": prod,
                "bodega": (f.get("bodega") or "").strip() or None,
                "sucursal_id": (f.get("sucursal_id") or "").strip() or None,
                "stock": stock,
                "origen": (f.get("origen") or "").strip() or None,
            }
        )

    # Si el motor manda una tanda vacia NO se borra lo que hay: es mejor mostrar
    # la foto anterior que dejar el catalogo sin stock por una corrida fallida.
    if not validas:
        return {"filas_cargadas": 0, "ignoradas": len(filas), "reemplazo": False}

    db.execute(delete(StockUnificado).where(StockUnificado.tenant_id == tenant))
    for i in range(0, len(validas), _LOTE):
        db.execute(insert(StockUnificado), validas[i : i + _LOTE])
    db.commit()
    return {
        "filas_cargadas": len(validas),
        "ignoradas": len(filas) - len(validas),
        "reemplazo": True,
    }


def stock_total_por_producto(db: Session, productos: list[str]) -> dict[str, float]:
    """Suma stock total para una lista de códigos. Devuelve {producto: total}.

    Tolerante: si la tabla aún no existe (primer deploy antes del push), devuelve {}.
    """
    if not productos:
        return {}
    stmt = (
        select(StockUnificado.producto, func.coalesce(func.sum(StockUnificado.stock), 0))
        .where(StockUnificado.producto.in_(productos))
        .group_by(StockUnificado.producto)
    )
    try:
        return {p: float(t) for p, t in db.execute(stmt).all()}
    except Exception:
        db.rollback()
        return {}


def stock_operativo_por_producto(db: Session, productos: list[str]) -> dict[str, float]:
    """Stock que se puede vender, por codigo. Devuelve {producto: total}.

    Distinto de `stock_total_por_producto`, que suma TODO lo que hay en
    `stock_unificado`, incluidas las bodegas virtuales: Dañados, Scrap, Devolucion,
    Mercado Libre, Importacion, Comex. Una unidad en Dañados no se le puede vender
    a nadie, y contarla como stock hace creer que el repuesto todavia se mueve.

    El filtro no es una lista escrita a mano: `dim_sucursal` trae solo las
    sucursales operativas (13 al 24-08-2026) y las bodegas virtuales no estan.
    Cuando Curifor abra o cierre una sucursal, esto se entera solo.
    """
    if not productos:
        return {}
    stmt = (
        select(StockUnificado.producto, func.coalesce(func.sum(StockUnificado.stock), 0))
        .join(DimSucursal, DimSucursal.sucursal_id == StockUnificado.sucursal_id)
        .where(StockUnificado.producto.in_(productos))
        .group_by(StockUnificado.producto)
    )
    try:
        return {p: float(t) for p, t in db.execute(stmt).all()}
    except Exception:
        db.rollback()
        return {}


def _bodegas_excluidas(db: Session) -> set[str]:
    # Import local: precios_service importa de aqui y un import de modulo haria un ciclo.
    from .precios_service import bodegas_excluidas

    return bodegas_excluidas(db)


def filtro_vendible(db: Session):
    """Funcion que deja de una lista de filas de stock solo las que un vendedor puede prometer.

    Misma regla que la lista de precios (`precios_service._stock`): sin las bodegas no
    disponibles (danados, devolucion, scrap, sin bodega), sin el stock de Frontera -que
    `stock_unificado` trae junto al de Curifor- y sin saldos en cero o negativos. Una
    unidad en Danados o en la otra empresa no se le puede vender a un cliente.

    Cada fila es un dict con `bodega`, `origen` y `stock` (lo que devuelve `stock_por_sucursal`).
    """
    excluidas = _bodegas_excluidas(db)

    def _filtrar(filas: list[dict]) -> list[dict]:
        return [
            r for r in filas
            if (r.get("stock") or 0) > 0
            and str(r.get("origen") or "CURIFOR").upper() != "FRONTERA"
            and (r.get("bodega") or "") not in excluidas
        ]

    return _filtrar


def _cuenta_para_el_vendedor(db: Session):
    """Condiciones SQL de la misma regla, para sumar o filtrar sin traer las filas."""
    condiciones = [
        StockUnificado.stock > 0,
        func.upper(func.coalesce(StockUnificado.origen, "CURIFOR")) != "FRONTERA",
    ]
    excluidas = _bodegas_excluidas(db)
    if excluidas:
        condiciones.append(func.coalesce(StockUnificado.bodega, "").notin_(excluidas))
    return condiciones


def stock_vendible_por_producto(db: Session, productos: list[str]) -> dict[str, float]:
    """{producto: stock que se puede vender}. Un producto sin stock vendible no aparece."""
    if not productos:
        return {}
    stmt = (
        select(StockUnificado.producto, func.coalesce(func.sum(StockUnificado.stock), 0))
        .where(StockUnificado.producto.in_(productos), *_cuenta_para_el_vendedor(db))
        .group_by(StockUnificado.producto)
    )
    try:
        return {p: float(t) for p, t in db.execute(stmt).all()}
    except Exception:
        db.rollback()
        return {}


def productos_con_stock_vendible(db: Session):
    """Subconsulta con los productos que tienen stock vendible (para el filtro 'solo con stock')."""
    return select(StockUnificado.producto).where(*_cuenta_para_el_vendedor(db))


def stock_por_sucursal(db: Session, producto: str) -> list[dict]:
    """Lista filas (bodega, sucursal_id, stock, origen) de un producto, orden por stock desc."""
    stmt = (
        select(
            StockUnificado.bodega,
            StockUnificado.sucursal_id,
            StockUnificado.stock,
            StockUnificado.origen,
        )
        .where(StockUnificado.producto == producto)
        .order_by(StockUnificado.stock.desc())
    )
    try:
        return [
            {"bodega": b, "sucursal_id": s, "stock": float(st or 0), "origen": o}
            for b, s, st, o in db.execute(stmt).all()
        ]
    except Exception:
        db.rollback()
        return []
