"""Endpoints de documentos: enlaces directos a archivos que viven en SharePoint.

Todo usuario autenticado ve la lista y abre los enlaces; solo un admin puede
crear, editar o borrar. La plataforma no descarga ni almacena nada: el archivo
se baja desde SharePoint con la cuenta corporativa del propio usuario.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import EnlaceDocumento
from ..schemas import DocumentoCreate, DocumentoOut, DocumentoUpdate
from ..services import auditoria_service
from ..services.auth import requiere_admin, requiere_auth

router = APIRouter(prefix="/api/documentos", tags=["documentos"])
settings = get_settings()


def _obtener(db: Session, doc_id: str) -> EnlaceDocumento:
    doc = db.get(EnlaceDocumento, doc_id)
    if not doc or doc.tenant_id != settings.default_tenant_id:
        raise HTTPException(status_code=404, detail="El documento no existe")
    return doc


@router.get("", response_model=list[DocumentoOut])
def listar(
    incluir_inactivos: bool = Query(False),
    db: Session = Depends(get_db),
):
    """Enlaces publicados, ordenados por categoria y orden manual."""
    stmt = select(EnlaceDocumento).where(
        EnlaceDocumento.tenant_id == settings.default_tenant_id
    )
    if not incluir_inactivos:
        stmt = stmt.where(EnlaceDocumento.activo.is_(True))
    rows = list(db.scalars(stmt).all())
    rows.sort(key=lambda d: (d.categoria.lower(), d.orden, d.titulo.lower()))
    return [DocumentoOut.model_validate(r) for r in rows]


@router.post("", response_model=DocumentoOut, status_code=201)
def crear(
    payload: DocumentoCreate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_admin),
):
    doc = EnlaceDocumento(
        tenant_id=settings.default_tenant_id,
        titulo=payload.titulo,
        descripcion=payload.descripcion,
        url=payload.url,
        categoria=(payload.categoria or "General").strip() or "General",
        orden=payload.orden,
        creado_por_email=email,
    )
    db.add(doc)
    auditoria_service.registrar(
        db, accion="documento_creado", entidad="documento", entidad_id=doc.id,
        usuario_email=email, detalle=f"{doc.categoria}: {doc.titulo}",
    )
    db.commit()
    db.refresh(doc)
    return DocumentoOut.model_validate(doc)


@router.patch("/{doc_id}", response_model=DocumentoOut)
def editar(
    doc_id: str,
    payload: DocumentoUpdate,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_admin),
):
    doc = _obtener(db, doc_id)
    for campo, valor in payload.model_dump(exclude_unset=True).items():
        setattr(doc, campo, valor)
    auditoria_service.registrar(
        db, accion="documento_editado", entidad="documento", entidad_id=doc.id,
        usuario_email=email, detalle=f"{doc.categoria}: {doc.titulo}",
    )
    db.commit()
    db.refresh(doc)
    return DocumentoOut.model_validate(doc)


@router.delete("/{doc_id}", status_code=204)
def eliminar(
    doc_id: str,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_admin),
):
    doc = _obtener(db, doc_id)
    auditoria_service.registrar(
        db, accion="documento_eliminado", entidad="documento", entidad_id=doc.id,
        usuario_email=email, detalle=f"{doc.categoria}: {doc.titulo}",
    )
    db.delete(doc)
    db.commit()


@router.post("/{doc_id}/apertura", status_code=204)
def registrar_apertura(
    doc_id: str,
    db: Session = Depends(get_db),
    email: str = Depends(requiere_auth),
):
    """Deja constancia de quien abrio que documento (queda en Auditoria)."""
    doc = _obtener(db, doc_id)
    auditoria_service.registrar(
        db, accion="documento_abierto", entidad="documento", entidad_id=doc.id,
        usuario_email=email, detalle=f"{doc.categoria}: {doc.titulo}",
    )
    db.commit()
