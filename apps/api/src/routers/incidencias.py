"""Mesa de incidencias: reportes de errores de la plataforma.

Cualquier usuario autenticado reporta y ve LO SUYO; el admin ve todas y las
gestiona. Al responder o cerrar una incidencia se le avisa al que la reporto por
la campanita, para que el reporte no se sienta un buzon sin fondo.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import Incidencia, Usuario
from ..schemas import (
    IncidenciaCreate,
    IncidenciaOut,
    IncidenciasResponse,
    IncidenciaUpdate,
)
from ..services import auditoria_service
from ..services.auth import requiere_admin, requiere_auth

router = APIRouter(prefix="/api/incidencias", tags=["incidencias"])
settings = get_settings()


def _es_admin(db: Session, email: str) -> bool:
    user = db.get(Usuario, email)
    return bool(user and user.es_admin)


@router.get("", response_model=IncidenciasResponse)
def listar(
    estado: str | None = Query(None, description="Filtra por estado"),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    """El admin ve todas; el resto solo las que reporto."""
    stmt = select(Incidencia).where(Incidencia.tenant_id == settings.default_tenant_id)
    if not _es_admin(db, email):
        stmt = stmt.where(Incidencia.reportado_por == email)
    if estado:
        stmt = stmt.where(Incidencia.estado == estado)
    rows = list(db.scalars(stmt.order_by(desc(Incidencia.creado_en)).limit(limit)).all())
    abiertas = sum(1 for r in rows if r.estado in ("abierta", "en_revision"))
    return IncidenciasResponse(
        items=[IncidenciaOut.model_validate(r) for r in rows], abiertas=abiertas
    )


@router.post("", response_model=IncidenciaOut, status_code=201)
def crear(
    payload: IncidenciaCreate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    inc = Incidencia(
        tenant_id=settings.default_tenant_id,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        pantalla=payload.pantalla,
        producto=payload.producto,
        sucursal_id=payload.sucursal_id,
        reportado_por=email,
    )
    db.add(inc)
    auditoria_service.registrar(
        db, accion="incidencia_creada", entidad="incidencia", entidad_id=inc.id,
        usuario_email=email, producto=payload.producto, sucursal_id=payload.sucursal_id,
        detalle=payload.titulo,
    )
    # Aviso a los admin (la campanita es global, no por usuario).
    auditoria_service.notificar(
        db, tipo="incidencia", titulo=f"Nueva incidencia: {payload.titulo}",
        mensaje=payload.descripcion, creado_por_email=email,
        producto=payload.producto, sucursal_id=payload.sucursal_id,
    )
    db.commit()
    db.refresh(inc)
    return IncidenciaOut.model_validate(inc)


@router.patch("/{inc_id}", response_model=IncidenciaOut)
def actualizar(
    inc_id: str,
    payload: IncidenciaUpdate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_admin),
):
    """Cambiar estado o responder. Solo admin."""
    inc = db.get(Incidencia, inc_id)
    if not inc or inc.tenant_id != settings.default_tenant_id:
        raise HTTPException(status_code=404, detail="La incidencia no existe")

    datos = payload.model_dump(exclude_unset=True)
    cerrada = datos.get("estado") in ("resuelta", "descartada")
    for campo, valor in datos.items():
        setattr(inc, campo, valor)
    if cerrada:
        inc.resuelto_por = email

    auditoria_service.registrar(
        db, accion="incidencia_actualizada", entidad="incidencia", entidad_id=inc.id,
        usuario_email=email, detalle=f"{inc.estado}: {inc.titulo}",
    )
    if cerrada and inc.reportado_por:
        # El que reporto se entera de que su reporte tuvo respuesta.
        auditoria_service.notificar(
            db, tipo="incidencia",
            titulo=f"Tu reporte quedo {inc.estado.replace('_', ' ')}: {inc.titulo}",
            mensaje=inc.respuesta, creado_por_email=email,
            producto=inc.producto, sucursal_id=inc.sucursal_id,
        )
    db.commit()
    db.refresh(inc)
    return IncidenciaOut.model_validate(inc)
