"""Proveedor deducido por producto: publicarlo y consultarlo.

El motor manda la tabla completa en cada corrida y aca se REEMPLAZA (no se
acumula): es una foto de la deduccion vigente, no un historico. Ver
`models/proveedor_producto.py` para el por que.
"""
from __future__ import annotations

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import ProveedorProducto

settings = get_settings()

_LOTE = 1000


def reemplazar(db: Session, filas: list[dict]) -> dict:
    """Reemplaza la foto con la que acaba de deducir el motor.

    Cada fila: producto, proveedor. Si un producto viene repetido gana el primero:
    el motor ya resolvio el desempate con la misma regla que usa el sugerido, y
    elegir aca de nuevo abriria la puerta a dos verdades distintas.
    """
    tenant = settings.default_tenant_id
    vistos: dict[str, str] = {}
    for f in filas:
        producto = (f.get("producto") or "").strip()
        proveedor = (f.get("proveedor") or "").strip()
        if producto and proveedor and producto not in vistos:
            vistos[producto] = proveedor

    db.execute(delete(ProveedorProducto).where(ProveedorProducto.tenant_id == tenant))
    registros = [
        {"tenant_id": tenant, "producto": p, "proveedor": prov}
        for p, prov in vistos.items()
    ]
    for i in range(0, len(registros), _LOTE):
        lote = registros[i : i + _LOTE]
        if lote:
            db.execute(insert(ProveedorProducto).values(lote))
    db.commit()
    return {"filas_cargadas": len(registros), "ignoradas": len(filas) - len(registros)}


def mapa(db: Session, productos: set[str] | list[str]) -> dict[str, str]:
    """{producto: proveedor} para los productos pedidos, en una sola query."""
    productos = [p for p in set(productos) if p]
    if not productos:
        return {}
    filas = db.execute(
        select(ProveedorProducto.producto, ProveedorProducto.proveedor).where(
            ProveedorProducto.tenant_id == settings.default_tenant_id,
            ProveedorProducto.producto.in_(productos),
        )
    ).all()
    return {p: prov for p, prov in filas}


def total(db: Session) -> int:
    """Cuantos productos tienen proveedor deducido (para el panel de admin)."""
    return db.scalar(
        select(func.count())
        .select_from(ProveedorProducto)
        .where(ProveedorProducto.tenant_id == settings.default_tenant_id)
    ) or 0
