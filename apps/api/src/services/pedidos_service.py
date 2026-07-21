"""Registro de lo que ya se pidio del sugerido.

Responde dos preguntas que hoy se contestan de memoria: "¿esto ya lo pedi?" y
"¿cuanto de lo que el modelo sugirio se compro de verdad?".
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import LineaPedida

settings = get_settings()

# Ventana en la que un pedido sigue "contando" contra el sugerido vigente. Mas
# alla de eso se asume que ya se recibio (o que se perdio) y el sugerido vuelve a
# pedirlo: un pedido de hace dos meses no puede tapar una necesidad real de hoy.
DIAS_VIGENCIA = 45


def _desde() -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=DIAS_VIGENCIA)


def registrar(
    db: Session,
    *,
    producto: str,
    sucursal_id: str,
    unidades: float,
    n_oc: str | None = None,
    proveedor: str | None = None,
    usuario_email: str | None = None,
) -> LineaPedida:
    linea = LineaPedida(
        tenant_id=settings.default_tenant_id,
        producto=producto,
        sucursal_id=sucursal_id,
        unidades=unidades,
        n_oc=(n_oc or "").strip() or None,
        proveedor=proveedor,
        creado_por=usuario_email,
    )
    db.add(linea)
    db.commit()
    db.refresh(linea)
    return linea


def pedido_por_par(db: Session) -> dict[tuple[str, str], float]:
    """Unidades pedidas y aun no recibidas por (producto, sucursal), vigentes."""
    filas = db.execute(
        select(
            LineaPedida.producto,
            LineaPedida.sucursal_id,
            func.sum(LineaPedida.unidades),
        )
        .where(
            LineaPedida.tenant_id == settings.default_tenant_id,
            LineaPedida.recibido.is_(False),
            LineaPedida.creado_en >= _desde(),
        )
        .group_by(LineaPedida.producto, LineaPedida.sucursal_id)
    ).all()
    return {(str(p), str(s)): float(u or 0) for p, s, u in filas}


def listar(
    db: Session, producto: str | None = None, sucursal_id: str | None = None, limit: int = 200
) -> list[LineaPedida]:
    stmt = select(LineaPedida).where(LineaPedida.tenant_id == settings.default_tenant_id)
    if producto:
        stmt = stmt.where(LineaPedida.producto == producto)
    if sucursal_id:
        stmt = stmt.where(LineaPedida.sucursal_id == sucursal_id)
    return list(db.scalars(stmt.order_by(desc(LineaPedida.creado_en)).limit(limit)).all())


def marcar_recibida(db: Session, linea_id: str) -> LineaPedida | None:
    linea = db.get(LineaPedida, linea_id)
    if not linea or linea.tenant_id != settings.default_tenant_id:
        return None
    linea.recibido = True
    linea.fecha_recepcion = datetime.now(timezone.utc)
    db.commit()
    db.refresh(linea)
    return linea


def eliminar(db: Session, linea_id: str) -> bool:
    linea = db.get(LineaPedida, linea_id)
    if not linea or linea.tenant_id != settings.default_tenant_id:
        return False
    db.delete(linea)
    db.commit()
    return True


def agregar_a_filas(items: list[dict], db: Session) -> None:
    """Suma a cada fila del sugerido lo ya pedido (columna `unidades_pedidas`).

    No descuenta del sugerido: el modelo ya considera el transito cuando la OC
    llega al ERP. Esto es informativo, para no pedir dos veces mientras tanto."""
    if not items:
        return
    pedidos = pedido_por_par(db)
    if not pedidos:
        for it in items:
            it.setdefault("unidades_pedidas", None)
        return
    for it in items:
        clave = (str(it.get("producto")), str(it.get("sucursal_id")))
        it["unidades_pedidas"] = pedidos.get(clave)
