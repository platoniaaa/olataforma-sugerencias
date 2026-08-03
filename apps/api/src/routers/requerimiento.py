"""Requerimiento de sucursal: pegar la lista, decidir, bajar el archivo del portal.

Reemplaza el Excel que el comprador usaba antes de la plataforma. El porque de
cada decision esta en `services/requerimiento_service.py` y `services/archivo_portal.py`.
"""
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import delete, insert
from sqlalchemy.orm import Session

from ..config import get_settings
from ..db import get_db
from ..models import SkuProveedor
from ..schemas import (
    AnalizarLineasRequest,
    AnalizarTextoRequest,
    ArchivoPortalRequest,
    RequerimientoResponse,
    SkuProveedorCarga,
)
from ..services import archivo_portal, auditoria_service, requerimiento_service
from ..services.auth import requiere_admin

router = APIRouter(prefix="/api/requerimiento", tags=["requerimiento"])
settings = get_settings()


@router.post("/analizar", response_model=RequerimientoResponse)
def analizar_texto(payload: AnalizarTextoRequest, db: Session = Depends(get_db)):
    """Texto pegado -> lineas con el contexto para decidir."""
    lineas = requerimiento_service.parsear(db, payload.texto)
    return requerimiento_service.analizar(db, payload.sucursal_id, lineas)


@router.post("/reanalizar", response_model=RequerimientoResponse)
def reanalizar(payload: AnalizarLineasRequest, db: Session = Depends(get_db)):
    """Mismo analisis pero con las lineas ya editadas (cantidades corregidas)."""
    lineas = [linea.model_dump() for linea in payload.lineas]
    return requerimiento_service.analizar(db, payload.sucursal_id, lineas)


@router.post("/archivo-portal")
def archivo_para_portal(payload: ArchivoPortalRequest, db: Session = Depends(get_db)):
    """CSV listo para subir al portal del proveedor.

    Cuantas lineas quedaron fuera (sin SKU o sin cantidad) viaja en una cabecera,
    para poder decirlo en pantalla en vez de que el comprador lo descubra cuando
    el portal le tire un error.
    """
    try:
        contenido, descartadas = archivo_portal.generar_csv(
            db, [linea.model_dump() for linea in payload.lineas], payload.proveedor
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e

    nombre = archivo_portal.nombre_archivo(payload.proveedor, payload.sucursal_id)
    return StreamingResponse(
        iter([contenido]),
        media_type="text/csv",
        headers={
            "Content-Disposition": f'attachment; filename="{nombre}"',
            "X-Lineas-Descartadas": str(len(descartadas)),
            "Access-Control-Expose-Headers": "X-Lineas-Descartadas, Content-Disposition",
        },
    )


@router.post("/sku-proveedor", dependencies=[Depends(requiere_admin)])
def cargar_sku_proveedor(payload: SkuProveedorCarga, db: Session = Depends(get_db)):
    """Reemplaza la equivalencia codigo -> SKU de un proveedor. La publica el motor."""
    proveedor = (payload.proveedor or "").strip().upper()
    if not proveedor:
        raise HTTPException(status_code=400, detail="Falta el proveedor.")
    tenant = settings.default_tenant_id
    filas = [
        {"tenant_id": tenant, "proveedor": proveedor, "clave": f.clave, "sku": f.sku}
        for f in payload.filas
        if f.clave and f.sku
    ]
    db.execute(
        delete(SkuProveedor).where(
            SkuProveedor.tenant_id == tenant, SkuProveedor.proveedor == proveedor
        )
    )
    for i in range(0, len(filas), 1000):
        lote = filas[i : i + 1000]
        if lote:
            db.execute(insert(SkuProveedor).values(lote))
    auditoria_service.registrar(
        db,
        accion="sku_proveedor_publicado",
        entidad="sku_proveedor",
        detalle=f"{proveedor}: {len(filas)} equivalencias",
    )
    db.commit()
    return {"proveedor": proveedor, "filas_cargadas": len(filas)}
