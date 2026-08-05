"""Stock en transito: lo publica el motor, lo consulta el detalle del requerimiento.

Ver `models/stock_transito.py` para el porque de tener tabla propia en vez de
leerlo del sugerido.
"""
from __future__ import annotations

from datetime import date

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import StockTransito

settings = get_settings()

_LOTE = 1000


def _fecha(v) -> date | None:
    """Acepta date, 'YYYY-MM-DD' y vacio. Una fecha rara no invalida la fila:
    la cantidad es el dato que importa, la fecha es contexto."""
    if isinstance(v, date):
        return v
    if not v:
        return None
    try:
        return date.fromisoformat(str(v)[:10])
    except ValueError:
        return None


def reemplazar(db: Session, filas: list[dict]) -> dict:
    """Reemplaza la foto del transito con la que acaba de calcular el motor.

    Cada fila: producto, sucursal_id, cantidad, pedido_desde.
    """
    tenant = settings.default_tenant_id
    validas: list[dict] = []
    for f in filas:
        prod = (f.get("producto") or "").strip()
        if not prod:
            continue
        try:
            cantidad = float(f.get("cantidad") or 0)
        except (TypeError, ValueError):
            continue
        # Una OC en cero no es informacion: solo agranda la tabla.
        if cantidad == 0:
            continue
        validas.append(
            {
                "tenant_id": tenant,
                "producto": prod,
                "sucursal_id": (f.get("sucursal_id") or "").strip() or None,
                "cantidad": cantidad,
                "pedido_desde": _fecha(f.get("pedido_desde")),
            }
        )

    # Igual que el stock: una tanda vacia NO borra lo que hay. Es mejor mostrar la
    # foto anterior (y que se note vieja) que decirle al comprador "no viene nada
    # en camino" porque una corrida del motor fallo.
    if not validas:
        return {"filas_cargadas": 0, "ignoradas": len(filas), "reemplazo": False}

    db.execute(delete(StockTransito).where(StockTransito.tenant_id == tenant))
    for i in range(0, len(validas), _LOTE):
        db.execute(insert(StockTransito), validas[i : i + _LOTE])
    db.commit()
    return {
        "filas_cargadas": len(validas),
        "ignoradas": len(filas) - len(validas),
        "reemplazo": True,
    }


def por_producto(
    db: Session, productos: set[str], sucursal_id: str | None = None
) -> dict[str, dict]:
    """{producto: {cantidad, pedido_desde}} para una sucursal, o el total nacional.

    Tolerante a que la tabla no exista todavia: mientras el motor no corra una vez
    con el cambio, el detalle muestra "sin dato" en vez de reventar.
    """
    if not productos:
        return {}
    stmt = (
        select(
            StockTransito.producto,
            func.sum(StockTransito.cantidad),
            func.min(StockTransito.pedido_desde),
        )
        .where(StockTransito.producto.in_(productos))
        .group_by(StockTransito.producto)
    )
    if sucursal_id:
        stmt = stmt.where(StockTransito.sucursal_id == sucursal_id)
    try:
        return {
            p: {"cantidad": float(c or 0), "pedido_desde": d}
            for p, c, d in db.execute(stmt).all()
        }
    except Exception:  # noqa: BLE001 - tabla ausente antes de la primera corrida
        db.rollback()
        return {}


def detalle_por_sucursal(db: Session, producto: str) -> list[dict]:
    """Donde esta el transito de un producto, de mayor a menor.

    Sirve para la decision real: si vienen 10 a Curico y ninguno a Linderos, la
    respuesta puede ser un traslado y no una compra.
    """
    stmt = (
        select(
            StockTransito.sucursal_id,
            func.sum(StockTransito.cantidad),
            func.min(StockTransito.pedido_desde),
        )
        .where(StockTransito.producto == producto)
        .group_by(StockTransito.sucursal_id)
        .order_by(func.sum(StockTransito.cantidad).desc())
    )
    try:
        return [
            {"sucursal_id": s, "cantidad": float(c or 0),
             "pedido_desde": d.isoformat() if d else None}
            for s, c, d in db.execute(stmt).all()
        ]
    except Exception:  # noqa: BLE001
        db.rollback()
        return []
