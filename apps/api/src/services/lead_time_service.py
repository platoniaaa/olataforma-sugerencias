"""Lead time calculado por el motor: publicarlo y consultarlo.

El motor manda la tabla completa en cada corrida y aca se REEMPLAZA (no se
acumula): es una foto del calculo vigente, no un historico.
"""
from __future__ import annotations

from datetime import datetime, timezone

from sqlalchemy import delete, func, or_, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import LeadTimeProveedorSucursal

settings = get_settings()


def reemplazar(db: Session, filas: list[dict]) -> dict:
    """Reemplaza la foto del lead time con la que acaba de calcular el motor.

    Cada fila: proveedor, sucursal_id (None = global del proveedor),
    lead_time_dias, n_muestras.
    """
    tenant = settings.default_tenant_id
    ahora = datetime.now(timezone.utc)
    db.execute(
        delete(LeadTimeProveedorSucursal).where(
            LeadTimeProveedorSucursal.tenant_id == tenant
        )
    )
    validas = 0
    for f in filas:
        prov = (f.get("proveedor") or "").strip()
        lt = f.get("lead_time_dias")
        if not prov or lt is None:
            continue
        suc = (f.get("sucursal_id") or "").strip() or None
        db.add(
            LeadTimeProveedorSucursal(
                tenant_id=tenant,
                actualizado_en=ahora,
                proveedor=prov,
                sucursal_id=suc,
                lead_time_dias=float(lt),
                n_muestras=int(f["n_muestras"]) if f.get("n_muestras") is not None else None,
            )
        )
        validas += 1
    db.commit()
    return {"filas_cargadas": validas, "ignoradas": len(filas) - validas}


def listar(
    db: Session,
    *,
    buscar: str | None = None,
    solo_global: bool = False,
    limite: int = 200,
) -> dict:
    """Filas del lead time, con buscador por proveedor o sucursal."""
    tenant = settings.default_tenant_id
    cond = [LeadTimeProveedorSucursal.tenant_id == tenant]
    if solo_global:
        cond.append(LeadTimeProveedorSucursal.sucursal_id.is_(None))
    if buscar:
        patron = f"%{buscar.strip().lower()}%"
        cond.append(
            or_(
                func.lower(LeadTimeProveedorSucursal.proveedor).like(patron),
                func.lower(func.coalesce(LeadTimeProveedorSucursal.sucursal_id, "")).like(patron),
            )
        )

    total = db.scalar(
        select(func.count()).select_from(LeadTimeProveedorSucursal).where(*cond)
    ) or 0
    filas = db.scalars(
        select(LeadTimeProveedorSucursal)
        .where(*cond)
        .order_by(
            LeadTimeProveedorSucursal.proveedor,
            LeadTimeProveedorSucursal.sucursal_id.nulls_first(),
        )
        .limit(limite)
    ).all()
    actualizado = db.scalar(
        select(func.max(LeadTimeProveedorSucursal.actualizado_en)).where(
            LeadTimeProveedorSucursal.tenant_id == tenant
        )
    )
    return {
        "total": total,
        "actualizado_en": actualizado,
        "items": [
            {
                "proveedor": f.proveedor,
                "sucursal_id": f.sucursal_id,
                "lead_time_dias": round(f.lead_time_dias, 2),
                "n_muestras": f.n_muestras,
            }
            for f in filas
        ],
    }
