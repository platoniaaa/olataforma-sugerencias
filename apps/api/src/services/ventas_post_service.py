"""Consultas sobre el resumen pre-calculado de la Planilla Post Venta.

Los datos detallados viven en post_venta_fila (JSON posicional), pero los
KPIs y graficos los leemos de post_venta_resumen para ser rapidos.
"""
from __future__ import annotations

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import PostVentaResumen

settings = get_settings()


def _tenant() -> str:
    return settings.default_tenant_id


def periodos_disponibles(db: Session) -> list[str]:
    """Lista los periodos (YYYYMM) que tienen datos, ordenados ascendentemente."""
    rows = db.execute(
        select(PostVentaResumen.periodo)
        .where(PostVentaResumen.tenant_id == _tenant())
        .distinct()
        .order_by(PostVentaResumen.periodo.asc())
    ).all()
    return [r[0] for r in rows if r[0]]


def kpis(db: Session) -> dict:
    """Totales del periodo mas reciente + el anterior + variacion %."""
    periodos = periodos_disponibles(db)
    if not periodos:
        return {
            "periodo_actual": None, "periodo_anterior": None,
            "actual": {"clp": 0, "unidades": 0, "n_lineas": 0},
            "anterior": {"clp": 0, "unidades": 0, "n_lineas": 0},
            "var_clp_pct": None, "var_unidades_pct": None,
        }
    p_actual = periodos[-1]
    p_anterior = periodos[-2] if len(periodos) > 1 else None

    def _totales(periodo: str | None) -> dict:
        if not periodo:
            return {"clp": 0.0, "unidades": 0.0, "n_lineas": 0}
        row = db.execute(
            select(
                func.coalesce(func.sum(PostVentaResumen.total_clp), 0),
                func.coalesce(func.sum(PostVentaResumen.total_unidades), 0),
                func.coalesce(func.sum(PostVentaResumen.n_lineas), 0),
            )
            .where(
                PostVentaResumen.tenant_id == _tenant(),
                PostVentaResumen.periodo == periodo,
            )
        ).first()
        clp, unid, nl = row or (0, 0, 0)
        return {"clp": float(clp), "unidades": float(unid), "n_lineas": int(nl)}

    act = _totales(p_actual)
    ant = _totales(p_anterior)

    def _var(a: float, b: float) -> float | None:
        if not b:
            return None
        return ((a - b) / b) * 100.0

    return {
        "periodo_actual": p_actual,
        "periodo_anterior": p_anterior,
        "actual": act,
        "anterior": ant,
        "var_clp_pct": _var(act["clp"], ant["clp"]),
        "var_unidades_pct": _var(act["unidades"], ant["unidades"]),
    }


def serie_mensual(db: Session, meses: int = 12) -> list[dict]:
    """Serie por periodo: ultimos N meses con totales CLP + unidades."""
    rows = db.execute(
        select(
            PostVentaResumen.periodo,
            func.coalesce(func.sum(PostVentaResumen.total_clp), 0),
            func.coalesce(func.sum(PostVentaResumen.total_unidades), 0),
        )
        .where(PostVentaResumen.tenant_id == _tenant())
        .group_by(PostVentaResumen.periodo)
        .order_by(PostVentaResumen.periodo.asc())
    ).all()
    serie = [
        {"periodo": p, "clp": float(c), "unidades": float(u)}
        for p, c, u in rows if p
    ]
    return serie[-meses:]


def por_sucursal(db: Session, periodo: str) -> list[dict]:
    """Lista de sucursales con sus totales para un periodo dado, orden por CLP desc."""
    rows = db.execute(
        select(
            PostVentaResumen.sucursal,
            func.coalesce(func.sum(PostVentaResumen.total_clp), 0),
            func.coalesce(func.sum(PostVentaResumen.total_unidades), 0),
            func.coalesce(func.sum(PostVentaResumen.n_lineas), 0),
        )
        .where(
            PostVentaResumen.tenant_id == _tenant(),
            PostVentaResumen.periodo == periodo,
        )
        .group_by(PostVentaResumen.sucursal)
        .order_by(desc(func.sum(PostVentaResumen.total_clp)))
    ).all()
    return [
        {
            "sucursal": s or "(sin sucursal)",
            "clp": float(c),
            "unidades": float(u),
            "n_lineas": int(n),
        }
        for s, c, u, n in rows
    ]
