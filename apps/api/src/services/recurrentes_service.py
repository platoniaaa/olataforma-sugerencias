"""Lógica de las sugerencias recurrentes: crear, listar, eliminar y procesar.

Comportamiento "mantener vigente": cada vez que una regla se ejecuta, archiva la
instancia que ella misma creó antes y crea una nueva, así no se acumulan.
"""
from __future__ import annotations

import json
from datetime import date, timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import SugerenciaManual, SugerenciaRecurrente
from ..schemas import SugeridoFiltros
from .sugerido_service import pares_filtrados

settings = get_settings()


def _archivar_instancias(db: Session, rec_id: str) -> None:
    db.execute(
        update(SugerenciaManual)
        .where(SugerenciaManual.recurrente_id == rec_id, SugerenciaManual.archivada.is_(False))
        .values(archivada=True)
    )


def _crear_instancias(db: Session, rec: SugerenciaRecurrente) -> int:
    """Archiva la instancia anterior de esta regla y crea la nueva. Devuelve cuántas creó."""
    _archivar_instancias(db, rec.id)
    tenant = rec.tenant_id
    nuevas: list[SugerenciaManual] = []
    if rec.modo == "individual":
        nuevas.append(
            SugerenciaManual(
                producto=rec.producto, sucursal_id=rec.sucursal_id, unidades=rec.unidades,
                motivo=rec.motivo, creado_por="recurrente", tenant_id=tenant, recurrente_id=rec.id,
            )
        )
    else:  # grupo
        f = SugeridoFiltros(**json.loads(rec.filtros or "{}"))
        for prod, suc in pares_filtrados(db, f):
            nuevas.append(
                SugerenciaManual(
                    producto=prod, sucursal_id=suc, unidades=rec.unidades, motivo=rec.motivo,
                    creado_por="recurrente", tenant_id=tenant, recurrente_id=rec.id,
                )
            )
    db.add_all(nuevas)
    return len(nuevas)


def _avanzar(rec: SugerenciaRecurrente, hoy: date) -> None:
    rec.ultima_ejecucion = hoy
    prox = rec.proxima_ejecucion
    while prox <= hoy:
        prox = prox + timedelta(days=rec.cada_dias)
    rec.proxima_ejecucion = prox
    if rec.fecha_fin and prox > rec.fecha_fin:
        rec.activa = False


def crear(db: Session, payload) -> SugerenciaRecurrente:
    hoy = date.today()
    filtros_json = None
    if payload.modo == "grupo":
        filtros_json = json.dumps((payload.filtros or SugeridoFiltros()).model_dump())
    rec = SugerenciaRecurrente(
        tenant_id=settings.default_tenant_id,
        modo=payload.modo,
        producto=payload.producto,
        sucursal_id=payload.sucursal_id,
        filtros=filtros_json,
        unidades=payload.unidades,
        motivo=payload.motivo,
        cada_dias=payload.cada_dias,
        fecha_fin=payload.fecha_fin,
        proxima_ejecucion=hoy,
        creado_por=settings.admin_email,
    )
    db.add(rec)
    db.flush()
    # Aplica de inmediato (primera instancia) y agenda la próxima.
    _crear_instancias(db, rec)
    _avanzar(rec, hoy)
    db.commit()
    db.refresh(rec)
    return rec


def listar(db: Session, incluir_inactivas: bool = False) -> list[SugerenciaRecurrente]:
    stmt = select(SugerenciaRecurrente).where(
        SugerenciaRecurrente.tenant_id == settings.default_tenant_id
    )
    if not incluir_inactivas:
        stmt = stmt.where(SugerenciaRecurrente.activa.is_(True))
    stmt = stmt.order_by(SugerenciaRecurrente.creado_en.desc())
    return list(db.scalars(stmt).all())


def eliminar(db: Session, rec_id: str) -> bool:
    rec = db.get(SugerenciaRecurrente, rec_id)
    if not rec:
        return False
    _archivar_instancias(db, rec_id)  # quita su aporte vigente de la compra
    db.delete(rec)
    db.commit()
    return True


def procesar(db: Session, hoy: date | None = None) -> dict:
    """Ejecuta todas las reglas vigentes cuyo turno llegó. Lo llama el cron diario."""
    hoy = hoy or date.today()
    recs = list(
        db.scalars(
            select(SugerenciaRecurrente).where(
                SugerenciaRecurrente.activa.is_(True),
                SugerenciaRecurrente.proxima_ejecucion <= hoy,
            )
        ).all()
    )
    creadas = 0
    procesadas = 0
    for rec in recs:
        if rec.fecha_fin and hoy > rec.fecha_fin:
            rec.activa = False
            continue
        creadas += _crear_instancias(db, rec)
        _avanzar(rec, hoy)
        procesadas += 1
    db.commit()
    return {"recurrencias_procesadas": procesadas, "sugerencias_creadas": creadas}


def resumen(rec: SugerenciaRecurrente) -> str:
    """Texto corto para mostrar la regla en la UI."""
    if rec.modo == "individual":
        return f"{rec.producto} · {rec.sucursal_id}"
    try:
        f = json.loads(rec.filtros or "{}")
    except json.JSONDecodeError:
        f = {}
    partes: list[str] = []
    if f.get("sucursales"):
        partes.append("Sucursal: " + ", ".join(f["sucursales"]))
    if f.get("filtro1"):
        partes.append("Marca: " + ", ".join(f["filtro1"]))
    if f.get("abc"):
        partes.append("ABC: " + ", ".join(f["abc"]))
    return " · ".join(partes) if partes else "Todos los productos"
