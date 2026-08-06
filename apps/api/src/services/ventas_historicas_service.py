"""Consulta del historico de ventas (desde 2018).

Responde las preguntas que hoy obligan a bajar un Excel de 40 MB y filtrarlo a
mano: como se vendio un producto por mes, que sucursal lo mueve, cuanto se vendio
en un periodo.
"""
from __future__ import annotations

from sqlalchemy import delete, func, insert, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import VentaHistorica
from .sugerido_service import PREFIJOS_EXCLUIDOS

settings = get_settings()

LIMITE_FILAS = 2000
_LOTE = 1000


def reemplazar_periodos(db: Session, filas: list[dict]) -> dict:
    """Carga meses de venta reemplazando SOLO los periodos que vienen.

    Se publica desde el motor, que es el unico que tiene los Excel a mano. Antes
    esto era un job manual que alguien tenia que acordarse de correr: el mes que
    se pegaba en el respaldo no llegaba nunca a la plataforma, y la columna
    "Venta 12m" y el grafico de consumo se quedaban atras sin avisar.

    Reemplazar por periodo (y no la tabla entera) permite recargar un mes
    corregido sin tocar el resto del historico.
    """
    tenant = settings.default_tenant_id
    validas: list[dict] = []
    for f in filas:
        periodo = str(f.get("periodo") or "").strip()
        producto = (f.get("producto") or "").strip()
        if len(periodo) != 6 or not periodo.isdigit() or not producto:
            continue
        try:
            cantidad = float(f.get("cantidad") or 0)
        except (TypeError, ValueError):
            continue
        neto = f.get("neto")
        try:
            neto = float(neto) if neto is not None else None
        except (TypeError, ValueError):
            neto = None
        validas.append({
            "tenant_id": tenant,
            "periodo": periodo,
            "producto": producto,
            # Se guarda el nombre TAL CUAL viene del Excel. Normalizarlo aca
            # perderia el dato original; quien cruza contra el sugerido usa
            # `sugerido_service.misma_sucursal`, que acepta las dos formas.
            "sucursal": (f.get("sucursal") or "").strip() or None,
            "cantidad": cantidad,
            "neto": neto,
            "n_lineas": int(f.get("n_lineas") or 0) or None,
        })

    if not validas:
        return {"filas_cargadas": 0, "ignoradas": len(filas), "periodos": []}

    periodos = sorted({f["periodo"] for f in validas})
    db.execute(
        delete(VentaHistorica).where(
            VentaHistorica.tenant_id == tenant,
            VentaHistorica.periodo.in_(periodos),
        )
    )
    for i in range(0, len(validas), _LOTE):
        db.execute(insert(VentaHistorica), validas[i : i + _LOTE])
    db.commit()
    return {
        "filas_cargadas": len(validas),
        "ignoradas": len(filas) - len(validas),
        "periodos": periodos,
    }


def _base(f: dict):
    stmt = select(VentaHistorica).where(
        VentaHistorica.tenant_id == settings.default_tenant_id
    )
    # Conceptos internos (contratistas, insumos de taller, incentivos): no son
    # repuestos y sus "unidades" son montos contables de millones que arruinan
    # cualquier ranking. Se ocultan igual que en el sugerido, salvo que se pidan.
    if not f.get("incluir_internos"):
        for pref in PREFIJOS_EXCLUIDOS:
            stmt = stmt.where(~VentaHistorica.producto.ilike(f"{pref}%"))
    if f.get("producto"):
        stmt = stmt.where(VentaHistorica.producto.ilike(f"%{f['producto']}%"))
    if f.get("sucursal"):
        stmt = stmt.where(VentaHistorica.sucursal == f["sucursal"])
    if f.get("periodo_desde"):
        stmt = stmt.where(VentaHistorica.periodo >= f["periodo_desde"])
    if f.get("periodo_hasta"):
        stmt = stmt.where(VentaHistorica.periodo <= f["periodo_hasta"])
    return stmt


def meta(db: Session) -> dict:
    """Que hay cargado: rango de periodos, filas y sucursales disponibles."""
    row = db.execute(
        select(
            func.min(VentaHistorica.periodo),
            func.max(VentaHistorica.periodo),
            func.count(),
        ).where(VentaHistorica.tenant_id == settings.default_tenant_id)
    ).first()
    sucursales = [
        s for (s,) in db.execute(
            select(VentaHistorica.sucursal)
            .where(VentaHistorica.tenant_id == settings.default_tenant_id)
            .distinct()
            .order_by(VentaHistorica.sucursal)
        ).all() if s
    ]
    return {
        "periodo_min": row[0], "periodo_max": row[1], "filas": row[2] or 0,
        "sucursales": sucursales,
    }


def por_periodo(db: Session, f: dict) -> list[dict]:
    """Serie mensual (para el grafico): una fila por periodo."""
    stmt = _base(f).with_only_columns(
        VentaHistorica.periodo,
        func.sum(VentaHistorica.cantidad),
        func.sum(VentaHistorica.neto),
    ).group_by(VentaHistorica.periodo).order_by(VentaHistorica.periodo)
    return [
        {"periodo": p, "cantidad": float(c or 0), "neto": float(n or 0)}
        for p, c, n in db.execute(stmt).all()
    ]


def por_sucursal(db: Session, f: dict) -> list[dict]:
    stmt = _base(f).with_only_columns(
        VentaHistorica.sucursal,
        func.sum(VentaHistorica.cantidad),
        func.sum(VentaHistorica.neto),
    ).group_by(VentaHistorica.sucursal)
    filas = [
        {"sucursal": s or "(sin sucursal)", "cantidad": float(c or 0), "neto": float(n or 0)}
        for s, c, n in db.execute(stmt).all()
    ]
    return sorted(filas, key=lambda x: x["cantidad"], reverse=True)


def detalle(db: Session, f: dict, limit: int = 500) -> dict:
    """Filas producto x sucursal x periodo, para ver o exportar."""
    limit = min(limit, LIMITE_FILAS)
    total = db.scalar(select(func.count()).select_from(_base(f).subquery())) or 0
    stmt = (
        _base(f)
        .order_by(VentaHistorica.periodo.desc(), VentaHistorica.cantidad.desc())
        .limit(limit)
    )
    items = [
        {
            "periodo": v.periodo, "producto": v.producto, "sucursal": v.sucursal,
            "cantidad": v.cantidad, "neto": v.neto, "n_lineas": v.n_lineas,
        }
        for v in db.scalars(stmt).all()
    ]
    return {"items": items, "total": total, "truncado": total > len(items)}
